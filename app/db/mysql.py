"""
MySQL database module — drop-in replacement for the former SQLite backend.

Public surface kept identical so the rest of the codebase needs only
import-path changes:

    create_connection()  -> returns a MySQLConnection wrapper
    get_db()             -> FastAPI dependency (generator)
    initialize_database()
"""

import json
import uuid
from typing import Any, Generator
from urllib.parse import unquote, urlparse

import pymysql
import pymysql.cursors
from sqlalchemy import delete as sa_delete, select
from sqlalchemy.orm import Session

from app.auth.constants import (
    DEFAULT_MENU_DEFINITIONS,
    DEFAULT_ROLE_DEFINITIONS,
    DEFAULT_ROLE_MENU_CODES,
    REMOVED_DEFAULT_MENU_CODES,
)
from app.auth.security import hash_password, normalize_timestamp_ms, utcnow_ms
from app.core.config import settings
from app.models.auth import Menu, Role, RoleMenu, User, UserRole


# ---------------------------------------------------------------------------
# Schema creation is now handled by ORM models (app/models/) via
# Base.metadata.create_all().  The hand-written CREATE TABLE statements
# that used to live here have been removed.
# ---------------------------------------------------------------------------


TIMESTAMP_COLUMN_DEFINITIONS: dict[str, dict[str, str]] = {
    "users": {
        "last_login_at": "BIGINT NULL",
        "created_at": "BIGINT NOT NULL",
        "updated_at": "BIGINT NOT NULL",
    },
    "roles": {
        "created_at": "BIGINT NOT NULL",
        "updated_at": "BIGINT NOT NULL",
    },
    "user_roles": {
        "created_at": "BIGINT NOT NULL",
    },
    "menus": {
        "created_at": "BIGINT NOT NULL",
        "updated_at": "BIGINT NOT NULL",
    },
    "role_menus": {
        "created_at": "BIGINT NOT NULL",
    },
    "refresh_tokens": {
        "expires_at": "BIGINT NOT NULL",
        "created_at": "BIGINT NOT NULL",
        "revoked_at": "BIGINT NULL",
    },
    "auth_sessions": {
        "created_at": "BIGINT NOT NULL",
        "updated_at": "BIGINT NOT NULL",
        "last_seen_at": "BIGINT NOT NULL",
        "revoked_at": "BIGINT NULL",
    },
    "auth_rate_limits": {
        "blocked_until": "BIGINT NULL",
        "last_attempt_at": "BIGINT NOT NULL",
        "created_at": "BIGINT NOT NULL",
        "updated_at": "BIGINT NOT NULL",
    },
    "project_messages": {
        "created_at": "BIGINT NOT NULL",
    },
    "media_assets": {
        "created_at": "BIGINT NOT NULL",
        "updated_at": "BIGINT NOT NULL",
    },
    "jobs": {
        "created_at": "BIGINT NOT NULL",
        "updated_at": "BIGINT NOT NULL",
        "started_at": "BIGINT NULL",
        "finished_at": "BIGINT NULL",
    },
    "motion_assets": {
        "created_at": "BIGINT NOT NULL",
        "updated_at": "BIGINT NOT NULL",
    },
    "system_settings": {
        "updated_at": "BIGINT NOT NULL",
    },
    "projects": {
        "created_at": "BIGINT NOT NULL",
        "updated_at": "BIGINT NOT NULL",
    },
    "project_task_steps": {
        "created_at": "BIGINT NOT NULL",
        "updated_at": "BIGINT NOT NULL",
    },
    "shot_segments": {
        "created_at": "BIGINT NOT NULL",
        "updated_at": "BIGINT NOT NULL",
    },
    "storyboards": {
        "created_at": "BIGINT NOT NULL",
        "updated_at": "BIGINT NOT NULL",
    },
    "storyboard_items": {
        "created_at": "BIGINT NOT NULL",
        "updated_at": "BIGINT NOT NULL",
    },
    "task_queue": {
        "started_at": "BIGINT NULL",
        "finished_at": "BIGINT NULL",
        "created_at": "BIGINT NOT NULL",
        "updated_at": "BIGINT NOT NULL",
    },
}




INTEGER_LIKE_DATA_TYPES = {
    "tinyint",
    "smallint",
    "mediumint",
    "int",
    "integer",
    "bigint",
    "decimal",
    "numeric",
}

LEGACY_MENU_ACCESS_COLUMN = "_".join(("per", "mission_code"))
LEGACY_MENU_ACCESS_INDEX = "".join(("idx_menus_", "per", "mission_code"))
LEGACY_ROLE_MENU_ACCESS_TABLE = "".join(("role_", "per", "missions"))
LEGACY_MENU_ACCESS_TABLE = "".join(("per", "missions"))


# ---------------------------------------------------------------------------
# MySQL connection wrapper — mimics sqlite3.Connection API surface
# ---------------------------------------------------------------------------


class CursorResult:
    """Wraps a pymysql cursor to provide fetchone/fetchall + rowcount."""

    __slots__ = ("_cursor",)

    def __init__(self, cursor: pymysql.cursors.DictCursor):
        self._cursor = cursor

    def fetchone(self) -> dict[str, Any] | None:
        return self._cursor.fetchone()

    def fetchall(self) -> list[dict[str, Any]]:
        return self._cursor.fetchall()

    @property
    def lastrowid(self) -> int | None:
        return self._cursor.lastrowid

    @property
    def rowcount(self) -> int:
        return self._cursor.rowcount


class MySQLConnection:
    """
    Thin wrapper around pymysql.Connection that exposes the same
    execute / commit / close API that the codebase used with sqlite3.

    Rows are returned as dicts (via DictCursor) so ``row["column"]``
    access works identically.
    """

    __slots__ = ("_conn",)

    def __init__(self, conn: pymysql.connections.Connection):
        self._conn = conn

    # -- main API used everywhere in the codebase --

    def execute(self, sql: str, params: tuple | list | None = None) -> CursorResult:
        cursor = self._conn.cursor()
        cursor.execute(sql, params)
        return CursorResult(cursor)

    def commit(self) -> None:
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()


# ---------------------------------------------------------------------------
# Connection factory
# ---------------------------------------------------------------------------

def _parse_database_url(database_url: str | None = None) -> tuple[dict[str, Any], str]:
    """Parse a mysql:// or mysql+pymysql:// URL into server kwargs + database."""
    raw_url = database_url or settings.database_url

    # Normalise scheme for urlparse
    url_for_parse = raw_url
    if url_for_parse.startswith("mysql+pymysql://"):
        url_for_parse = "mysql://" + url_for_parse[len("mysql+pymysql://"):]
    elif url_for_parse.startswith("mysql://"):
        pass
    else:
        raise ValueError(
            "database_url 必须以 mysql:// 或 mysql+pymysql:// 开头。"
            f"当前值: {raw_url}"
        )

    parsed = urlparse(url_for_parse)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 3306
    user = parsed.username or "root"
    password = parsed.password or ""
    database = unquote((parsed.path or "").lstrip("/"))

    if not database:
        raise ValueError("database_url 必须指定数据库名称。")

    return {
        "host": host,
        "port": port,
        "user": user,
        "password": password,
        "charset": "utf8mb4",
        "cursorclass": pymysql.cursors.DictCursor,
        "autocommit": False,
    }, database


def _quote_identifier(identifier: str) -> str:
    return f"`{identifier.replace('`', '``')}`"


def _ensure_database_exists(database_url: str | None = None) -> None:
    connection_kwargs, database = _parse_database_url(database_url)
    admin_connection = pymysql.connect(**connection_kwargs)
    try:
        cursor = admin_connection.cursor()
        cursor.execute(
            "CREATE DATABASE IF NOT EXISTS "
            f"{_quote_identifier(database)} "
            "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
        )
        admin_connection.commit()
    finally:
        admin_connection.close()


def create_connection(database_url: str | None = None) -> MySQLConnection:
    kwargs, database = _parse_database_url(database_url)
    kwargs["database"] = database
    conn = pymysql.connect(**kwargs)
    return MySQLConnection(conn)


def get_db() -> Generator[MySQLConnection, None, None]:
    connection = create_connection()
    try:
        yield connection
    finally:
        connection.close()


# ---------------------------------------------------------------------------
# Database initialisation
# ---------------------------------------------------------------------------

def initialize_database(database_url: str | None = None) -> None:
    _ensure_database_exists(database_url)

    # --- Schema creation via ORM metadata (single source of truth) ---
    from app.db.base import Base
    from app.db.engine import get_engine
    import app.models  # noqa: F401 — register all models with Base.metadata

    engine = get_engine()
    Base.metadata.create_all(engine)

    # --- Legacy migrations for existing databases ---
    connection = create_connection(database_url)
    try:
        _migrate_schema(connection)
        connection.commit()
    finally:
        connection.close()

    # --- Seed reference data via ORM session ---
    from app.db.session import get_db_session
    session_gen = get_db_session()
    session = next(session_gen)
    try:
        _seed_default_roles(session)
        _seed_default_menus(session)
        _purge_removed_default_menus(session)
        _seed_role_menus(session)
        _seed_initial_admin(session)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Schema migration helpers
# ---------------------------------------------------------------------------

def _migrate_schema(connection: MySQLConnection) -> None:
    additional_columns = (
        ("motion_assets", "origin", "VARCHAR(64) NOT NULL DEFAULT 'ai_generated'"),
        ("motion_assets", "project_id", "INT"),
        ("users", "token_version", "INT NOT NULL DEFAULT 0"),
        ("users", "avatar_url", "TEXT"),
        ("refresh_tokens", "session_id", "VARCHAR(32)"),
        ("jobs", "project_id", "INT"),
        ("projects", "source_type", "VARCHAR(32) NOT NULL DEFAULT 'upload'"),
        ("projects", "generated_media_url", "TEXT"),
        ("system_settings", "updated_by_user_id", "VARCHAR(32)"),
        ("media_assets", "sha256", "VARCHAR(255)"),
        ("shot_segments", "owner_user_id", "VARCHAR(32)"),
        ("shot_segments", "scene_label", "VARCHAR(128)"),
        ("shot_segments", "confidence", "FLOAT"),
        ("storyboards", "job_id", "VARCHAR(32)"),
        ("storyboards", "owner_user_id", "VARCHAR(32)"),
        ("storyboards", "generator_provider", "VARCHAR(64)"),
        ("storyboards", "generator_model", "VARCHAR(128)"),
        ("storyboards", "prompt_version", "VARCHAR(64)"),
        ("storyboards", "item_count", "INT NOT NULL DEFAULT 0"),
        ("storyboard_items", "title", "VARCHAR(255) NOT NULL DEFAULT ''"),
        ("storyboard_items", "shot_type_code", "VARCHAR(64)"),
        ("storyboard_items", "camera_angle_code", "VARCHAR(64)"),
        ("storyboard_items", "camera_motion_code", "VARCHAR(64)"),
        ("storyboard_items", "transcript_excerpt", "LONGTEXT"),
        ("storyboard_items", "ocr_excerpt", "LONGTEXT"),
        ("storyboard_items", "confidence", "FLOAT"),
        ("storyboard_items", "review_status", "VARCHAR(32) NOT NULL DEFAULT 'auto_generated'"),
        ("storyboard_item_segments", "display_order", "INT NOT NULL DEFAULT 1"),
    )
    for table_name, column_name, definition in additional_columns:
        _ensure_column(connection, table_name, column_name, definition)
    _drop_legacy_menu_access_schema(connection)
    _ensure_timestamp_column_types(connection)
    _backfill_project_media_links(connection)
    connection.commit()


def _ensure_column(
    connection: MySQLConnection,
    table_name: str,
    column_name: str,
    definition: str,
) -> None:
    """Add a column if it does not already exist (MySQL INFORMATION_SCHEMA)."""
    row = connection.execute(
        """
        SELECT COLUMN_NAME
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = %s
          AND COLUMN_NAME = %s
        LIMIT 1
        """,
        (table_name, column_name),
    ).fetchone()
    if row is None:
        connection.execute(
            f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}"
        )


def _drop_index_if_exists(
    connection: MySQLConnection,
    table_name: str,
    index_name: str,
) -> None:
    row = connection.execute(
        """
        SELECT INDEX_NAME
        FROM INFORMATION_SCHEMA.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = %s
          AND INDEX_NAME = %s
        LIMIT 1
        """,
        (table_name, index_name),
    ).fetchone()
    if row is not None:
        connection.execute(
            f"ALTER TABLE {_quote_identifier(table_name)} "
            f"DROP INDEX {_quote_identifier(index_name)}"
        )


def _drop_table_if_exists(
    connection: MySQLConnection,
    table_name: str,
) -> None:
    connection.execute(f"DROP TABLE IF EXISTS {_quote_identifier(table_name)}")


def _drop_foreign_keys_for_column(
    connection: MySQLConnection,
    table_name: str,
    column_name: str,
) -> None:
    rows = connection.execute(
        """
        SELECT CONSTRAINT_NAME
        FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = %s
          AND COLUMN_NAME = %s
          AND REFERENCED_TABLE_NAME IS NOT NULL
        """,
        (table_name, column_name),
    ).fetchall()
    for row in rows:
        constraint_name = str(row["CONSTRAINT_NAME"])
        connection.execute(
            f"ALTER TABLE {_quote_identifier(table_name)} "
            f"DROP FOREIGN KEY {_quote_identifier(constraint_name)}"
        )


def _drop_column_if_exists(
    connection: MySQLConnection,
    table_name: str,
    column_name: str,
) -> None:
    row = connection.execute(
        """
        SELECT COLUMN_NAME
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = %s
          AND COLUMN_NAME = %s
        LIMIT 1
        """,
        (table_name, column_name),
    ).fetchone()
    if row is not None:
        connection.execute(
            f"ALTER TABLE {_quote_identifier(table_name)} "
            f"DROP COLUMN {_quote_identifier(column_name)}"
        )


def _drop_legacy_menu_access_schema(connection: MySQLConnection) -> None:
    connection.execute("SET FOREIGN_KEY_CHECKS = 0")
    connection.commit()
    try:
        _drop_foreign_keys_for_column(connection, "menus", LEGACY_MENU_ACCESS_COLUMN)
        _drop_index_if_exists(connection, "menus", LEGACY_MENU_ACCESS_INDEX)
        _drop_column_if_exists(connection, "menus", LEGACY_MENU_ACCESS_COLUMN)
        _drop_table_if_exists(connection, LEGACY_ROLE_MENU_ACCESS_TABLE)
        _drop_table_if_exists(connection, LEGACY_MENU_ACCESS_TABLE)
        connection.commit()
    finally:
        connection.execute("SET FOREIGN_KEY_CHECKS = 1")
        connection.commit()


def _get_column_data_type(
    connection: MySQLConnection,
    table_name: str,
    column_name: str,
) -> str | None:
    row = connection.execute(
        """
        SELECT DATA_TYPE
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = %s
          AND COLUMN_NAME = %s
        LIMIT 1
        """,
        (table_name, column_name),
    ).fetchone()
    if row is None:
        return None
    data_type = row.get("DATA_TYPE")
    return str(data_type).lower() if data_type is not None else None


def _get_primary_key_columns(
    connection: MySQLConnection,
    table_name: str,
) -> list[str]:
    rows = connection.execute(
        """
        SELECT COLUMN_NAME
        FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = %s
          AND CONSTRAINT_NAME = 'PRIMARY'
        ORDER BY ORDINAL_POSITION ASC
        """,
        (table_name,),
    ).fetchall()
    return [str(row["COLUMN_NAME"]) for row in rows]


def _convert_timestamp_column_values(
    connection: MySQLConnection,
    table_name: str,
    column_name: str,
    primary_key_columns: list[str],
) -> int:
    if not primary_key_columns:
        return 0

    select_columns = ", ".join(
        f"{_quote_identifier(column)}" for column in (*primary_key_columns, column_name)
    )
    where_sql = " AND ".join(
        f"{_quote_identifier(column)} = %s" for column in primary_key_columns
    )
    rows = connection.execute(
        f"""
        SELECT {select_columns}
        FROM {_quote_identifier(table_name)}
        WHERE {_quote_identifier(column_name)} IS NOT NULL
        """
    ).fetchall()
    changed = 0
    for row in rows:
        raw_value = row[column_name]
        converted_value = normalize_timestamp_ms(raw_value)
        if converted_value is None:
            continue
        if isinstance(raw_value, int) and raw_value == converted_value:
            continue
        if isinstance(raw_value, str) and raw_value.isdigit() and int(raw_value) == converted_value:
            continue

        params: list[Any] = [converted_value]
        params.extend(row[column] for column in primary_key_columns)
        connection.execute(
            f"""
            UPDATE {_quote_identifier(table_name)}
            SET {_quote_identifier(column_name)} = %s
            WHERE {where_sql}
            """,
            tuple(params),
        )
        changed += 1

    if changed:
        connection.commit()
    return changed


def _migrate_timestamp_column_to_bigint(
    connection: MySQLConnection,
    table_name: str,
    column_name: str,
    definition: str,
) -> None:
    data_type = _get_column_data_type(connection, table_name, column_name)
    if data_type is None:
        return

    primary_key_columns = _get_primary_key_columns(connection, table_name)
    if data_type == "bigint":
        _convert_timestamp_column_values(connection, table_name, column_name, primary_key_columns)
        connection.execute(
            f"""
            ALTER TABLE {_quote_identifier(table_name)}
            MODIFY COLUMN {_quote_identifier(column_name)} {definition}
            """
        )
        connection.commit()
        return

    if data_type in INTEGER_LIKE_DATA_TYPES:
        connection.execute(
            f"""
            ALTER TABLE {_quote_identifier(table_name)}
            MODIFY COLUMN {_quote_identifier(column_name)} {definition}
            """
        )
        connection.commit()
        _convert_timestamp_column_values(connection, table_name, column_name, primary_key_columns)
        return

    temp_column = f"__tmp_{column_name}_ms"
    temp_quoted = _quote_identifier(temp_column)
    table_quoted = _quote_identifier(table_name)
    column_quoted = _quote_identifier(column_name)
    existing_temp = _get_column_data_type(connection, table_name, temp_column)
    if existing_temp is not None:
        connection.execute(f"ALTER TABLE {table_quoted} DROP COLUMN {temp_quoted}")
        connection.commit()

    connection.execute(
        f"ALTER TABLE {table_quoted} ADD COLUMN {temp_quoted} BIGINT NULL"
    )
    connection.commit()

    select_columns = ", ".join(
        f"{_quote_identifier(column)}" for column in (*primary_key_columns, column_name)
    )
    where_sql = " AND ".join(
        f"{_quote_identifier(column)} = %s" for column in primary_key_columns
    )
    rows = connection.execute(
        f"""
        SELECT {select_columns}
        FROM {table_quoted}
        WHERE {column_quoted} IS NOT NULL
        """
    ).fetchall()
    for row in rows:
        converted_value = normalize_timestamp_ms(row[column_name])
        if converted_value is None:
            continue
        params: list[Any] = [converted_value]
        params.extend(row[column] for column in primary_key_columns)
        connection.execute(
            f"""
            UPDATE {table_quoted}
            SET {temp_quoted} = %s
            WHERE {where_sql}
            """,
            tuple(params),
        )
    connection.commit()

    connection.execute(
        f"""
        ALTER TABLE {table_quoted}
        DROP COLUMN {column_quoted},
        CHANGE COLUMN {temp_quoted} {column_quoted} {definition}
        """
    )
    connection.commit()


def _ensure_timestamp_column_types(connection: MySQLConnection) -> None:
    connection.execute("SET FOREIGN_KEY_CHECKS = 0")
    connection.commit()
    try:
        for table_name, columns in TIMESTAMP_COLUMN_DEFINITIONS.items():
            for column_name, definition in columns.items():
                _migrate_timestamp_column_to_bigint(
                    connection,
                    table_name,
                    column_name,
                    definition,
                )
    finally:
        connection.execute("SET FOREIGN_KEY_CHECKS = 1")
        connection.commit()





def _load_json_value(raw_value: Any) -> dict[str, Any]:
    if isinstance(raw_value, dict):
        return raw_value
    if not raw_value:
        return {}
    try:
        loaded = json.loads(raw_value)
    except (TypeError, ValueError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _extract_public_url_from_metadata(raw_value: Any) -> str | None:
    metadata = _load_json_value(raw_value)
    public_url = metadata.get("public_url")
    if public_url is None:
        return None
    normalized = str(public_url).strip()
    return normalized or None


def _backfill_project_media_links(connection: MySQLConnection) -> None:
    rows = connection.execute(
        """
        SELECT
            p.id,
            p.media_url,
            p.generated_media_url,
            p.video_generation_json,
            source_asset.metadata_json AS source_asset_metadata_json
        FROM projects AS p
        LEFT JOIN media_assets AS source_asset
            ON source_asset.id = p.source_asset_id
        """
    ).fetchall()

    for row in rows:
        project_id = row["id"]
        current_media_url = str(row.get("media_url") or "").strip()
        current_generated_media_url = str(row.get("generated_media_url") or "").strip()
        source_media_url = _extract_public_url_from_metadata(row.get("source_asset_metadata_json"))
        video_generation = _load_json_value(row.get("video_generation_json"))
        generated_asset_url = str(video_generation.get("asset_url") or "").strip()

        if not generated_asset_url and current_media_url.startswith("/uploads/generated/"):
            generated_asset_url = current_media_url

        updates: dict[str, str] = {}
        if generated_asset_url and current_generated_media_url != generated_asset_url:
            updates["generated_media_url"] = generated_asset_url

        should_restore_source_media = bool(source_media_url) and (
            not current_media_url
            or current_media_url == generated_asset_url
            or current_media_url.startswith("/uploads/generated/")
        )
        if should_restore_source_media and current_media_url != source_media_url:
            updates["media_url"] = source_media_url

        if not updates:
            continue

        assignments = ", ".join(f"{column_name} = %s" for column_name in updates)
        connection.execute(
            f"UPDATE projects SET {assignments} WHERE id = %s",
            (*updates.values(), project_id),
        )

# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------

def _seed_default_roles(session: Session) -> None:
    now = utcnow_ms()
    for definition in DEFAULT_ROLE_DEFINITIONS:
        existing = session.scalar(select(Role).where(Role.code == definition["code"]))
        if existing is None:
            session.add(Role(
                id=uuid.uuid4().hex,
                code=definition["code"],
                name=definition["name"],
                description=definition["description"],
                is_system=bool(definition["is_system"]),
                created_at=now,
                updated_at=now,
            ))
    session.flush()


def _seed_default_menus(session: Session) -> None:
    now = utcnow_ms()
    menu_id_by_code = {
        m.code: m.id
        for m in session.scalars(select(Menu)).all()
    }

    for definition in DEFAULT_MENU_DEFINITIONS:
        parent_code = definition["parent_code"]
        parent_id = menu_id_by_code.get(parent_code) if parent_code else None
        existing = session.scalar(select(Menu).where(Menu.code == definition["code"]))
        if existing is None:
            menu_id = uuid.uuid4().hex
            session.add(Menu(
                id=menu_id,
                parent_id=parent_id,
                code=definition["code"],
                title=definition["title"],
                menu_type=definition["menu_type"],
                route_path=definition["route_path"],
                route_name=definition["route_name"],
                redirect_path=definition["redirect_path"],
                icon=definition["icon"],
                component_key=definition["component_key"],
                sort_order=definition["sort_order"],
                is_visible=bool(definition["is_visible"]),
                is_enabled=bool(definition["is_enabled"]),
                is_external=bool(definition["is_external"]),
                open_mode=definition["open_mode"],
                is_cacheable=bool(definition["is_cacheable"]),
                is_affix=bool(definition["is_affix"]),
                active_menu_path=definition["active_menu_path"],
                badge_text=definition["badge_text"],
                badge_type=definition["badge_type"],
                remark=definition["remark"],
                meta_json=json.dumps(definition["meta_json"], ensure_ascii=False),
                created_at=now,
                updated_at=now,
            ))
            session.flush()
            menu_id_by_code[definition["code"]] = menu_id
        else:
            menu_id = existing.id
            if existing.parent_id is None and parent_id is not None:
                existing.parent_id = parent_id
            existing.title = definition["title"]
            existing.icon = definition["icon"]
            existing.route_path = definition["route_path"]
            existing.updated_at = now
            menu_id_by_code[definition["code"]] = menu_id


def _purge_removed_default_menus(session: Session) -> None:
    if not REMOVED_DEFAULT_MENU_CODES:
        return
    menus = session.scalars(
        select(Menu).where(Menu.code.in_(REMOVED_DEFAULT_MENU_CODES))
    ).all()
    if not menus:
        return
    menu_ids = [m.id for m in menus]
    session.execute(sa_delete(RoleMenu).where(RoleMenu.menu_id.in_(menu_ids)))
    session.execute(sa_delete(Menu).where(Menu.id.in_(menu_ids)))
    session.flush()


def _seed_role_menus(session: Session) -> None:
    now = utcnow_ms()
    role_id_by_code = {
        r.code: r.id
        for r in session.scalars(select(Role)).all()
    }
    menu_id_by_code = {
        m.code: m.id
        for m in session.scalars(select(Menu)).all()
    }

    for role_code, menu_codes in DEFAULT_ROLE_MENU_CODES.items():
        role_id = role_id_by_code.get(role_code)
        if role_id is None:
            continue

        target_codes = list(menu_id_by_code.keys()) if menu_codes == "*" else menu_codes
        for menu_code in target_codes:
            menu_id = menu_id_by_code.get(menu_code)
            if menu_id is None:
                continue
            existing = session.get(RoleMenu, {"role_id": role_id, "menu_id": menu_id})
            if existing is None:
                session.add(RoleMenu(role_id=role_id, menu_id=menu_id, created_at=now))
    session.flush()


def _seed_initial_admin(session: Session) -> None:
    now = utcnow_ms()
    admin_username = settings.auth_initial_admin_username.strip().lower()
    admin_email = settings.auth_initial_admin_email.strip().lower()

    admin = session.scalar(
        select(User).where(
            (User.username == admin_username) | (User.email == admin_email)
        )
    )
    if admin is None:
        user_id = uuid.uuid4().hex
        session.add(User(
            id=user_id,
            username=admin_username,
            email=admin_email,
            display_name=(
                settings.auth_initial_admin_display_name.strip() or admin_username
            ),
            password_hash=hash_password(settings.auth_initial_admin_password),
            is_active=True,
            is_superuser=True,
            token_version=0,
            created_at=now,
            updated_at=now,
        ))
        session.flush()
    else:
        user_id = admin.id
        admin.is_active = True
        admin.is_superuser = True
        admin.updated_at = now
        session.flush()

    super_admin_role = session.scalar(select(Role).where(Role.code == "super_admin"))
    if super_admin_role is not None:
        existing_ur = session.get(UserRole, {"user_id": user_id, "role_id": super_admin_role.id})
        if existing_ur is None:
            session.add(UserRole(user_id=user_id, role_id=super_admin_role.id, created_at=now))
    session.flush()
