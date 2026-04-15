"""
Alembic environment configuration.

Reads the database URL from app.core.config.settings so migrations
always target the same database as the running application.

Usage:
    # Generate a new auto-migration (compares models to DB)
    alembic revision --autogenerate -m "describe_your_change"

    # Apply all pending migrations
    alembic upgrade head

    # Roll back one step
    alembic downgrade -1
"""
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# --- Import all ORM models so Alembic can detect schema changes ----------
# Each import registers the model's __tablename__ with Base.metadata.
import app.models.auth  # noqa: F401
import app.models.asset  # noqa: F401
import app.models.job  # noqa: F401
import app.models.project  # noqa: F401

from app.db.base import Base
from app.core.config import settings

# Alembic Config object — gives access to values in alembic.ini
config = context.config

# Inject the live database URL from application settings
config.set_main_option("sqlalchemy.url", settings.database_url)

# Set up Python logging as configured in alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# The MetaData object that Alembic will compare against the database
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations without a live DB connection (emits SQL to stdout)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live database connection."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
