"""Auftragsplanung: Tätigkeiten (Arbeitsplan), Rohstoffliste und Durchführungsprotokoll je Auftrag.

Bildet die Reiter »Auftragdetails«, »Rohstoffliste« und »Durchführung« des
bisherigen Excel-Formulars (Compoundierplan F030) ab.
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base, utcnow


class OrderActivity(Base):
    __tablename__ = "order_activities"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True)
    position: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    activity: Mapped[str] = mapped_column(String(200), nullable=False)
    subject: Mapped[str | None] = mapped_column(String(200))  # Probe / Rezeptur
    responsible_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    responsible_text: Mapped[str | None] = mapped_column(String(60))  # Kürzel aus Excel, falls kein Benutzer
    planned_on: Mapped[date | None] = mapped_column(Date)
    started_on: Mapped[date | None] = mapped_column(Date)
    done_on: Mapped[date | None] = mapped_column(Date)
    documented_on: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str | None] = mapped_column(String(40))
    result: Mapped[str | None] = mapped_column(Text)
    remark: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    responsible = relationship("User", lazy="joined")

    @property
    def responsible_label(self) -> str:
        if self.responsible is not None:
            return self.responsible.short_name or self.responsible.full_name
        return self.responsible_text or ""

    @property
    def label(self) -> str:
        return f"{self.position}. {self.activity}"


class OrderMaterial(Base):
    """Zeile der Rohstoffliste eines Auftrags."""

    __tablename__ = "order_materials"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True)
    position: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    section: Mapped[str] = mapped_column(String(80), nullable=False)
    material_id: Mapped[int] = mapped_column(ForeignKey("materials.id"), nullable=False)
    batch_id: Mapped[int | None] = mapped_column(ForeignKey("batches.id"))
    entry_date: Mapped[date | None] = mapped_column(Date)
    required_kg: Mapped[float | None]
    remark: Mapped[str | None] = mapped_column(Text)

    material = relationship("Material", lazy="joined")
    batch = relationship("Batch", lazy="joined")


class OrderLogEntry(Base):
    """Durchführungsprotokoll: Arbeitsschritt, von, Datum, Bemerkung."""

    __tablename__ = "order_log_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True)
    position: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    step: Mapped[str] = mapped_column(Text, nullable=False)
    done_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    done_by_text: Mapped[str | None] = mapped_column(String(60))
    entry_date: Mapped[date | None] = mapped_column(Date)
    remark: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(20), default="manuell", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    done_by = relationship("User", lazy="joined")

    @property
    def done_by_label(self) -> str:
        if self.done_by is not None:
            return self.done_by.short_name or self.done_by.full_name
        return self.done_by_text or ""
