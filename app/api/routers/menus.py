from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.auth.dependencies import require_admin_access, require_csrf_protection
from app.auth.service import create_menu, delete_menu, list_menu_tree, update_menu
from app.core.http import ResponseModel, build_response
from app.db import get_db_session
from app.schemas.menus import MenuCreateRequest, MenuUpdateRequest

router = APIRouter()


@router.get(
    "/tree",
    response_model=ResponseModel,
    summary="菜单树 / List menu tree",
)
def menu_tree(
    request: Request,
    session: Annotated[Session, Depends(get_db_session)],
    _: Annotated[dict, Depends(require_admin_access)],
) -> ResponseModel:
    return build_response(request, data=list_menu_tree(session))


@router.post(
    "",
    response_model=ResponseModel,
    summary="创建菜单 / Create menu",
)
def create_menu_endpoint(
    request: Request,
    payload: MenuCreateRequest,
    session: Annotated[Session, Depends(get_db_session)],
    _: Annotated[dict, Depends(require_admin_access)],
    __: Annotated[None, Depends(require_csrf_protection)],
) -> ResponseModel:
    result = create_menu(
        session,
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
    session: Annotated[Session, Depends(get_db_session)],
    _: Annotated[dict, Depends(require_admin_access)],
    __: Annotated[None, Depends(require_csrf_protection)],
) -> ResponseModel:
    data = payload.model_dump(exclude_unset=True)
    result = update_menu(
        session,
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
    session: Annotated[Session, Depends(get_db_session)],
    _: Annotated[dict, Depends(require_admin_access)],
    __: Annotated[None, Depends(require_csrf_protection)],
) -> ResponseModel:
    return build_response(request, data=delete_menu(session, menu_id))
