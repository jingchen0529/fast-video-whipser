import sqlite3
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel, Field, StringConstraints

from app.auth.dependencies import get_current_user, require_csrf_protection, require_permissions, validate_csrf_request
from app.auth.security import decode_jwt_token
from app.auth.service import (
    assert_login_allowed,
    assign_permissions_to_role,
    assign_roles_to_user,
    authenticate_user,
    change_password,
    create_permission,
    create_role,
    create_user,
    delete_role,
    delete_user,
    get_session_by_id,
    list_permissions,
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
from app.db import get_db
from app.services import captcha_service

router = APIRouter()

NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
OptionalString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class RegisterRequest(BaseModel):
    username: NonEmptyString = Field(..., description="登录用户名。")
    email: NonEmptyString = Field(..., description="用户邮箱。")
    password: NonEmptyString = Field(..., description="登录密码。")
    display_name: str | None = Field(None, description="显示名称。")
    remember: bool = Field(False, description="是否持久化登录。")


class LoginRequest(BaseModel):
    login: NonEmptyString = Field(..., description="用户名或邮箱。")
    password: NonEmptyString = Field(..., description="登录密码。")
    captcha_id: NonEmptyString = Field(..., description="验证码 ID。")
    captcha_code: NonEmptyString = Field(..., description="验证码内容。")
    remember: bool = Field(False, description="是否持久化登录。")


class RefreshTokenRequest(BaseModel):
    refresh_token: NonEmptyString = Field(..., description="刷新令牌。")


class ChangePasswordRequest(BaseModel):
    current_password: NonEmptyString = Field(..., description="当前密码。")
    new_password: NonEmptyString = Field(..., description="新密码。")


class PermissionCreateRequest(BaseModel):
    code: NonEmptyString = Field(..., description="权限编码。")
    name: NonEmptyString = Field(..., description="权限名称。")
    group_name: NonEmptyString = Field(..., description="权限分组。")
    description: str | None = Field(None, description="权限备注。")


class RoleCreateRequest(BaseModel):
    code: NonEmptyString = Field(..., description="角色编码。")
    name: NonEmptyString = Field(..., description="角色名称。")
    description: str | None = Field(None, description="角色备注。")
    permission_codes: list[str] = Field(default_factory=list, description="角色权限编码列表。")


class RoleUpdateRequest(BaseModel):
    name: OptionalString | None = Field(None, description="角色名称。")
    description: str | None = Field(None, description="角色备注。")


class RolePermissionAssignmentRequest(BaseModel):
    permission_codes: list[str] = Field(default_factory=list, description="权限编码列表。")


class AdminCreateUserRequest(BaseModel):
    username: NonEmptyString = Field(..., description="用户名。")
    email: NonEmptyString = Field(..., description="邮箱。")
    password: NonEmptyString = Field(..., description="密码。")
    display_name: str | None = Field(None, description="显示名称。")
    role_codes: list[str] = Field(default_factory=lambda: ["user"], description="角色编码列表。")
    is_active: bool = Field(True, description="是否启用。")
    is_superuser: bool = Field(False, description="是否超级管理员。")


class UserUpdateRequest(BaseModel):
    email: OptionalString | None = Field(None, description="新邮箱。")
    display_name: OptionalString | None = Field(None, description="新显示名称。")
    is_active: bool | None = Field(None, description="是否启用。")
    is_superuser: bool | None = Field(None, description="是否超级管理员。")


class UserRoleAssignmentRequest(BaseModel):
    role_codes: list[str] = Field(default_factory=list, description="角色编码列表。")


class ProfileUpdateRequest(BaseModel):
    display_name: OptionalString | None = Field(None, description="新显示名称。")
    email: OptionalString | None = Field(None, description="新邮箱。")


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


def _clear_auth_cookies(response: Response) -> None:
    for cookie_name in (
        settings.auth_cookie_access_name,
        settings.auth_cookie_refresh_name,
        settings.auth_cookie_csrf_name,
    ):
        response.delete_cookie(
            cookie_name,
            domain=settings.auth_cookie_domain,
            path=settings.auth_cookie_path,
            secure=settings.auth_cookie_secure,
            samesite=settings.auth_cookie_samesite,
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
    connection: sqlite3.Connection,
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

    session = get_session_by_id(connection, session_id)
    if session is None or session["revoked_at"] is not None:
        raise HTTPException(status_code=401, detail="当前会话已失效。")

    validate_csrf_request(
        request,
        expected_token=session["csrf_token"],
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
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
) -> ResponseModel:
    if not settings.auth_allow_public_register:
        raise HTTPException(status_code=403, detail="当前环境已关闭公开注册。")

    result = register_user(
        connection,
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
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
) -> ResponseModel:
    client_ip = _client_ip(request)
    assert_login_allowed(connection, login=payload.login, client_ip=client_ip)

    if settings.auth_require_captcha_for_login:
        verified = captcha_service.verify_captcha(payload.captcha_id, payload.captcha_code)
        if not verified:
            register_login_failure(connection, login=payload.login, client_ip=client_ip)
            raise HTTPException(status_code=400, detail="验证码错误或已过期。")

    result = authenticate_user(
        connection,
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
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
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
            connection=connection,
        )

    result = refresh_user_token(
        connection,
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
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    payload: RefreshTokenRequest | None = None,
) -> ResponseModel:
    refresh_token_value, source = _resolve_refresh_token(request, payload)
    access_cookie_token = _resolve_access_cookie_token(request)

    if source == "cookie" and refresh_token_value:
        _validate_cookie_token_csrf(
            request,
            token=refresh_token_value,
            expected_type="refresh",
            connection=connection,
        )
    elif access_cookie_token:
        _validate_cookie_token_csrf(
            request,
            token=access_cookie_token,
            expected_type="access",
            connection=connection,
        )

    try:
        result = revoke_refresh_token(
            connection,
            refresh_token=refresh_token_value,
            access_token=access_cookie_token if refresh_token_value is None else None,
        )
    except HTTPException as exc:
        if exc.status_code not in {400, 401}:
            raise
        result = {"revoked": True}
    _clear_auth_cookies(response)
    return build_response(request, data=result)


@router.get(
    "/me",
    response_model=ResponseModel,
    summary="当前用户信息 / Get current user profile",
)
def me(
    request: Request,
    current_user: Annotated[dict, Depends(get_current_user)],
) -> ResponseModel:
    return build_response(request, data=current_user)


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
    connection: sqlite3.Connection = Depends(get_db),
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

    # Store relative URL path — works across dev/prod
    avatar_url = f"/uploads/avatars/{filename}"

    from app.auth.service import update_user
    update_user(
        connection,
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
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
) -> ResponseModel:
    from app.auth.service import update_user, build_user_profile
    update_user(
        connection,
        current_user["id"],
        email=payload.email,
        display_name=payload.display_name,
    )
    profile = build_user_profile(connection, current_user["id"])
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
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
) -> ResponseModel:
    result = change_password(
        connection,
        user_id=current_user["id"],
        current_password=payload.current_password,
        new_password=payload.new_password,
    )
    _clear_auth_cookies(response)
    return build_response(request, data=result)


@router.get(
    "/users",
    response_model=ResponseModel,
    summary="用户列表 / List users",
)
def users(
    request: Request,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    _: Annotated[dict, Depends(require_permissions("users.view"))],
) -> ResponseModel:
    return build_response(request, data=list_users(connection))


@router.post(
    "/users",
    response_model=ResponseModel,
    summary="创建用户 / Create user by admin",
)
def admin_create_user(
    request: Request,
    payload: AdminCreateUserRequest,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    _: Annotated[dict, Depends(require_permissions("users.create"))],
    __: Annotated[None, Depends(require_csrf_protection)],
) -> ResponseModel:
    result = create_user(
        connection,
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
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    _: Annotated[dict, Depends(require_permissions("users.update"))],
    __: Annotated[None, Depends(require_csrf_protection)],
) -> ResponseModel:
    result = update_user(
        connection,
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
    current_user: Annotated[dict, Depends(get_current_user)],
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    _: Annotated[dict, Depends(require_permissions("users.delete"))],
    __: Annotated[None, Depends(require_csrf_protection)],
) -> ResponseModel:
    result = delete_user(
        connection,
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
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    _: Annotated[dict, Depends(require_permissions("users.assign_roles"))],
    __: Annotated[None, Depends(require_csrf_protection)],
) -> ResponseModel:
    result = assign_roles_to_user(connection, user_id, payload.role_codes)
    return build_response(request, data=result)


@router.get(
    "/roles",
    response_model=ResponseModel,
    summary="角色列表 / List roles",
)
def roles(
    request: Request,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    _: Annotated[dict, Depends(require_permissions("roles.view"))],
) -> ResponseModel:
    return build_response(request, data=list_roles(connection))


@router.post(
    "/roles",
    response_model=ResponseModel,
    summary="创建角色 / Create role",
)
def create_role_endpoint(
    request: Request,
    payload: RoleCreateRequest,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    _: Annotated[dict, Depends(require_permissions("roles.create"))],
    __: Annotated[None, Depends(require_csrf_protection)],
) -> ResponseModel:
    result = create_role(
        connection,
        code=payload.code,
        name=payload.name,
        description=payload.description,
        permission_codes=payload.permission_codes,
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
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    _: Annotated[dict, Depends(require_permissions("roles.update"))],
    __: Annotated[None, Depends(require_csrf_protection)],
) -> ResponseModel:
    result = update_role(
        connection,
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
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    _: Annotated[dict, Depends(require_permissions("roles.delete"))],
    __: Annotated[None, Depends(require_csrf_protection)],
) -> ResponseModel:
    result = delete_role(connection, role_id)
    return build_response(request, data=result)


@router.put(
    "/roles/{role_id}/permissions",
    response_model=ResponseModel,
    summary="分配角色权限 / Assign permissions to role",
)
def role_permissions(
    request: Request,
    role_id: str,
    payload: RolePermissionAssignmentRequest,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    _: Annotated[dict, Depends(require_permissions("roles.assign_permissions"))],
    __: Annotated[None, Depends(require_csrf_protection)],
) -> ResponseModel:
    result = assign_permissions_to_role(
        connection,
        role_id,
        payload.permission_codes,
    )
    return build_response(request, data=result)


@router.get(
    "/permissions",
    response_model=ResponseModel,
    summary="权限列表 / List permissions",
)
def permissions(
    request: Request,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    _: Annotated[dict, Depends(require_permissions("permissions.view"))],
) -> ResponseModel:
    return build_response(request, data=list_permissions(connection))


@router.post(
    "/permissions",
    response_model=ResponseModel,
    summary="创建权限 / Create custom permission",
)
def create_permission_endpoint(
    request: Request,
    payload: PermissionCreateRequest,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    _: Annotated[dict, Depends(require_permissions("permissions.create"))],
    __: Annotated[None, Depends(require_csrf_protection)],
) -> ResponseModel:
    result = create_permission(
        connection,
        code=payload.code,
        name=payload.name,
        group_name=payload.group_name,
        description=payload.description,
    )
    return build_response(request, data=result)
