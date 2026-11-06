"""Status- und Freigabeprozess für Versuche.

Ablauf: in Bearbeitung → abgeschlossen → zur Prüfung → (geprüft →) freigegeben.
Freigegebene Stände sind gesperrt; Änderungen erfolgen über eine neue Revision.
Bei Einreichung und Freigabe wird ein unveränderlicher Datenstand (Snapshot)
mit SHA-256-Prüfsumme gespeichert.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from sqlalchemy.orm import Session

from ..db import utcnow
from ..models import ApprovalRecord, Attachment, Experiment, Measurement, RecordSnapshot, Sample, User
from . import audit
from .audit import Actor
from .records import RecordError, RecordPermissionError
from .system_settings import get_setting

LOCKED_STATES = {"zur Prüfung", "geprüft", "freigegeben", "archiviert", "abgebrochen"}

# Einfache Statuswechsel (ohne Prüf-/Freigabeschritt)
SIMPLE_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "Entwurf": ("geplant", "in Bearbeitung", "abgebrochen"),
    "geplant": ("in Bearbeitung", "Entwurf", "abgebrochen"),
    "in Bearbeitung": ("pausiert", "abgebrochen"),
    "pausiert": ("in Bearbeitung", "abgebrochen"),
    "abgeschlossen": ("in Bearbeitung",),
    "Korrektur erforderlich": ("in Bearbeitung",),
    "freigegeben": ("archiviert",),
    "abgebrochen": ("archiviert",),
}


@dataclass
class WorkflowAction:
    key: str
    label: str
    style: str = "secondary"
    needs_reason: bool = False
    confirm: str | None = None


def experiment_snapshot_data(db: Session, exp: Experiment) -> dict:
    """Vollständiger, serialisierbarer Datenstand eines Versuchs."""
    def d(v):
        return v.isoformat() if v else None

    samples = db.query(Sample).filter(Sample.experiment_id == exp.id).order_by(Sample.code).all()
    measurements = db.query(Measurement).filter(Measurement.experiment_id == exp.id).order_by(Measurement.code).all()
    attachments = (
        db.query(Attachment)
        .filter(Attachment.entity_type == "experiment", Attachment.entity_id == exp.id)
        .order_by(Attachment.id)
        .all()
    )
    recipe = None
    if exp.recipe:
        recipe = {
            "code": exp.recipe.code, "revision": exp.recipe.revision, "name": exp.recipe.name,
            "items": [
                {"position": i.position, "material_code": i.material.code, "material_number": i.material.material_number,
                 "material": i.material.name, "batch": i.batch.batch_number if i.batch else None,
                 "function": i.function, "target_amount": i.target_amount, "unit": i.unit,
                 "actual_amount": i.actual_amount, "weight_percent": i.weight_percent, "tolerance": i.tolerance,
                 "remark": i.remark}
                for i in exp.recipe.items
            ],
        }
    return {
        "code": exp.code, "revision": exp.revision, "title": exp.title, "status": exp.status,
        "order": exp.order.code if exp.order else None, "series": exp.series.code if exp.series else None,
        "experiment_type": exp.experiment_type, "department": exp.department,
        "objective": exp.objective, "hypothesis": exp.hypothesis,
        "responsible": exp.responsible.username if exp.responsible else None,
        "participants": sorted(u.username for u in exp.participants),
        "planned_date": d(exp.planned_date), "actual_date": d(exp.actual_date),
        "method": exp.method.label if exp.method else None,
        "devices": sorted(x.code for x in exp.devices), "materials": sorted(x.code for x in exp.materials),
        "batches": sorted(x.code for x in exp.batches), "used_samples": sorted(x.code for x in exp.used_samples),
        "recipe": recipe, "process_steps": exp.process_steps, "process_parameters": exp.process_parameters,
        "observations": exp.observations, "deviations": exp.deviations, "raw_data": exp.raw_data,
        "results": exp.results, "evaluation": exp.evaluation, "conclusion": exp.conclusion,
        "follow_up": exp.follow_up, "tags": exp.tags,
        "samples": [{"code": s.code, "name": s.name, "type": s.sample_type} for s in samples],
        "measurements": [
            {"code": m.code, "property": m.property_name, "unit": m.unit,
             "values": [[v.x_value, v.value] for v in m.values]} for m in measurements
        ],
        "attachments": [
            {"file_uid": a.file_uid, "name": a.original_filename, "sha256": a.sha256, "version": a.version,
             "status": a.status} for a in attachments
        ],
    }


def create_snapshot(db: Session, actor: Actor, exp: Experiment, kind: str) -> RecordSnapshot:
    data = experiment_snapshot_data(db, exp)
    text = json.dumps(data, ensure_ascii=False, sort_keys=True)
    snap = RecordSnapshot(entity_type="experiment", entity_id=exp.id, revision=exp.revision, kind=kind,
                          data_json=text, sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
                          created_by_id=actor.user_id)
    db.add(snap)
    db.flush()
    return snap


def _set(db: Session, actor: Actor, exp: Experiment, new_status: str, action: str, reason: str | None) -> None:
    old = exp.status
    exp.status = new_status
    exp.locked = new_status in LOCKED_STATES
    exp.version += 1
    exp.updated_by_id = actor.user_id
    exp.updated_at = utcnow()
    audit.log(db, actor, action, entity_type="experiment", entity=exp, field="Status", old=old, new=new_status,
              reason=reason)


def _require(user: User, permission: str, text: str) -> None:
    if not user.has(permission):
        raise RecordPermissionError(f"Keine Berechtigung: {text}.")


def _independent(db: Session, user: User, exp: Experiment, step: str) -> None:
    if not get_setting(db, "require_independent_review"):
        return
    if user.id in {exp.responsible_id, exp.submitted_by_id}:
        raise RecordError(
            f"Unabhängige {step} erforderlich: Sie sind verantwortlich für diesen Versuch oder haben ihn eingereicht."
        )
    if step == "Freigabe" and user.id == exp.reviewed_by_id:
        raise RecordError("Die Freigabe muss durch eine andere Person als die Prüfung erfolgen.")


def available_actions(db: Session, user: User, exp: Experiment) -> list[WorkflowAction]:
    acts: list[WorkflowAction] = []
    s = exp.status
    if user.has("edit"):
        for target in SIMPLE_TRANSITIONS.get(s, ()):
            if target == "archiviert" and not user.has("archive"):
                continue
            label = {"in Bearbeitung": "Bearbeitung starten" if s in ("Entwurf", "geplant") else "Wieder aufnehmen",
                     "pausiert": "Pausieren", "abgebrochen": "Abbrechen", "geplant": "Als geplant markieren",
                     "Entwurf": "Zurück zu Entwurf", "archiviert": "Archivieren"}.get(target, target)
            if s in ("abgeschlossen", "Korrektur erforderlich") and target == "in Bearbeitung":
                label = "Wieder öffnen"
            acts.append(WorkflowAction(f"status:{target}", label,
                                       "danger" if target in ("abgebrochen", "archiviert") else "secondary",
                                       needs_reason=target in ("abgebrochen", "archiviert", "pausiert"),
                                       confirm=f"Status auf »{target}« setzen?" if target in ("abgebrochen", "archiviert") else None))
    if s == "in Bearbeitung" and user.has("complete"):
        acts.append(WorkflowAction("complete", "Abschließen", "primary"))
    if s == "abgeschlossen" and user.has("complete"):
        acts.append(WorkflowAction("submit", "Zur Prüfung einreichen", "primary",
                                   confirm="Der Versuch wird gesperrt und zur Prüfung eingereicht. Fortfahren?"))
    if s == "zur Prüfung" and user.has("review"):
        acts.append(WorkflowAction("review_approve", "Prüfung bestanden", "success",
                                   confirm="Prüfung bestätigen? Dieser Vermerk wird mit Ihrem Namen gespeichert."))
        acts.append(WorkflowAction("review_reject", "Zurückweisen", "danger", needs_reason=True))
    if s == "geprüft" and user.has("approve"):
        acts.append(WorkflowAction("approve", "Freigeben (Abteilungsleitung)", "success",
                                   confirm="Versuch endgültig freigeben?"))
        acts.append(WorkflowAction("review_reject", "Zurückweisen", "danger", needs_reason=True))
    if s == "freigegeben" and user.has("edit"):
        acts.append(WorkflowAction("new_revision", "Neue Revision anlegen", "secondary", needs_reason=True,
                                   confirm="Eine neue Revision entsperrt den Versuch zur Bearbeitung. Der freigegebene Stand bleibt erhalten."))
    return acts


def perform(db: Session, actor: Actor, exp: Experiment, action: str, reason: str | None = None) -> str:
    """Führt eine Workflow-Aktion aus und gibt eine Erfolgsmeldung zurück."""
    user = actor.user
    assert user is not None
    reason = (reason or "").strip() or None
    now = utcnow()

    if action.startswith("status:"):
        target = action.split(":", 1)[1]
        _require(user, "edit", "Status ändern")
        if target not in SIMPLE_TRANSITIONS.get(exp.status, ()):
            raise RecordError(f"Wechsel von »{exp.status}« nach »{target}« ist nicht zulässig.")
        if target == "archiviert":
            _require(user, "archive", "Archivieren")
        if target in ("abgebrochen", "archiviert", "pausiert") and not reason:
            raise RecordError("Bitte eine Begründung angeben.")
        _set(db, actor, exp, target, "archive" if target == "archiviert" else "status", reason)
        return f"Status auf »{target}« gesetzt."

    if action == "complete":
        _require(user, "complete", "Abschließen")
        if exp.status != "in Bearbeitung":
            raise RecordError("Nur Versuche »in Bearbeitung« können abgeschlossen werden.")
        missing = [label for attr, label in (("results", "Ergebnisse"), ("conclusion", "Schlussfolgerung"))
                   if not getattr(exp, attr)]
        if missing:
            raise RecordError("Vor dem Abschluss bitte ausfüllen: " + ", ".join(missing) + ".")
        exp.completed_at = now
        if not exp.actual_date:
            exp.actual_date = now.date()
        _set(db, actor, exp, "abgeschlossen", "status", reason)
        return "Versuch abgeschlossen. Er kann jetzt zur Prüfung eingereicht werden."

    if action == "submit":
        _require(user, "complete", "Einreichen")
        if exp.status != "abgeschlossen":
            raise RecordError("Nur abgeschlossene Versuche können eingereicht werden.")
        exp.submitted_at = now
        exp.submitted_by_id = user.id
        exp.reviewed_by_id = None
        exp.reviewed_at = None
        _set(db, actor, exp, "zur Prüfung", "submit", reason)
        snap = create_snapshot(db, actor, exp, "Einreichung")
        db.add(ApprovalRecord(entity_type="experiment", entity_id=exp.id, revision=exp.revision, step="Einreichung",
                              decision="eingereicht", comment=reason, user_id=user.id, snapshot_id=snap.id))
        return "Versuch zur Prüfung eingereicht und gesperrt."

    if action == "review_approve":
        _require(user, "review", "Prüfen")
        if exp.status != "zur Prüfung":
            raise RecordError("Der Versuch befindet sich nicht in Prüfung.")
        _independent(db, user, exp, "Prüfung")
        exp.reviewed_at = now
        exp.reviewed_by_id = user.id
        manager = get_setting(db, "require_manager_approval")
        snap = create_snapshot(db, actor, exp, "Prüfung")
        db.add(ApprovalRecord(entity_type="experiment", entity_id=exp.id, revision=exp.revision, step="Prüfung",
                              decision="bestanden", comment=reason, user_id=user.id, snapshot_id=snap.id))
        if manager:
            _set(db, actor, exp, "geprüft", "review_approve", reason)
            return "Prüfung bestätigt. Die Freigabe durch die Abteilungsleitung steht aus."
        exp.approved_at = now
        exp.approved_by_id = user.id
        _set(db, actor, exp, "freigegeben", "approve", reason)
        return "Prüfung bestätigt – der Versuch ist freigegeben und gesperrt."

    if action == "approve":
        _require(user, "approve", "Freigeben")
        if exp.status != "geprüft":
            raise RecordError("Nur geprüfte Versuche können freigegeben werden.")
        if not (user.role_keys & {"leitung", "admin"}):
            raise RecordPermissionError("Die zweite Freigabe ist der Abteilungsleitung vorbehalten.")
        _independent(db, user, exp, "Freigabe")
        exp.approved_at = now
        exp.approved_by_id = user.id
        snap = create_snapshot(db, actor, exp, "Freigabe")
        db.add(ApprovalRecord(entity_type="experiment", entity_id=exp.id, revision=exp.revision, step="Freigabe",
                              decision="freigegeben", comment=reason, user_id=user.id, snapshot_id=snap.id))
        _set(db, actor, exp, "freigegeben", "approve", reason)
        return "Versuch freigegeben und gesperrt."

    if action == "review_reject":
        if exp.status == "zur Prüfung":
            _require(user, "review", "Zurückweisen")
        elif exp.status == "geprüft":
            _require(user, "approve", "Zurückweisen")
        else:
            raise RecordError("Zurückweisen ist in diesem Status nicht möglich.")
        if not reason:
            raise RecordError("Bitte eine Begründung für die Zurückweisung angeben.")
        db.add(ApprovalRecord(entity_type="experiment", entity_id=exp.id, revision=exp.revision,
                              step="Prüfung" if exp.status == "zur Prüfung" else "Freigabe",
                              decision="zurückgewiesen", comment=reason, user_id=user.id))
        _set(db, actor, exp, "Korrektur erforderlich", "review_reject", reason)
        return "Versuch zur Korrektur zurückgewiesen."

    if action == "new_revision":
        _require(user, "edit", "Neue Revision")
        if exp.status != "freigegeben":
            raise RecordError("Eine neue Revision kann nur von einem freigegebenen Versuch erstellt werden.")
        if not reason:
            raise RecordError("Bitte einen Änderungsgrund für die neue Revision angeben.")
        old_rev = exp.revision
        exp.revision += 1
        exp.approved_at = exp.approved_by_id = None
        exp.reviewed_at = exp.reviewed_by_id = None
        exp.submitted_at = exp.submitted_by_id = None
        exp.completed_at = None
        audit.log(db, actor, "new_revision", entity_type="experiment", entity=exp, field="Revision",
                  old=str(old_rev), new=str(exp.revision), reason=reason)
        _set(db, actor, exp, "in Bearbeitung", "status", reason)
        return f"Revision {exp.revision} angelegt. Der freigegebene Stand Rev. {old_rev} bleibt unverändert gespeichert."

    raise RecordError("Unbekannte Aktion.")
