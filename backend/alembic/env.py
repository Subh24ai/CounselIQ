"""Alembic migration environment for CounselIQ.

The async application URL (asyncpg) is rewritten to the synchronous psycopg2
driver for the Alembic runner, which keeps migrations simple and free of an
event loop. ``DATABASE_URL`` is read directly from the environment to avoid
importing the application settings cache during migration. Both offline (SQL
emit) and online (live connection) modes are supported.
"""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from pgvector.sqlalchemy import Vector
from sqlalchemy import engine_from_config, pool

# Import Base from the models package so every model is registered on the
# shared metadata before autogenerate runs.
from app.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def _sync_database_url() -> str:
    """Return a synchronous (psycopg2) SQLAlchemy URL for the Alembic runner."""
    url = os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://counseliq:counseliq@localhost:5433/counseliq",
    )
    # Alembic uses a synchronous DBAPI; swap asyncpg for psycopg2.
    url = url.replace("postgresql+asyncpg", "postgresql+psycopg2")
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


config.set_main_option("sqlalchemy.url", _sync_database_url())

target_metadata = Base.metadata


def render_item(type_: str, obj: object, autogen_context) -> str | bool:
    """Render pgvector ``Vector`` columns with the correct import in migrations."""
    if type_ == "type" and isinstance(obj, Vector):
        autogen_context.imports.add("import pgvector")
        return f"pgvector.sqlalchemy.Vector(dim={obj.dim})"
    return False


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL without a DBAPI connection)."""
    context.configure(
        url=_sync_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        render_item=render_item,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode with a live database connection."""
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
            render_item=render_item,
        )

        with context.begin_transaction():
            context.run_migrations()

    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
