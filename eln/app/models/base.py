"""Gemeinsame Bausteine der Datenmodelle."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from ..db import utcnow


class TrackedMixin:
    """Ersteller, Zeitstempel und Versionszähler für jeden Stammdatensatz."""

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    updated_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
