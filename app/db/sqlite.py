import json
import sqlite3
import uuid
from pathlib import Path
from typing import Generator

from app.auth.constants import (
    DEFAULT_MENU_DEFINITIONS,
    DEFAULT_ROLE_DEFINITIONS,
    DEFAULT_ROLE_MENU_CODES,
    REMOVED_DEFAULT_MENU_CODES,
)
from app.auth.security import hash_password, utcnow_iso
from app.core.config import settings


# ---------------------------------------------------------------------------
# Schema creation is now handled by ORM models (app/models/) via
# Base.metadata.create_all().  The hand-written CREATE TABLE statements
# that used to live here have been removed.
# ---------------------------------------------------------------------------

_LEGACY_SCHEMA_SQL_REMOVED = True  # marker — see git history for the old SQL


def resolve_sqlite_path(database_url: str | None = None) -> Path:
    raw_url = database_url or settings.database_url
    if not raw_url.startswith("sqlite:///"):
        raise ValueError("当前仅支持 sqlite:/// 开头的 SQLite 数据库地址。")

    relative_path = raw_url.removeprefix("sqlite:///")
    path = Path(relative_path)
    if not path.is_absolute():
        path = Path.cwd() / path
    return path.resolve()


def create_connection(database_url: str | None = None) -> sqlite3.Connection:
    database_path = resolve_sqlite_path(database_url)
    database_path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(database_path, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    return connection


def get_db() -> Generator[sqlite3.Connection, None, None]:
    connection = create_connection()
    try:
        yield connection
    finally:
        connection.close()


def initialize_database(database_url: str | None = None) -> None:
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
        _seed_default_roles(connection)
        _seed_default_menus(connection)
        _purge_removed_default_menus(connection)
        _seed_role_menus(connection)
        _seed_initial_admin(connection)
        connection.commit()
    finally:
        connection.close()


def _migrate_schema(connection: sqlite3.Connection) -> None:
    _ensure_column(connection, "motion_assets", "origin", "TEXT NOT NULL DEFAULT 'ai_generated'")
    _ensure_column(connection, "motion_assets", "project_id", "INTEGER")
    _ensure_column(connection, "users", "token_version", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(connection, "users", "avatar_url", "TEXT")
    _ensure_column(connection, "refresh_tokens", "session_id", "TEXT")
    _ensure_column(connection, "jobs", "project_id", "INTEGER")
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_refresh_tokens_session_id ON refresh_tokens(session_id)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_auth_sessions_user_id ON auth_sessions(user_id)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_auth_sessions_revoked_at ON auth_sessions(revoked_at)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_auth_rate_limits_blocked_until ON auth_rate_limits(blocked_until)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_project_messages_project_id ON project_messages(project_id)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_project_messages_created_at ON project_messages(created_at)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_media_assets_owner_user_id ON media_assets(owner_user_id)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_media_assets_asset_type ON media_assets(asset_type)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_jobs_project_id ON jobs(project_id)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_jobs_job_type ON jobs(job_type)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_projects_user_id ON projects(user_id)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_projects_status ON projects(status)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_projects_updated_at ON projects(updated_at)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_project_task_steps_project_id ON project_task_steps(project_id)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_project_task_steps_status ON project_task_steps(status)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_menus_parent_id ON menus(parent_id)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_menus_sort_order ON menus(sort_order)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_menus_visible_enabled ON menus(is_visible, is_enabled)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_role_menus_role_id ON role_menus(role_id)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_role_menus_menu_id ON role_menus(menu_id)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_motion_assets_owner_user_id ON motion_assets(owner_user_id)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_motion_assets_project_id ON motion_assets(project_id)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_motion_assets_source_video_asset_id ON motion_assets(source_video_asset_id)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_motion_assets_action_label ON motion_assets(action_label)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_motion_assets_scene_label ON motion_assets(scene_label)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_motion_assets_review_status ON motion_assets(review_status)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_shot_segments_project_id ON shot_segments(project_id)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_shot_segments_source_video_asset_id ON shot_segments(source_video_asset_id)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_shot_segments_job_id ON shot_segments(job_id)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_shot_segments_start_ms ON shot_segments(project_id, start_ms)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_storyboards_project_id ON storyboards(project_id)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_storyboards_source_video_asset_id ON storyboards(source_video_asset_id)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_storyboard_items_storyboard_id ON storyboard_items(storyboard_id)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_storyboard_items_start_ms ON storyboard_items(storyboard_id, start_ms)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_storyboard_item_segments_shot_segment_id ON storyboard_item_segments(shot_segment_id)"
    )


def _ensure_column(
    connection: sqlite3.Connection,
    table_name: str,
    column_name: str,
    definition: str,
) -> None:
    columns = {
        row["name"]
        for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    if column_name not in columns:
        connection.execute(
            f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}"
        )



def _seed_default_roles(connection: sqlite3.Connection) -> None:
    now = utcnow_iso()
    for definition in DEFAULT_ROLE_DEFINITIONS:
        connection.execute(
            """
            INSERT OR IGNORE INTO roles (
                id, code, name, description, is_system, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                uuid.uuid4().hex,
                definition["code"],
                definition["name"],
                definition["description"],
                definition["is_system"],
                now,
                now,
            ),
        )



def _seed_default_menus(connection: sqlite3.Connection) -> None:
    now = utcnow_iso()
    menu_id_by_code = {
        row["code"]: row["id"]
        for row in connection.execute("SELECT id, code FROM menus").fetchall()
    }

    for definition in DEFAULT_MENU_DEFINITIONS:
        parent_code = definition["parent_code"]
        parent_id = menu_id_by_code.get(parent_code) if parent_code else None
        existing = connection.execute(
            "SELECT id FROM menus WHERE code = ? LIMIT 1",
            (definition["code"],),
        ).fetchone()
        if existing is None:
            menu_id = uuid.uuid4().hex
            connection.execute(
                """
                INSERT INTO menus (
                    id, parent_id, code, title, menu_type, route_path, route_name,
                    redirect_path, icon, component_key, sort_order,
                    is_visible, is_enabled, is_external, open_mode, is_cacheable,
                    is_affix, active_menu_path, badge_text, badge_type, remark,
                    meta_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    menu_id,
                    parent_id,
                    definition["code"],
                    definition["title"],
                    definition["menu_type"],
                    definition["route_path"],
                    definition["route_name"],
                    definition["redirect_path"],
                    definition["icon"],
                    definition["component_key"],
                    definition["sort_order"],
                    definition["is_visible"],
                    definition["is_enabled"],
                    definition["is_external"],
                    definition["open_mode"],
                    definition["is_cacheable"],
                    definition["is_affix"],
                    definition["active_menu_path"],
                    definition["badge_text"],
                    definition["badge_type"],
                    definition["remark"],
                    json.dumps(definition["meta_json"], ensure_ascii=False),
                    now,
                    now,
                ),
            )
            menu_id_by_code[definition["code"]] = menu_id
            continue

        menu_id = existing["id"]
        connection.execute(
            """
            UPDATE menus
            SET parent_id = COALESCE(parent_id, ?),
                updated_at = ?
            WHERE id = ?
            """,
            (parent_id, now, menu_id),
        )
        menu_id_by_code[definition["code"]] = menu_id


def _purge_removed_default_menus(connection: sqlite3.Connection) -> None:
    if not REMOVED_DEFAULT_MENU_CODES:
        return

    placeholders = ", ".join("?" for _ in REMOVED_DEFAULT_MENU_CODES)
    rows = connection.execute(
        f"SELECT id FROM menus WHERE code IN ({placeholders})",
        tuple(REMOVED_DEFAULT_MENU_CODES),
    ).fetchall()
    if not rows:
        return

    menu_ids = [row["id"] for row in rows]
    menu_placeholders = ", ".join("?" for _ in menu_ids)
    connection.execute(
        f"DELETE FROM role_menus WHERE menu_id IN ({menu_placeholders})",
        tuple(menu_ids),
    )
    connection.execute(
        f"DELETE FROM menus WHERE id IN ({menu_placeholders})",
        tuple(menu_ids),
    )


def _seed_role_menus(connection: sqlite3.Connection) -> None:
    now = utcnow_iso()
    role_id_by_code = {
        row["code"]: row["id"]
        for row in connection.execute("SELECT id, code FROM roles").fetchall()
    }
    menu_id_by_code = {
        row["code"]: row["id"]
        for row in connection.execute("SELECT id, code FROM menus").fetchall()
    }

    for role_code, menu_codes in DEFAULT_ROLE_MENU_CODES.items():
        role_id = role_id_by_code.get(role_code)
        if role_id is None:
            continue

        if menu_codes == "*":
            target_codes = tuple(menu_id_by_code.keys())
        else:
            target_codes = menu_codes

        for menu_code in target_codes:
            menu_id = menu_id_by_code.get(menu_code)
            if menu_id is None:
                continue
            connection.execute(
                """
                INSERT OR IGNORE INTO role_menus (
                    role_id, menu_id, created_at
                ) VALUES (?, ?, ?)
                """,
                (role_id, menu_id, now),
            )


def _seed_initial_admin(connection: sqlite3.Connection) -> None:
    now = utcnow_iso()
    admin_row = connection.execute(
        """
        SELECT id
        FROM users
        WHERE username = ? OR email = ?
        LIMIT 1
        """,
        (
            settings.auth_initial_admin_username.strip().lower(),
            settings.auth_initial_admin_email.strip().lower(),
        ),
    ).fetchone()

    if admin_row is None:
        user_id = uuid.uuid4().hex
        connection.execute(
            """
            INSERT INTO users (
                id, username, email, display_name, password_hash,
                is_active, is_superuser, token_version, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                settings.auth_initial_admin_username.strip().lower(),
                settings.auth_initial_admin_email.strip().lower(),
                settings.auth_initial_admin_display_name.strip()
                or settings.auth_initial_admin_username.strip().lower(),
                hash_password(settings.auth_initial_admin_password),
                1,
                1,
                0,
                now,
                now,
            ),
        )
    else:
        user_id = admin_row["id"]
        connection.execute(
            """
            UPDATE users
            SET is_active = 1,
                is_superuser = 1,
                updated_at = ?
            WHERE id = ?
            """,
            (now, user_id),
        )

    super_admin_role = connection.execute(
        "SELECT id FROM roles WHERE code = ? LIMIT 1",
        ("super_admin",),
    ).fetchone()
    if super_admin_role is not None:
        connection.execute(
            """
            INSERT OR IGNORE INTO user_roles (user_id, role_id, created_at)
            VALUES (?, ?, ?)
            """,
            (user_id, super_admin_role["id"], now),
        )
