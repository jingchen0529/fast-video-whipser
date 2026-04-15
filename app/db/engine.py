"""
SQLAlchemy engine singleton.

Usage::

    from app.db.engine import get_engine

    engine = get_engine()
"""

from sqlalchemy import Engine, create_engine as _create_engine

from app.core.config import settings

_engine: Engine | None = None
_engine_url: str | None = None


def get_engine() -> Engine:
    """Return the SQLAlchemy Engine, creating it on first call.

    If ``settings.database_url`` changes (e.g. during tests), the engine is
    recreated automatically so the session factory always talks to the right
    database.
    """
    global _engine, _engine_url

    current_url = settings.database_url
    if _engine is not None and _engine_url == current_url:
        return _engine

    if _engine is not None:
        _engine.dispose()

    _engine = _create_engine(
        current_url,
        pool_size=5,
        max_overflow=10,
        pool_recycle=1800,
        pool_pre_ping=True,
        echo=False,
    )
    _engine_url = current_url
    return _engine
