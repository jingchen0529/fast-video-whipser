from typing import Any, Dict

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.http.exceptions import APIError
from app.core.http.schemas import ErrorResponseModel
from app.core.logging import configure_logging

logger = configure_logging(__name__)


def _build_error_payload(
    request: Request,
    *,
    status_code: int,
    message: str,
    details: Any = None,
) -> Dict[str, Any]:
    return ErrorResponseModel(
        code=status_code,
        message=message,
        router=request.url.path,
        params=dict(request.query_params),
        details=details,
    ).model_dump()


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(APIError)
    async def handle_api_error(request: Request, exc: APIError) -> JSONResponse:
        status_code = exc.status_code or 502
        logger.warning("APIError on %s: %s", request.url.path, str(exc))
        return JSONResponse(
            status_code=status_code,
            content=_build_error_payload(
                request,
                status_code=status_code,
                message=exc.message,
            ),
        )

    @app.exception_handler(ValueError)
    async def handle_value_error(request: Request, exc: ValueError) -> JSONResponse:
        logger.warning("ValueError on %s: %s", request.url.path, str(exc))
        return JSONResponse(
            status_code=400,
            content=_build_error_payload(
                request,
                status_code=400,
                message=str(exc),
            ),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        logger.warning("Request validation failed on %s", request.url.path)
        return JSONResponse(
            status_code=422,
            content=_build_error_payload(
                request,
                status_code=422,
                message="Request validation failed.",
                details=exc.errors(),
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(
        request: Request,
        exc: StarletteHTTPException,
    ) -> JSONResponse:
        message = str(exc.detail)
        logger.warning("HTTPException on %s: %s", request.url.path, message)
        return JSONResponse(
            status_code=exc.status_code,
            content=_build_error_payload(
                request,
                status_code=exc.status_code,
                message=message,
            ),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception on %s", request.url.path)
        return JSONResponse(
            status_code=500,
            content=_build_error_payload(
                request,
                status_code=500,
                message="Internal server error.",
            ),
        )
