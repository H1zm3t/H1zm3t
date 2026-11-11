"""Datenmodell Compoundierung (Doppelschneckenextruder)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ...db import Base
from ...models.base import TrackedMixin


class CompoundingRun(TrackedMixin, Base):
    __tablename__ = "mod_compounding_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    experiment_id: Mapped[int] = mapped_column(ForeignKey("experiments.id"), nullable=False, index=True)
    recipe_id: Mapped[int | None] = mapped_column(ForeignKey("recipes.id"))
    device_id: Mapped[int | None] = mapped_column(ForeignKey("devices.id"))
    operator_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    screw_config: Mapped[str | None] = mapped_column(Text)
    throughput_set: Mapped[float | None] = mapped_column(Float)
    throughput_actual: Mapped[float | None] = mapped_column(Float)
    screw_speed: Mapped[float | None] = mapped_column(Float)
    torque: Mapped[float | None] = mapped_column(Float)
    melt_pressure: Mapped[float | None] = mapped_column(Float)
    melt_temperature: Mapped[float | None] = mapped_column(Float)
    vacuum: Mapped[float | None] = mapped_column(Float)
    cooling: Mapped[str | None] = mapped_column(Text)
    pelletizing: Mapped[str | None] = mapped_column(Text)
    start_time: Mapped[datetime | None] = mapped_column(DateTime)
    end_time: Mapped[datetime | None] = mapped_column(DateTime)
    observations: Mapped[str | None] = mapped_column(Text)
    disturbances: Mapped[str | None] = mapped_column(Text)
    deviations: Mapped[str | None] = mapped_column(Text)
    sampling: Mapped[str | None] = mapped_column(Text)
    evaluation: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="geplant", nullable=False)
    # Weitere Protokollzeilen (z. B. aus dem Excel-Extrusionsprotokoll), als Liste [Bezeichnung, Wert]
    protocol_json: Mapped[str | None] = mapped_column(Text)

    experiment = relationship("Experiment", lazy="joined")
    recipe = relationship("Recipe", lazy="joined")
    device = relationship("Device", lazy="joined")
    operator = relationship("User", foreign_keys=[operator_id], lazy="joined")
    zones: Mapped[list["CompoundingZone"]] = relationship(
        back_populates="run", cascade="all, delete-orphan", order_by="CompoundingZone.position", lazy="selectin")
    feeders: Mapped[list["CompoundingFeeder"]] = relationship(
        back_populates="run", cascade="all, delete-orphan", order_by="CompoundingFeeder.position", lazy="selectin")
    readings: Mapped[list["CompoundingReading"]] = relationship(
        back_populates="run", cascade="all, delete-orphan", order_by="CompoundingReading.minute", lazy="selectin")

    @property
    def label(self) -> str:
        return f"{self.code} – {self.title}"

    @property
    def protocol(self) -> list:
        import json

        try:
            return json.loads(self.protocol_json or "[]")
        except ValueError:
            return []

    @property
    def duration_min(self) -> float | None:
        if self.start_time and self.end_time:
            return round((self.end_time - self.start_time).total_seconds() / 60, 1)
        return None


class CompoundingZone(Base):
    """Zylindertemperaturzone – Anzahl und Bezeichnung frei konfigurierbar."""

    __tablename__ = "mod_compounding_zones"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("mod_compounding_runs.id", ondelete="CASCADE"), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(60), nullable=False)
    set_temp: Mapped[float | None] = mapped_column(Float)
    actual_temp: Mapped[float | None] = mapped_column(Float)

    run = relationship("CompoundingRun", back_populates="zones")


class CompoundingFeeder(Base):
    __tablename__ = "mod_compounding_feeders"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("mod_compounding_runs.id", ondelete="CASCADE"), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    feed_point: Mapped[str] = mapped_column(String(60), nullable=False)
    feeder: Mapped[str | None] = mapped_column(String(120))
    material_id: Mapped[int | None] = mapped_column(ForeignKey("materials.id"))
    component: Mapped[str | None] = mapped_column(String(200))
    set_rate: Mapped[float | None] = mapped_column(Float)
    actual_rate: Mapped[float | None] = mapped_column(Float)

    run = relationship("CompoundingRun", back_populates="feeders")
    material = relationship("Material", lazy="joined")


class CompoundingReading(Base):
    """Prozessverlauf (Messpunkte während des Laufs)."""

    __tablename__ = "mod_compounding_readings"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("mod_compounding_runs.id", ondelete="CASCADE"), nullable=False)
    minute: Mapped[float] = mapped_column(Float, nullable=False)
    screw_speed: Mapped[float | None] = mapped_column(Float)
    torque: Mapped[float | None] = mapped_column(Float)
    melt_pressure: Mapped[float | None] = mapped_column(Float)
    melt_temperature: Mapped[float | None] = mapped_column(Float)
    throughput: Mapped[float | None] = mapped_column(Float)
    remark: Mapped[str | None] = mapped_column(String(200))

    run = relationship("CompoundingRun", back_populates="readings")
