"""Stammdaten: Materialien, Chargen, Geräte, Methoden."""
from __future__ import annotations

from datetime import date

from sqlalchemy import Column, Date, ForeignKey, String, Table, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base
from .base import TrackedMixin

device_methods = Table(
    "device_methods",
    Base.metadata,
    Column("device_id", ForeignKey("devices.id", ondelete="CASCADE"), primary_key=True),
    Column("method_id", ForeignKey("methods.id", ondelete="CASCADE"), primary_key=True),
)


class Material(TrackedMixin, Base):
    __tablename__ = "materials"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    material_number: Mapped[str | None] = mapped_column(String(60), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    trade_name: Mapped[str | None] = mapped_column(String(200))
    manufacturer: Mapped[str | None] = mapped_column(String(200))
    supplier: Mapped[str | None] = mapped_column(String(200))
    material_type: Mapped[str | None] = mapped_column(String(80))
    function: Mapped[str | None] = mapped_column(String(120))
    cas_number: Mapped[str | None] = mapped_column(String(40))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="aktiv", nullable=False)
    remarks: Mapped[str | None] = mapped_column(Text)

    batches: Mapped[list["Batch"]] = relationship(back_populates="material", order_by="Batch.batch_number")

    @property
    def label(self) -> str:
        num = f"{self.material_number} – " if self.material_number else ""
        return f"{num}{self.name}"


class Batch(TrackedMixin, Base):
    __tablename__ = "batches"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    material_id: Mapped[int] = mapped_column(ForeignKey("materials.id"), nullable=False)
    batch_number: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    received_date: Mapped[date | None] = mapped_column(Date)
    expiry_date: Mapped[date | None] = mapped_column(Date)
    storage_location: Mapped[str | None] = mapped_column(String(120))
    quantity: Mapped[float | None]
    unit: Mapped[str | None] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(30), default="freigegeben", nullable=False)
    remarks: Mapped[str | None] = mapped_column(Text)

    material: Mapped[Material] = relationship(back_populates="batches", lazy="joined")

    @property
    def label(self) -> str:
        return f"{self.batch_number} ({self.material.name if self.material else ''})"


class Method(TrackedMixin, Base):
    __tablename__ = "methods"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    standard: Mapped[str | None] = mapped_column(String(120))
    category: Mapped[str | None] = mapped_column(String(80))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="gültig", nullable=False)

    devices: Mapped[list["Device"]] = relationship(secondary=device_methods, back_populates="methods")

    @property
    def label(self) -> str:
        return f"{self.name}" + (f" ({self.standard})" if self.standard else "")


class Device(TrackedMixin, Base):
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    device_type: Mapped[str | None] = mapped_column(String(80))
    manufacturer: Mapped[str | None] = mapped_column(String(120))
    model: Mapped[str | None] = mapped_column(String(120))
    serial_number: Mapped[str | None] = mapped_column(String(120))
    location: Mapped[str | None] = mapped_column(String(120))
    responsible_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(30), default="betriebsbereit", nullable=False)
    last_maintenance: Mapped[date | None] = mapped_column(Date)
    next_maintenance: Mapped[date | None] = mapped_column(Date)
    last_calibration: Mapped[date | None] = mapped_column(Date)
    next_calibration: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)

    responsible = relationship("User", foreign_keys=[responsible_id], lazy="joined")
    methods: Mapped[list[Method]] = relationship(secondary=device_methods, back_populates="devices")

    @property
    def label(self) -> str:
        return f"{self.code} – {self.name}"
