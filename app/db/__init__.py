"""
Public interface for the database layer.

Exports:
    get_db_session      — SQLAlchemy ORM session (used by services)
    initialize_database — create/migrate schema on startup
    create_connection   — raw driver connection (used by tests and legacy code)

Schema creation uses ORM models (``app.models``) as the single source of
truth via ``Base.metadata.create_all()``.  Alembic migrations build on the
same ``Base.metadata``.  Hand-written SQL schema definitions are no longer
used for table creation.

``create_connection`` is resolved at call-time based on ``settings.database_url``
so it works correctly even when tests override the URL at runtime.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from app.db.session import get_db_session

if TYPE_CHECKING:
    # Only for type checkers; actual import is deferred to call-time.
    from app.db.mysql import MySQLConnection
    import sqlite3


def initialize_database(database_url: str | None = None) -> None:
    """Create tables / run migrations / seed reference data.

    Dispatches to the backend-specific initialiser based on
    ``settings.database_url``.  Both backends now use
    ``Base.metadata.create_all()`` for table creation and keep legacy
    migration helpers for existing databases only.
    """
    from app.core.config import settings

    url = database_url or settings.database_url
    if url.startswith("sqlite"):
        from app.db.sqlite import initialize_database as _sqlite_init
        _sqlite_init(database_url)
    else:
        from app.db.mysql import initialize_database as _mysql_init
        _mysql_init(database_url)


def create_connection(database_url: str | None = None):
    """Return a raw database connection for the configured backend.

    Dispatches to ``app.db.mysql.create_connection`` or
    ``app.db.sqlite.create_connection`` depending on the current
    ``settings.database_url``.  The URL is read at call-time so that test
    fixtures that override ``settings.database_url`` are handled correctly.
    """
    from app.core.config import settings

    url = database_url or settings.database_url
    if url.startswith("sqlite"):
        from app.db.sqlite import create_connection as _sqlite_conn
        return _sqlite_conn(url)
    else:
        from app.db.mysql import create_connection as _mysql_conn
        return _mysql_conn(url)


__all__ = [
    "get_db_session",
    "initialize_database",
    "create_connection",
]
