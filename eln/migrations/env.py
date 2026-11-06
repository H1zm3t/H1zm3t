"""Alembic-Umgebung: lädt Kern- und Modulmodelle."""
from __future__ import annotations

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.config import get_settings
from app.core.modules import get_registry
from app.db import Base
import app.models  # noqa: F401  Kernmodelle registrieren

for _module in get_registry().all():  # Modulmodelle registrieren
    _module.models()

config = context.config
if not config.get_main_option("sqlalchemy.url"):
    config.set_main_option("sqlalchemy.url", get_settings().database_url)
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(url=config.get_main_option("sqlalchemy.url"), target_metadata=target_metadata,
                      literal_binds=True, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(config.get_section(config.config_ini_section, {}), prefix="sqlalchemy.",
                                     poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
