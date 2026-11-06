"""Initialisierung: Migrationen (mit vorheriger Sicherung), Rollen, Module."""
from __future__ import annotations

import logging

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect

from .config import BASE_DIR, get_settings
from .core.modules import get_registry
from .db import get_engine, session_scope

log = logging.getLogger("eln.bootstrap")


def alembic_config() -> Config:
    cfg = Config(str(BASE_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BASE_DIR / "migrations"))
    cfg.set_main_option("sqlalchemy.url", get_settings().database_url)
    return cfg


def migration_status() -> tuple[str | None, str | None]:
    cfg = alembic_config()
    head = ScriptDirectory.from_config(cfg).get_current_head()
    with get_engine().connect() as conn:
        current = MigrationContext.configure(conn).get_current_revision()
    return current, head


def run_migrations(backup_before: bool = True) -> str:
    settings = get_settings()
    settings.ensure_dirs()
    current, head = migration_status()
    if current == head:
        return "Datenbank ist aktuell."
    has_tables = bool(inspect(get_engine()).get_table_names())
    if has_tables and backup_before and settings.is_sqlite:
        from .services.backup import create_backup

        result = create_backup("vor Migration", "system", record=current is not None)
        if not result["ok"]:
            raise RuntimeError(f"Sicherung vor Migration fehlgeschlagen: {result['message']}")
        log.info("Sicherung vor Migration erstellt: %s", result["filename"])
    command.upgrade(alembic_config(), "head")
    log.info("Datenbank migriert: %s -> %s", current, head)
    with session_scope() as db:
        from .services import audit

        audit.log(db, audit.SYSTEM, "migration", entity_type="system", old=current or "(leer)", new=head)
    return f"Datenbank migriert ({current or 'neu'} → {head})."


def init_database() -> str:
    msg = run_migrations()
    from .services.auth import ensure_default_roles

    registry = get_registry()
    with session_scope() as db:
        ensure_default_roles(db)
        registry.sync_states(db)
    return msg
