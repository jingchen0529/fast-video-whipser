import hmac
import sqlite3
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth.security import decode_jwt_token
from app.auth.service import validate_token_session
from app.core.config import settings
from app.db import get_db

bearer_scheme = HTTPBearer(auto_error=False)
SAFE_HTTP_METHODS = {"GET", "HEAD", "OPTIONS"}


def get_access_token_from_request(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None,
) -> tuple[str | None, str | None]:
    if credentials is not None and credentials.scheme.lower() == "bearer":
        return credentials.credentials, "header"

    access_cookie = request.cookies.get(settings.auth_cookie_access_name)
    if access_cookie:
        return access_cookie, "cookie"

    return None, None


def validate_csrf_request(
    request: Request,
    *,
    expected_token: str | None = None,
    enforce_cookie_presence: bool = False,
) -> None:
    if request.method.upper() in SAFE_HTTP_METHODS:
        return

    csrf_cookie = request.cookies.get(settings.auth_cookie_csrf_name)
    using_cookie_auth = (
        settings.auth_cookie_access_name in request.cookies
        or settings.auth_cookie_refresh_name in request.cookies
    )
    if not using_cookie_auth and not enforce_cookie_presence:
        return

    csrf_header = request.headers.get("x-csrf-token", "")
    if not csrf_cookie or not csrf_header:
        raise HTTPException(status_code=403, detail="缺少有效的 CSRF 令牌。")
    if not hmac.compare_digest(csrf_cookie, csrf_header):
        raise HTTPException(status_code=403, detail="CSRF 令牌校验失败。")
    if expected_token and not hmac.compare_digest(expected_token, csrf_header):
        raise HTTPException(status_code=403, detail="CSRF 会话令牌校验失败。")


def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict:
    token, token_source = get_access_token_from_request(request, credentials)
    if not token:
        raise HTTPException(status_code=401, detail="未提供有效的认证令牌。")

    try:
        claims = decode_jwt_token(
            token,
            secret=settings.auth_jwt_secret,
            issuer=settings.auth_jwt_issuer,
            expected_type="access",
        )
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    session, user = validate_token_session(
        connection,
        claims=claims,
        require_active_user=True,
    )
    request.state.auth_session = session
    request.state.auth_token_source = token_source
    return user


def require_csrf_protection(
    request: Request,
    _: Annotated[dict, Depends(get_current_user)],
) -> None:
    session = getattr(request.state, "auth_session", None)
    expected_token = session["csrf_token"] if session else None
    validate_csrf_request(request, expected_token=expected_token)


def require_permissions(*permission_codes: str):
    def dependency(
        current_user: Annotated[dict, Depends(get_current_user)],
    ) -> dict:
        if current_user["is_superuser"]:
            return current_user

        current_permission_codes = {
            permission["code"]
            for permission in current_user["permissions"]
        }
        missing_codes = [
            permission_code
            for permission_code in permission_codes
            if permission_code not in current_permission_codes
        ]
        if missing_codes:
            raise HTTPException(
                status_code=403,
                detail=f"缺少权限: {', '.join(missing_codes)}",
            )
        return current_user

    return dependency

