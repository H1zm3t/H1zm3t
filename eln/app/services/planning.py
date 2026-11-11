"""Auftragsplanung: Fortschritt, Status je Kategorie, Tätigkeiten, Rohstoffliste, Durchführung,
Zusammensetzungen der Rezepturen eines Auftrags."""
from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from ..core import vocab
from ..models import Order, OrderActivity, OrderLogEntry, OrderMaterial, Recipe, User
from . import audit
from .audit import Actor
from .records import RecordError

STATUS_CLASS = {
    "abgeschlossen": "success", "praktisch abgeschlossen": "primary", "Dokumentation offen": "warning",
    "in Bearbeitung": "info", "bereit": "info", "geplant": "neutral", "wartet auf Voraussetzung": "warning",
    "zurückgestellt": "warning", "entfallen": "neutral", "nicht erforderlich": "neutral",
}


def activities(db: Session, order_id: int) -> list[OrderActivity]:
    return db.query(OrderActivity).filter_by(order_id=order_id).order_by(OrderActivity.position, OrderActivity.id).all()


def summary(acts: list[OrderActivity]) -> dict:
    """Fortschritt wie im Excel-Blatt: erledigte / gezählte Tätigkeiten."""
    counted = [a for a in acts if a.status not in vocab.ACTIVITY_NOT_COUNTED]
    done = [a for a in counted if a.status in vocab.ACTIVITY_DONE]
    started = [a for a in counted if a.started_on or a.status in ("in Bearbeitung", "praktisch abgeschlossen",
                                                                  "Dokumentation offen", "abgeschlossen")]
    if not counted:
        overall = "keine Tätigkeiten geplant"
    elif len(done) == len(counted):
        overall = "abgeschlossen"
    elif started:
        overall = "in Bearbeitung"
    else:
        overall = "noch nicht in Bearbeitung"
    return {"total": len(counted), "done": len(done), "open": len(counted) - len(done),
            "progress": round(len(done) / len(counted) * 100, 1) if counted else 0.0, "status": overall}


def category_status(acts: list[OrderActivity]) -> list[dict]:
    """Entspricht dem Excel-Blatt »Gesamtstatus«."""
    rows = []
    names = list(vocab.ACTIVITY_CATEGORIES) + sorted({a.category for a in acts} - set(vocab.ACTIVITY_CATEGORIES))
    for cat in names:
        items = [a for a in acts if a.category == cat and a.status not in vocab.ACTIVITY_NOT_COUNTED]
        done = [a for a in items if a.status in vocab.ACTIVITY_DONE]
        starts = [a.started_on for a in items if a.started_on]
        ends = [a.done_on for a in items if a.done_on]
        docs = [a.documented_on for a in items if a.documented_on]
        if not items:
            status = "nicht im Auftrag"
        elif len(done) == len(items):
            status = "abgeschlossen"
        elif starts or done or any(a.status == "in Bearbeitung" for a in items):
            status = "in Bearbeitung"
        else:
            status = "noch nicht in Bearbeitung"
        rows.append({"category": cat, "start": min(starts) if starts else None, "end": max(ends) if ends else None,
                     "documented": max(docs) if docs and len(docs) == len(items) else None,
                     "count": len(items), "done": len(done), "status": status})
    return rows


def find_user(db: Session, text: str | None) -> User | None:
    """Benutzer über Kürzel, Benutzername oder Namen finden (ohne Groß-/Kleinschreibung)."""
    t = (text or "").strip().lower()
    if not t:
        return None
    for u in db.query(User).all():
        if t in {(u.short_name or "").lower(), u.username.lower(), u.full_name.lower()}:
            return u
    return None


ACT_LABELS = {"category": "Kategorie", "activity": "Tätigkeit", "subject": "Probe / Rezeptur",
              "responsible": "Zuständig", "planned_on": "Geplant am", "started_on": "Begonnen am",
              "done_on": "Erledigt am", "documented_on": "Dokumentiert am", "status": "Status",
              "result": "Ergebnis / Ablage", "remark": "Bemerkung"}


def save_activity(db: Session, actor: Actor, order: Order, act: OrderActivity | None, values: dict) -> OrderActivity:
    if not (values.get("category") and values.get("activity")):
        raise RecordError("Kategorie und Tätigkeit sind Pflichtfelder.")
    if values.get("status") and values["status"] not in vocab.ACTIVITY_STATUS:
        raise RecordError("Ungültiger Status.")
    resp_text = (values.pop("responsible", None) or "").strip()
    user = find_user(db, resp_text)
    values["responsible_id"] = user.id if user else None
    values["responsible_text"] = None if user else (resp_text or None)
    # Statuslogik: Datumsangaben sinnvoll ergänzen
    if values.get("status") == "abgeschlossen" and not values.get("done_on"):
        values["done_on"] = date.today()
    if values.get("status") in ("in Bearbeitung", "abgeschlossen") and not values.get("started_on"):
        values["started_on"] = values.get("done_on") or date.today()
    if act is None:
        last = db.query(OrderActivity).filter_by(order_id=order.id).order_by(OrderActivity.position.desc()).first()
        act = OrderActivity(order_id=order.id, position=(last.position + 1) if last else 1, **values)
        db.add(act)
        db.flush()
        audit.log(db, actor, "create", entity_type="order", entity=order, field="Tätigkeit",
                  new=f"{act.position}. {act.category}: {act.activity}")
        return act
    for k, v in values.items():
        old = getattr(act, k)
        if old != v:
            label = ACT_LABELS.get("responsible" if k.startswith("responsible") else k, k)
            audit.log(db, actor, "update", entity_type="order", entity=order,
                      field=f"Tätigkeit {act.position} ({act.activity}): {label}", old=old, new=v)
            setattr(act, k, v)
    return act


def delete_activity(db: Session, actor: Actor, order: Order, act: OrderActivity, reason: str | None) -> None:
    if not reason:
        raise RecordError("Bitte eine Begründung angeben.")
    audit.log(db, actor, "delete", entity_type="order", entity=order, field="Tätigkeit",
              old=f"{act.position}. {act.category}: {act.activity} ({act.status or 'ohne Status'})", reason=reason)
    db.delete(act)


def add_log(db: Session, actor: Actor, order: Order, step: str, by: str | None, entry_date: date | None,
            remark: str | None, source: str = "manuell") -> OrderLogEntry:
    if not (step or "").strip():
        raise RecordError("Bitte den Arbeitsschritt beschreiben.")
    user = find_user(db, by) if by else actor.user
    last = db.query(OrderLogEntry).filter_by(order_id=order.id).order_by(OrderLogEntry.position.desc()).first()
    e = OrderLogEntry(order_id=order.id, position=(last.position + 1) if last else 1, step=step.strip(),
                      done_by_id=user.id if user else None, done_by_text=None if user else (by or None),
                      entry_date=entry_date or date.today(), remark=(remark or "").strip() or None, source=source)
    db.add(e)
    db.flush()
    audit.log(db, actor, "create", entity_type="order", entity=order, field="Durchführung", new=step.strip()[:300])
    return e


def log_entries(db: Session, order_id: int) -> list[OrderLogEntry]:
    return db.query(OrderLogEntry).filter_by(order_id=order_id).order_by(OrderLogEntry.position, OrderLogEntry.id).all()


def order_materials(db: Session, order_id: int) -> list[OrderMaterial]:
    return db.query(OrderMaterial).filter_by(order_id=order_id).order_by(OrderMaterial.position, OrderMaterial.id).all()


def add_material(db: Session, actor: Actor, order: Order, *, section: str, material_id: int, batch_id: int | None,
                 entry_date: date | None, remark: str | None, required_kg: float | None = None) -> OrderMaterial:
    from ..models import Batch, Material

    mat = db.get(Material, material_id)
    if mat is None:
        raise RecordError("Bitte ein Material auswählen.")
    if batch_id:
        b = db.get(Batch, batch_id)
        if b is None or b.material_id != mat.id:
            raise RecordError("Die Charge gehört nicht zum gewählten Material.")
    last = db.query(OrderMaterial).filter_by(order_id=order.id).order_by(OrderMaterial.position.desc()).first()
    om = OrderMaterial(order_id=order.id, position=(last.position + 1) if last else 1, section=section,
                       material_id=mat.id, batch_id=batch_id or None, entry_date=entry_date, remark=remark or None,
                       required_kg=required_kg)
    db.add(om)
    db.flush()
    audit.log(db, actor, "create", entity_type="order", entity=order, field="Rohstoffliste", new=mat.label)
    return om


def remove_material(db: Session, actor: Actor, order: Order, om: OrderMaterial) -> None:
    audit.log(db, actor, "delete", entity_type="order", entity=order, field="Rohstoffliste", old=om.material.label)
    db.delete(om)


# --- Zusammensetzungen --------------------------------------------------------

def order_recipes(db: Session, order_id: int) -> dict[str, list[Recipe]]:
    """Aktuelle Rezepturen des Auftrags, gruppiert nach Art."""
    groups: dict[str, list[Recipe]] = {}
    for r in db.query(Recipe).filter(Recipe.order_id == order_id, Recipe.status.notin_(("ersetzt", "archiviert"))) \
            .order_by(Recipe.id):
        groups.setdefault(r.recipe_type or "Sonstige", []).append(r)
    order = ["Masterbatch", "Pulvermischung", "Additivmischung", "Compound", "Sonstige"]
    return {k: groups[k] for k in order + sorted(set(groups) - set(order)) if k in groups}


def composition_matrix(recipes: list[Recipe]) -> dict:
    """Matrix Komponente × Rezeptur in Gew.-% (wie die Excel-Rezepturblätter)."""
    rows: dict[int, dict] = {}
    for r in recipes:
        for i in r.items:
            row = rows.setdefault(i.material_id, {"material": i.material, "source_recipe": i.source_recipe,
                                                  "values": {}, "order": len(rows)})
            row["values"][r.id] = (row["values"].get(r.id) or 0) + (i.weight_percent or 0)
            if i.source_recipe is not None:
                row["source_recipe"] = i.source_recipe
    ordered = sorted(rows.values(), key=lambda x: x["order"])
    return {"recipes": recipes, "rows": [{"material": x["material"], "source_recipe": x["source_recipe"],
                                          "cells": [x["values"].get(r.id) for r in recipes]} for x in ordered],
            "totals": [r.percent_sum for r in recipes]}


def resolved_composition(recipe: Recipe, _depth: int = 0) -> dict[int, tuple]:
    """Zusammensetzung bis auf die Rohstoffe aufgelöst (Masterbatche werden in ihre Bestandteile zerlegt).

    Rückgabe: {material_id: (material, gew_prozent)}
    """
    result: dict[int, tuple] = {}
    for i in recipe.items:
        pct = i.weight_percent or 0
        if i.source_recipe is not None and _depth < 5 and i.source_recipe.items:
            for mid, (mat, sub) in resolved_composition(i.source_recipe, _depth + 1).items():
                prev = result.get(mid, (mat, 0.0))[1]
                result[mid] = (mat, prev + pct * sub / 100.0)
        else:
            prev = result.get(i.material_id, (i.material, 0.0))[1]
            result[i.material_id] = (i.material, prev + pct)
    return result


def resolved_matrix(recipes: list[Recipe]) -> dict | None:
    if not any(i.source_recipe_id for r in recipes for i in r.items):
        return None
    comps = [resolved_composition(r) for r in recipes]
    mats: dict[int, object] = {}
    for c in comps:
        for mid, (mat, _) in c.items():
            mats.setdefault(mid, mat)
    rows = [{"material": mat, "cells": [c.get(mid, (None, None))[1] for c in comps]} for mid, mat in mats.items()]
    rows.sort(key=lambda r: -(max(v or 0 for v in r["cells"])))
    return {"recipes": recipes, "rows": rows}
