"""
alembic/env.py — Alembic migration environment.

WHAT IS ALEMBIC?
    Alembic is SQLAlchemy's migration tool. When you change your ORM models
    (add a column, rename a table), you can't just re-run init_db() —
    that only creates tables that don't exist yet.

    Alembic generates versioned migration scripts. Each script has an
    upgrade() and downgrade() function. You run 'alembic upgrade head'
    to apply all pending migrations in order.

    This is how every production PostgreSQL schema evolves safely.

WORKFLOW:
    1. Change TaskRecord ORM model (e.g. add webhook_url column)
    2. Run: alembic revision --autogenerate -m "add webhook_url to tasks"
    3. Alembic generates a migration script in alembic/versions/
    4. Review the generated script
    5. Run: alembic upgrade head
    6. Column is added to production DB without data loss
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import settings
from db.database import Base

# Load alembic.ini logging config
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Point Alembic at our ORM models so it can autogenerate migrations
target_metadata = Base.metadata

# Override the DB URL from config (not from alembic.ini)
config.set_main_option("sqlalchemy.url", settings.database_url)


def run_migrations_offline() -> None:
    """Run migrations without a DB connection — generates SQL scripts."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations with async engine."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,  # No pool for migrations — single connection
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
