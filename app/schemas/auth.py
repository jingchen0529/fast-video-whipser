"""Pydantic request/response schemas for auth-related endpoints."""
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

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


class RoleCreateRequest(BaseModel):
    code: NonEmptyString = Field(..., description="角色编码。")
    name: NonEmptyString = Field(..., description="角色名称。")
    description: str | None = Field(None, description="角色备注。")


class RoleUpdateRequest(BaseModel):
    name: OptionalString | None = Field(None, description="角色名称。")
    description: str | None = Field(None, description="角色备注。")


class RoleMenuAssignmentRequest(BaseModel):
    menu_ids: list[str] = Field(default_factory=list, description="菜单 ID 列表。")


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
