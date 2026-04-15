import json
import re
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select, func, delete as sa_delete
from sqlalchemy.orm import Session, selectinload

from app.auth.security import (
    create_jwt_token,
    datetime_to_timestamp_ms,
    decode_jwt_token,
    hash_password,
    parse_datetime_value,
    utcnow_ms,
    verify_password,
)
from app.core.config import settings
from app.core.logging import configure_logging
from app.models.auth import (
    AuthRateLimit,
    AuthSession,
    Menu,
    RefreshToken,
    Role,
    RoleMenu,
    User,
    UserRole,
)

USERNAME_PATTERN = re.compile(r"^[a-z0-9_.-]{3,50}$")

ROLE_CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]{2,99}$")
MENU_CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]{2,99}$")
LOGIN_BLOCK_MESSAGE = "登录尝试过于频繁，请稍后再试。"
logger = configure_logging(__name__)
_UNSET = object()


def normalize_username(username: str) -> str:
    normalized = username.strip().lower()
    if not USERNAME_PATTERN.fullmatch(normalized):
        raise ValueError("用户名只能包含字母、数字、点、下划线、中划线，长度为 3 到 50 位。")
    return normalized


def normalize_email(email: str) -> str:
    normalized = email.strip().lower()
    if not normalized or "@" not in normalized:
        raise ValueError("邮箱格式不正确。")
    return normalized


def normalize_role_code(code: str) -> str:
    normalized = code.strip().lower()
    if not ROLE_CODE_PATTERN.fullmatch(normalized):
        raise ValueError("角色编码格式不正确。")
    return normalized


def normalize_menu_code(code: str) -> str:
    normalized = code.strip().lower()
    if not MENU_CODE_PATTERN.fullmatch(normalized):
        raise ValueError("菜单编码格式不正确。")
    return normalized


def ensure_password_strength(password: str) -> None:
    if len(password.strip()) < 8:
        raise ValueError("密码长度至少需要 8 位。")


def _parse_datetime(value: Any) -> datetime:
    parsed = parse_datetime_value(value)
    if parsed is None:
        raise ValueError("时间值不能为空。")
    return parsed


# ---------------------------------------------------------------------------
# Serialization helpers: ORM model -> dict
# ---------------------------------------------------------------------------

def _user_to_dict(user: User) -> dict[str, Any]:
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "display_name": user.display_name,
        "avatar_url": user.avatar_url,
        "is_active": user.is_active,
        "is_superuser": user.is_superuser,
        "last_login_at": user.last_login_at,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
    }


def _role_to_dict(role: Role) -> dict[str, Any]:
    return {
        "id": role.id,
        "code": role.code,
        "name": role.name,
        "description": role.description,
        "is_system": role.is_system,
        "created_at": role.created_at,
        "updated_at": role.updated_at,
    }


def _menu_to_dict(menu: Menu) -> dict[str, Any]:
    try:
        meta_json = json.loads(menu.meta_json or "{}")
    except json.JSONDecodeError:
        meta_json = {}

    return {
        "id": menu.id,
        "parent_id": menu.parent_id,
        "code": menu.code,
        "title": menu.title,
        "menu_type": menu.menu_type,
        "route_path": menu.route_path or "",
        "route_name": menu.route_name,
        "redirect_path": menu.redirect_path,
        "icon": menu.icon,
        "component_key": menu.component_key,
        "sort_order": menu.sort_order or 0,
        "is_visible": menu.is_visible,
        "is_enabled": menu.is_enabled,
        "is_external": menu.is_external,
        "open_mode": menu.open_mode or "self",
        "is_cacheable": menu.is_cacheable,
        "is_affix": menu.is_affix,
        "active_menu_path": menu.active_menu_path,
        "badge_text": menu.badge_text,
        "badge_type": menu.badge_type,
        "remark": menu.remark,
        "meta_json": meta_json,
        "created_at": menu.created_at,
        "updated_at": menu.updated_at,
    }


def _session_to_dict(session: AuthSession) -> dict[str, Any]:
    return {
        "id": session.id,
        "user_id": session.user_id,
        "token_version": session.token_version,
        "csrf_token": session.csrf_token,
        "remember": session.remember,
        "client_ip": session.client_ip,
        "user_agent": session.user_agent,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
        "last_seen_at": session.last_seen_at,
        "revoked_at": session.revoked_at,
        "revoked_reason": session.revoked_reason,
    }


# ---------------------------------------------------------------------------
# Session (auth_sessions) helpers
# ---------------------------------------------------------------------------

def get_session_by_id(
    session: Session,
    session_id: str,
) -> dict[str, Any] | None:
    obj = session.get(AuthSession, session_id)
    if obj is None:
        return None
    return _session_to_dict(obj)


def _get_active_session(
    session: Session,
    session_id: str,
) -> dict[str, Any]:
    s = get_session_by_id(session, session_id)
    if s is None or s["revoked_at"] is not None:
        raise HTTPException(status_code=401, detail="当前会话已失效。")
    return s


# ---------------------------------------------------------------------------
# Audit log (no change — pure logging)
# ---------------------------------------------------------------------------

def _issue_audit_log(
    action: str,
    *,
    outcome: str,
    user_id: str | None = None,
    target_user_id: str | None = None,
    session_id: str | None = None,
    detail: str | None = None,
) -> None:
    logger.info(
        "auth_event action=%s outcome=%s user_id=%s target_user_id=%s session_id=%s detail=%s",
        action,
        outcome,
        user_id or "-",
        target_user_id or "-",
        session_id or "-",
        detail or "-",
    )


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------

def _rate_limit_scopes(login: str, client_ip: str | None) -> list[tuple[str, str]]:
    normalized_ip = (client_ip or "unknown").strip() or "unknown"
    normalized_login = login.strip().lower() or "unknown"
    return [
        ("ip", normalized_ip),
        ("login", normalized_login),
        ("combo", f"{normalized_ip}:{normalized_login}"),
    ]


def assert_login_allowed(
    session: Session,
    *,
    login: str,
    client_ip: str | None = None,
) -> None:
    now = datetime.now(UTC)
    for scope_type, scope_key in _rate_limit_scopes(login, client_ip):
        obj = session.get(AuthRateLimit, (scope_type, scope_key))
        if obj is None or not obj.blocked_until:
            continue
        if _parse_datetime(obj.blocked_until) > now:
            raise HTTPException(status_code=429, detail=LOGIN_BLOCK_MESSAGE)


def register_login_failure(
    session: Session,
    *,
    login: str,
    client_ip: str | None = None,
) -> None:
    now = datetime.now(UTC)
    now_ts = utcnow_ms()
    blocked_until_ts = datetime_to_timestamp_ms(
        now + timedelta(seconds=settings.auth_rate_limit_block_seconds)
    )
    max_attempts = max(1, settings.auth_rate_limit_max_attempts)
    for scope_type, scope_key in _rate_limit_scopes(login, client_ip):
        obj = session.get(AuthRateLimit, (scope_type, scope_key))
        if obj is None:
            failure_count = 1
            obj = AuthRateLimit(
                scope_type=scope_type,
                scope_key=scope_key,
                failure_count=failure_count,
                blocked_until=blocked_until_ts if failure_count >= max_attempts else None,
                last_attempt_at=now_ts,
                created_at=now_ts,
                updated_at=now_ts,
            )
            session.add(obj)
            continue

        failure_count = obj.failure_count
        if obj.blocked_until and _parse_datetime(obj.blocked_until) <= now:
            failure_count = 0

        failure_count += 1
        obj.failure_count = failure_count
        obj.blocked_until = blocked_until_ts if failure_count >= max_attempts else None
        obj.last_attempt_at = now_ts
        obj.updated_at = now_ts
    # Rate limit changes must persist even if the request later raises HTTPException
    session.commit()


def clear_login_failures(
    session: Session,
    *,
    login: str,
    client_ip: str | None = None,
) -> None:
    for scope_type, scope_key in _rate_limit_scopes(login, client_ip):
        session.execute(
            sa_delete(AuthRateLimit).where(
                AuthRateLimit.scope_type == scope_type,
                AuthRateLimit.scope_key == scope_key,
            )
        )
    session.commit()


# ---------------------------------------------------------------------------
# Role helpers
# ---------------------------------------------------------------------------

def _get_role_by_id(session: Session, role_id: str) -> Role | None:
    return session.get(Role, role_id)


def _get_role_by_code(session: Session, role_code: str) -> Role | None:
    return session.scalar(
        select(Role).where(Role.code == normalize_role_code(role_code))
    )


# ---------------------------------------------------------------------------
# Menu helpers
# ---------------------------------------------------------------------------

def _get_menu_by_id(session: Session, menu_id: str) -> Menu | None:
    return session.get(Menu, menu_id)


def _get_menu_by_code(session: Session, code: str) -> Menu | None:
    return session.scalar(
        select(Menu).where(Menu.code == normalize_menu_code(code))
    )


# ---------------------------------------------------------------------------
# User queries
# ---------------------------------------------------------------------------

def get_user_by_id(session: Session, user_id: str) -> dict[str, Any] | None:
    user = session.get(User, user_id)
    if user is None:
        return None
    return _user_to_dict(user)


def get_user_roles(session: Session, user_id: str) -> list[dict[str, Any]]:
    roles = session.scalars(
        select(Role)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user_id)
        .order_by(Role.name.asc())
    ).all()
    return [_role_to_dict(r) for r in roles]


def build_user_profile(
    session: Session,
    user_id: str,
) -> dict[str, Any] | None:
    user = get_user_by_id(session, user_id)
    if user is None:
        return None
    user["roles"] = get_user_roles(session, user_id)
    return user


# ---------------------------------------------------------------------------
# Menu CRUD
# ---------------------------------------------------------------------------

def list_menus(session: Session) -> list[dict[str, Any]]:
    menus = session.scalars(
        select(Menu).order_by(Menu.sort_order.asc(), Menu.created_at.asc(), Menu.id.asc())
    ).all()
    return [_menu_to_dict(m) for m in menus]


def build_menu_tree(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    nodes = []
    by_id: dict[str, dict[str, Any]] = {}

    for item in items:
        node = {
            **item,
            "children": [],
        }
        by_id[node["id"]] = node

    for node in by_id.values():
        parent_id = node["parent_id"]
        if parent_id and parent_id in by_id:
            by_id[parent_id]["children"].append(node)
        else:
            nodes.append(node)

    def sort_nodes(target: list[dict[str, Any]]) -> list[dict[str, Any]]:
        target.sort(key=lambda item: (int(item.get("sort_order") or 0), str(item.get("title") or ""), str(item.get("id") or "")))
        for child in target:
            sort_nodes(child["children"])
        return target

    return sort_nodes(nodes)


def list_menu_tree(session: Session) -> list[dict[str, Any]]:
    return build_menu_tree(list_menus(session))


def _assert_menu_parent_available(
    session: Session,
    *,
    parent_id: str | None,
    menu_id: str | None = None,
) -> Menu | None:
    if not parent_id:
        return None
    parent = _get_menu_by_id(session, parent_id)
    if parent is None:
        raise HTTPException(status_code=404, detail="父级菜单不存在。")
    if menu_id and parent_id == menu_id:
        raise HTTPException(status_code=400, detail="菜单不能将自己设置为父级。")
    return parent


def _assert_menu_parent_chain(
    session: Session,
    *,
    menu_id: str,
    parent_id: str | None,
) -> None:
    current_parent_id = parent_id
    while current_parent_id:
        if current_parent_id == menu_id:
            raise HTTPException(status_code=400, detail="菜单父级关系不能形成循环。")
        parent = _get_menu_by_id(session, current_parent_id)
        if parent is None:
            break
        current_parent_id = parent.parent_id


def create_menu(
    session: Session,
    *,
    code: str,
    title: str,
    menu_type: str,
    route_path: str = "",
    route_name: str | None = None,
    redirect_path: str | None = None,
    icon: str | None = None,
    component_key: str | None = None,
    parent_id: str | None = None,
    sort_order: int = 0,
    is_visible: bool = True,
    is_enabled: bool = True,
    is_external: bool = False,
    open_mode: str = "self",
    is_cacheable: bool = False,
    is_affix: bool = False,
    active_menu_path: str | None = None,
    badge_text: str | None = None,
    badge_type: str | None = None,
    remark: str | None = None,
    meta_json: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_code = normalize_menu_code(code)
    normalized_title = title.strip()
    if not normalized_title:
        raise ValueError("菜单名称不能为空。")
    normalized_menu_type = (menu_type or "").strip().lower()
    if normalized_menu_type not in {"directory", "menu", "link"}:
        raise ValueError("菜单类型仅支持 directory、menu、link。")
    normalized_open_mode = (open_mode or "self").strip().lower()
    if normalized_open_mode not in {"self", "blank"}:
        raise ValueError("打开方式仅支持 self 或 blank。")

    if _get_menu_by_code(session, normalized_code) is not None:
        raise HTTPException(status_code=409, detail="菜单编码已存在。")

    _assert_menu_parent_available(session, parent_id=parent_id)
    now = utcnow_ms()
    menu = Menu(
        id=uuid.uuid4().hex,
        parent_id=parent_id,
        code=normalized_code,
        title=normalized_title,
        menu_type=normalized_menu_type,
        route_path=route_path.strip(),
        route_name=route_name.strip() if route_name else None,
        redirect_path=redirect_path.strip() if redirect_path else None,
        icon=icon.strip() if icon else None,
        component_key=component_key.strip() if component_key else None,
        sort_order=int(sort_order),
        is_visible=is_visible,
        is_enabled=is_enabled,
        is_external=is_external,
        open_mode=normalized_open_mode,
        is_cacheable=is_cacheable,
        is_affix=is_affix,
        active_menu_path=active_menu_path.strip() if active_menu_path else None,
        badge_text=badge_text.strip() if badge_text else None,
        badge_type=badge_type.strip() if badge_type else None,
        remark=remark.strip() if remark else None,
        meta_json=json.dumps(meta_json or {}, ensure_ascii=False),
        created_at=now,
        updated_at=now,
    )
    session.add(menu)
    session.flush()
    _issue_audit_log("menu_create", outcome="success", detail=normalized_code)
    return _menu_to_dict(menu)


def update_menu(
    session: Session,
    menu_id: str,
    *,
    title: Any = _UNSET,
    menu_type: Any = _UNSET,
    route_path: Any = _UNSET,
    route_name: Any = _UNSET,
    redirect_path: Any = _UNSET,
    icon: Any = _UNSET,
    component_key: Any = _UNSET,
    parent_id: Any = _UNSET,
    sort_order: Any = _UNSET,
    is_visible: Any = _UNSET,
    is_enabled: Any = _UNSET,
    is_external: Any = _UNSET,
    open_mode: Any = _UNSET,
    is_cacheable: Any = _UNSET,
    is_affix: Any = _UNSET,
    active_menu_path: Any = _UNSET,
    badge_text: Any = _UNSET,
    badge_type: Any = _UNSET,
    remark: Any = _UNSET,
    meta_json: Any = _UNSET,
) -> dict[str, Any]:
    menu = _get_menu_by_id(session, menu_id)
    if menu is None:
        raise HTTPException(status_code=404, detail="菜单不存在。")

    changed = False
    if title is not _UNSET:
        normalized_title = title.strip()
        if not normalized_title:
            raise ValueError("菜单名称不能为空。")
        menu.title = normalized_title
        changed = True
    if menu_type is not _UNSET:
        normalized_menu_type = menu_type.strip().lower()
        if normalized_menu_type not in {"directory", "menu", "link"}:
            raise ValueError("菜单类型仅支持 directory、menu、link。")
        menu.menu_type = normalized_menu_type
        changed = True
    if route_path is not _UNSET:
        menu.route_path = (route_path or "").strip()
        changed = True
    if route_name is not _UNSET:
        menu.route_name = (route_name or "").strip() or None
        changed = True
    if redirect_path is not _UNSET:
        menu.redirect_path = (redirect_path or "").strip() or None
        changed = True
    if icon is not _UNSET:
        menu.icon = (icon or "").strip() or None
        changed = True
    if component_key is not _UNSET:
        menu.component_key = (component_key or "").strip() or None
        changed = True
    if parent_id is not _UNSET:
        _assert_menu_parent_available(session, parent_id=parent_id, menu_id=menu_id)
        _assert_menu_parent_chain(session, menu_id=menu_id, parent_id=parent_id)
        menu.parent_id = parent_id or None
        changed = True
    if sort_order is not _UNSET:
        menu.sort_order = int(sort_order)
        changed = True
    if is_visible is not _UNSET:
        menu.is_visible = bool(is_visible)
        changed = True
    if is_enabled is not _UNSET:
        menu.is_enabled = bool(is_enabled)
        changed = True
    if is_external is not _UNSET:
        menu.is_external = bool(is_external)
        changed = True
    if open_mode is not _UNSET:
        normalized_open_mode = open_mode.strip().lower()
        if normalized_open_mode not in {"self", "blank"}:
            raise ValueError("打开方式仅支持 self 或 blank。")
        menu.open_mode = normalized_open_mode
        changed = True
    if is_cacheable is not _UNSET:
        menu.is_cacheable = bool(is_cacheable)
        changed = True
    if is_affix is not _UNSET:
        menu.is_affix = bool(is_affix)
        changed = True
    if active_menu_path is not _UNSET:
        menu.active_menu_path = (active_menu_path or "").strip() or None
        changed = True
    if badge_text is not _UNSET:
        menu.badge_text = (badge_text or "").strip() or None
        changed = True
    if badge_type is not _UNSET:
        menu.badge_type = (badge_type or "").strip() or None
        changed = True
    if remark is not _UNSET:
        menu.remark = (remark or "").strip() or None
        changed = True
    if meta_json is not _UNSET:
        menu.meta_json = json.dumps(meta_json or {}, ensure_ascii=False)
        changed = True

    if changed:
        menu.updated_at = utcnow_ms()
        session.flush()

    _issue_audit_log("menu_update", outcome="success", detail=menu_id)
    return _menu_to_dict(menu)


def delete_menu(session: Session, menu_id: str) -> dict[str, Any]:
    menu = _get_menu_by_id(session, menu_id)
    if menu is None:
        raise HTTPException(status_code=404, detail="菜单不存在。")

    child_count = session.scalar(
        select(func.count()).select_from(Menu).where(Menu.parent_id == menu_id)
    )
    if child_count > 0:
        raise HTTPException(status_code=400, detail="当前菜单仍存在子节点，无法删除。")

    result = {
        "id": menu.id,
        "code": menu.code,
        "title": menu.title,
        "deleted": True,
    }
    session.delete(menu)
    session.flush()
    _issue_audit_log("menu_delete", outcome="success", detail=menu_id)
    return result


def get_role_menus(session: Session, role_id: str) -> list[dict[str, Any]]:
    menus = session.scalars(
        select(Menu)
        .join(RoleMenu, RoleMenu.menu_id == Menu.id)
        .where(RoleMenu.role_id == role_id)
        .order_by(Menu.sort_order.asc(), Menu.created_at.asc(), Menu.id.asc())
    ).all()
    return [_menu_to_dict(m) for m in menus]


def assign_menus_to_role(
    session: Session,
    role_id: str,
    menu_ids: list[str],
) -> dict[str, Any]:
    role = _get_role_by_id(session, role_id)
    if role is None:
        raise HTTPException(status_code=404, detail="角色不存在。")

    normalized_menu_ids = [mid.strip() for mid in menu_ids if mid and mid.strip()]
    normalized_menu_ids = list(dict.fromkeys(normalized_menu_ids))
    if normalized_menu_ids:
        menu_rows = session.scalars(
            select(Menu).where(Menu.id.in_(normalized_menu_ids))
        ).all()
    else:
        menu_rows = []

    found_ids = {m.id for m in menu_rows}
    missing_ids = [mid for mid in normalized_menu_ids if mid not in found_ids]
    if missing_ids:
        raise HTTPException(status_code=404, detail=f"以下菜单不存在: {', '.join(missing_ids)}")

    # Collect all ancestor menu IDs
    all_ids = set(normalized_menu_ids)
    parent_lookup = {m.id: m.parent_id for m in menu_rows}
    pending_parent_ids = {pid for pid in parent_lookup.values() if pid}

    while pending_parent_ids:
        parent_menus = session.scalars(
            select(Menu).where(Menu.id.in_(pending_parent_ids))
        ).all()
        if not parent_menus:
            break
        pending_parent_ids = set()
        for m in parent_menus:
            if m.id in all_ids:
                continue
            all_ids.add(m.id)
            if m.parent_id:
                pending_parent_ids.add(m.parent_id)

    # Replace role-menu bindings
    session.execute(sa_delete(RoleMenu).where(RoleMenu.role_id == role_id))
    now = utcnow_ms()
    for mid in all_ids:
        session.add(RoleMenu(role_id=role_id, menu_id=mid, created_at=now))
    session.flush()

    result = _role_to_dict(role)
    result["menus"] = get_role_menus(session, role_id)
    _issue_audit_log("role_assign_menus", outcome="success", detail=role_id)
    return result


def list_user_navigation(
    session: Session,
    *,
    user_id: str,
    is_superuser: bool,
) -> list[dict[str, Any]]:
    if is_superuser:
        candidate_menus_q = (
            select(Menu)
            .where(Menu.is_enabled == True, Menu.is_visible == True)
            .order_by(Menu.sort_order.asc(), Menu.created_at.asc(), Menu.id.asc())
        )
    else:
        candidate_menus_q = (
            select(Menu)
            .join(RoleMenu, RoleMenu.menu_id == Menu.id)
            .join(UserRole, UserRole.role_id == RoleMenu.role_id)
            .where(
                UserRole.user_id == user_id,
                Menu.is_enabled == True,
                Menu.is_visible == True,
            )
            .order_by(Menu.sort_order.asc(), Menu.created_at.asc(), Menu.id.asc())
            .distinct()
        )

    candidate_rows = session.scalars(candidate_menus_q).all()
    candidate_menus = [_menu_to_dict(m) for m in candidate_rows]

    visible_menu_ids: set[str] = set()
    by_id = {menu["id"]: menu for menu in candidate_menus}

    for menu in candidate_menus:
        visible_menu_ids.add(menu["id"])
        parent_id = menu.get("parent_id")
        while parent_id and parent_id in by_id:
            visible_menu_ids.add(parent_id)
            parent_id = by_id[parent_id].get("parent_id")

    filtered_menus = [menu for menu in candidate_menus if menu["id"] in visible_menu_ids]
    return build_menu_tree(filtered_menus)


# ---------------------------------------------------------------------------
# Role CRUD
# ---------------------------------------------------------------------------

def list_roles(session: Session) -> list[dict[str, Any]]:
    roles = session.scalars(
        select(Role).order_by(Role.created_at.asc(), Role.id.asc())
    ).all()
    result = []
    for r in roles:
        role_dict = _role_to_dict(r)
        role_dict["menus"] = get_role_menus(session, r.id)
        result.append(role_dict)
    return result


def create_role(
    session: Session,
    *,
    code: str,
    name: str,
    description: str | None = None,
) -> dict[str, Any]:
    normalized_code = normalize_role_code(code)
    normalized_name = name.strip()
    if not normalized_name:
        raise ValueError("角色名称不能为空。")

    existing = _get_role_by_code(session, normalized_code)
    if existing is not None:
        raise HTTPException(status_code=409, detail="角色编码已存在。")

    now = utcnow_ms()
    role = Role(
        id=uuid.uuid4().hex,
        code=normalized_code,
        name=normalized_name,
        description=description.strip() if description else None,
        is_system=False,
        created_at=now,
        updated_at=now,
    )
    session.add(role)
    session.flush()

    result = _role_to_dict(role)
    result["menus"] = get_role_menus(session, role.id)
    _issue_audit_log("role_create", outcome="success", detail=normalized_code)
    return result


def update_role(
    session: Session,
    role_id: str,
    *,
    name: str | None = None,
    description: str | None = None,
) -> dict[str, Any]:
    role = _get_role_by_id(session, role_id)
    if role is None:
        raise HTTPException(status_code=404, detail="角色不存在。")

    changed = False
    if name is not None:
        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("角色名称不能为空。")
        role.name = normalized_name
        changed = True
    if description is not None:
        role.description = description.strip() or None
        changed = True

    if changed:
        role.updated_at = utcnow_ms()
        session.flush()

    result = _role_to_dict(role)
    result["menus"] = get_role_menus(session, role_id)
    _issue_audit_log("role_update", outcome="success", detail=role_id)
    return result


def delete_role(
    session: Session,
    role_id: str,
) -> dict[str, Any]:
    role = _get_role_by_id(session, role_id)
    if role is None:
        raise HTTPException(status_code=404, detail="角色不存在。")
    if role.is_system:
        raise HTTPException(status_code=400, detail="系统内置角色不允许删除。")

    bound_user_count = session.scalar(
        select(func.count()).select_from(UserRole).where(UserRole.role_id == role_id)
    )
    if bound_user_count > 0:
        raise HTTPException(
            status_code=400,
            detail="当前角色仍分配给用户，无法删除。请先解除用户绑定。",
        )

    result = {
        "id": role.id,
        "code": role.code,
        "name": role.name,
        "deleted": True,
    }
    session.delete(role)
    session.flush()
    _issue_audit_log("role_delete", outcome="success", detail=role_id)
    return result


# ---------------------------------------------------------------------------
# User CRUD
# ---------------------------------------------------------------------------

def list_users(session: Session) -> list[dict[str, Any]]:
    users = session.scalars(
        select(User).order_by(User.created_at.asc(), User.id.asc())
    ).all()
    return [build_user_profile(session, u.id) for u in users]


def _ensure_user_uniqueness(
    session: Session,
    *,
    username: str,
    email: str,
    exclude_user_id: str | None = None,
) -> None:
    username_q = select(User.id).where(User.username == username)
    if exclude_user_id:
        username_q = username_q.where(User.id != exclude_user_id)
    if session.scalar(username_q) is not None:
        raise HTTPException(status_code=409, detail="用户名已存在。")

    email_q = select(User.id).where(User.email == email)
    if exclude_user_id:
        email_q = email_q.where(User.id != exclude_user_id)
    if session.scalar(email_q) is not None:
        raise HTTPException(status_code=409, detail="邮箱已存在。")


def _resolve_role_ids(
    session: Session,
    role_codes: list[str],
) -> list[str]:
    normalized_codes = [normalize_role_code(code) for code in role_codes]
    normalized_codes = list(dict.fromkeys(normalized_codes))
    if not normalized_codes:
        return []

    roles = session.scalars(
        select(Role).where(Role.code.in_(normalized_codes))
    ).all()
    role_id_by_code = {r.code: r.id for r in roles}
    missing_codes = [code for code in normalized_codes if code not in role_id_by_code]
    if missing_codes:
        raise HTTPException(
            status_code=404,
            detail=f"以下角色不存在: {', '.join(missing_codes)}",
        )
    return [role_id_by_code[code] for code in normalized_codes]


def _sync_user_roles(
    session: Session,
    user_id: str,
    role_codes: list[str],
) -> None:
    now = utcnow_ms()
    role_ids = _resolve_role_ids(session, role_codes)
    session.execute(sa_delete(UserRole).where(UserRole.user_id == user_id))
    for role_id in role_ids:
        session.add(UserRole(user_id=user_id, role_id=role_id, created_at=now))


def create_user(
    session: Session,
    *,
    username: str,
    email: str,
    password: str,
    display_name: str | None = None,
    role_codes: list[str] | None = None,
    is_active: bool = True,
    is_superuser: bool = False,
) -> dict[str, Any]:
    normalized_username = normalize_username(username)
    normalized_email = normalize_email(email)
    ensure_password_strength(password)
    _ensure_user_uniqueness(
        session,
        username=normalized_username,
        email=normalized_email,
    )

    user_id = uuid.uuid4().hex
    now = utcnow_ms()
    user = User(
        id=user_id,
        username=normalized_username,
        email=normalized_email,
        display_name=display_name.strip() if display_name and display_name.strip() else normalized_username,
        password_hash=hash_password(password),
        is_active=is_active,
        is_superuser=is_superuser,
        token_version=0,
        created_at=now,
        updated_at=now,
    )
    session.add(user)
    _sync_user_roles(session, user_id, role_codes or ["user"])
    session.flush()
    _issue_audit_log("user_create", outcome="success", target_user_id=user_id)
    return build_user_profile(session, user_id)


def update_user(
    session: Session,
    user_id: str,
    *,
    email: str | None = None,
    display_name: str | None = None,
    avatar_url: str | None = None,
    is_active: bool | None = None,
    is_superuser: bool | None = None,
) -> dict[str, Any]:
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在。")

    normalized_email = normalize_email(email) if email is not None else user.email
    _ensure_user_uniqueness(
        session,
        username=user.username,
        email=normalized_email,
        exclude_user_id=user_id,
    )

    changed = False
    if email is not None:
        user.email = normalized_email
        changed = True
    if display_name is not None:
        normalized_display_name = display_name.strip()
        if not normalized_display_name:
            raise ValueError("显示名称不能为空。")
        user.display_name = normalized_display_name
        changed = True
    if is_active is not None:
        user.is_active = is_active
        changed = True
    if is_superuser is not None:
        user.is_superuser = is_superuser
        changed = True
    if avatar_url is not None:
        user.avatar_url = avatar_url
        changed = True

    if changed:
        user.updated_at = utcnow_ms()
        if is_active is False:
            _revoke_user_sessions(session, user_id=user_id, reason="user_disabled")
        session.flush()

    _issue_audit_log("user_update", outcome="success", target_user_id=user_id)
    return build_user_profile(session, user_id)


def delete_user(
    session: Session,
    user_id: str,
    *,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在。")
    if actor_user_id and actor_user_id == user_id:
        raise HTTPException(status_code=400, detail="不允许删除当前登录用户。")

    if user.is_superuser:
        superuser_count = session.scalar(
            select(func.count()).select_from(User).where(User.is_superuser == True)
        )
        if superuser_count <= 1:
            raise HTTPException(
                status_code=400,
                detail="系统至少需要保留一个超级管理员，当前用户无法删除。",
            )

    result = {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "deleted": True,
    }
    session.delete(user)
    session.flush()
    _issue_audit_log(
        "user_delete",
        outcome="success",
        user_id=actor_user_id,
        target_user_id=user_id,
    )
    return result


def assign_roles_to_user(
    session: Session,
    user_id: str,
    role_codes: list[str],
) -> dict[str, Any]:
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在。")

    _sync_user_roles(session, user_id, role_codes)
    session.flush()
    _issue_audit_log("user_assign_roles", outcome="success", target_user_id=user_id)
    return build_user_profile(session, user_id)


# ---------------------------------------------------------------------------
# Token & session management
# ---------------------------------------------------------------------------

def _get_user_token_version(session: Session, user_id: str) -> int:
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在。")
    return user.token_version


def _create_session(
    session: Session,
    *,
    user_id: str,
    remember: bool,
    client_ip: str | None = None,
    user_agent: str | None = None,
) -> dict[str, Any]:
    now = utcnow_ms()
    session_id = uuid.uuid4().hex
    auth_session = AuthSession(
        id=session_id,
        user_id=user_id,
        token_version=_get_user_token_version(session, user_id),
        csrf_token=secrets.token_urlsafe(32),
        remember=remember,
        client_ip=client_ip,
        user_agent=user_agent,
        created_at=now,
        updated_at=now,
        last_seen_at=now,
    )
    session.add(auth_session)
    session.flush()
    result = get_session_by_id(session, session_id)
    if result is None:
        raise HTTPException(status_code=500, detail="创建会话失败。")
    return result


def _touch_session(session: Session, session_id: str) -> None:
    auth_session = session.get(AuthSession, session_id)
    if auth_session is not None:
        now = utcnow_ms()
        auth_session.last_seen_at = now
        auth_session.updated_at = now


def _revoke_session(
    session: Session,
    *,
    session_id: str,
    reason: str,
) -> None:
    now = utcnow_ms()
    auth_session = session.get(AuthSession, session_id)
    if auth_session is not None:
        if auth_session.revoked_at is None:
            auth_session.revoked_at = now
        if auth_session.revoked_reason is None:
            auth_session.revoked_reason = reason
        auth_session.updated_at = now

    # Revoke related refresh tokens
    tokens = session.scalars(
        select(RefreshToken).where(
            RefreshToken.session_id == session_id,
            RefreshToken.revoked_at.is_(None),
        )
    ).all()
    for token in tokens:
        token.revoked_at = now
        token.revoked_reason = reason


def _revoke_user_sessions(
    session: Session,
    *,
    user_id: str,
    reason: str,
) -> None:
    active_sessions = session.scalars(
        select(AuthSession).where(
            AuthSession.user_id == user_id,
            AuthSession.revoked_at.is_(None),
        )
    ).all()
    for s in active_sessions:
        _revoke_session(session, session_id=s.id, reason=reason)


def _extract_session_claims(claims: dict[str, Any]) -> tuple[str, int]:
    session_id = str(claims.get("sid") or "").strip()
    if not session_id:
        raise HTTPException(status_code=401, detail="令牌缺少会话标识。")

    try:
        token_version = int(claims["ver"])
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="令牌缺少有效版本信息。") from exc

    return session_id, token_version


def validate_token_session(
    session: Session,
    *,
    claims: dict[str, Any],
    require_active_user: bool = True,
) -> tuple[dict[str, Any], dict[str, Any]]:
    session_id, token_version = _extract_session_claims(claims)
    auth_session = _get_active_session(session, session_id)
    if auth_session["user_id"] != claims["sub"]:
        raise HTTPException(status_code=401, detail="当前会话与用户不匹配。")
    if auth_session["token_version"] != token_version:
        raise HTTPException(status_code=401, detail="当前令牌版本已失效。")

    user = build_user_profile(session, claims["sub"])
    if user is None:
        raise HTTPException(status_code=401, detail="用户不存在。")
    if require_active_user and not user["is_active"]:
        raise HTTPException(status_code=403, detail="当前用户已被禁用。")
    if _get_user_token_version(session, user["id"]) != token_version:
        raise HTTPException(status_code=401, detail="当前令牌版本已失效。")
    return auth_session, user


def _issue_token_pair(
    session: Session,
    user: dict[str, Any],
    auth_session: dict[str, Any],
) -> dict[str, Any]:
    additional_claims = {
        "username": user["username"],
        "sid": auth_session["id"],
        "ver": auth_session["token_version"],
    }
    access_token = create_jwt_token(
        subject=user["id"],
        secret=settings.auth_jwt_secret,
        issuer=settings.auth_jwt_issuer,
        token_type="access",
        expires_delta=timedelta(minutes=settings.auth_access_token_expire_minutes),
        additional_claims=additional_claims,
    )
    refresh_token = create_jwt_token(
        subject=user["id"],
        secret=settings.auth_jwt_secret,
        issuer=settings.auth_jwt_issuer,
        token_type="refresh",
        expires_delta=timedelta(days=settings.auth_refresh_token_expire_days),
        additional_claims=additional_claims,
    )

    rt = RefreshToken(
        id=uuid.uuid4().hex,
        user_id=user["id"],
        session_id=auth_session["id"],
        token_jti=refresh_token["claims"]["jti"],
        expires_at=datetime_to_timestamp_ms(
            datetime.fromtimestamp(refresh_token["claims"]["exp"], tz=UTC)
        ),
        created_at=utcnow_ms(),
    )
    session.add(rt)
    _touch_session(session, auth_session["id"])
    session.flush()

    return {
        "token_type": "Cookie",
        "access_token": access_token["token"],
        "refresh_token": refresh_token["token"],
        "csrf_token": auth_session["csrf_token"],
        "access_token_expires_in": settings.auth_access_token_expire_minutes * 60,
        "refresh_token_expires_in": settings.auth_refresh_token_expire_days * 24 * 60 * 60,
        "user": user,
        "remember": auth_session["remember"],
        "session_id": auth_session["id"],
    }


# ---------------------------------------------------------------------------
# High-level auth operations
# ---------------------------------------------------------------------------

def register_user(
    session: Session,
    *,
    username: str,
    email: str,
    password: str,
    display_name: str | None = None,
    remember: bool = False,
    client_ip: str | None = None,
    user_agent: str | None = None,
) -> dict[str, Any]:
    user = create_user(
        session,
        username=username,
        email=email,
        password=password,
        display_name=display_name,
        role_codes=["user"],
        is_active=True,
        is_superuser=False,
    )
    auth_session = _create_session(
        session,
        user_id=user["id"],
        remember=remember,
        client_ip=client_ip,
        user_agent=user_agent,
    )
    result = _issue_token_pair(session, user, auth_session)
    _issue_audit_log("register", outcome="success", user_id=user["id"], session_id=auth_session["id"])
    return result


def _get_user_login_row(session: Session, login: str) -> User | None:
    normalized_login = login.strip().lower()
    return session.scalar(
        select(User).where(
            (User.username == normalized_login) | (User.email == normalized_login)
        )
    )


def authenticate_user(
    session: Session,
    *,
    login: str,
    password: str,
    remember: bool = False,
    client_ip: str | None = None,
    user_agent: str | None = None,
) -> dict[str, Any]:
    user_obj = _get_user_login_row(session, login)
    if user_obj is None or not verify_password(password, user_obj.password_hash):
        register_login_failure(session, login=login, client_ip=client_ip)
        _issue_audit_log("login", outcome="failure", detail="invalid_credentials")
        raise HTTPException(status_code=401, detail="用户名或密码错误。")

    if not user_obj.is_active:
        register_login_failure(session, login=login, client_ip=client_ip)
        _issue_audit_log("login", outcome="failure", user_id=user_obj.id, detail="user_disabled")
        raise HTTPException(status_code=403, detail="当前用户已被禁用。")

    clear_login_failures(session, login=login, client_ip=client_ip)
    now = utcnow_ms()
    user_obj.last_login_at = now
    user_obj.updated_at = now
    session.flush()

    user = build_user_profile(session, user_obj.id)
    auth_session = _create_session(
        session,
        user_id=user["id"],
        remember=remember,
        client_ip=client_ip,
        user_agent=user_agent,
    )
    result = _issue_token_pair(session, user, auth_session)
    _issue_audit_log("login", outcome="success", user_id=user["id"], session_id=auth_session["id"])
    return result


def refresh_user_token(
    session: Session,
    *,
    refresh_token: str,
) -> dict[str, Any]:
    try:
        claims = decode_jwt_token(
            refresh_token,
            secret=settings.auth_jwt_secret,
            issuer=settings.auth_jwt_issuer,
            expected_type="refresh",
        )
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    token_obj = session.scalar(
        select(RefreshToken).where(
            RefreshToken.token_jti == claims["jti"],
            RefreshToken.revoked_at.is_(None),
        )
    )
    if token_obj is None:
        raise HTTPException(status_code=401, detail="刷新令牌不存在或已失效。")

    if _parse_datetime(token_obj.expires_at) <= datetime.now(UTC):
        raise HTTPException(status_code=401, detail="刷新令牌已过期。")

    auth_session, user = validate_token_session(
        session,
        claims=claims,
        require_active_user=True,
    )
    if token_obj.session_id and token_obj.session_id != auth_session["id"]:
        raise HTTPException(status_code=401, detail="刷新令牌会话不匹配。")

    token_obj.revoked_at = utcnow_ms()
    token_obj.revoked_reason = "rotated"
    session.flush()

    result = _issue_token_pair(session, user, auth_session)
    _issue_audit_log("refresh", outcome="success", user_id=user["id"], session_id=auth_session["id"])
    return result


def revoke_refresh_token(
    session: Session,
    *,
    refresh_token: str | None = None,
    access_token: str | None = None,
) -> dict[str, Any]:
    token_value = refresh_token or access_token
    if not token_value:
        raise HTTPException(status_code=400, detail="缺少可用于退出登录的会话令牌。")

    expected_type = "refresh" if refresh_token else "access"
    try:
        claims = decode_jwt_token(
            token_value,
            secret=settings.auth_jwt_secret,
            issuer=settings.auth_jwt_issuer,
            expected_type=expected_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    session_id, _ = _extract_session_claims(claims)
    _revoke_session(session, session_id=session_id, reason="logout")
    session.flush()
    _issue_audit_log("logout", outcome="success", user_id=claims.get("sub"), session_id=session_id)
    return {"revoked": True}


def change_password(
    session: Session,
    *,
    user_id: str,
    current_password: str,
    new_password: str,
) -> dict[str, Any]:
    ensure_password_strength(new_password)
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在。")

    if not verify_password(current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="当前密码不正确。")

    user.password_hash = hash_password(new_password)
    user.token_version = user.token_version + 1
    user.updated_at = utcnow_ms()
    _revoke_user_sessions(session, user_id=user_id, reason="password_changed")
    session.flush()
    _issue_audit_log("password_change", outcome="success", user_id=user_id)
    return {"changed": True}
