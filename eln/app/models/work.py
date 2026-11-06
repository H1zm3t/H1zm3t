"""Fachliche Kerndaten: Projekte, Aufträge, Versuche, Rezepturen, Proben, Messdaten."""
from __future__ import annotations

import json
import statistics
from datetime import date, datetime

from sqlalchemy import Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, String, Table, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base
from .base import TrackedMixin


def _m2m(name: str, left: str, right: str) -> Table:
    return Table(
        name,
        Base.metadata,
        Column(f"{left}_id", ForeignKey(f"{left}s.id", ondelete="CASCADE"), primary_key=True),
        Column(f"{right}_id", ForeignKey(f"{right}s.id", ondelete="CASCADE"), primary_key=True),
    )


order_participants = Table(
    "order_participants",
    Base.metadata,
    Column("order_id", ForeignKey("orders.id", ondelete="CASCADE"), primary_key=True),
    Column("user_id", ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
)
experiment_participants = Table(
    "experiment_participants",
    Base.metadata,
    Column("experiment_id", ForeignKey("experiments.id", ondelete="CASCADE"), primary_key=True),
    Column("user_id", ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
)
experiment_devices = _m2m("experiment_devices", "experiment", "device")
experiment_materials = _m2m("experiment_materials", "experiment", "material")
experiment_batches = Table(
    "experiment_batches",
    Base.metadata,
    Column("experiment_id", ForeignKey("experiments.id", ondelete="CASCADE"), primary_key=True),
    Column("batch_id", ForeignKey("batches.id", ondelete="CASCADE"), primary_key=True),
)
experiment_used_samples = _m2m("experiment_used_samples", "experiment", "sample")


class Project(TrackedMixin, Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    customer: Mapped[str | None] = mapped_column(String(200))
    responsible_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(30), default="aktiv", nullable=False)
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    tags: Mapped[str | None] = mapped_column(String(300))

    responsible = relationship("User", foreign_keys=[responsible_id], lazy="joined")
    orders: Mapped[list["Order"]] = relationship(back_populates="project")

    @property
    def label(self) -> str:
        return f"{self.code} – {self.name}"


class Order(TrackedMixin, Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    external_number: Mapped[str | None] = mapped_column(String(60), index=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"))
    title: Mapped[str] = mapped_column(String(250), nullable=False)
    client: Mapped[str | None] = mapped_column(String(200))
    customer: Mapped[str | None] = mapped_column(String(200))
    task_description: Mapped[str | None] = mapped_column(Text)
    objective: Mapped[str | None] = mapped_column(Text)
    priority: Mapped[str] = mapped_column(String(20), default="normal", nullable=False)
    responsible_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    due_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(30), default="offen", nullable=False)
    confidentiality: Mapped[str] = mapped_column(String(30), default="intern", nullable=False)
    tags: Mapped[str | None] = mapped_column(String(300))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime)

    project = relationship("Project", back_populates="orders", lazy="joined")
    responsible = relationship("User", foreign_keys=[responsible_id], lazy="joined")
    participants = relationship("User", secondary=order_participants, lazy="selectin")
    experiments: Mapped[list["Experiment"]] = relationship(back_populates="order", order_by="Experiment.code")

    @property
    def label(self) -> str:
        return f"{self.code} – {self.title}"


class ExperimentSeries(TrackedMixin, Base):
    __tablename__ = "experiment_series"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="aktiv", nullable=False)

    order = relationship("Order", lazy="joined")
    experiments: Mapped[list["Experiment"]] = relationship(back_populates="series")

    @property
    def label(self) -> str:
        return f"{self.code} – {self.name}"


class Recipe(TrackedMixin, Base):
    __tablename__ = "recipes"
    __table_args__ = (UniqueConstraint("code", "revision", name="uq_recipe_code_revision"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"))
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("recipes.id"))
    target_total: Mapped[float | None] = mapped_column(Float)
    total_unit: Mapped[str] = mapped_column(String(10), default="kg", nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="Entwurf", nullable=False)
    revision_reason: Mapped[str | None] = mapped_column(Text)

    order = relationship("Order", lazy="joined")
    parent = relationship("Recipe", remote_side=[id], lazy="joined")
    items: Mapped[list["RecipeItem"]] = relationship(
        back_populates="recipe", cascade="all, delete-orphan", order_by="RecipeItem.position", lazy="selectin"
    )

    @property
    def label(self) -> str:
        return f"{self.code} Rev. {self.revision} – {self.name}"

    @property
    def percent_sum(self) -> float:
        return round(sum(i.weight_percent or 0 for i in self.items), 6)


class RecipeItem(Base):
    __tablename__ = "recipe_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    material_id: Mapped[int] = mapped_column(ForeignKey("materials.id"), nullable=False)
    batch_id: Mapped[int | None] = mapped_column(ForeignKey("batches.id"))
    function: Mapped[str | None] = mapped_column(String(120))
    target_amount: Mapped[float | None] = mapped_column(Float)
    unit: Mapped[str | None] = mapped_column(String(10))
    actual_amount: Mapped[float | None] = mapped_column(Float)
    weight_percent: Mapped[float | None] = mapped_column(Float)
    tolerance: Mapped[float | None] = mapped_column(Float)
    remark: Mapped[str | None] = mapped_column(String(300))

    recipe = relationship("Recipe", back_populates="items")
    material = relationship("Material", lazy="joined")
    batch = relationship("Batch", lazy="joined")


class Experiment(TrackedMixin, Base):
    __tablename__ = "experiments"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(250), nullable=False)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"))
    series_id: Mapped[int | None] = mapped_column(ForeignKey("experiment_series.id"))
    experiment_type: Mapped[str | None] = mapped_column(String(80))
    department: Mapped[str | None] = mapped_column(String(80))
    objective: Mapped[str | None] = mapped_column(Text)
    hypothesis: Mapped[str | None] = mapped_column(Text)
    responsible_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    planned_date: Mapped[date | None] = mapped_column(Date)
    actual_date: Mapped[date | None] = mapped_column(Date)
    method_id: Mapped[int | None] = mapped_column(ForeignKey("methods.id"))
    recipe_id: Mapped[int | None] = mapped_column(ForeignKey("recipes.id"))
    process_steps: Mapped[str | None] = mapped_column(Text)
    process_parameters_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    observations: Mapped[str | None] = mapped_column(Text)
    deviations: Mapped[str | None] = mapped_column(Text)
    raw_data: Mapped[str | None] = mapped_column(Text)
    results: Mapped[str | None] = mapped_column(Text)
    evaluation: Mapped[str | None] = mapped_column(Text)
    conclusion: Mapped[str | None] = mapped_column(Text)
    follow_up: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[str | None] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(40), default="Entwurf", nullable=False, index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    locked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime)
    submitted_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime)
    reviewed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime)
    approved_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)

    order = relationship("Order", back_populates="experiments", lazy="joined")
    series = relationship("ExperimentSeries", back_populates="experiments", lazy="joined")
    responsible = relationship("User", foreign_keys=[responsible_id], lazy="joined")
    submitted_by = relationship("User", foreign_keys=[submitted_by_id])
    reviewed_by = relationship("User", foreign_keys=[reviewed_by_id])
    approved_by = relationship("User", foreign_keys=[approved_by_id])
    method = relationship("Method", lazy="joined")
    recipe = relationship("Recipe", lazy="joined")
    participants = relationship("User", secondary=experiment_participants, lazy="selectin")
    devices = relationship("Device", secondary=experiment_devices, lazy="selectin")
    materials = relationship("Material", secondary=experiment_materials, lazy="selectin")
    batches = relationship("Batch", secondary=experiment_batches, lazy="selectin")
    used_samples = relationship("Sample", secondary=experiment_used_samples, lazy="selectin")

    @property
    def label(self) -> str:
        return f"{self.code} – {self.title}"

    @property
    def process_parameters(self) -> list[dict]:
        try:
            return json.loads(self.process_parameters_json or "[]")
        except ValueError:
            return []


class Sample(TrackedMixin, Base):
    __tablename__ = "samples"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    sample_type: Mapped[str | None] = mapped_column(String(80))
    origin: Mapped[str | None] = mapped_column(String(200))
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"))
    experiment_id: Mapped[int | None] = mapped_column(ForeignKey("experiments.id"))
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("samples.id"))
    material_id: Mapped[int | None] = mapped_column(ForeignKey("materials.id"))
    recipe_id: Mapped[int | None] = mapped_column(ForeignKey("recipes.id"))
    batch_id: Mapped[int | None] = mapped_column(ForeignKey("batches.id"))
    production_date: Mapped[date | None] = mapped_column(Date)
    sampling_date: Mapped[date | None] = mapped_column(Date)
    quantity: Mapped[float | None] = mapped_column(Float)
    unit: Mapped[str | None] = mapped_column(String(20))
    storage_location: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(30), default="vorhanden", nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    order = relationship("Order", lazy="joined")
    experiment = relationship("Experiment", foreign_keys=[experiment_id], lazy="joined")
    parent = relationship("Sample", remote_side=[id], back_populates="children", lazy="joined")
    children: Mapped[list["Sample"]] = relationship(back_populates="parent")
    material = relationship("Material", lazy="joined")
    recipe = relationship("Recipe", lazy="joined")
    batch = relationship("Batch", lazy="joined")

    @property
    def label(self) -> str:
        return f"{self.code} – {self.name}"


class Measurement(TrackedMixin, Base):
    """Numerischer Datensatz (Messreihe) mit Einheit und Metadaten."""

    __tablename__ = "measurements"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    property_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    unit: Mapped[str | None] = mapped_column(String(30))
    x_name: Mapped[str | None] = mapped_column(String(80))
    x_unit: Mapped[str | None] = mapped_column(String(30))
    experiment_id: Mapped[int | None] = mapped_column(ForeignKey("experiments.id"))
    sample_id: Mapped[int | None] = mapped_column(ForeignKey("samples.id"))
    device_id: Mapped[int | None] = mapped_column(ForeignKey("devices.id"))
    method_id: Mapped[int | None] = mapped_column(ForeignKey("methods.id"))
    measured_on: Mapped[date | None] = mapped_column(Date)
    conditions: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    source: Mapped[str] = mapped_column(String(60), default="manuell", nullable=False)

    experiment = relationship("Experiment", lazy="joined")
    sample = relationship("Sample", lazy="joined")
    device = relationship("Device", lazy="joined")
    method = relationship("Method", lazy="joined")
    values: Mapped[list["MeasurementValue"]] = relationship(
        back_populates="measurement", cascade="all, delete-orphan", order_by="MeasurementValue.idx", lazy="selectin"
    )

    @property
    def label(self) -> str:
        return f"{self.code} – {self.name}"

    @property
    def meta(self) -> dict:
        try:
            return json.loads(self.metadata_json or "{}")
        except ValueError:
            return {}

    @property
    def stats(self) -> dict:
        vals = [v.value for v in self.values if v.value is not None]
        return describe(vals)


class MeasurementValue(Base):
    __tablename__ = "measurement_values"

    id: Mapped[int] = mapped_column(primary_key=True)
    measurement_id: Mapped[int] = mapped_column(ForeignKey("measurements.id", ondelete="CASCADE"), nullable=False)
    idx: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    x_value: Mapped[float | None] = mapped_column(Float)
    value: Mapped[float | None] = mapped_column(Float)
    label: Mapped[str | None] = mapped_column(String(120))

    measurement = relationship("Measurement", back_populates="values")


def describe(values: list[float]) -> dict:
    """Statistische Kennwerte: Anzahl, Mittelwert, Median, Min, Max, Standardabweichung."""
    if not values:
        return {"n": 0, "mean": None, "median": None, "min": None, "max": None, "std": None}
    return {
        "n": len(values),
        "mean": statistics.fmean(values),
        "median": statistics.median(values),
        "min": min(values),
        "max": max(values),
        "std": statistics.stdev(values) if len(values) > 1 else 0.0,
    }
