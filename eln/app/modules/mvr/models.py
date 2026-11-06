"""Beispielmodul MVR/MFR – eigenes Datenmodell."""
from __future__ import annotations

import json

from sqlalchemy import Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ...db import Base
from ...models import describe
from ...models.base import TrackedMixin


class MvrTest(TrackedMixin, Base):
    __tablename__ = "mod_mvr_tests"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    sample_id: Mapped[int] = mapped_column(ForeignKey("samples.id"), nullable=False)
    experiment_id: Mapped[int | None] = mapped_column(ForeignKey("experiments.id"))
    device_id: Mapped[int | None] = mapped_column(ForeignKey("devices.id"))
    temperature_c: Mapped[float] = mapped_column(Float, nullable=False)
    load_kg: Mapped[float] = mapped_column(Float, nullable=False)
    melt_density: Mapped[float | None] = mapped_column(Float)
    values_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    remark: Mapped[str | None] = mapped_column(Text)
    measurement_id: Mapped[int | None] = mapped_column(ForeignKey("measurements.id"))

    sample = relationship("Sample", lazy="joined")
    experiment = relationship("Experiment", lazy="joined")
    device = relationship("Device", lazy="joined")

    @property
    def values(self) -> list[float]:
        return json.loads(self.values_json or "[]")

    @property
    def stats(self) -> dict:
        return describe(self.values)

    @property
    def mfr(self) -> float | None:
        """MFR [g/10 min] = MVR [cm³/10 min] × Schmelzedichte [g/cm³]."""
        mean = self.stats["mean"]
        return round(mean * self.melt_density, 3) if mean is not None and self.melt_density else None

    @property
    def label(self) -> str:
        return f"{self.code} – MVR {self.temperature_c:g} °C/{self.load_kg:g} kg"
