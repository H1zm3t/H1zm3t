"""Auftrags-Dashboard: Tätigkeiten, Rohstoffliste, Durchführung, Zusammensetzungen
sowie Import des Excel-Formulars »Compoundierplan«."""
from __future__ import annotations

import json
import secrets
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request

from ..config import get_settings
from ..core import vocab
from ..core.formatting import parse_date, parse_number
from ..core.modules import get_registry
from ..models import Batch, Material, OrderActivity, OrderMaterial
from ..services import awt_import, planning
from ..services.entities import ENTITY_DEFS
from ..services.records import RecordError
from . import experiments  # noqa: F401 - stellt sicher, dass der Auftrags-Hook bereits registriert ist
from .deps import Ctx, get_ctx
from .records import get_obj, hooks

router = APIRouter()
ORDER = ENTITY_DEFS["order"]
MAX_BYTES = 30 * 1024 * 1024


def _order_planning(ctx: Ctx, order) -> dict:
    db = ctx.db
    acts = planning.activities(db, order.id)
    groups = planning.order_recipes(db, order.id)
    matrices = [{"type": t, "matrix": planning.composition_matrix(rs), "resolved": planning.resolved_matrix(rs)}
                for t, rs in groups.items()]
    runs = []
    if get_registry().is_enabled(db, "compounding"):
        from ..modules.compounding.models import CompoundingRun

        exp_ids = [e.id for e in order.experiments]
        if exp_ids:
            runs = db.query(CompoundingRun).filter(CompoundingRun.experiment_id.in_(exp_ids)) \
                .order_by(CompoundingRun.id).all()
    mats = planning.order_materials(db, order.id)
    sections: dict[str, list] = {}
    for m in mats:
        sections.setdefault(m.section, []).append(m)
    return {
        "activities": acts, "plan_summary": planning.summary(acts), "category_status": planning.category_status(acts),
        "activity_class": planning.STATUS_CLASS, "material_sections": sections, "log_entries": planning.log_entries(db, order.id),
        "matrices": matrices, "compounding_runs": runs, "activity_status": vocab.ACTIVITY_STATUS,
        "activity_categories": vocab.ACTIVITY_CATEGORIES,
        "activity_map_json": json.dumps(vocab.ACTIVITY_CATEGORIES, ensure_ascii=False),
        "section_names": vocab.MATERIAL_SECTIONS,
        "all_materials": db.query(Material).filter(Material.status != "ausgelaufen").order_by(Material.name).all(),
        "batch_map_json": json.dumps([{"id": b.id, "material_id": b.material_id, "label": b.batch_number}
                                      for b in db.query(Batch).order_by(Batch.batch_number)], ensure_ascii=False),
    }


_previous = hooks("order").detail_context


def _order_detail(ctx: Ctx, order) -> dict:
    data = _previous(ctx, order) if _previous else {}
    data.update(_order_planning(ctx, order))
    return data


hooks("order").detail_context = _order_detail


def _date(form, key):
    try:
        return parse_date(form.get(key))
    except (ValueError, TypeError):
        raise RecordError(f"Ungültiges Datum im Feld »{key}«.") from None


def _activity_values(form) -> dict:
    return {
        "category": (form.get("category") or "").strip()[:80], "activity": (form.get("activity") or "").strip()[:200],
        "subject": (form.get("subject") or "").strip()[:200] or None, "responsible": form.get("responsible"),
        "planned_on": _date(form, "planned_on"), "started_on": _date(form, "started_on"),
        "done_on": _date(form, "done_on"), "documented_on": _date(form, "documented_on"),
        "status": (form.get("status") or "").strip() or None, "result": (form.get("result") or "").strip() or None,
        "remark": (form.get("remark") or "").strip() or None,
    }


def _back(order) -> str:
    return f"/auftraege/{order.id}"


# --- Tätigkeiten ----------------------------------------------------------------

@router.post("/auftraege/{oid:int}/taetigkeiten")
async def add_activity(oid: int, request: Request, ctx: Ctx = Depends(get_ctx)):
    ctx.require("edit")
    order = get_obj(ctx, ORDER, oid)
    form = await request.form()
    values = _activity_values(form)
    values["status"] = values["status"] or "geplant"
    act = planning.save_activity(ctx.db, ctx.actor, order, None, values)
    return ctx.redirect(_back(order) + "#arbeitsplan", "success", f"Tätigkeit »{act.activity}« hinzugefügt.")


def _get_activity(ctx: Ctx, order, aid: int) -> OrderActivity:
    act = ctx.db.get(OrderActivity, aid)
    if act is None or act.order_id != order.id:
        raise HTTPException(404, "Tätigkeit nicht gefunden.")
    return act


@router.get("/auftraege/{oid:int}/taetigkeiten/{aid:int}")
def edit_activity_form(oid: int, aid: int, ctx: Ctx = Depends(get_ctx)):
    ctx.require("edit")
    order = get_obj(ctx, ORDER, oid)
    act = _get_activity(ctx, order, aid)
    return ctx.render("planning/activity_form.html", order=order, act=act, statuses=vocab.ACTIVITY_STATUS,
                      categories=vocab.ACTIVITY_CATEGORIES,
                      activity_map_json=json.dumps(vocab.ACTIVITY_CATEGORIES, ensure_ascii=False))


@router.post("/auftraege/{oid:int}/taetigkeiten/{aid:int}")
async def update_activity(oid: int, aid: int, request: Request, ctx: Ctx = Depends(get_ctx)):
    ctx.require("edit")
    order = get_obj(ctx, ORDER, oid)
    act = _get_activity(ctx, order, aid)
    form = await request.form()
    planning.save_activity(ctx.db, ctx.actor, order, act, _activity_values(form))
    return ctx.redirect(_back(order) + "#arbeitsplan", "success", "Tätigkeit gespeichert.")


@router.post("/auftraege/{oid:int}/taetigkeiten/{aid:int}/status")
async def quick_status(oid: int, aid: int, request: Request, ctx: Ctx = Depends(get_ctx)):
    """Schnellaktion aus der Tabelle: Status setzen (z. B. »in Bearbeitung«, »abgeschlossen«)."""
    ctx.require("edit")
    order = get_obj(ctx, ORDER, oid)
    act = _get_activity(ctx, order, aid)
    form = await request.form()
    status = form.get("status", "")
    if status not in vocab.ACTIVITY_STATUS:
        raise RecordError("Ungültiger Status.")
    values = {"category": act.category, "activity": act.activity, "subject": act.subject,
              "responsible": act.responsible_label or (ctx.user.short_name or ctx.user.username),
              "planned_on": act.planned_on, "started_on": act.started_on, "done_on": act.done_on,
              "documented_on": act.documented_on, "status": status, "result": act.result, "remark": act.remark}
    planning.save_activity(ctx.db, ctx.actor, order, act, values)
    return ctx.redirect(_back(order) + "#arbeitsplan", "success", f"»{act.activity}«: {status}.")


@router.post("/auftraege/{oid:int}/taetigkeiten/{aid:int}/loeschen")
async def delete_activity(oid: int, aid: int, request: Request, ctx: Ctx = Depends(get_ctx)):
    ctx.require("edit")
    order = get_obj(ctx, ORDER, oid)
    act = _get_activity(ctx, order, aid)
    form = await request.form()
    planning.delete_activity(ctx.db, ctx.actor, order, act, (form.get("reason") or "").strip() or None)
    return ctx.redirect(_back(order) + "#arbeitsplan", "success", "Tätigkeit entfernt (im Verlauf protokolliert).")


# --- Durchführung und Rohstoffliste ------------------------------------------------

@router.post("/auftraege/{oid:int}/durchfuehrung")
async def add_log(oid: int, request: Request, ctx: Ctx = Depends(get_ctx)):
    ctx.require("edit")
    order = get_obj(ctx, ORDER, oid)
    form = await request.form()
    planning.add_log(ctx.db, ctx.actor, order, form.get("step") or "", (form.get("by") or "").strip() or None,
                     _date(form, "entry_date"), form.get("remark"))
    return ctx.redirect(_back(order) + "#durchfuehrung", "success", "Arbeitsschritt eingetragen.")


@router.post("/auftraege/{oid:int}/rohstoffe")
async def add_material(oid: int, request: Request, ctx: Ctx = Depends(get_ctx)):
    ctx.require("edit")
    order = get_obj(ctx, ORDER, oid)
    form = await request.form()
    try:
        material_id = int(form.get("material_id") or 0)
        batch_id = int(form.get("batch_id")) if form.get("batch_id") else None
        required = parse_number(form.get("required_kg"))
    except ValueError:
        raise RecordError("Ungültige Eingabe in der Rohstoffliste.") from None
    section = form.get("section") or vocab.MATERIAL_SECTIONS[0]
    planning.add_material(ctx.db, ctx.actor, order, section=section[:80], material_id=material_id, batch_id=batch_id,
                          entry_date=_date(form, "entry_date"), remark=(form.get("remark") or "").strip() or None,
                          required_kg=required)
    return ctx.redirect(_back(order) + "#rohstoffe", "success", "Rohstoff hinzugefügt.")


@router.post("/auftraege/{oid:int}/rohstoffe/{mid:int}/loeschen")
async def remove_material(oid: int, mid: int, ctx: Ctx = Depends(get_ctx)):
    ctx.require("edit")
    order = get_obj(ctx, ORDER, oid)
    om = ctx.db.get(OrderMaterial, mid)
    if om is None or om.order_id != order.id:
        raise HTTPException(404)
    planning.remove_material(ctx.db, ctx.actor, order, om)
    return ctx.redirect(_back(order) + "#rohstoffe", "success", "Rohstoff aus der Liste entfernt.")


# --- Excel-Import ---------------------------------------------------------------------

def _tmp_dir() -> Path:
    d = get_settings().files_dir / "_tmp"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _tmp_path(token: str) -> Path:
    if not token or not all(c in "0123456789abcdef" for c in token) or len(token) != 32:
        raise RecordError("Ungültiger Importvorgang. Bitte die Datei erneut hochladen.")
    return _tmp_dir() / f"awt_{token}.xlsx"


@router.get("/auftraege/compoundierplan")
def import_form(ctx: Ctx = Depends(get_ctx)):
    ctx.require("import")
    return ctx.render("planning/import.html", plan=None)


@router.post("/auftraege/compoundierplan")
async def import_upload(request: Request, ctx: Ctx = Depends(get_ctx)):
    ctx.require("import")
    form = await request.form()
    if form.get("token"):  # Bestätigung nach der Vorschau
        path = _tmp_path(form.get("token"))
        if not path.exists():
            raise RecordError("Die hochgeladene Datei ist nicht mehr vorhanden. Bitte erneut hochladen.")
        content = path.read_bytes()
        filename = (form.get("filename") or "Compoundierplan.xlsx")[:200]
        plan = awt_import.parse(content)
        report = awt_import.apply(ctx.db, ctx.actor, plan, filename, content)
        ctx.db.commit()
        path.unlink(missing_ok=True)
        order = report["order"]
        for m in report["messages"][:5]:
            ctx.flash("warning", m)
        text = (f"Compoundierplan AWT {plan.awt_number} {'angelegt' if report['order_created'] else 'aktualisiert'}: "
                f"{report['activities']} Tätigkeiten, {report['materials']} Rohstoffe, "
                f"{report['recipes_new']} neue und {report['recipes_updated']} geänderte Rezepturen, "
                f"{report['runs']} Extrusionsprotokolle.")
        return ctx.redirect(f"/auftraege/{order.id}", "success", text)
    up = form.get("file")
    if not hasattr(up, "filename") or not up.filename:
        raise RecordError("Bitte eine Excel-Datei auswählen.")
    if not up.filename.lower().endswith((".xlsx", ".xlsm")):
        raise RecordError("Bitte die Datei im Format .xlsx hochladen (ältere .xls-Dateien vorher in Excel als .xlsx speichern).")
    content = await up.read()
    if len(content) > MAX_BYTES:
        raise RecordError("Die Datei ist zu groß (max. 30 MB).")
    plan = awt_import.parse(content)
    token = secrets.token_hex(16)
    _tmp_path(token).write_bytes(content)
    return ctx.render("planning/import.html", plan=plan, pv=awt_import.preview(ctx.db, plan), token=token,
                      filename=files_name(up.filename))


def files_name(name: str) -> str:
    from ..services.files import safe_display_name

    return safe_display_name(name)
