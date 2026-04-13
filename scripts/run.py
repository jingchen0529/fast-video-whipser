from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIR = PROJECT_ROOT / "frontend"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import settings

FRONTEND_DEFAULT_MAX_OLD_SPACE_SIZE_MB = 4096


def _resolve_project_path(path_value: str) -> Path:
    path = Path(path_value)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def _backend_bind_host() -> str:
    return settings.host


def _backend_proxy_host() -> str:
    return "127.0.0.1" if settings.host in {"0.0.0.0", "::"} else settings.host


def _backend_base_url() -> str:
    return f"http://{_backend_proxy_host()}:{settings.port}"


def _ensure_tool(name: str) -> None:
    if shutil.which(name) is None:
        raise SystemExit(f"Required tool not found in PATH: {name}")


def _run_checked(
    command: Sequence[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
) -> None:
    subprocess.run(command, cwd=cwd, env=env, check=True)


def _spawn(
    command: Sequence[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
) -> subprocess.Popen[bytes]:
    return subprocess.Popen(command, cwd=cwd, env=env)


def _build_frontend_env() -> dict[str, str]:
    env = os.environ.copy()
    env["NUXT_API_BASE"] = _backend_base_url()
    max_old_space_size = (
        env.get("FRONTEND_NODE_MAX_OLD_SPACE_SIZE")
        or env.get("NUXT_NODE_MAX_OLD_SPACE_SIZE")
        or str(FRONTEND_DEFAULT_MAX_OLD_SPACE_SIZE_MB)
    ).strip()
    existing_node_options = env.get("NODE_OPTIONS", "").strip()
    max_old_space_option = f"--max-old-space-size={max_old_space_size}"

    if max_old_space_option not in existing_node_options.split():
        env["NODE_OPTIONS"] = (
            f"{existing_node_options} {max_old_space_option}".strip()
            if existing_node_options
            else max_old_space_option
        )
    return env


def _backend_command(*, reload_enabled: bool) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "uvicorn",
        "app.core.application:app",
        "--host",
        _backend_bind_host(),
        "--port",
        str(settings.port),
    ]
    if reload_enabled:
        command.append("--reload")
    return command


def _frontend_dev_command(*, port: int) -> list[str]:
    return [
        "pnpm",
        "exec",
        "nuxt",
        "dev",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
    ]


def _frontend_generate_command() -> list[str]:
    return ["pnpm", "exec", "nuxt", "generate"]


def _resolve_frontend_entrypoint(frontend_output_dir: Path) -> Path:
    candidates = (
        frontend_output_dir / "index.html",
        frontend_output_dir / "200.html",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise SystemExit(
        "Nuxt generate completed, but neither index.html nor 200.html was created."
    )


def _terminate_processes(processes: Sequence[subprocess.Popen[bytes]]) -> None:
    for process in processes:
        if process.poll() is None:
            process.terminate()

    deadline = time.time() + 5
    for process in processes:
        if process.poll() is not None:
            continue
        timeout = max(0.0, deadline - time.time())
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()


def _build_static_frontend() -> Path:
    _ensure_tool("pnpm")
    static_dir = _resolve_project_path(settings.frontend_static_dir)
    frontend_output_dir = FRONTEND_DIR / ".output" / "public"

    _run_checked(
        _frontend_generate_command(),
        cwd=FRONTEND_DIR,
        env=_build_frontend_env(),
    )

    _resolve_frontend_entrypoint(frontend_output_dir)

    static_dir.parent.mkdir(parents=True, exist_ok=True)
    if static_dir.exists():
        shutil.rmtree(static_dir)
    shutil.copytree(frontend_output_dir, static_dir)
    return static_dir


def command_backend(args: argparse.Namespace) -> None:
    _run_checked(
        _backend_command(reload_enabled=not args.no_reload),
        cwd=PROJECT_ROOT,
        env=os.environ.copy(),
    )


def command_frontend(args: argparse.Namespace) -> None:
    _ensure_tool("pnpm")
    _run_checked(
        _frontend_dev_command(port=args.port),
        cwd=FRONTEND_DIR,
        env=_build_frontend_env(),
    )


def command_dev(_: argparse.Namespace) -> None:
    _ensure_tool("pnpm")
    processes = [
        _spawn(
            _backend_command(reload_enabled=True),
            cwd=PROJECT_ROOT,
            env=os.environ.copy(),
        ),
        _spawn(
            _frontend_dev_command(port=settings.frontend_dev_port),
            cwd=FRONTEND_DIR,
            env=_build_frontend_env(),
        ),
    ]

    try:
        while True:
            for process in processes:
                return_code = process.poll()
                if return_code is not None:
                    raise SystemExit(return_code)
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        _terminate_processes(processes)


def command_build_frontend(_: argparse.Namespace) -> None:
    static_dir = _build_static_frontend()
    print(f"Frontend static build copied to {static_dir}")


def command_combined(args: argparse.Namespace) -> None:
    if args.build:
        static_dir = _build_static_frontend()
        print(f"Frontend static build copied to {static_dir}")

    env = os.environ.copy()
    env["SERVE_FRONTEND_STATIC"] = "true"
    _run_checked(
        _backend_command(reload_enabled=not args.no_reload),
        cwd=PROJECT_ROOT,
        env=env,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run backend, frontend, or combined project workflows.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    backend_parser = subparsers.add_parser("backend", help="Run the FastAPI backend.")
    backend_parser.add_argument(
        "--no-reload",
        action="store_true",
        help="Disable uvicorn reload mode.",
    )
    backend_parser.set_defaults(func=command_backend)

    frontend_parser = subparsers.add_parser("frontend", help="Run the Nuxt frontend.")
    frontend_parser.add_argument(
        "--port",
        type=int,
        default=settings.frontend_dev_port,
        help="Port for the Nuxt dev server.",
    )
    frontend_parser.set_defaults(func=command_frontend)

    dev_parser = subparsers.add_parser(
        "dev",
        help="Run backend and frontend dev servers together.",
    )
    dev_parser.set_defaults(func=command_dev)

    build_parser = subparsers.add_parser(
        "build-frontend",
        help="Generate the frontend and copy the static output into the backend static directory.",
    )
    build_parser.set_defaults(func=command_build_frontend)

    combined_parser = subparsers.add_parser(
        "combined",
        help="Run the backend and serve a generated frontend from the static directory.",
    )
    combined_parser.add_argument(
        "--build",
        action="store_true",
        help="Build the frontend into the static directory before starting the backend.",
    )
    combined_parser.add_argument(
        "--no-reload",
        action="store_true",
        help="Disable uvicorn reload mode.",
    )
    combined_parser.set_defaults(func=command_combined)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
