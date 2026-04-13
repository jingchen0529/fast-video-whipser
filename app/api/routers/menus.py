import sqlite3
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field, StringConstraints

from app.auth.dependencies import require_admin_access, require_csrf_protection
from app.auth.service import create_menu, delete_menu, list_menu_tree, update_menu
from app.core.http import ResponseModel, build_response
from app.db import get_db

router = APIRouter()

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


@router.get(
    "/tree",
    response_model=ResponseModel,
    summary="菜单树 / List menu tree",
)
def menu_tree(
    request: Request,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    _: Annotated[dict, Depends(require_admin_access)],
) -> ResponseModel:
    return build_response(request, data=list_menu_tree(connection))


@router.post(
    "",
    response_model=ResponseModel,
    summary="创建菜单 / Create menu",
)
def create_menu_endpoint(
    request: Request,
    payload: MenuCreateRequest,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    _: Annotated[dict, Depends(require_admin_access)],
    __: Annotated[None, Depends(require_csrf_protection)],
) -> ResponseModel:
    result = create_menu(
        connection,
        code=payload.code,
        title=payload.title,
        menu_type=payload.menu_type,
        route_path=payload.route_path,
        route_name=payload.route_name,
        redirect_path=payload.redirect_path,
        icon=payload.icon,
        component_key=payload.component_key,

        parent_id=payload.parent_id,
        sort_order=payload.sort_order,
        is_visible=payload.is_visible,
        is_enabled=payload.is_enabled,
        is_external=payload.is_external,
        open_mode=payload.open_mode,
        is_cacheable=payload.is_cacheable,
        is_affix=payload.is_affix,
        active_menu_path=payload.active_menu_path,
        badge_text=payload.badge_text,
        badge_type=payload.badge_type,
        remark=payload.remark,
        meta_json=payload.meta_json,
    )
    return build_response(request, data=result)


@router.patch(
    "/{menu_id}",
    response_model=ResponseModel,
    summary="更新菜单 / Update menu",
)
def update_menu_endpoint(
    request: Request,
    menu_id: str,
    payload: MenuUpdateRequest,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    _: Annotated[dict, Depends(require_admin_access)],
    __: Annotated[None, Depends(require_csrf_protection)],
) -> ResponseModel:
    data = payload.model_dump(exclude_unset=True)
    result = update_menu(
        connection,
        menu_id,
        **data,
    )
    return build_response(request, data=result)


@router.delete(
    "/{menu_id}",
    response_model=ResponseModel,
    summary="删除菜单 / Delete menu",
)
def delete_menu_endpoint(
    request: Request,
    menu_id: str,
    connection: Annotated[sqlite3.Connection, Depends(get_db)],
    _: Annotated[dict, Depends(require_admin_access)],
    __: Annotated[None, Depends(require_csrf_protection)],
) -> ResponseModel:
    return build_response(request, data=delete_menu(connection, menu_id))
