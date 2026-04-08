import re
import secrets
import sqlite3
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException

from app.auth.security import (
    create_jwt_token,
    decode_jwt_token,
    hash_password,
    utcnow_iso,
    verify_password,
)
from app.core.config import settings
from app.core.logging import configure_logging

USERNAME_PATTERN = re.compile(r"^[a-z0-9_.-]{3,50}$")
PERMISSION_CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]{2,99}$")
ROLE_CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]{2,99}$")
LOGIN_BLOCK_MESSAGE = "登录尝试过于频繁，请稍后再试。"
logger = configure_logging(__name__)


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


def normalize_permission_code(code: str) -> str:
    normalized = code.strip().lower()
    if not PERMISSION_CODE_PATTERN.fullmatch(normalized):
        raise ValueError("权限编码格式不正确。")
    return normalized


def normalize_role_code(code: str) -> str:
    normalized = code.strip().lower()
    if not ROLE_CODE_PATTERN.fullmatch(normalized):
        raise ValueError("角色编码格式不正确。")
    return normalized


def ensure_password_strength(password: str) -> None:
    if len(password.strip()) < 8:
        raise ValueError("密码长度至少需要 8 位。")


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _row_to_session(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "token_version": int(row["token_version"]),
        "csrf_token": row["csrf_token"],
        "remember": bool(row["remember"]),
        "client_ip": row["client_ip"],
        "user_agent": row["user_agent"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "last_seen_at": row["last_seen_at"],
        "revoked_at": row["revoked_at"],
        "revoked_reason": row["revoked_reason"],
    }


def get_session_by_id(
    connection: sqlite3.Connection,
    session_id: str,
) -> dict[str, Any] | None:
    row = connection.execute(
        "SELECT * FROM auth_sessions WHERE id = ? LIMIT 1",
        (session_id,),
    ).fetchone()
    if row is None:
        return None
    return _row_to_session(row)


def _get_active_session(
    connection: sqlite3.Connection,
    session_id: str,
) -> dict[str, Any]:
    session = get_session_by_id(connection, session_id)
    if session is None or session["revoked_at"] is not None:
        raise HTTPException(status_code=401, detail="当前会话已失效。")
    return session


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


def _rate_limit_scopes(login: str, client_ip: str | None) -> list[tuple[str, str]]:
    normalized_ip = (client_ip or "unknown").strip() or "unknown"
    normalized_login = login.strip().lower() or "unknown"
    return [
        ("ip", normalized_ip),
        ("login", normalized_login),
        ("combo", f"{normalized_ip}:{normalized_login}"),
    ]


def assert_login_allowed(
    connection: sqlite3.Connection,
    *,
    login: str,
    client_ip: str | None = None,
) -> None:
    now = datetime.now(UTC)
    for scope_type, scope_key in _rate_limit_scopes(login, client_ip):
        row = connection.execute(
            """
            SELECT blocked_until
            FROM auth_rate_limits
            WHERE scope_type = ? AND scope_key = ?
            LIMIT 1
            """,
            (scope_type, scope_key),
        ).fetchone()
        if row is None or not row["blocked_until"]:
            continue
        if _parse_datetime(row["blocked_until"]) > now:
            raise HTTPException(status_code=429, detail=LOGIN_BLOCK_MESSAGE)


def register_login_failure(
    connection: sqlite3.Connection,
    *,
    login: str,
    client_ip: str | None = None,
) -> None:
    now = datetime.now(UTC)
    now_iso = utcnow_iso()
    blocked_until_iso = (now + timedelta(seconds=settings.auth_rate_limit_block_seconds)).isoformat()
    max_attempts = max(1, settings.auth_rate_limit_max_attempts)
    for scope_type, scope_key in _rate_limit_scopes(login, client_ip):
        row = connection.execute(
            """
            SELECT failure_count, blocked_until
            FROM auth_rate_limits
            WHERE scope_type = ? AND scope_key = ?
            LIMIT 1
            """,
            (scope_type, scope_key),
        ).fetchone()
        if row is None:
            failure_count = 1
            connection.execute(
                """
                INSERT INTO auth_rate_limits (
                    scope_type, scope_key, failure_count, blocked_until,
                    last_attempt_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    scope_type,
                    scope_key,
                    failure_count,
                    blocked_until_iso if failure_count >= max_attempts else None,
                    now_iso,
                    now_iso,
                    now_iso,
                ),
            )
            continue

        blocked_until = row["blocked_until"]
        failure_count = int(row["failure_count"])
        if blocked_until and _parse_datetime(blocked_until) <= now:
            failure_count = 0

        failure_count += 1
        connection.execute(
            """
            UPDATE auth_rate_limits
            SET failure_count = ?,
                blocked_until = ?,
                last_attempt_at = ?,
                updated_at = ?
            WHERE scope_type = ? AND scope_key = ?
            """,
            (
                failure_count,
                blocked_until_iso if failure_count >= max_attempts else None,
                now_iso,
                now_iso,
                scope_type,
                scope_key,
            ),
        )
    connection.commit()


def clear_login_failures(
    connection: sqlite3.Connection,
    *,
    login: str,
    client_ip: str | None = None,
) -> None:
    for scope_type, scope_key in _rate_limit_scopes(login, client_ip):
        connection.execute(
            "DELETE FROM auth_rate_limits WHERE scope_type = ? AND scope_key = ?",
            (scope_type, scope_key),
        )
    connection.commit()


def _row_to_permission(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "code": row["code"],
        "name": row["name"],
        "group_name": row["group_name"],
        "description": row["description"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _row_to_role(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "code": row["code"],
        "name": row["name"],
        "description": row["description"],
        "is_system": bool(row["is_system"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _row_to_user(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "username": row["username"],
        "email": row["email"],
        "display_name": row["display_name"],
        "avatar_url": row["avatar_url"],
        "is_active": bool(row["is_active"]),
        "is_superuser": bool(row["is_superuser"]),
        "last_login_at": row["last_login_at"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def get_user_by_id(connection: sqlite3.Connection, user_id: str) -> dict[str, Any] | None:
    row = connection.execute(
        "SELECT * FROM users WHERE id = ? LIMIT 1",
        (user_id,),
    ).fetchone()
    if row is None:
        return None
    return _row_to_user(row)


def get_user_roles(connection: sqlite3.Connection, user_id: str) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT r.*
        FROM roles r
        INNER JOIN user_roles ur ON ur.role_id = r.id
        WHERE ur.user_id = ?
        ORDER BY r.name ASC
        """,
        (user_id,),
    ).fetchall()
    return [_row_to_role(row) for row in rows]


def get_role_permissions(
    connection: sqlite3.Connection,
    role_id: str,
) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT p.*
        FROM permissions p
        INNER JOIN role_permissions rp ON rp.permission_id = p.id
        WHERE rp.role_id = ?
        ORDER BY p.group_name ASC, p.code ASC
        """,
        (role_id,),
    ).fetchall()
    return [_row_to_permission(row) for row in rows]


def get_user_permissions(
    connection: sqlite3.Connection,
    user_id: str,
    *,
    is_superuser: bool,
) -> list[dict[str, Any]]:
    if is_superuser:
        return list_permissions(connection)

    rows = connection.execute(
        """
        SELECT DISTINCT p.*
        FROM permissions p
        INNER JOIN role_permissions rp ON rp.permission_id = p.id
        INNER JOIN user_roles ur ON ur.role_id = rp.role_id
        WHERE ur.user_id = ?
        ORDER BY p.group_name ASC, p.code ASC
        """,
        (user_id,),
    ).fetchall()
    return [_row_to_permission(row) for row in rows]


def build_user_profile(
    connection: sqlite3.Connection,
    user_id: str,
) -> dict[str, Any] | None:
    user = get_user_by_id(connection, user_id)
    if user is None:
        return None

    roles = get_user_roles(connection, user_id)
    permissions = get_user_permissions(
        connection,
        user_id,
        is_superuser=user["is_superuser"],
    )
    user["roles"] = roles
    user["permissions"] = permissions
    return user


def list_permissions(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT *
        FROM permissions
        ORDER BY group_name ASC, code ASC
        """
    ).fetchall()
    return [_row_to_permission(row) for row in rows]


def create_permission(
    connection: sqlite3.Connection,
    *,
    code: str,
    name: str,
    group_name: str,
    description: str | None = None,
) -> dict[str, Any]:
    normalized_code = normalize_permission_code(code)
    normalized_group = group_name.strip().lower()
    normalized_name = name.strip()
    if not normalized_name:
        raise ValueError("权限名称不能为空。")
    if not normalized_group:
        raise ValueError("权限分组不能为空。")

    exists = connection.execute(
        "SELECT id FROM permissions WHERE code = ? LIMIT 1",
        (normalized_code,),
    ).fetchone()
    if exists is not None:
        raise HTTPException(status_code=409, detail="权限编码已存在。")

    now = utcnow_iso()
    permission_id = uuid.uuid4().hex
    connection.execute(
        """
        INSERT INTO permissions (
            id, code, name, group_name, description, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            permission_id,
            normalized_code,
            normalized_name,
            normalized_group,
            description.strip() if description else None,
            now,
            now,
        ),
    )
    super_admin_role = _get_role_by_code(connection, "super_admin")
    if super_admin_role is not None:
        connection.execute(
            """
            INSERT OR IGNORE INTO role_permissions (role_id, permission_id, created_at)
            VALUES (?, ?, ?)
            """,
            (super_admin_role["id"], permission_id, now),
        )
    connection.commit()

    row = connection.execute(
        "SELECT * FROM permissions WHERE id = ? LIMIT 1",
        (permission_id,),
    ).fetchone()
    _issue_audit_log("permission_create", outcome="success", detail=normalized_code)
    return _row_to_permission(row)


def list_roles(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT *
        FROM roles
        ORDER BY created_at ASC, id ASC
        """
    ).fetchall()
    roles = []
    for row in rows:
        role = _row_to_role(row)
        if role["code"] == "super_admin":
            role["permissions"] = list_permissions(connection)
        else:
            role["permissions"] = get_role_permissions(connection, role["id"])
        roles.append(role)
    return roles


def _get_role_by_id(connection: sqlite3.Connection, role_id: str) -> sqlite3.Row | None:
    return connection.execute(
        "SELECT * FROM roles WHERE id = ? LIMIT 1",
        (role_id,),
    ).fetchone()


def _get_role_by_code(connection: sqlite3.Connection, role_code: str) -> sqlite3.Row | None:
    return connection.execute(
        "SELECT * FROM roles WHERE code = ? LIMIT 1",
        (normalize_role_code(role_code),),
    ).fetchone()


def create_role(
    connection: sqlite3.Connection,
    *,
    code: str,
    name: str,
    description: str | None = None,
    permission_codes: list[str] | None = None,
) -> dict[str, Any]:
    normalized_code = normalize_role_code(code)
    normalized_name = name.strip()
    if not normalized_name:
        raise ValueError("角色名称不能为空。")

    existing = _get_role_by_code(connection, normalized_code)
    if existing is not None:
        raise HTTPException(status_code=409, detail="角色编码已存在。")

    now = utcnow_iso()
    role_id = uuid.uuid4().hex
    connection.execute(
        """
        INSERT INTO roles (
            id, code, name, description, is_system, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            role_id,
            normalized_code,
            normalized_name,
            description.strip() if description else None,
            0,
            now,
            now,
        ),
    )

    if permission_codes is not None:
        _sync_role_permissions(connection, role_id, permission_codes)

    connection.commit()
    role_row = _get_role_by_id(connection, role_id)
    role = _row_to_role(role_row)
    role["permissions"] = get_role_permissions(connection, role_id)
    _issue_audit_log("role_create", outcome="success", detail=normalized_code)
    return role


def update_role(
    connection: sqlite3.Connection,
    role_id: str,
    *,
    name: str | None = None,
    description: str | None = None,
) -> dict[str, Any]:
    role_row = _get_role_by_id(connection, role_id)
    if role_row is None:
        raise HTTPException(status_code=404, detail="角色不存在。")

    updates: list[str] = []
    values: list[Any] = []
    if name is not None:
        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("角色名称不能为空。")
        updates.append("name = ?")
        values.append(normalized_name)
    if description is not None:
        updates.append("description = ?")
        values.append(description.strip() or None)

    if updates:
        updates.append("updated_at = ?")
        values.append(utcnow_iso())
        values.append(role_id)
        connection.execute(
            f"UPDATE roles SET {', '.join(updates)} WHERE id = ?",
            tuple(values),
        )
        connection.commit()

    role = _row_to_role(_get_role_by_id(connection, role_id))
    role["permissions"] = get_role_permissions(connection, role_id)
    _issue_audit_log("role_update", outcome="success", detail=role_id)
    return role


def delete_role(
    connection: sqlite3.Connection,
    role_id: str,
) -> dict[str, Any]:
    role_row = _get_role_by_id(connection, role_id)
    if role_row is None:
        raise HTTPException(status_code=404, detail="角色不存在。")
    if bool(role_row["is_system"]):
        raise HTTPException(status_code=400, detail="系统内置角色不允许删除。")

    bound_user_count = int(
        connection.execute(
            "SELECT COUNT(1) AS count FROM user_roles WHERE role_id = ?",
            (role_id,),
        ).fetchone()["count"]
    )
    if bound_user_count > 0:
        raise HTTPException(
            status_code=400,
            detail="当前角色仍分配给用户，无法删除。请先解除用户绑定。",
        )

    role = _row_to_role(role_row)
    connection.execute("DELETE FROM roles WHERE id = ?", (role_id,))
    connection.commit()
    _issue_audit_log("role_delete", outcome="success", detail=role_id)
    return {
        "id": role["id"],
        "code": role["code"],
        "name": role["name"],
        "deleted": True,
    }


def assign_permissions_to_role(
    connection: sqlite3.Connection,
    role_id: str,
    permission_codes: list[str],
) -> dict[str, Any]:
    role_row = _get_role_by_id(connection, role_id)
    if role_row is None:
        raise HTTPException(status_code=404, detail="角色不存在。")
    if role_row["code"] == "super_admin":
        raise HTTPException(
            status_code=400,
            detail="super_admin 角色默认拥有全部权限，无需单独分配。",
        )

    _sync_role_permissions(connection, role_id, permission_codes)
    connection.commit()

    role = _row_to_role(_get_role_by_id(connection, role_id))
    role["permissions"] = get_role_permissions(connection, role_id)
    _issue_audit_log("role_assign_permissions", outcome="success", detail=role_id)
    return role


def _sync_role_permissions(
    connection: sqlite3.Connection,
    role_id: str,
    permission_codes: list[str],
) -> None:
    now = utcnow_iso()
    normalized_codes = [normalize_permission_code(code) for code in permission_codes]
    normalized_codes = list(dict.fromkeys(normalized_codes))
    if normalized_codes:
        placeholders = ", ".join("?" for _ in normalized_codes)
        permission_rows = connection.execute(
            f"SELECT id, code FROM permissions WHERE code IN ({placeholders})",
            tuple(normalized_codes),
        ).fetchall()
    else:
        permission_rows = []

    permission_id_by_code = {row["code"]: row["id"] for row in permission_rows}
    missing_codes = [code for code in normalized_codes if code not in permission_id_by_code]
    if missing_codes:
        raise HTTPException(
            status_code=404,
            detail=f"以下权限不存在: {', '.join(missing_codes)}",
        )

    connection.execute(
        "DELETE FROM role_permissions WHERE role_id = ?",
        (role_id,),
    )
    for permission_code in normalized_codes:
        connection.execute(
            """
            INSERT INTO role_permissions (role_id, permission_id, created_at)
            VALUES (?, ?, ?)
            """,
            (role_id, permission_id_by_code[permission_code], now),
        )


def list_users(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT *
        FROM users
        ORDER BY created_at ASC, id ASC
        """
    ).fetchall()
    return [build_user_profile(connection, row["id"]) for row in rows]


def _ensure_user_uniqueness(
    connection: sqlite3.Connection,
    *,
    username: str,
    email: str,
    exclude_user_id: str | None = None,
) -> None:
    username_row = connection.execute(
        """
        SELECT id
        FROM users
        WHERE username = ? AND (? IS NULL OR id != ?)
        LIMIT 1
        """,
        (username, exclude_user_id, exclude_user_id),
    ).fetchone()
    if username_row is not None:
        raise HTTPException(status_code=409, detail="用户名已存在。")

    email_row = connection.execute(
        """
        SELECT id
        FROM users
        WHERE email = ? AND (? IS NULL OR id != ?)
        LIMIT 1
        """,
        (email, exclude_user_id, exclude_user_id),
    ).fetchone()
    if email_row is not None:
        raise HTTPException(status_code=409, detail="邮箱已存在。")


def _resolve_role_ids(
    connection: sqlite3.Connection,
    role_codes: list[str],
) -> list[str]:
    normalized_codes = [normalize_role_code(code) for code in role_codes]
    normalized_codes = list(dict.fromkeys(normalized_codes))
    if not normalized_codes:
        return []

    placeholders = ", ".join("?" for _ in normalized_codes)
    rows = connection.execute(
        f"SELECT id, code FROM roles WHERE code IN ({placeholders})",
        tuple(normalized_codes),
    ).fetchall()
    role_id_by_code = {row["code"]: row["id"] for row in rows}
    missing_codes = [code for code in normalized_codes if code not in role_id_by_code]
    if missing_codes:
        raise HTTPException(
            status_code=404,
            detail=f"以下角色不存在: {', '.join(missing_codes)}",
        )

    return [role_id_by_code[code] for code in normalized_codes]


def _sync_user_roles(
    connection: sqlite3.Connection,
    user_id: str,
    role_codes: list[str],
) -> None:
    now = utcnow_iso()
    role_ids = _resolve_role_ids(connection, role_codes)
    connection.execute("DELETE FROM user_roles WHERE user_id = ?", (user_id,))
    for role_id in role_ids:
        connection.execute(
            """
            INSERT INTO user_roles (user_id, role_id, created_at)
            VALUES (?, ?, ?)
            """,
            (user_id, role_id, now),
        )


def create_user(
    connection: sqlite3.Connection,
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
        connection,
        username=normalized_username,
        email=normalized_email,
    )

    user_id = uuid.uuid4().hex
    now = utcnow_iso()
    connection.execute(
        """
        INSERT INTO users (
            id, username, email, display_name, password_hash,
            is_active, is_superuser, token_version, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            normalized_username,
            normalized_email,
            display_name.strip() if display_name and display_name.strip() else normalized_username,
            hash_password(password),
            int(is_active),
            int(is_superuser),
            0,
            now,
            now,
        ),
    )
    _sync_user_roles(connection, user_id, role_codes or ["user"])
    connection.commit()
    _issue_audit_log("user_create", outcome="success", target_user_id=user_id)
    return build_user_profile(connection, user_id)


def update_user(
    connection: sqlite3.Connection,
    user_id: str,
    *,
    email: str | None = None,
    display_name: str | None = None,
    avatar_url: str | None = None,
    is_active: bool | None = None,
    is_superuser: bool | None = None,
) -> dict[str, Any]:
    current_user = get_user_by_id(connection, user_id)
    if current_user is None:
        raise HTTPException(status_code=404, detail="用户不存在。")

    normalized_email = (
        normalize_email(email)
        if email is not None
        else current_user["email"]
    )
    _ensure_user_uniqueness(
        connection,
        username=current_user["username"],
        email=normalized_email,
        exclude_user_id=user_id,
    )

    updates: list[str] = []
    values: list[Any] = []
    if email is not None:
        updates.append("email = ?")
        values.append(normalized_email)
    if display_name is not None:
        normalized_display_name = display_name.strip()
        if not normalized_display_name:
            raise ValueError("显示名称不能为空。")
        updates.append("display_name = ?")
        values.append(normalized_display_name)
    if is_active is not None:
        updates.append("is_active = ?")
        values.append(int(is_active))
    if is_superuser is not None:
        updates.append("is_superuser = ?")
        values.append(int(is_superuser))
    if avatar_url is not None:
        updates.append("avatar_url = ?")
        values.append(avatar_url)

    if updates:
        updates.append("updated_at = ?")
        values.append(utcnow_iso())
        values.append(user_id)
        connection.execute(
            f"UPDATE users SET {', '.join(updates)} WHERE id = ?",
            tuple(values),
        )
        if is_active is False:
            _revoke_user_sessions(connection, user_id=user_id, reason="user_disabled")
        connection.commit()

    _issue_audit_log("user_update", outcome="success", target_user_id=user_id)
    return build_user_profile(connection, user_id)


def delete_user(
    connection: sqlite3.Connection,
    user_id: str,
    *,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    user = get_user_by_id(connection, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在。")
    if actor_user_id and actor_user_id == user_id:
        raise HTTPException(status_code=400, detail="不允许删除当前登录用户。")

    if user["is_superuser"]:
        superuser_count = int(
            connection.execute(
                "SELECT COUNT(1) AS count FROM users WHERE is_superuser = 1",
            ).fetchone()["count"]
        )
        if superuser_count <= 1:
            raise HTTPException(
                status_code=400,
                detail="系统至少需要保留一个超级管理员，当前用户无法删除。",
            )

    connection.execute("DELETE FROM users WHERE id = ?", (user_id,))
    connection.commit()
    _issue_audit_log(
        "user_delete",
        outcome="success",
        user_id=actor_user_id,
        target_user_id=user_id,
    )
    return {
        "id": user["id"],
        "username": user["username"],
        "display_name": user["display_name"],
        "deleted": True,
    }


def assign_roles_to_user(
    connection: sqlite3.Connection,
    user_id: str,
    role_codes: list[str],
) -> dict[str, Any]:
    current_user = get_user_by_id(connection, user_id)
    if current_user is None:
        raise HTTPException(status_code=404, detail="用户不存在。")

    _sync_user_roles(connection, user_id, role_codes)
    connection.commit()
    _issue_audit_log("user_assign_roles", outcome="success", target_user_id=user_id)
    return build_user_profile(connection, user_id)


def _get_user_token_version(connection: sqlite3.Connection, user_id: str) -> int:
    row = connection.execute(
        "SELECT token_version FROM users WHERE id = ? LIMIT 1",
        (user_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="用户不存在。")
    return int(row["token_version"])


def _create_session(
    connection: sqlite3.Connection,
    *,
    user_id: str,
    remember: bool,
    client_ip: str | None = None,
    user_agent: str | None = None,
) -> dict[str, Any]:
    now = utcnow_iso()
    session_id = uuid.uuid4().hex
    connection.execute(
        """
        INSERT INTO auth_sessions (
            id, user_id, token_version, csrf_token, remember,
            client_ip, user_agent, created_at, updated_at, last_seen_at,
            revoked_at, revoked_reason
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            session_id,
            user_id,
            _get_user_token_version(connection, user_id),
            secrets.token_urlsafe(32),
            int(remember),
            client_ip,
            user_agent,
            now,
            now,
            now,
            None,
            None,
        ),
    )
    session = get_session_by_id(connection, session_id)
    if session is None:
        raise HTTPException(status_code=500, detail="创建会话失败。")
    return session


def _touch_session(connection: sqlite3.Connection, session_id: str) -> None:
    now = utcnow_iso()
    connection.execute(
        """
        UPDATE auth_sessions
        SET last_seen_at = ?, updated_at = ?
        WHERE id = ?
        """,
        (now, now, session_id),
    )


def _revoke_session(
    connection: sqlite3.Connection,
    *,
    session_id: str,
    reason: str,
) -> None:
    now = utcnow_iso()
    connection.execute(
        """
        UPDATE auth_sessions
        SET revoked_at = COALESCE(revoked_at, ?),
            revoked_reason = COALESCE(revoked_reason, ?),
            updated_at = ?
        WHERE id = ?
        """,
        (now, reason, now, session_id),
    )
    connection.execute(
        """
        UPDATE refresh_tokens
        SET revoked_at = COALESCE(revoked_at, ?),
            revoked_reason = COALESCE(revoked_reason, ?)
        WHERE session_id = ? AND revoked_at IS NULL
        """,
        (now, reason, session_id),
    )


def _revoke_user_sessions(
    connection: sqlite3.Connection,
    *,
    user_id: str,
    reason: str,
) -> None:
    session_rows = connection.execute(
        """
        SELECT id
        FROM auth_sessions
        WHERE user_id = ? AND revoked_at IS NULL
        """,
        (user_id,),
    ).fetchall()
    for row in session_rows:
        _revoke_session(connection, session_id=row["id"], reason=reason)


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
    connection: sqlite3.Connection,
    *,
    claims: dict[str, Any],
    require_active_user: bool = True,
) -> tuple[dict[str, Any], dict[str, Any]]:
    session_id, token_version = _extract_session_claims(claims)
    session = _get_active_session(connection, session_id)
    if session["user_id"] != claims["sub"]:
        raise HTTPException(status_code=401, detail="当前会话与用户不匹配。")
    if session["token_version"] != token_version:
        raise HTTPException(status_code=401, detail="当前令牌版本已失效。")

    user = build_user_profile(connection, claims["sub"])
    if user is None:
        raise HTTPException(status_code=401, detail="用户不存在。")
    if require_active_user and not user["is_active"]:
        raise HTTPException(status_code=403, detail="当前用户已被禁用。")
    if _get_user_token_version(connection, user["id"]) != token_version:
        raise HTTPException(status_code=401, detail="当前令牌版本已失效。")
    return session, user


def _issue_token_pair(
    connection: sqlite3.Connection,
    user: dict[str, Any],
    session: dict[str, Any],
) -> dict[str, Any]:
    additional_claims = {
        "username": user["username"],
        "sid": session["id"],
        "ver": session["token_version"],
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

    connection.execute(
        """
        INSERT INTO refresh_tokens (
            id, user_id, session_id, token_jti, expires_at, created_at, revoked_at, revoked_reason
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            uuid.uuid4().hex,
            user["id"],
            session["id"],
            refresh_token["claims"]["jti"],
            datetime.fromtimestamp(
                refresh_token["claims"]["exp"],
                tz=UTC,
            ).isoformat(),
            utcnow_iso(),
            None,
            None,
        ),
    )
    _touch_session(connection, session["id"])
    connection.commit()

    return {
        "token_type": "Cookie",
        "access_token": access_token["token"],
        "refresh_token": refresh_token["token"],
        "csrf_token": session["csrf_token"],
        "access_token_expires_in": settings.auth_access_token_expire_minutes * 60,
        "refresh_token_expires_in": settings.auth_refresh_token_expire_days * 24 * 60 * 60,
        "user": user,
        "remember": session["remember"],
        "session_id": session["id"],
    }


def register_user(
    connection: sqlite3.Connection,
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
        connection,
        username=username,
        email=email,
        password=password,
        display_name=display_name,
        role_codes=["user"],
        is_active=True,
        is_superuser=False,
    )
    session = _create_session(
        connection,
        user_id=user["id"],
        remember=remember,
        client_ip=client_ip,
        user_agent=user_agent,
    )
    result = _issue_token_pair(connection, user, session)
    _issue_audit_log("register", outcome="success", user_id=user["id"], session_id=session["id"])
    return result


def _get_user_login_row(
    connection: sqlite3.Connection,
    login: str,
) -> sqlite3.Row | None:
    normalized_login = login.strip().lower()
    return connection.execute(
        """
        SELECT *
        FROM users
        WHERE username = ? OR email = ?
        LIMIT 1
        """,
        (normalized_login, normalized_login),
    ).fetchone()


def authenticate_user(
    connection: sqlite3.Connection,
    *,
    login: str,
    password: str,
    remember: bool = False,
    client_ip: str | None = None,
    user_agent: str | None = None,
) -> dict[str, Any]:
    user_row = _get_user_login_row(connection, login)
    if user_row is None or not verify_password(password, user_row["password_hash"]):
        register_login_failure(connection, login=login, client_ip=client_ip)
        _issue_audit_log("login", outcome="failure", detail="invalid_credentials")
        raise HTTPException(status_code=401, detail="用户名或密码错误。")

    if not bool(user_row["is_active"]):
        register_login_failure(connection, login=login, client_ip=client_ip)
        _issue_audit_log("login", outcome="failure", user_id=user_row["id"], detail="user_disabled")
        raise HTTPException(status_code=403, detail="当前用户已被禁用。")

    clear_login_failures(connection, login=login, client_ip=client_ip)
    connection.execute(
        """
        UPDATE users
        SET last_login_at = ?, updated_at = ?
        WHERE id = ?
        """,
        (utcnow_iso(), utcnow_iso(), user_row["id"]),
    )
    connection.commit()

    user = build_user_profile(connection, user_row["id"])
    session = _create_session(
        connection,
        user_id=user["id"],
        remember=remember,
        client_ip=client_ip,
        user_agent=user_agent,
    )
    result = _issue_token_pair(connection, user, session)
    _issue_audit_log("login", outcome="success", user_id=user["id"], session_id=session["id"])
    return result


def refresh_user_token(
    connection: sqlite3.Connection,
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

    token_row = connection.execute(
        """
        SELECT *
        FROM refresh_tokens
        WHERE token_jti = ? AND revoked_at IS NULL
        LIMIT 1
        """,
        (claims["jti"],),
    ).fetchone()
    if token_row is None:
        raise HTTPException(status_code=401, detail="刷新令牌不存在或已失效。")

    if _parse_datetime(token_row["expires_at"]) <= datetime.now(UTC):
        raise HTTPException(status_code=401, detail="刷新令牌已过期。")

    session, user = validate_token_session(
        connection,
        claims=claims,
        require_active_user=True,
    )
    if token_row["session_id"] and token_row["session_id"] != session["id"]:
        raise HTTPException(status_code=401, detail="刷新令牌会话不匹配。")

    connection.execute(
        """
        UPDATE refresh_tokens
        SET revoked_at = ?, revoked_reason = ?
        WHERE token_jti = ?
        """,
        (utcnow_iso(), "rotated", claims["jti"]),
    )
    connection.commit()
    result = _issue_token_pair(connection, user, session)
    _issue_audit_log("refresh", outcome="success", user_id=user["id"], session_id=session["id"])
    return result


def revoke_refresh_token(
    connection: sqlite3.Connection,
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
    _revoke_session(connection, session_id=session_id, reason="logout")
    connection.commit()
    _issue_audit_log("logout", outcome="success", user_id=claims.get("sub"), session_id=session_id)
    return {"revoked": True}


def change_password(
    connection: sqlite3.Connection,
    *,
    user_id: str,
    current_password: str,
    new_password: str,
) -> dict[str, Any]:
    ensure_password_strength(new_password)
    user_row = connection.execute(
        "SELECT id, password_hash FROM users WHERE id = ? LIMIT 1",
        (user_id,),
    ).fetchone()
    if user_row is None:
        raise HTTPException(status_code=404, detail="用户不存在。")

    if not verify_password(current_password, user_row["password_hash"]):
        raise HTTPException(status_code=400, detail="当前密码不正确。")

    connection.execute(
        """
        UPDATE users
        SET password_hash = ?,
            token_version = token_version + 1,
            updated_at = ?
        WHERE id = ?
        """,
        (hash_password(new_password), utcnow_iso(), user_id),
    )
    _revoke_user_sessions(connection, user_id=user_id, reason="password_changed")
    connection.commit()
    _issue_audit_log("password_change", outcome="success", user_id=user_id)
    return {"changed": True}
