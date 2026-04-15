from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional, Union

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.core.config import settings, validate_runtime_settings
from app.core.http import register_exception_handlers
from app.core.logging import configure_logging
from app.db import initialize_database
from app.middleware import AuthCookieCleanupMiddleware

logger = configure_logging("fast_video_whisper")
RESERVED_FRONTEND_PATHS = ("api", "docs", "redoc", "openapi.json", "uploads")


async def _workflow_executor(*, project_id: int) -> None:
    """Task queue executor for workflow tasks."""
    from app.workflows.engine import WorkflowEngine
    engine = WorkflowEngine()
    await engine.run(project_id=project_id)


async def _motion_extraction_executor(
    *,
    job_id: str,
    project_id: int,
    owner_user_id: str | None = None,
    extraction_hint: str | None = None,
) -> None:
    from app.services.motion_service import MotionService

    service = MotionService()
    await service.run_job(
        job_id=job_id,
        project_id=project_id,
        owner_user_id=owner_user_id,
        extraction_hint=extraction_hint,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_runtime_settings()
    initialize_database()
    # Ensure uploads directory exists
    uploads_dir = Path("uploads")
    uploads_dir.mkdir(parents=True, exist_ok=True)

    # Import workflows to trigger registration, then start task queue worker
    import app.workflows  # noqa: F401
    from app.workflows.task_queue import TaskQueue

    TaskQueue.register_executor("workflow", _workflow_executor)
    TaskQueue.register_executor("motion_extraction", _motion_extraction_executor)
    queue = TaskQueue.instance()
    await queue.start_worker()

    logger.info(
        "Starting %s in %s mode",
        settings.app_name,
        settings.environment,
    )
    yield
    await queue.stop_worker()
    
    from app.utils.process_pool import shutdown_process_pool

    shutdown_process_pool(wait=True)
    
    logger.info("Stopping %s", settings.app_name)


def _resolve_frontend_static_dir(
    frontend_static_dir: Optional[Union[str, Path]] = None,
) -> Path:
    if frontend_static_dir is None:
        frontend_static_dir = settings.frontend_static_dir

    static_dir = Path(frontend_static_dir)
    if not static_dir.is_absolute():
        static_dir = Path.cwd() / static_dir
    return static_dir.resolve()


def _resolve_frontend_asset(static_dir: Path, relative_path: str) -> Optional[Path]:
    candidate = (static_dir / relative_path).resolve()
    try:
        candidate.relative_to(static_dir)
    except ValueError:
        return None

    if candidate.is_file():
        return candidate
    if candidate.is_dir():
        nested_index = candidate / "index.html"
        if nested_index.is_file():
            return nested_index
    return None


def _resolve_frontend_entrypoint(static_dir: Path) -> Optional[Path]:
    candidates = (
        static_dir / "index.html",
        static_dir / "200.html",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _register_frontend_routes(
    app: FastAPI,
    *,
    frontend_static_dir: Optional[Union[str, Path]] = None,
) -> None:
    static_dir = _resolve_frontend_static_dir(frontend_static_dir)
    entrypoint_path = _resolve_frontend_entrypoint(static_dir)

    if entrypoint_path is None:
        logger.info(
            "Frontend static build not found at %s. Skipping frontend routes.",
            static_dir,
        )
        return

    logger.info("Serving frontend static files from %s", static_dir)

    @app.get("/", include_in_schema=False)
    async def frontend_index() -> FileResponse:
        return FileResponse(entrypoint_path)

    @app.get("/{full_path:path}", include_in_schema=False)
    async def frontend_entry(full_path: str) -> FileResponse:
        normalized_path = full_path.lstrip("/")
        if not normalized_path:
            return FileResponse(entrypoint_path)

        if (
            normalized_path in RESERVED_FRONTEND_PATHS
            or normalized_path.startswith("api/")
            or normalized_path.startswith("docs/")
        ):
            raise HTTPException(status_code=404, detail="Not Found")

        asset_path = _resolve_frontend_asset(static_dir, normalized_path)
        if asset_path is not None:
            return FileResponse(asset_path)

        if Path(normalized_path).suffix:
            raise HTTPException(status_code=404, detail="Not Found")

        return FileResponse(entrypoint_path)


def create_app(
    *,
    serve_frontend_static: Optional[bool] = None,
    frontend_static_dir: Optional[Union[str, Path]] = None,
) -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(AuthCookieCleanupMiddleware)
    register_exception_handlers(app)
    app.include_router(api_router, prefix="/api")
    app.include_router(api_router, include_in_schema=False)

    # Serve uploaded files (avatars, etc.) at /uploads/...
    uploads_dir = Path("uploads")
    uploads_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/uploads", StaticFiles(directory=str(uploads_dir)), name="uploads")

    should_serve_frontend = (
        settings.serve_frontend_static
        if serve_frontend_static is None
        else serve_frontend_static
    )
    if should_serve_frontend:
        _register_frontend_routes(
            app,
            frontend_static_dir=frontend_static_dir,
        )
    return app


def run() -> None:
    import uvicorn

    uvicorn.run(
        "app.core.application:app",
        host=settings.host,
        port=settings.port,
        reload=settings.reload,
    )


app = create_app()


__all__ = ["app", "create_app", "run"]
