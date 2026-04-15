"""
Auth cookie cleanup middleware.

Clears stale auth cookies from the browser when the server returns 401
on specific sensitive endpoints (token refresh, logout, /me).
"""
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.auth.dependencies import clear_auth_cookies
from app.core.config import settings

# Map endpoint paths → which cookies to clear on 401
_CLEANUP_RULES: dict[str, dict[str, bool]] = {
    "/api/auth/me": {
        "clear_access": True,
        "clear_refresh": False,
        "clear_csrf": False,
    },
    "/auth/me": {
        "clear_access": True,
        "clear_refresh": False,
        "clear_csrf": False,
    },
    "/api/auth/refresh": {
        "clear_access": True,
        "clear_refresh": True,
        "clear_csrf": True,
    },
    "/auth/refresh": {
        "clear_access": True,
        "clear_refresh": True,
        "clear_csrf": True,
    },
    "/api/auth/logout": {
        "clear_access": True,
        "clear_refresh": True,
        "clear_csrf": True,
    },
    "/auth/logout": {
        "clear_access": True,
        "clear_refresh": True,
        "clear_csrf": True,
    },
}

_AUTH_COOKIE_NAMES = (
    settings.auth_cookie_access_name,
    settings.auth_cookie_refresh_name,
    settings.auth_cookie_csrf_name,
)


class AuthCookieCleanupMiddleware(BaseHTTPMiddleware):
    """Remove stale auth cookies on 401 responses from auth endpoints."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        cleanup_rule = _CLEANUP_RULES.get(request.url.path)
        if cleanup_rule is None or response.status_code != 401:
            return response

        if not any(name in request.cookies for name in _AUTH_COOKIE_NAMES):
            return response

        clear_auth_cookies(response, **cleanup_rule)
        return response
