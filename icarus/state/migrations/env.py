"""Alembic environment (task 0.4). DSN from ICARUS_PG_DSN; targets the models' metadata."""

from __future__ import annotations

import os

from alembic import context
from sqlalchemy import engine_from_config, pool

from icarus.state.models import Base

config = context.config

# DSN from env, never from the ini file (no committed creds).
dsn = os.environ.get("ICARUS_PG_DSN")
if dsn:
    config.set_main_option("sqlalchemy.url", dsn)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
