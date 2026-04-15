import hmac
from typing import Annotated

from fastapi import Depends, HTTPException, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.auth.security import decode_jwt_token
from app.auth.service import validate_token_session
from app.core.config import settings
from app.db import get_db_session

bearer_scheme = HTTPBearer(auto_error=False)
SAFE_HTTP_METHODS = {"GET", "HEAD", "OPTIONS"}
ADMIN_ROLE_CODES = {"super_admin", "admin"}


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


def clear_auth_cookies(
    response: Response,
    *,
    clear_access: bool = True,
    clear_refresh: bool = True,
    clear_csrf: bool = True,
) -> None:
    cookie_targets = []
    if clear_access:
        cookie_targets.append(settings.auth_cookie_access_name)
    if clear_refresh:
        cookie_targets.append(settings.auth_cookie_refresh_name)
    if clear_csrf:
        cookie_targets.append(settings.auth_cookie_csrf_name)

    for cookie_name in cookie_targets:
        response.delete_cookie(
            cookie_name,
            domain=settings.auth_cookie_domain,
            path=settings.auth_cookie_path,
            secure=settings.auth_cookie_secure,
            samesite=settings.auth_cookie_samesite,
        )


def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    session: Annotated[Session, Depends(get_db_session)],
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

    auth_session, user = validate_token_session(
        session,
        claims=claims,
        require_active_user=True,
    )
    request.state.auth_session = auth_session
    request.state.auth_token_source = token_source
    return user


def require_admin_access(
    current_user: Annotated[dict, Depends(get_current_user)],
) -> dict:
    if bool(current_user.get("is_superuser")):
        return current_user

    role_codes = {
        str(role.get("code") or "").strip().lower()
        for role in current_user.get("roles") or []
    }
    if role_codes & ADMIN_ROLE_CODES:
        return current_user

    raise HTTPException(status_code=403, detail="当前账号无法访问该资源。")


def require_csrf_protection(
    request: Request,
    _: Annotated[dict, Depends(get_current_user)],
) -> None:
    session = getattr(request.state, "auth_session", None)
    expected_token = session["csrf_token"] if session else None
    validate_csrf_request(request, expected_token=expected_token)
