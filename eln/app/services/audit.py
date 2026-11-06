"""Audit Trail mit Hash-Kette.

Jeder Eintrag speichert den Hash seines Vorgängers. ``verify_chain`` erkennt
dadurch nachträglich veränderte, gelöschte oder eingefügte Einträge. Zusätzlich
verhindern Datenbank-Trigger UPDATE und DELETE auf der Tabelle ``audit_log``.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from sqlalchemy.orm import Session

from ..db import utcnow
from ..models import AuditLog, User


@dataclass
class Actor:
    """Wer handelt – Benutzer und (soweit verfügbar) IP-Adresse."""

    user: User | None
    ip: str | None = None

    @property
    def user_id(self) -> int | None:
        return self.user.id if self.user else None

    @property
    def username(self) -> str:
        return self.user.username if self.user else "system"


SYSTEM = Actor(user=None, ip="lokal")

ACTION_LABELS = {
    "create": "Angelegt",
    "update": "Geändert",
    "status": "Statuswechsel",
    "archive": "Archiviert",
    "invalidate": "Ungültig gesetzt",
    "delete": "Gelöscht",
    "submit": "Zur Prüfung eingereicht",
    "review_approve": "Prüfung bestanden",
    "review_reject": "Zurückgewiesen",
    "approve": "Freigegeben",
    "new_revision": "Neue Revision",
    "file_upload": "Datei hochgeladen",
    "file_new_version": "Neue Dateiversion",
    "file_download": "Datei heruntergeladen",
    "file_archive": "Datei archiviert",
    "file_invalidate": "Datei ungültig gesetzt",
    "file_update": "Dateiangaben geändert",
    "comment": "Kommentar",
    "login": "Anmeldung",
    "login_failed": "Fehlgeschlagene Anmeldung",
    "logout": "Abmeldung",
    "account_locked": "Konto gesperrt",
    "password_change": "Passwort geändert",
    "permission_denied": "Zugriff verweigert",
    "csrf_failed": "CSRF-Prüfung fehlgeschlagen",
    "settings": "Einstellung geändert",
    "module_enable": "Modul aktiviert",
    "module_disable": "Modul deaktiviert",
    "backup": "Sicherung erstellt",
    "restore": "Wiederherstellung",
    "import": "Import",
    "export": "Export",
    "link": "Verknüpfung",
    "unlink": "Verknüpfung entfernt",
    "migration": "Datenbankmigration",
}


def to_text(value: Any) -> str | None:
    """Wandelt einen Wert in eine stabile Textform für den Audit Trail um."""
    if value is None:
        return None
    if isinstance(value, bool):
        return "Ja" if value else "Nein"
    if isinstance(value, datetime):
        return value.isoformat(sep=" ", timespec="minutes")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, (list, tuple, set)):
        return ", ".join(sorted(to_text(v) or "" for v in value))
    if hasattr(value, "code") and getattr(value, "code", None):
        return str(value.code)
    if hasattr(value, "username"):
        return str(value.username)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def _hash_entry(e: AuditLog) -> str:
    payload = json.dumps(
        [
            e.timestamp.isoformat() if e.timestamp else None,
            e.user_id, e.username, e.action, e.entity_type, e.entity_id, e.entity_code,
            e.field, e.old_value, e.new_value, e.reason, e.ip_address, e.record_version,
            e.result, e.prev_hash,
        ],
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def log(
    db: Session,
    actor: Actor,
    action: str,
    *,
    entity_type: str | None = None,
    entity: Any = None,
    entity_id: int | None = None,
    entity_code: str | None = None,
    field: str | None = None,
    old: Any = None,
    new: Any = None,
    reason: str | None = None,
    version: int | None = None,
    result: str = "erfolgreich",
) -> AuditLog:
    if entity is not None:
        entity_id = entity_id or getattr(entity, "id", None)
        entity_code = entity_code or getattr(entity, "code", None)
        if version is None:
            version = getattr(entity, "version", None)
    last = db.query(AuditLog.entry_hash).order_by(AuditLog.id.desc()).first()
    entry = AuditLog(
        timestamp=utcnow(),
        user_id=actor.user_id,
        username=actor.username,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        entity_code=entity_code,
        field=field,
        old_value=to_text(old) if not isinstance(old, str) else old,
        new_value=to_text(new) if not isinstance(new, str) else new,
        reason=reason,
        ip_address=actor.ip,
        record_version=version,
        result=result,
        prev_hash=last[0] if last else None,
    )
    entry.entry_hash = _hash_entry(entry)
    db.add(entry)
    db.flush()
    return entry


def log_changes(db: Session, actor: Actor, entity_type: str, entity: Any,
                changes: dict[str, tuple[Any, Any]], reason: str | None, labels: dict[str, str] | None = None) -> None:
    for field_name, (old, new) in changes.items():
        log(db, actor, "update", entity_type=entity_type, entity=entity,
            field=(labels or {}).get(field_name, field_name), old=old, new=new, reason=reason)


def log_security(db: Session, actor: Actor, action: str, detail: str | None = None,
                 result: str = "erfolgreich") -> AuditLog:
    """Sicherheitsereignis (Anmeldung, Sperre, verweigerter Zugriff …)."""
    return log(db, actor, action, entity_type="security", new=detail, result=result)


def verify_chain(db: Session) -> dict:
    """Prüft die Hash-Kette. Ergebnis mit Anzahl und ggf. erstem Fehler."""
    prev: str | None = None
    count = 0
    for e in db.query(AuditLog).order_by(AuditLog.id).yield_per(1000):
        count += 1
        if e.prev_hash != prev:
            return {"ok": False, "count": count, "broken_id": e.id,
                    "message": f"Verkettung bei Eintrag {e.id} unterbrochen (Eintrag fehlt oder wurde eingefügt)."}
        if _hash_entry(e) != e.entry_hash:
            return {"ok": False, "count": count, "broken_id": e.id,
                    "message": f"Inhalt von Eintrag {e.id} wurde nachträglich verändert."}
        prev = e.entry_hash
    return {"ok": True, "count": count, "broken_id": None, "message": f"{count} Einträge geprüft – Kette intakt."}
