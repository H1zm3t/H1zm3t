"""Datenbankverbindung (SQLAlchemy 2).

Die Anwendung verwendet ausschließlich SQLAlchemy-Ausdrücke bzw. gebundene
Parameter – dadurch sind SQL-Injections ausgeschlossen. Ein Wechsel auf
PostgreSQL oder Microsoft SQL Server erfolgt über ``ELN_DATABASE_URL``
(siehe docs/MEHRBENUTZERBETRIEB.md).
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from typing import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


_engine: Engine | None = None
_SessionLocal: sessionmaker | None = None


def _sqlite_pragmas(dbapi_conn, _record) -> None:
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA foreign_keys=ON")
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA busy_timeout=5000")
    cur.close()


def get_engine() -> Engine:
    global _engine, _SessionLocal
    if _engine is None:
        settings = get_settings()
        settings.ensure_dirs()
        kwargs: dict = {"future": True}
        if settings.is_sqlite:
            kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
        _engine = create_engine(settings.database_url, **kwargs)
        if settings.is_sqlite:
            event.listen(_engine, "connect", _sqlite_pragmas)
        _SessionLocal = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)
    return _engine


def reset_engine() -> None:
    """Schließt alle Verbindungen (z. B. vor einer Wiederherstellung)."""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None


def SessionLocal() -> Session:  # noqa: N802 - bewusst wie eine Klasse benannt
    get_engine()
    assert _SessionLocal is not None
    return _SessionLocal()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transaktion: alles oder nichts."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def utcnow() -> datetime:
    """Lokale Zeit ohne Zeitzone – das ELN läuft an einem Standort.

    Für einen späteren standortübergreifenden Betrieb siehe Dokumentation.
    """
    return datetime.now().replace(microsecond=0)
