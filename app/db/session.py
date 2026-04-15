"""
SQLAlchemy session factory and FastAPI dependency.

Usage in routers::

    from app.db.session import get_db_session

    @router.get("/items")
    def list_items(session: Annotated[Session, Depends(get_db_session)]):
        ...
"""

from collections.abc import Generator

from sqlalchemy.orm import Session, sessionmaker

from app.db.engine import get_engine


def _make_session_factory() -> sessionmaker[Session]:
    return sessionmaker(
        bind=get_engine(),
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )


def get_db_session() -> Generator[Session, None, None]:
    """FastAPI dependency that provides a SQLAlchemy Session.

    Yields a session for the duration of the request.
    Commits on success, rolls back on exception, always closes.
    """
    factory = _make_session_factory()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
