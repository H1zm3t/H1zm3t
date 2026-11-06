"""Strukturierte Dateiablage für Anhänge.

- Dateien liegen im Dateisystem (``<files_dir>/<jahr>/<monat>/<uuid>.<endung>``),
  nicht in der Datenbank.
- Interne Dateinamen sind UUIDs → keine Pfadmanipulation, keine Überschreibung.
- SHA-256-Prüfsumme bei jedem Upload; identische Dateien werden erkannt.
- Ausführbare Dateien sind gesperrt.
- Freigegebene Dateien werden nicht gelöscht, sondern archiviert oder ungültig gesetzt.
"""
from __future__ import annotations

import hashlib
import mimetypes
import os
import re
import shutil
import tempfile
import unicodedata
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import utcnow
from ..models import Attachment, User
from . import audit
from .audit import Actor
from .records import RecordError
from .system_settings import get_setting
from .text_extract import extract_text

BLOCKED_EXTENSIONS = {
    "exe", "bat", "cmd", "com", "ps1", "psm1", "psd1", "ps1xml", "vbs", "vbe", "js", "jse", "wsf", "wsh", "msi",
    "msp", "scr", "pif", "cpl", "dll", "sys", "jar", "hta", "lnk", "reg", "sh", "bash", "app", "gadget", "inf",
    "application", "msc", "scf", "ws", "py", "pyw", "vb", "xlam", "docm", "pptm", "dotm",
}
IMAGE_EXT = {"png", "jpg", "jpeg", "gif", "bmp", "tif", "tiff", "webp"}
PREVIEW_IMAGE_EXT = {"png", "jpg", "jpeg", "gif", "bmp", "webp"}
# Typische Signaturen ausführbarer Dateien (Windows-PE/ELF), unabhängig von der Endung
EXECUTABLE_MAGIC = (b"MZ", b"\x7fELF")

FILE_TYPES = {
    "Bild": IMAGE_EXT,
    "PDF": {"pdf"},
    "Excel": {"xlsx", "xls", "xlsm"},
    "Word": {"docx", "doc"},
    "PowerPoint": {"pptx"},
    "CSV": {"csv", "tsv"},
    "Text": {"txt", "log", "md", "ini"},
    "JSON": {"json"},
    "XML": {"xml"},
    "Archiv": {"zip"},
}

CHUNK = 1024 * 1024


@dataclass
class UploadResult:
    attachment: Attachment
    duplicates: list[Attachment]


def safe_display_name(name: str) -> str:
    """Bereinigt den Originalnamen nur für Anzeige/Download (nie als Pfad verwendet)."""
    name = unicodedata.normalize("NFC", name or "datei")
    name = name.replace("\\", "/").split("/")[-1]
    name = re.sub(r"[\x00-\x1f<>:\"|?*]", "_", name).strip(" .")
    return name[:200] or "datei"


def extension_of(name: str) -> str:
    base = safe_display_name(name).lower()
    if base.endswith(".ngb-dsv") or base.endswith(".ngb-ss3") or base.endswith(".ngb-taa"):
        return base.rsplit(".", 1)[1]
    return base.rsplit(".", 1)[1] if "." in base else ""


def classify(ext: str) -> str:
    for label, exts in FILE_TYPES.items():
        if ext in exts:
            return label
    return "Messdatei"


def allowed_extensions(db: Session) -> set[str]:
    raw = get_setting(db, "allowed_extensions")
    return {e.strip().lower().lstrip(".") for e in raw.split(",") if e.strip()} - BLOCKED_EXTENSIONS


def validate_name(db: Session, filename: str) -> str:
    ext = extension_of(filename)
    parts = safe_display_name(filename).lower().split(".")
    if any(p in BLOCKED_EXTENSIONS for p in parts[1:]):
        raise RecordError(f"Der Dateityp von »{safe_display_name(filename)}« ist aus Sicherheitsgründen gesperrt.")
    if not ext:
        raise RecordError("Dateien ohne Endung sind nicht zulässig.")
    if ext not in allowed_extensions(db):
        raise RecordError(f"Die Endung ».{ext}« ist nicht erlaubt. Erlaubte Endungen siehe Einstellungen.")
    return ext


def _store_stream(stream: BinaryIO, max_bytes: int) -> tuple[Path, int, str, bytes]:
    settings = get_settings()
    tmp_dir = settings.files_dir / "_tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=tmp_dir)
    sha = hashlib.sha256()
    size = 0
    head = b""
    try:
        with os.fdopen(fd, "wb") as out:
            while True:
                chunk = stream.read(CHUNK)
                if not chunk:
                    break
                if not head:
                    head = chunk[:8]
                size += len(chunk)
                if size > max_bytes:
                    raise RecordError(f"Die Datei überschreitet die maximale Größe von {max_bytes // (1024 * 1024)} MB.")
                sha.update(chunk)
                out.write(chunk)
    except Exception:
        Path(tmp_name).unlink(missing_ok=True)
        raise
    return Path(tmp_name), size, sha.hexdigest(), head


def sha256_of_file(path: Path) -> str:
    sha = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(CHUNK), b""):
            sha.update(chunk)
    return sha.hexdigest()


def find_duplicates(db: Session, sha: str, exclude_id: int | None = None) -> list[Attachment]:
    q = db.query(Attachment).filter(Attachment.sha256 == sha)
    if exclude_id:
        q = q.filter(Attachment.id != exclude_id)
    return q.all()


def entity_locked(db: Session, entity_type: str, entity_id: int) -> str | None:
    from .entities import get_entity

    obj = get_entity(db, entity_type, entity_id)
    if obj is None:
        raise RecordError("Der Datensatz existiert nicht.")
    if entity_type == "experiment" and obj.locked:
        return f"Versuch {obj.code} ist gesperrt (»{obj.status}«). Anhänge nur nach neuer Revision."
    exp = getattr(obj, "experiment", None)
    if entity_type not in ("sample", "measurement") and exp is not None and getattr(exp, "locked", False):
        return f"Der zugehörige Versuch {exp.code} ist gesperrt."
    return None


def save_upload(db: Session, actor: Actor, *, stream: BinaryIO, filename: str, entity_type: str, entity_id: int,
                description: str | None = None, caption: str | None = None, category: str | None = None,
                confidentiality: str = "intern", previous: Attachment | None = None,
                reason: str | None = None) -> UploadResult:
    settings = get_settings()
    ext = validate_name(db, filename)
    locked = entity_locked(db, entity_type, entity_id)
    if locked:
        raise RecordError(locked)
    tmp_path, size, sha, head = _store_stream(stream, settings.max_upload_mb * 1024 * 1024)
    try:
        if size == 0:
            raise RecordError("Leere Dateien können nicht hochgeladen werden.")
        if head.startswith(EXECUTABLE_MAGIC):
            raise RecordError("Die Datei enthält ausführbaren Programmcode und wird abgelehnt.")
        uid = str(uuid.uuid4())
        now = utcnow()
        rel_dir = Path(f"{now:%Y}") / f"{now:%m}"
        stored_name = f"{uid}.{ext}"
        target_dir = settings.files_dir / rel_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / stored_name
        if target.exists():  # praktisch ausgeschlossen (UUID), aber niemals überschreiben
            raise RecordError("Interner Fehler: Zieldatei existiert bereits.")
        shutil.move(str(tmp_path), target)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise
    duplicates = find_duplicates(db, sha)
    mime = mimetypes.guess_type(f"x.{ext}")[0] or "application/octet-stream"
    att = Attachment(
        file_uid=uid, original_filename=safe_display_name(filename), stored_filename=stored_name, extension=ext,
        file_type=classify(ext), mime_type=mime, size_bytes=size, sha256=sha,
        storage_path=(rel_dir / stored_name).as_posix(), entity_type=entity_type, entity_id=entity_id,
        category=category or ("Foto" if ext in IMAGE_EXT else None), description=description, caption=caption,
        confidentiality=confidentiality, created_by_id=actor.user_id,
        version=(previous.version + 1) if previous else 1, previous_id=previous.id if previous else None,
    )
    try:
        att.extracted_text = extract_text(target, ext)
    except Exception:  # Textextraktion ist optional – Fehler dürfen den Upload nicht verhindern
        att.extracted_text = None
    db.add(att)
    db.flush()
    if previous is not None:
        previous.status = "ersetzt"
        previous.status_changed_at = now
        previous.status_reason = reason
        audit.log(db, actor, "file_new_version", entity_type=entity_type, entity_id=entity_id,
                  field=att.original_filename, old=f"Version {previous.version} ({previous.sha256[:12]}…)",
                  new=f"Version {att.version} ({sha[:12]}…)", reason=reason, version=att.version)
    else:
        audit.log(db, actor, "file_upload", entity_type=entity_type, entity_id=entity_id,
                  field=att.original_filename, new=f"SHA-256 {sha}; {size} Bytes", version=1)
    return UploadResult(att, duplicates)


def absolute_path(att: Attachment) -> Path:
    base = get_settings().files_dir.resolve()
    path = (base / att.storage_path).resolve()
    if base not in path.parents:
        raise RecordError("Ungültiger Speicherpfad.")
    return path


def verify_attachment(att: Attachment) -> bool:
    path = absolute_path(att)
    return path.exists() and sha256_of_file(path) == att.sha256


def can_view_attachment(user: User, att: Attachment) -> bool:
    if att.confidentiality != "streng vertraulich":
        return True
    return att.created_by_id == user.id or bool(user.role_keys & {"admin", "leitung"})


def set_status(db: Session, actor: Actor, att: Attachment, new_status: str, reason: str | None) -> None:
    """Archivieren oder ungültig setzen – Dateien werden nie unbemerkt entfernt."""
    if not reason:
        raise RecordError("Bitte eine Begründung angeben.")
    if new_status not in ("archiviert", "ungültig"):
        raise RecordError("Unzulässiger Status.")
    old = att.status
    att.status = new_status
    att.status_changed_at = utcnow()
    att.status_reason = reason
    audit.log(db, actor, "file_archive" if new_status == "archiviert" else "file_invalidate",
              entity_type=att.entity_type, entity_id=att.entity_id, field=att.original_filename, old=old,
              new=new_status, reason=reason, version=att.version)


def update_meta(db: Session, actor: Actor, att: Attachment, *, description: str | None, caption: str | None,
                category: str | None, confidentiality: str, reason: str | None) -> None:
    changes = {}
    for attr, val in (("description", description), ("caption", caption), ("category", category),
                      ("confidentiality", confidentiality)):
        if getattr(att, attr) != val:
            changes[attr] = (getattr(att, attr), val)
            setattr(att, attr, val)
    labels = {"description": "Beschreibung", "caption": "Bildunterschrift", "category": "Kategorie",
              "confidentiality": "Vertraulichkeit"}
    for attr, (old, new) in changes.items():
        audit.log(db, actor, "file_update", entity_type=att.entity_type, entity_id=att.entity_id,
                  field=f"{att.original_filename}: {labels[attr]}", old=old, new=new, reason=reason,
                  version=att.version)


def list_for(db: Session, entity_type: str, entity_id: int, include_inactive: bool = True) -> list[Attachment]:
    q = db.query(Attachment).filter(Attachment.entity_type == entity_type, Attachment.entity_id == entity_id)
    if not include_inactive:
        q = q.filter(Attachment.status == "aktiv")
    return q.order_by(Attachment.created_at.desc(), Attachment.id.desc()).all()
