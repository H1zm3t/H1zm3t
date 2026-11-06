"""Querschnittsfunktionen: Anhänge, Kommentare, Aufgaben, Audit Trail,
Freigaben, Einstellungen, Nummernkreise, Sicherungen, Module."""
from __future__ import annotations

import json
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base, utcnow


class Attachment(Base):
    __tablename__ = "attachments"

    id: Mapped[int] = mapped_column(primary_key=True)
    file_uid: Mapped[str] = mapped_column(String(36), unique=True, nullable=False, index=True)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_filename: Mapped[str] = mapped_column(String(80), nullable=False)
    extension: Mapped[str] = mapped_column(String(20), nullable=False)
    file_type: Mapped[str] = mapped_column(String(30), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(120), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    storage_path: Mapped[str] = mapped_column(String(400), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    category: Mapped[str | None] = mapped_column(String(60))
    description: Mapped[str | None] = mapped_column(Text)
    caption: Mapped[str | None] = mapped_column(String(300))
    confidentiality: Mapped[str] = mapped_column(String(30), default="intern", nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    previous_id: Mapped[int | None] = mapped_column(ForeignKey("attachments.id"))
    status: Mapped[str] = mapped_column(String(20), default="aktiv", nullable=False)
    extracted_text: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    status_changed_at: Mapped[datetime | None] = mapped_column(DateTime)
    status_reason: Mapped[str | None] = mapped_column(Text)

    created_by = relationship("User", lazy="joined")

    @property
    def is_image(self) -> bool:
        return self.file_type == "Bild"

    @property
    def is_pdf(self) -> bool:
        return self.extension == "pdf"


class Comment(Base):
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))

    created_by = relationship("User", lazy="joined")


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(250), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    entity_type: Mapped[str | None] = mapped_column(String(40))
    entity_id: Mapped[int | None] = mapped_column(Integer)
    assignee_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    priority: Mapped[str] = mapped_column(String(20), default="normal", nullable=False)
    due_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(30), default="offen", nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    updated_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    assignee = relationship("User", foreign_keys=[assignee_id], lazy="joined")
    created_by = relationship("User", foreign_keys=[created_by_id])

    @property
    def label(self) -> str:
        return f"{self.code} – {self.title}"

    @property
    def is_overdue(self) -> bool:
        return bool(self.due_date and self.status != "erledigt" and self.due_date < date.today())


class AuditLog(Base):
    """Audit Trail – nur Einfügen erlaubt (Trigger verhindern UPDATE/DELETE).

    Jeder Eintrag enthält den Hash des Vorgängers (Hash-Kette). Eine
    nachträgliche Manipulation direkt in der Datenbankdatei wird dadurch
    bei der Integritätsprüfung erkannt.
    """

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False, index=True)
    user_id: Mapped[int | None] = mapped_column(Integer, index=True)
    username: Mapped[str | None] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    entity_type: Mapped[str | None] = mapped_column(String(40), index=True)
    entity_id: Mapped[int | None] = mapped_column(Integer, index=True)
    entity_code: Mapped[str | None] = mapped_column(String(60), index=True)
    field: Mapped[str | None] = mapped_column(String(80))
    old_value: Mapped[str | None] = mapped_column(Text)
    new_value: Mapped[str | None] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(Text)
    ip_address: Mapped[str | None] = mapped_column(String(64))
    record_version: Mapped[int | None] = mapped_column(Integer)
    result: Mapped[str] = mapped_column(String(20), default="erfolgreich", nullable=False)
    prev_hash: Mapped[str | None] = mapped_column(String(64))
    entry_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class ApprovalRecord(Base):
    """Elektronischer Prüf-/Freigabevermerk mit Bezug auf einen unveränderlichen Stand."""

    __tablename__ = "approval_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    step: Mapped[str] = mapped_column(String(40), nullable=False)
    decision: Mapped[str] = mapped_column(String(40), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    snapshot_id: Mapped[int | None] = mapped_column(ForeignKey("record_snapshots.id"))

    user = relationship("User", lazy="joined")
    snapshot = relationship("RecordSnapshot", lazy="joined")


class RecordSnapshot(Base):
    """Eingefrorener Datenstand (z. B. bei Einreichung und Freigabe)."""

    __tablename__ = "record_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    data_json: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))

    created_by = relationship("User", lazy="joined")

    @property
    def data(self) -> dict:
        return json.loads(self.data_json)


class EntityLink(Base):
    """Allgemeine Verknüpfung zwischen Datensätzen (auch modulübergreifend)."""

    __tablename__ = "entity_links"
    __table_args__ = (UniqueConstraint("source_type", "source_id", "target_type", "target_id", "relation"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    source_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    target_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    target_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    relation: Mapped[str] = mapped_column(String(60), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


class SystemSetting(Base):
    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class Counter(Base):
    __tablename__ = "counters"

    key: Mapped[str] = mapped_column(String(40), primary_key=True)
    value: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class SavedQuery(Base):
    __tablename__ = "saved_queries"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    scope: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    query_json: Mapped[str] = mapped_column(Text, nullable=False)
    is_shared: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    user = relationship("User", lazy="joined")

    @property
    def query(self) -> dict:
        return json.loads(self.query_json)


class BackupRecord(Base):
    __tablename__ = "backup_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    path: Mapped[str] = mapped_column(String(500), nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(64))
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    sha256: Mapped[str | None] = mapped_column(String(64))
    file_count: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    message: Mapped[str | None] = mapped_column(Text)


class ModuleState(Base):
    __tablename__ = "module_states"

    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    installed_version: Mapped[str | None] = mapped_column(String(20))
    config_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    @property
    def config(self) -> dict:
        return json.loads(self.config_json or "{}")


class ModuleRecord(Base):
    """Generische Datenablage für deklarative Fachmodule (Grundgerüste).

    Module mit eigenem Datenmodell (z. B. Compoundierung) nutzen eigene Tabellen.
    """

    __tablename__ = "module_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    module_key: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(250), nullable=False)
    experiment_id: Mapped[int | None] = mapped_column(ForeignKey("experiments.id"))
    sample_id: Mapped[int | None] = mapped_column(ForeignKey("samples.id"))
    device_id: Mapped[int | None] = mapped_column(ForeignKey("devices.id"))
    data_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="erfasst", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    updated_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    experiment = relationship("Experiment", lazy="joined")
    sample = relationship("Sample", lazy="joined")
    device = relationship("Device", lazy="joined")

    @property
    def data(self) -> dict:
        return json.loads(self.data_json or "{}")

    @property
    def label(self) -> str:
        return f"{self.code} – {self.title}"
