import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from sqlalchemy.orm import Session

from app.auth.dependencies import (
    clear_auth_cookies,
    get_current_user,
    require_admin_access,
    require_csrf_protection,
    validate_csrf_request,
)
from app.auth.security import decode_jwt_token
from app.auth.service import (
    assign_menus_to_role,
    assert_login_allowed,
    assign_roles_to_user,
    authenticate_user,
    change_password,
    create_role,
    create_user,
    delete_role,
    delete_user,
    get_session_by_id,
    get_role_menus,
    list_user_navigation,
    list_roles,
    list_users,
    refresh_user_token,
    register_login_failure,
    register_user,
    revoke_refresh_token,
    update_role,
    update_user,
)
from app.core.config import settings
from app.core.http import ResponseModel, build_response
from app.db import get_db_session
from app.schemas.auth import (
    AdminCreateUserRequest,
    ChangePasswordRequest,
    LoginRequest,
    ProfileUpdateRequest,
    RefreshTokenRequest,
    RegisterRequest,
    RoleCreateRequest,
    RoleMenuAssignmentRequest,
    RoleUpdateRequest,
    UserRoleAssignmentRequest,
    UserUpdateRequest,
)
from app.services import captcha_service

router = APIRouter()


def _cookie_kwargs(*, max_age: int | None, httponly: bool) -> dict[str, object]:
    return {
        "httponly": httponly,
        "secure": settings.auth_cookie_secure,
        "samesite": settings.auth_cookie_samesite,
        "domain": settings.auth_cookie_domain,
        "path": settings.auth_cookie_path,
        "max_age": max_age,
    }


def _set_auth_cookies(response: Response, result: dict) -> None:
    access_max_age = result["access_token_expires_in"] if result["remember"] else None
    refresh_max_age = result["refresh_token_expires_in"] if result["remember"] else None

    response.set_cookie(
        settings.auth_cookie_access_name,
        result["access_token"],
        **_cookie_kwargs(max_age=access_max_age, httponly=True),
    )
    response.set_cookie(
        settings.auth_cookie_refresh_name,
        result["refresh_token"],
        **_cookie_kwargs(max_age=refresh_max_age, httponly=True),
    )
    response.set_cookie(
        settings.auth_cookie_csrf_name,
        result["csrf_token"],
        **_cookie_kwargs(max_age=refresh_max_age, httponly=False),
    )

def _build_auth_payload(result: dict) -> dict:
    return {
        "token_type": result["token_type"],
        "csrf_token": result["csrf_token"],
        "access_token_expires_in": result["access_token_expires_in"],
        "refresh_token_expires_in": result["refresh_token_expires_in"],
        "user": result["user"],
    }


def _client_ip(request: Request) -> str | None:
    forwarded_for = request.headers.get("x-forwarded-for", "").strip()
    if forwarded_for:
        return forwarded_for.split(",")[0].strip() or None
    if request.client is not None:
        return request.client.host
    return None


def _user_agent(request: Request) -> str | None:
    user_agent = request.headers.get("user-agent", "").strip()
    return user_agent or None


def _resolve_refresh_token(
    request: Request,
    payload: RefreshTokenRequest | None,
) -> tuple[str | None, str | None]:
    if payload is not None and payload.refresh_token:
        return payload.refresh_token, "body"

    refresh_cookie = request.cookies.get(settings.auth_cookie_refresh_name)
    if refresh_cookie:
        return refresh_cookie, "cookie"

    return None, None


def _resolve_access_cookie_token(request: Request) -> str | None:
    return request.cookies.get(settings.auth_cookie_access_name)


def _validate_cookie_token_csrf(
    request: Request,
    *,
    token: str,
    expected_type: str,
    session: Session,
) -> None:
    try:
        claims = decode_jwt_token(
            token,
            secret=settings.auth_jwt_secret,
            issuer=settings.auth_jwt_issuer,
            expected_type=expected_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    session_id = str(claims.get("sid") or "").strip()
    if not session_id:
        raise HTTPException(status_code=401, detail="令牌缺少会话标识。")

    auth_session = get_session_by_id(session, session_id)
    if auth_session is None or auth_session["revoked_at"] is not None:
        raise HTTPException(status_code=401, detail="当前会话已失效。")

    validate_csrf_request(
        request,
        expected_token=auth_session["csrf_token"],
        enforce_cookie_presence=True,
    )


@router.post(
    "/register",
    response_model=ResponseModel,
    summary="用户注册 / Register a new user",
)
def register(
    request: Request,
    response: Response,
    payload: RegisterRequest,
    session: Annotated[Session, Depends(get_db_session)],
) -> ResponseModel:
    if not settings.auth_allow_public_register:
        raise HTTPException(status_code=403, detail="当前环境已关闭公开注册。")

    result = register_user(
        session,
        username=payload.username,
        email=payload.email,
        password=payload.password,
        display_name=payload.display_name,
        remember=payload.remember,
        client_ip=_client_ip(request),
        user_agent=_user_agent(request),
    )
    _set_auth_cookies(response, result)
    return build_response(request, data=_build_auth_payload(result))


@router.post(
    "/login",
    response_model=ResponseModel,
    summary="用户登录 / Login with username or email",
)
def login(
    request: Request,
    response: Response,
    payload: LoginRequest,
    session: Annotated[Session, Depends(get_db_session)],
) -> ResponseModel:
    client_ip = _client_ip(request)
    assert_login_allowed(session, login=payload.login, client_ip=client_ip)

    if settings.auth_require_captcha_for_login:
        verified = captcha_service.verify_captcha(payload.captcha_id, payload.captcha_code)
        if not verified:
            register_login_failure(session, login=payload.login, client_ip=client_ip)
            raise HTTPException(status_code=400, detail="验证码错误或已过期。")

    result = authenticate_user(
        session,
        login=payload.login,
        password=payload.password,
        remember=payload.remember,
        client_ip=client_ip,
        user_agent=_user_agent(request),
    )
    _set_auth_cookies(response, result)
    return build_response(request, data=_build_auth_payload(result))


@router.post(
    "/refresh",
    response_model=ResponseModel,
    summary="刷新令牌 / Refresh JWT token pair",
)
def refresh_token(
    request: Request,
    response: Response,
    session: Annotated[Session, Depends(get_db_session)],
    payload: RefreshTokenRequest | None = None,
) -> ResponseModel:
    refresh_token_value, source = _resolve_refresh_token(request, payload)
    if not refresh_token_value:
        raise HTTPException(status_code=401, detail="缺少刷新令牌。")
    if source == "cookie":
        _validate_cookie_token_csrf(
            request,
            token=refresh_token_value,
            expected_type="refresh",
            session=session,
        )

    result = refresh_user_token(
        session,
        refresh_token=refresh_token_value,
    )
    _set_auth_cookies(response, result)
    return build_response(request, data=_build_auth_payload(result))


@router.post(
    "/logout",
    response_model=ResponseModel,
    summary="退出登录 / Revoke current session",
)
def logout(
    request: Request,
    response: Response,
    session: Annotated[Session, Depends(get_db_session)],
    payload: RefreshTokenRequest | None = None,
) -> ResponseModel:
    refresh_token_value, source = _resolve_refresh_token(request, payload)
    access_cookie_token = _resolve_access_cookie_token(request)

    if source == "cookie" and refresh_token_value:
        _validate_cookie_token_csrf(
            request,
            token=refresh_token_value,
            expected_type="refresh",
            session=session,
        )
    elif access_cookie_token:
        _validate_cookie_token_csrf(
            request,
            token=access_cookie_token,
            expected_type="access",
            session=session,
        )

    try:
        result = revoke_refresh_token(
            session,
            refresh_token=refresh_token_value,
            access_token=access_cookie_token if refresh_token_value is None else None,
        )
    except HTTPException as exc:
        if exc.status_code not in {400, 401}:
            raise
        result = {"revoked": True}
    clear_auth_cookies(response)
    return build_response(request, data=result)


@router.get(
    "/me",
    response_model=ResponseModel,
    summary="当前用户信息 / Get current user profile",
)
def me(
    request: Request,
    response: Response,
    current_user: Annotated[dict, Depends(get_current_user)],
) -> ResponseModel:
    auth_session = getattr(request.state, "auth_session", None)
    if auth_session is not None:
        csrf_max_age = (
            settings.auth_refresh_token_expire_days * 24 * 60 * 60
            if auth_session.get("remember")
            else None
        )
        response.set_cookie(
            settings.auth_cookie_csrf_name,
            auth_session["csrf_token"],
            **_cookie_kwargs(max_age=csrf_max_age, httponly=False),
        )
    return build_response(request, data=current_user)


@router.get(
    "/me/navigation",
    response_model=ResponseModel,
    summary="当前用户导航菜单 / Get current user navigation tree",
)
def me_navigation(
    request: Request,
    current_user: Annotated[dict, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db_session)],
) -> ResponseModel:
    data = list_user_navigation(
        session,
        user_id=current_user["id"],
        is_superuser=bool(current_user.get("is_superuser")),
    )
    return build_response(request, data=data)


ALLOWED_AVATAR_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_AVATAR_SIZE = 5 * 1024 * 1024  # 5 MB
UPLOADS_DIR = Path("uploads/avatars")


@router.post(
    "/me/avatar",
    response_model=ResponseModel,
    summary="上传当前用户头像 / Upload avatar for current user",
)
async def upload_avatar(
    request: Request,
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
    _: Annotated[None, Depends(require_csrf_protection)] = None,
    session: Session = Depends(get_db_session),
) -> ResponseModel:
    content_type = file.content_type or "application/octet-stream"
    if content_type not in ALLOWED_AVATAR_TYPES:
        raise HTTPException(status_code=400, detail="仅支持 JPG、PNG、WEBP、GIF 格式的图片。")

    data = await file.read()
    if len(data) > MAX_AVATAR_SIZE:
        raise HTTPException(status_code=400, detail="头像文件大小不能超过 5MB。")

    ext = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
    }.get(content_type, ".jpg")

    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{current_user['id']}_{uuid.uuid4().hex[:8]}{ext}"
    file_path = UPLOADS_DIR / filename
    file_path.write_bytes(data)

    avatar_url = f"/uploads/avatars/{filename}"

    update_user(
        session,
        current_user["id"],
        avatar_url=avatar_url,
    )

    return build_response(request, data={"avatar_url": avatar_url})


@router.patch(
    "/me",
    response_model=ResponseModel,
    summary="更新当前用户资料 / Update current user profile",
)
def update_profile(
    request: Request,
    payload: ProfileUpdateRequest,
    current_user: Annotated[dict, Depends(get_current_user)],
    _: Annotated[None, Depends(require_csrf_protection)],
    session: Annotated[Session, Depends(get_db_session)],
) -> ResponseModel:
    update_user(
        session,
        current_user["id"],
        email=payload.email,
        display_name=payload.display_name,
    )
    from app.auth.service import build_user_profile
    profile = build_user_profile(session, current_user["id"])
    return build_response(request, data=profile)


@router.post(
    "/change-password",
    response_model=ResponseModel,
    summary="修改密码 / Change current user password",
)
def update_password(
    request: Request,
    response: Response,
    payload: ChangePasswordRequest,
    current_user: Annotated[dict, Depends(get_current_user)],
    _: Annotated[None, Depends(require_csrf_protection)],
    session: Annotated[Session, Depends(get_db_session)],
) -> ResponseModel:
    result = change_password(
        session,
        user_id=current_user["id"],
        current_password=payload.current_password,
        new_password=payload.new_password,
    )
    clear_auth_cookies(response)
    return build_response(request, data=result)


@router.get(
    "/users",
    response_model=ResponseModel,
    summary="用户列表 / List users",
)
def users(
    request: Request,
    session: Annotated[Session, Depends(get_db_session)],
    _: Annotated[dict, Depends(require_admin_access)],
) -> ResponseModel:
    return build_response(request, data=list_users(session))


@router.post(
    "/users",
    response_model=ResponseModel,
    summary="创建用户 / Create user by admin",
)
def admin_create_user(
    request: Request,
    payload: AdminCreateUserRequest,
    session: Annotated[Session, Depends(get_db_session)],
    _: Annotated[dict, Depends(require_admin_access)],
    __: Annotated[None, Depends(require_csrf_protection)],
) -> ResponseModel:
    result = create_user(
        session,
        username=payload.username,
        email=payload.email,
        password=payload.password,
        display_name=payload.display_name,
        role_codes=payload.role_codes,
        is_active=payload.is_active,
        is_superuser=payload.is_superuser,
    )
    return build_response(request, data=result)


@router.patch(
    "/users/{user_id}",
    response_model=ResponseModel,
    summary="更新用户 / Update user",
)
def admin_update_user(
    request: Request,
    user_id: str,
    payload: UserUpdateRequest,
    session: Annotated[Session, Depends(get_db_session)],
    _: Annotated[dict, Depends(require_admin_access)],
    __: Annotated[None, Depends(require_csrf_protection)],
) -> ResponseModel:
    result = update_user(
        session,
        user_id,
        email=payload.email,
        display_name=payload.display_name,
        is_active=payload.is_active,
        is_superuser=payload.is_superuser,
    )
    return build_response(request, data=result)


@router.delete(
    "/users/{user_id}",
    response_model=ResponseModel,
    summary="删除用户 / Delete user",
)
def admin_delete_user(
    request: Request,
    user_id: str,
    current_user: Annotated[dict, Depends(require_admin_access)],
    session: Annotated[Session, Depends(get_db_session)],
    __: Annotated[None, Depends(require_csrf_protection)],
) -> ResponseModel:
    result = delete_user(
        session,
        user_id,
        actor_user_id=current_user["id"],
    )
    return build_response(request, data=result)


@router.post(
    "/users/{user_id}/roles",
    response_model=ResponseModel,
    summary="分配用户角色 / Assign roles to user",
)
def user_roles(
    request: Request,
    user_id: str,
    payload: UserRoleAssignmentRequest,
    session: Annotated[Session, Depends(get_db_session)],
    _: Annotated[dict, Depends(require_admin_access)],
    __: Annotated[None, Depends(require_csrf_protection)],
) -> ResponseModel:
    result = assign_roles_to_user(session, user_id, payload.role_codes)
    return build_response(request, data=result)


@router.get(
    "/roles",
    response_model=ResponseModel,
    summary="角色列表 / List roles",
)
def roles(
    request: Request,
    session: Annotated[Session, Depends(get_db_session)],
    _: Annotated[dict, Depends(require_admin_access)],
) -> ResponseModel:
    return build_response(request, data=list_roles(session))


@router.post(
    "/roles",
    response_model=ResponseModel,
    summary="创建角色 / Create role",
)
def create_role_endpoint(
    request: Request,
    payload: RoleCreateRequest,
    session: Annotated[Session, Depends(get_db_session)],
    _: Annotated[dict, Depends(require_admin_access)],
    __: Annotated[None, Depends(require_csrf_protection)],
) -> ResponseModel:
    result = create_role(
        session,
        code=payload.code,
        name=payload.name,
        description=payload.description,
    )
    return build_response(request, data=result)


@router.patch(
    "/roles/{role_id}",
    response_model=ResponseModel,
    summary="更新角色 / Update role",
)
def update_role_endpoint(
    request: Request,
    role_id: str,
    payload: RoleUpdateRequest,
    session: Annotated[Session, Depends(get_db_session)],
    _: Annotated[dict, Depends(require_admin_access)],
    __: Annotated[None, Depends(require_csrf_protection)],
) -> ResponseModel:
    result = update_role(
        session,
        role_id,
        name=payload.name,
        description=payload.description,
    )
    return build_response(request, data=result)


@router.delete(
    "/roles/{role_id}",
    response_model=ResponseModel,
    summary="删除角色 / Delete role",
)
def delete_role_endpoint(
    request: Request,
    role_id: str,
    session: Annotated[Session, Depends(get_db_session)],
    _: Annotated[dict, Depends(require_admin_access)],
    __: Annotated[None, Depends(require_csrf_protection)],
) -> ResponseModel:
    result = delete_role(session, role_id)
    return build_response(request, data=result)


@router.get(
    "/roles/{role_id}/menus",
    response_model=ResponseModel,
    summary="角色菜单列表 / Get role menus",
)
def role_menus(
    request: Request,
    role_id: str,
    session: Annotated[Session, Depends(get_db_session)],
    _: Annotated[dict, Depends(require_admin_access)],
) -> ResponseModel:
    return build_response(request, data=get_role_menus(session, role_id))


@router.put(
    "/roles/{role_id}/menus",
    response_model=ResponseModel,
    summary="分配角色菜单 / Assign menus to role",
)
def assign_role_menus(
    request: Request,
    role_id: str,
    payload: RoleMenuAssignmentRequest,
    session: Annotated[Session, Depends(get_db_session)],
    _: Annotated[dict, Depends(require_admin_access)],
    __: Annotated[None, Depends(require_csrf_protection)],
) -> ResponseModel:
    result = assign_menus_to_role(
        session,
        role_id,
        payload.menu_ids,
    )
    return build_response(request, data=result)
