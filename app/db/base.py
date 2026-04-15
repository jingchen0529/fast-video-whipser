"""
Declarative base for all SQLAlchemy ORM models.

This module is the **single source of truth** for the database schema.
All table definitions live in ``app/models/`` as ORM classes that inherit
from ``Base``.  Schema creation uses ``Base.metadata.create_all(engine)``
and future migrations are managed by Alembic (``alembic revision
--autogenerate``).

Imported by every model file under ``app/models/``.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
