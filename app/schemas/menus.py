"""Pydantic request/response schemas for menu-related endpoints."""
from typing import Annotated, Any

from pydantic import BaseModel, Field, StringConstraints

NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
OptionalString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class MenuCreateRequest(BaseModel):
    code: NonEmptyString = Field(..., description="菜单编码。")
    title: NonEmptyString = Field(..., description="菜单名称。")
    menu_type: NonEmptyString = Field(..., description="菜单类型：directory/menu/link。")
    route_path: str = Field("", description="路由路径。")
    route_name: str | None = Field(None, description="路由名称。")
    redirect_path: str | None = Field(None, description="重定向路径。")
    icon: str | None = Field(None, description="图标名称。")
    component_key: str | None = Field(None, description="组件标识。")
    parent_id: str | None = Field(None, description="父级菜单 ID。")
    sort_order: int = Field(0, description="排序值。")
    is_visible: bool = Field(True, description="是否可见。")
    is_enabled: bool = Field(True, description="是否启用。")
    is_external: bool = Field(False, description="是否外链。")
    open_mode: str = Field("self", description="打开方式：self/blank。")
    is_cacheable: bool = Field(False, description="是否缓存。")
    is_affix: bool = Field(False, description="是否固定标签页。")
    active_menu_path: str | None = Field(None, description="激活菜单路径。")
    badge_text: str | None = Field(None, description="徽标文字。")
    badge_type: str | None = Field(None, description="徽标类型。")
    remark: str | None = Field(None, description="备注。")
    meta_json: dict[str, Any] = Field(default_factory=dict, description="扩展元数据。")


class MenuUpdateRequest(BaseModel):
    title: OptionalString | None = Field(None, description="菜单名称。")
    menu_type: OptionalString | None = Field(None, description="菜单类型。")
    route_path: str | None = Field(None, description="路由路径。")
    route_name: str | None = Field(None, description="路由名称。")
    redirect_path: str | None = Field(None, description="重定向路径。")
    icon: str | None = Field(None, description="图标名称。")
    component_key: str | None = Field(None, description="组件标识。")
    parent_id: str | None = Field(None, description="父级菜单 ID。")
    sort_order: int | None = Field(None, description="排序值。")
    is_visible: bool | None = Field(None, description="是否可见。")
    is_enabled: bool | None = Field(None, description="是否启用。")
    is_external: bool | None = Field(None, description="是否外链。")
    open_mode: str | None = Field(None, description="打开方式。")
    is_cacheable: bool | None = Field(None, description="是否缓存。")
    is_affix: bool | None = Field(None, description="是否固定标签页。")
    active_menu_path: str | None = Field(None, description="激活菜单路径。")
    badge_text: str | None = Field(None, description="徽标文字。")
    badge_type: str | None = Field(None, description="徽标类型。")
    remark: str | None = Field(None, description="备注。")
    meta_json: dict[str, Any] | None = Field(None, description="扩展元数据。")
