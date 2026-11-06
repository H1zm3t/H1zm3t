"""Generisches Anlegen, Ändern und Archivieren von Datensätzen mit Audit Trail.

Kern-Datensätze werden nie physisch gelöscht – nur archiviert bzw. als
ungültig gekennzeichnet.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy.orm import Session

from ..models import Device, User
from . import audit
from .audit import Actor
from .entities import ENTITY_DEFS, EntityDef, get_def
from .numbering import next_code
from .system_settings import get_setting


class RecordError(Exception):
    """Fachlicher Fehler mit verständlicher Meldung."""


EXPERIMENT_OPEN_STATES = ("Entwurf", "geplant", "in Bearbeitung", "pausiert")


def reason_required(db: Session, key: str, obj: Any) -> bool:
    if obj is None or not get_setting(db, "reason_required_for_edits"):
        return False
    status = getattr(obj, "status", None)
    if key in ("task", "project", "series"):
        return False
    if key == "experiment":
        return status not in EXPERIMENT_OPEN_STATES or obj.revision > 1
    if key == "recipe":
        return status != "Entwurf"
    if key == "order":
        return status in ("abgeschlossen", "storniert", "archiviert")
    return True


def _target_model(ref: str):
    return User if ref == "user" else ENTITY_DEFS[ref].model


def _resolve_multi(db: Session, ref: str, ids: list[int]) -> list:
    if not ids:
        return []
    model = _target_model(ref)
    items = db.query(model).filter(model.id.in_(ids)).all()
    if len(items) != len(set(ids)):
        raise RecordError("Mindestens ein ausgewählter Eintrag existiert nicht mehr.")
    return items


def _check_refs(db: Session, d: EntityDef, values: dict) -> None:
    for spec in d.fields:
        if spec.kind == "ref" and values.get(spec.name):
            if db.get(_target_model(spec.ref), values[spec.name]) is None:
                raise RecordError(f"»{spec.label}«: Der ausgewählte Eintrag existiert nicht.")


def device_warnings(db: Session, devices: list[Device]) -> list[str]:
    warn_days = get_setting(db, "calibration_warning_days")
    today = date.today()
    messages = []
    for dev in devices:
        if dev.status in ("gesperrt", "außer Betrieb"):
            messages.append(f"Gerät {dev.code} ({dev.name}) ist »{dev.status}«.")
        elif dev.status == "in Wartung":
            messages.append(f"Gerät {dev.code} ({dev.name}) ist derzeit in Wartung.")
        if dev.next_calibration and dev.next_calibration < today:
            messages.append(f"Kalibrierung von {dev.code} ({dev.name}) ist seit {dev.next_calibration:%d.%m.%Y} überfällig.")
        elif dev.next_calibration and dev.next_calibration <= today + timedelta(days=warn_days):
            messages.append(f"Kalibrierung von {dev.code} ({dev.name}) wird am {dev.next_calibration:%d.%m.%Y} fällig.")
    return messages


def blocking_device_problems(db: Session, devices: list[Device]) -> list[str]:
    if not get_setting(db, "block_locked_devices"):
        return []
    today = date.today()
    return [
        f"Gerät {d.code} darf nicht verwendet werden (Status »{d.status}« oder Kalibrierung überfällig)."
        for d in devices
        if d.status in ("gesperrt", "außer Betrieb") or (d.next_calibration and d.next_calibration < today)
    ]


def _assign(db: Session, d: EntityDef, obj: Any, values: dict) -> dict[str, tuple[Any, Any]]:
    changes: dict[str, tuple[Any, Any]] = {}
    for spec in d.fields:
        if spec.name not in values:
            continue
        new = values[spec.name]
        if spec.kind == "multi_ref":
            new_items = _resolve_multi(db, spec.ref, new)
            old_items = list(getattr(obj, spec.name) or [])
            old_keys = sorted(audit.to_text(i) or "" for i in old_items)
            new_keys = sorted(audit.to_text(i) or "" for i in new_items)
            if old_keys != new_keys:
                changes[spec.name] = (", ".join(old_keys) or None, ", ".join(new_keys) or None)
                setattr(obj, spec.name, new_items)
            continue
        old = getattr(obj, spec.name)
        if old != new:
            if spec.kind == "ref":
                old_obj = db.get(_target_model(spec.ref), old) if old else None
                new_obj = db.get(_target_model(spec.ref), new) if new else None
                changes[spec.name] = (audit.to_text(old_obj), audit.to_text(new_obj))
            else:
                changes[spec.name] = (old, new)
            setattr(obj, spec.name, new)
    return changes


def create_record(db: Session, actor: Actor, key: str, values: dict, **extra) -> Any:
    d = get_def(key)
    _check_refs(db, d, values)
    obj = d.model()
    for k, v in d.default_values.items():
        setattr(obj, k, v)
    _assign(db, d, obj, values)
    for k, v in extra.items():
        setattr(obj, k, v)
    if not getattr(obj, "code", None):
        obj.code = next_code(db, key)
    obj.created_by_id = actor.user_id
    obj.updated_by_id = actor.user_id
    obj.version = 1
    db.add(obj)
    db.flush()
    audit.log(db, actor, "create", entity_type=key, entity=obj, new=getattr(obj, "label", obj.code))
    return obj


def ensure_editable(key: str, obj: Any) -> None:
    if key == "experiment" and obj.locked:
        raise RecordError(
            f"Versuch {obj.code} ist im Status »{obj.status}« gesperrt. "
            "Änderungen sind nur über eine neue Revision möglich."
        )
    if key == "recipe" and obj.status in ("ersetzt", "archiviert"):
        raise RecordError("Diese Rezepturrevision ist ersetzt bzw. archiviert und kann nicht mehr geändert werden.")


def update_record(db: Session, actor: Actor, key: str, obj: Any, values: dict, reason: str | None) -> dict:
    d = get_def(key)
    ensure_editable(key, obj)
    reason = (reason or "").strip() or None
    if reason_required(db, key, obj) and not reason:
        raise RecordError("Bitte einen Änderungsgrund angeben.")
    _check_refs(db, d, values)
    changes = _assign(db, d, obj, values)
    if not changes:
        return {}
    obj.version = (obj.version or 1) + 1
    obj.updated_by_id = actor.user_id
    labels = {s.name: s.label for s in d.fields}
    audit.log_changes(db, actor, key, obj, changes, reason, labels)
    db.flush()
    return changes


def set_status(db: Session, actor: Actor, key: str, obj: Any, new_status: str, reason: str | None) -> None:
    d = get_def(key)
    if not d.status_field:
        raise RecordError("Dieser Datensatztyp hat keinen Status.")
    old = getattr(obj, d.status_field)
    if old == new_status:
        return
    setattr(obj, d.status_field, new_status)
    obj.version = (obj.version or 1) + 1
    obj.updated_by_id = actor.user_id
    action = "archive" if new_status == d.archive_status else "status"
    audit.log(db, actor, action, entity_type=key, entity=obj, field="Status", old=old, new=new_status, reason=reason)
