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


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    email TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    avatar_url TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    is_superuser INTEGER NOT NULL DEFAULT 0,
    token_version INTEGER NOT NULL DEFAULT 0,
    last_login_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS roles (
    id TEXT PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    description TEXT,
    is_system INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);


CREATE TABLE IF NOT EXISTS user_roles (
    user_id TEXT NOT NULL,
    role_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (user_id, role_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE CASCADE
);


CREATE TABLE IF NOT EXISTS menus (
    id TEXT PRIMARY KEY,
    parent_id TEXT,
    code TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    menu_type TEXT NOT NULL DEFAULT 'menu',
    route_path TEXT NOT NULL DEFAULT '',
    route_name TEXT,
    redirect_path TEXT,
    icon TEXT,
    component_key TEXT,

    sort_order INTEGER NOT NULL DEFAULT 0,
    is_visible INTEGER NOT NULL DEFAULT 1,
    is_enabled INTEGER NOT NULL DEFAULT 1,
    is_external INTEGER NOT NULL DEFAULT 0,
    open_mode TEXT NOT NULL DEFAULT 'self',
    is_cacheable INTEGER NOT NULL DEFAULT 0,
    is_affix INTEGER NOT NULL DEFAULT 0,
    active_menu_path TEXT,
    badge_text TEXT,
    badge_type TEXT,
    remark TEXT,
    meta_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (parent_id) REFERENCES menus(id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS role_menus (
    role_id TEXT NOT NULL,
    menu_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (role_id, menu_id),
    FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE CASCADE,
    FOREIGN KEY (menu_id) REFERENCES menus(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS refresh_tokens (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    session_id TEXT,
    token_jti TEXT NOT NULL UNIQUE,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    revoked_at TEXT,
    revoked_reason TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS auth_sessions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    token_version INTEGER NOT NULL DEFAULT 0,
    csrf_token TEXT NOT NULL,
    remember INTEGER NOT NULL DEFAULT 0,
    client_ip TEXT,
    user_agent TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    revoked_at TEXT,
    revoked_reason TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS auth_rate_limits (
    scope_type TEXT NOT NULL,
    scope_key TEXT NOT NULL,
    failure_count INTEGER NOT NULL DEFAULT 0,
    blocked_until TEXT,
    last_attempt_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (scope_type, scope_key)
);

CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    user_id TEXT NOT NULL,
    conversation_type TEXT NOT NULL DEFAULT 'mixed',
    source_video_id TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS conversation_messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    role TEXT NOT NULL,
    message_type TEXT NOT NULL DEFAULT 'text',
    content TEXT NOT NULL DEFAULT '',
    content_json TEXT,
    reply_to_message_id TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE,
    FOREIGN KEY (reply_to_message_id) REFERENCES conversation_messages(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS media_assets (
    id TEXT PRIMARY KEY,
    owner_user_id TEXT,
    asset_type TEXT NOT NULL,
    source_type TEXT NOT NULL,
    file_name TEXT NOT NULL,
    file_path TEXT NOT NULL,
    mime_type TEXT,
    duration_ms INTEGER,
    width INTEGER,
    height INTEGER,
    size_bytes INTEGER,
    sha256 TEXT,
    thumbnail_path TEXT,
    metadata_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (owner_user_id) REFERENCES users(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    conversation_id TEXT,
    trigger_message_id TEXT,
    job_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    progress INTEGER NOT NULL DEFAULT 0,
    input_asset_id TEXT,
    output_asset_id TEXT,
    parent_job_id TEXT,
    source_job_id TEXT,
    error_message TEXT,
    result_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE SET NULL,
    FOREIGN KEY (trigger_message_id) REFERENCES conversation_messages(id) ON DELETE SET NULL,
    FOREIGN KEY (input_asset_id) REFERENCES media_assets(id) ON DELETE SET NULL,
    FOREIGN KEY (output_asset_id) REFERENCES media_assets(id) ON DELETE SET NULL,
    FOREIGN KEY (parent_job_id) REFERENCES jobs(id) ON DELETE SET NULL,
    FOREIGN KEY (source_job_id) REFERENCES jobs(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    conversation_id TEXT,
    title TEXT NOT NULL,
    source_url TEXT NOT NULL DEFAULT '',
    source_platform TEXT NOT NULL DEFAULT 'local',
    workflow_type TEXT NOT NULL DEFAULT 'analysis',
    source_type TEXT NOT NULL DEFAULT 'upload',
    source_name TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'queued',
    media_url TEXT,
    objective TEXT NOT NULL DEFAULT '',
    summary TEXT NOT NULL DEFAULT '',
    source_asset_id TEXT,
    script_overview_json TEXT,
    ecommerce_analysis_json TEXT,
    source_analysis_json TEXT,
    timeline_segments_json TEXT,
    video_generation_json TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE SET NULL,
    FOREIGN KEY (source_asset_id) REFERENCES media_assets(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS project_task_steps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    step_key TEXT NOT NULL,
    title TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending',
    error_detail TEXT,
    output_json TEXT,
    display_order INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    UNIQUE(project_id, step_key)
);

CREATE TABLE IF NOT EXISTS motion_assets (
    id TEXT PRIMARY KEY,
    source_video_asset_id TEXT,
    clip_asset_id TEXT,
    conversation_id TEXT,
    job_id TEXT,
    owner_user_id TEXT,
    start_ms INTEGER NOT NULL,
    end_ms INTEGER NOT NULL,
    action_summary TEXT NOT NULL,
    action_label TEXT,
    entrance_style TEXT,
    emotion_label TEXT,
    temperament_label TEXT,
    scene_label TEXT,
    camera_motion TEXT,
    camera_shot TEXT,
    origin TEXT NOT NULL DEFAULT 'ai_generated',
    review_status TEXT NOT NULL DEFAULT 'draft',
    copyright_risk_level TEXT NOT NULL DEFAULT 'unknown',
    metadata_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (source_video_asset_id) REFERENCES media_assets(id) ON DELETE SET NULL,
    FOREIGN KEY (clip_asset_id) REFERENCES media_assets(id) ON DELETE SET NULL,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE SET NULL,
    FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE SET NULL,
    FOREIGN KEY (owner_user_id) REFERENCES users(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS shot_segments (
    id TEXT PRIMARY KEY,
    project_id INTEGER NOT NULL,
    conversation_id TEXT,
    job_id TEXT,
    source_video_asset_id TEXT NOT NULL,
    owner_user_id TEXT,
    segment_index INTEGER NOT NULL,
    start_ms INTEGER NOT NULL,
    end_ms INTEGER NOT NULL,
    duration_ms INTEGER NOT NULL,
    start_frame INTEGER,
    end_frame INTEGER,
    boundary_in_type TEXT NOT NULL DEFAULT 'cut',
    boundary_out_type TEXT NOT NULL DEFAULT 'cut',
    detector_name TEXT NOT NULL DEFAULT 'pyscenedetect',
    detector_version TEXT,
    detector_config_json TEXT,
    keyframe_asset_ids_json TEXT,
    transcript_text TEXT NOT NULL DEFAULT '',
    ocr_text TEXT NOT NULL DEFAULT '',
    visual_summary TEXT,
    title TEXT,
    shot_type_code TEXT,
    camera_angle_code TEXT,
    camera_motion_code TEXT,
    scene_label TEXT,
    confidence REAL,
    metadata_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE SET NULL,
    FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE SET NULL,
    FOREIGN KEY (source_video_asset_id) REFERENCES media_assets(id) ON DELETE CASCADE,
    FOREIGN KEY (owner_user_id) REFERENCES users(id) ON DELETE SET NULL,
    UNIQUE(project_id, segment_index)
);

CREATE TABLE IF NOT EXISTS storyboards (
    id TEXT PRIMARY KEY,
    project_id INTEGER NOT NULL,
    conversation_id TEXT,
    job_id TEXT,
    source_video_asset_id TEXT NOT NULL,
    owner_user_id TEXT,
    version_no INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'generated',
    generator_provider TEXT,
    generator_model TEXT,
    prompt_version TEXT,
    summary TEXT,
    item_count INTEGER NOT NULL DEFAULT 0,
    metadata_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE SET NULL,
    FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE SET NULL,
    FOREIGN KEY (source_video_asset_id) REFERENCES media_assets(id) ON DELETE CASCADE,
    FOREIGN KEY (owner_user_id) REFERENCES users(id) ON DELETE SET NULL,
    UNIQUE(project_id, version_no)
);

CREATE TABLE IF NOT EXISTS storyboard_items (
    id TEXT PRIMARY KEY,
    storyboard_id TEXT NOT NULL,
    item_index INTEGER NOT NULL,
    title TEXT NOT NULL,
    start_ms INTEGER NOT NULL,
    end_ms INTEGER NOT NULL,
    duration_ms INTEGER NOT NULL,
    shot_type_code TEXT,
    camera_angle_code TEXT,
    camera_motion_code TEXT,
    visual_description TEXT NOT NULL,
    transcript_excerpt TEXT NOT NULL DEFAULT '',
    ocr_excerpt TEXT NOT NULL DEFAULT '',
    confidence REAL,
    review_status TEXT NOT NULL DEFAULT 'auto_generated',
    metadata_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (storyboard_id) REFERENCES storyboards(id) ON DELETE CASCADE,
    UNIQUE(storyboard_id, item_index)
);

CREATE TABLE IF NOT EXISTS storyboard_item_segments (
    storyboard_item_id TEXT NOT NULL,
    shot_segment_id TEXT NOT NULL,
    display_order INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (storyboard_item_id, shot_segment_id),
    FOREIGN KEY (storyboard_item_id) REFERENCES storyboard_items(id) ON DELETE CASCADE,
    FOREIGN KEY (shot_segment_id) REFERENCES shot_segments(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS system_settings (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    updated_by_user_id TEXT,
    FOREIGN KEY (updated_by_user_id) REFERENCES users(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS task_queue (
    id TEXT PRIMARY KEY,
    task_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    payload_json TEXT,
    max_retries INTEGER NOT NULL DEFAULT 0,
    retry_count INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    started_at TEXT,
    finished_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_task_queue_status_created
    ON task_queue (status, created_at);

CREATE INDEX IF NOT EXISTS idx_user_roles_user_id ON user_roles(user_id);
CREATE INDEX IF NOT EXISTS idx_user_roles_role_id ON user_roles(role_id);

CREATE INDEX IF NOT EXISTS idx_menus_parent_id ON menus(parent_id);
CREATE INDEX IF NOT EXISTS idx_menus_sort_order ON menus(sort_order);

CREATE INDEX IF NOT EXISTS idx_menus_visible_enabled ON menus(is_visible, is_enabled);
CREATE INDEX IF NOT EXISTS idx_role_menus_role_id ON role_menus(role_id);
CREATE INDEX IF NOT EXISTS idx_role_menus_menu_id ON role_menus(menu_id);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user_id ON refresh_tokens(user_id);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_token_jti ON refresh_tokens(token_jti);
CREATE INDEX IF NOT EXISTS idx_conversations_user_id ON conversations(user_id);
CREATE INDEX IF NOT EXISTS idx_conversations_updated_at ON conversations(updated_at);
CREATE INDEX IF NOT EXISTS idx_conversation_messages_conversation_id ON conversation_messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_conversation_messages_created_at ON conversation_messages(created_at);
CREATE INDEX IF NOT EXISTS idx_media_assets_owner_user_id ON media_assets(owner_user_id);
CREATE INDEX IF NOT EXISTS idx_media_assets_asset_type ON media_assets(asset_type);
CREATE INDEX IF NOT EXISTS idx_jobs_conversation_id ON jobs(conversation_id);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_job_type ON jobs(job_type);
CREATE INDEX IF NOT EXISTS idx_projects_user_id ON projects(user_id);
CREATE INDEX IF NOT EXISTS idx_projects_conversation_id ON projects(conversation_id);
CREATE INDEX IF NOT EXISTS idx_projects_status ON projects(status);
CREATE INDEX IF NOT EXISTS idx_projects_updated_at ON projects(updated_at);
CREATE INDEX IF NOT EXISTS idx_project_task_steps_project_id ON project_task_steps(project_id);
CREATE INDEX IF NOT EXISTS idx_project_task_steps_status ON project_task_steps(status);
CREATE INDEX IF NOT EXISTS idx_motion_assets_owner_user_id ON motion_assets(owner_user_id);
CREATE INDEX IF NOT EXISTS idx_motion_assets_source_video_asset_id ON motion_assets(source_video_asset_id);
CREATE INDEX IF NOT EXISTS idx_motion_assets_action_label ON motion_assets(action_label);
CREATE INDEX IF NOT EXISTS idx_motion_assets_scene_label ON motion_assets(scene_label);
CREATE INDEX IF NOT EXISTS idx_motion_assets_review_status ON motion_assets(review_status);
CREATE INDEX IF NOT EXISTS idx_shot_segments_project_id ON shot_segments(project_id);
CREATE INDEX IF NOT EXISTS idx_shot_segments_source_video_asset_id ON shot_segments(source_video_asset_id);
CREATE INDEX IF NOT EXISTS idx_shot_segments_job_id ON shot_segments(job_id);
CREATE INDEX IF NOT EXISTS idx_shot_segments_start_ms ON shot_segments(project_id, start_ms);
CREATE INDEX IF NOT EXISTS idx_storyboards_project_id ON storyboards(project_id);
CREATE INDEX IF NOT EXISTS idx_storyboards_source_video_asset_id ON storyboards(source_video_asset_id);
CREATE INDEX IF NOT EXISTS idx_storyboard_items_storyboard_id ON storyboard_items(storyboard_id);
CREATE INDEX IF NOT EXISTS idx_storyboard_items_start_ms ON storyboard_items(storyboard_id, start_ms);
CREATE INDEX IF NOT EXISTS idx_storyboard_item_segments_shot_segment_id ON storyboard_item_segments(shot_segment_id);
"""


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
    connection = create_connection(database_url)
    try:
        connection.executescript(SCHEMA_SQL)
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
    _ensure_column(connection, "users", "token_version", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(connection, "users", "avatar_url", "TEXT")
    _ensure_column(connection, "refresh_tokens", "session_id", "TEXT")
    _ensure_column(connection, "projects", "conversation_id", "TEXT")
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
        "CREATE INDEX IF NOT EXISTS idx_conversations_user_id ON conversations(user_id)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_conversations_updated_at ON conversations(updated_at)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_conversation_messages_conversation_id ON conversation_messages(conversation_id)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_conversation_messages_created_at ON conversation_messages(created_at)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_media_assets_owner_user_id ON media_assets(owner_user_id)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_media_assets_asset_type ON media_assets(asset_type)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_jobs_conversation_id ON jobs(conversation_id)"
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
        "CREATE INDEX IF NOT EXISTS idx_projects_conversation_id ON projects(conversation_id)"
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
