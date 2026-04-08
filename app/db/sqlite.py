import sqlite3
import uuid
from pathlib import Path
from typing import Generator

from app.auth.constants import DEFAULT_PERMISSION_DEFINITIONS, DEFAULT_ROLE_DEFINITIONS
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

CREATE TABLE IF NOT EXISTS permissions (
    id TEXT PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    group_name TEXT NOT NULL,
    description TEXT,
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

CREATE TABLE IF NOT EXISTS role_permissions (
    role_id TEXT NOT NULL,
    permission_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (role_id, permission_id),
    FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE CASCADE,
    FOREIGN KEY (permission_id) REFERENCES permissions(id) ON DELETE CASCADE
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

CREATE TABLE IF NOT EXISTS system_settings (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    updated_by_user_id TEXT,
    FOREIGN KEY (updated_by_user_id) REFERENCES users(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_user_roles_user_id ON user_roles(user_id);
CREATE INDEX IF NOT EXISTS idx_user_roles_role_id ON user_roles(role_id);
CREATE INDEX IF NOT EXISTS idx_role_permissions_role_id ON role_permissions(role_id);
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
        _seed_default_permissions(connection)
        _seed_default_roles(connection)
        _seed_role_permissions(connection)
        _seed_initial_admin(connection)
        connection.commit()
    finally:
        connection.close()


def _migrate_schema(connection: sqlite3.Connection) -> None:
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


def _seed_default_permissions(connection: sqlite3.Connection) -> None:
    now = utcnow_iso()
    for definition in DEFAULT_PERMISSION_DEFINITIONS:
        connection.execute(
            """
            INSERT OR IGNORE INTO permissions (
                id, code, name, group_name, description, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                uuid.uuid4().hex,
                definition["code"],
                definition["name"],
                definition["group_name"],
                definition["description"],
                now,
                now,
            ),
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


def _seed_role_permissions(connection: sqlite3.Connection) -> None:
    now = utcnow_iso()
    permission_id_by_code = {
        row["code"]: row["id"]
        for row in connection.execute("SELECT id, code FROM permissions").fetchall()
    }
    role_id_by_code = {
        row["code"]: row["id"]
        for row in connection.execute("SELECT id, code FROM roles").fetchall()
    }

    for definition in DEFAULT_ROLE_DEFINITIONS:
        role_id = role_id_by_code[definition["code"]]
        permission_codes = definition["permission_codes"]
        if permission_codes == "*":
            codes_to_bind = tuple(permission_id_by_code.keys())
        else:
            codes_to_bind = permission_codes

        for permission_code in codes_to_bind:
            permission_id = permission_id_by_code[permission_code]
            connection.execute(
                """
                INSERT OR IGNORE INTO role_permissions (
                    role_id, permission_id, created_at
                ) VALUES (?, ?, ?)
                """,
                (role_id, permission_id, now),
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
