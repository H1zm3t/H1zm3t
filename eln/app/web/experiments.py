"""Versuche und Aufträge: Workflow, Prozessparameter, Dossiers, Snapshots."""
from __future__ import annotations

import json
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

from ..core.formatting import parse_number
from ..core.modules import get_registry
from ..models import Device, Experiment, ExperimentSeries, Measurement, ModuleRecord, Order, RecordSnapshot, Sample
from ..services import audit, records as rec, workflow
from ..services import export as export_service
from ..services import reports
from ..services.entities import ENTITY_DEFS, can_see
from ..services.recipes import check_sum
from .deps import Ctx, get_ctx
from .records import _ascii, get_obj, hooks

router = APIRouter()
EXP = ENTITY_DEFS["experiment"]
ORDER = ENTITY_DEFS["order"]


# --- Hooks Versuch ---------------------------------------------------------------

def _device_info(ctx: Ctx) -> dict:
    devices = ctx.db.query(Device).all()
    return {str(d.id): rec.device_warnings(ctx.db, [d]) for d in devices if rec.device_warnings(ctx.db, [d])}


def _exp_form_context(ctx: Ctx, obj) -> dict:
    params = obj.process_parameters if obj is not None else []
    return {"process_parameters": params, "device_warnings_json": json.dumps(_device_info(ctx), ensure_ascii=False)}


def _parse_params(ctx: Ctx, form, obj) -> tuple[dict, dict]:
    idx = sorted({int(k.split("-")[1]) for k in form.keys() if k.startswith("param-") and k.count("-") >= 2})
    params, errors = [], {}
    for i in idx:
        name = (form.get(f"param-{i}-name") or "").strip()
        value = (form.get(f"param-{i}-value") or "").strip()
        unit = (form.get(f"param-{i}-unit") or "").strip()
        if not name and not value:
            continue
        if not name:
            errors["process_parameters"] = "Jeder Prozessparameter benötigt eine Bezeichnung."
            continue
        entry = {"name": name[:120], "value": value[:120], "unit": unit[:30]}
        try:
            num = parse_number(value)
            if num is not None:
                entry["numeric"] = num
        except ValueError:
            pass
        params.append(entry)
    return {"process_parameters": params}, errors


def _apply_params(ctx: Ctx, obj: Experiment, extra: dict, reason: str | None) -> None:
    new = extra.get("process_parameters", [])
    old = obj.process_parameters
    if [(p["name"], p["value"], p["unit"]) for p in old] == [(p["name"], p["value"], p["unit"]) for p in new]:
        return
    obj.process_parameters_json = json.dumps(new, ensure_ascii=False)
    fmt = lambda ps: "; ".join(f"{p['name']}={p['value']} {p['unit']}".strip() for p in ps) or None  # noqa: E731
    audit.log(ctx.db, ctx.actor, "update", entity_type="experiment", entity=obj, field="Prozessparameter",
              old=fmt(old), new=fmt(new), reason=reason)


def _exp_validate(ctx: Ctx, values: dict, obj) -> dict:
    ids = values.get("devices") or []
    devices = ctx.db.query(Device).filter(Device.id.in_(ids)).all() if ids else []
    problems = rec.blocking_device_problems(ctx.db, devices)
    return {"devices": " ".join(problems)} if problems else {}


def _exp_after_save(ctx: Ctx, obj: Experiment, values: dict) -> list[str]:
    return rec.device_warnings(ctx.db, list(obj.devices))


def _exp_prefill(ctx: Ctx, raw: dict) -> dict:
    raw.setdefault("responsible_id", str(ctx.user.id))
    if raw.get("order_id"):
        order = ctx.db.get(Order, int(raw["order_id"])) if str(raw["order_id"]).isdigit() else None
        if order:
            raw.setdefault("objective", order.objective or "")
    return raw


def _exp_detail(ctx: Ctx, exp: Experiment) -> dict:
    db = ctx.db
    samples = db.query(Sample).filter(Sample.experiment_id == exp.id).order_by(Sample.code).all()
    measurements = db.query(Measurement).filter(Measurement.experiment_id == exp.id).order_by(Measurement.code).all()
    snapshots = (db.query(RecordSnapshot).filter(RecordSnapshot.entity_type == "experiment",
                                                 RecordSnapshot.entity_id == exp.id).order_by(RecordSnapshot.id).all())
    panels = []
    for module in get_registry().enabled(db):
        if module.departments and exp.department not in module.departments:
            continue
        for p in module.experiment_panels():
            panels.append({"module": module, "title": p.title, "template": p.template,
                           "context": p.context(db, exp, ctx.user)})
    module_records = db.query(ModuleRecord).filter(ModuleRecord.experiment_id == exp.id).all()
    return {
        "workflow_actions": workflow.available_actions(db, ctx.user, exp),
        "samples": samples, "measurements": measurements, "snapshots": snapshots, "module_panels": panels,
        "module_records": module_records, "registry": get_registry(),
        "device_warnings": rec.device_warnings(db, list(exp.devices)),
        "recipe_check": check_sum(db, exp.recipe) if exp.recipe else None,
    }


h = hooks("experiment")
h.form_template = "records/_experiment_extra.html"
h.form_context = _exp_form_context
h.parse_extra = _parse_params
h.apply_extra = _apply_params
h.validate = _exp_validate
h.after_save = _exp_after_save
h.prefill = _exp_prefill
h.detail_context = _exp_detail


# --- Hooks Auftrag -----------------------------------------------------------------

def _order_detail(ctx: Ctx, order: Order) -> dict:
    db = ctx.db
    exps = [e for e in order.experiments]
    by_status: dict[str, int] = {}
    for e in exps:
        by_status[e.status] = by_status.get(e.status, 0) + 1
    done = sum(1 for e in exps if e.status in ("freigegeben", "archiviert"))
    return {
        "experiments": exps, "series": db.query(ExperimentSeries).filter(ExperimentSeries.order_id == order.id).all(),
        "samples": db.query(Sample).filter(Sample.order_id == order.id).order_by(Sample.code).all(),
        "progress": round(done / len(exps) * 100) if exps else 0, "by_status": by_status,
    }


def _order_prefill(ctx: Ctx, raw: dict) -> dict:
    raw.setdefault("responsible_id", str(ctx.user.id))
    return raw


hooks("order").detail_context = _order_detail
hooks("order").prefill = _order_prefill


# --- Routen --------------------------------------------------------------------

@router.post("/versuche/{obj_id:int}/workflow")
async def workflow_action(obj_id: int, request: Request, ctx: Ctx = Depends(get_ctx)):
    exp = get_obj(ctx, EXP, obj_id)
    form = await request.form()
    action = form.get("action", "")
    message = workflow.perform(ctx.db, ctx.actor, exp, action, form.get("reason"))
    return ctx.redirect(f"/versuche/{exp.id}", "success", message)


@router.post("/versuche/{obj_id:int}/kopieren")
async def copy_experiment(obj_id: int, ctx: Ctx = Depends(get_ctx)):
    ctx.require("create")
    src = get_obj(ctx, EXP, obj_id)
    values = {
        "title": f"{src.title} (Kopie)", "order_id": src.order_id, "series_id": src.series_id,
        "experiment_type": src.experiment_type, "department": src.department, "responsible_id": ctx.user.id,
        "participants": [u.id for u in src.participants], "objective": src.objective, "hypothesis": src.hypothesis,
        "method_id": src.method_id, "recipe_id": src.recipe_id, "devices": [x.id for x in src.devices],
        "materials": [x.id for x in src.materials], "batches": [x.id for x in src.batches],
        "process_steps": src.process_steps, "tags": src.tags,
    }
    new = rec.create_record(ctx.db, ctx.actor, "experiment", values)
    new.process_parameters_json = src.process_parameters_json
    audit.log(ctx.db, ctx.actor, "update", entity_type="experiment", entity=new, field="Kopiert von",
              new=f"{src.code} Rev. {src.revision}")
    return ctx.redirect(f"/versuche/{new.id}", "success",
                        f"Versuch {new.code} als Kopie von {src.code} angelegt (ohne Ergebnisse).")


@router.get("/versuche/{obj_id:int}/snapshot/{snap_id:int}")
def view_snapshot(obj_id: int, snap_id: int, ctx: Ctx = Depends(get_ctx)):
    ctx.require("view")
    exp = get_obj(ctx, EXP, obj_id)
    snap = ctx.db.get(RecordSnapshot, snap_id)
    if snap is None or snap.entity_type != "experiment" or snap.entity_id != exp.id:
        raise HTTPException(404)
    import hashlib

    intact = hashlib.sha256(snap.data_json.encode("utf-8")).hexdigest() == snap.sha256
    return ctx.render("records/snapshot.html", exp=exp, snap=snap, data=snap.data, intact=intact)


def _dossier_response(ctx: Ctx, kind: str, obj, fmt: str):
    ctx.require("export")
    if kind == "experiment":
        dossier = export_service.experiment_dossier(ctx.db, ctx.user, obj)
        pdf = lambda: reports.experiment_pdf(dossier)  # noqa: E731
        base = f"Versuchsdossier_{obj.code}_Rev{obj.revision}"
    else:
        dossier = export_service.order_dossier(ctx.db, ctx.user, obj)
        pdf = lambda: reports.order_pdf(dossier)  # noqa: E731
        base = f"Auftragsdossier_{obj.code}"
    audit.log(ctx.db, ctx.actor, "export", entity_type=kind, entity=obj, new=f"Dossier als {fmt.upper()}")
    ctx.db.commit()
    base = _ascii(base)
    if fmt == "pdf":
        return Response(pdf(), media_type="application/pdf",
                        headers={"Content-Disposition": f'inline; filename="{base}.pdf"'})
    if fmt == "json":
        return Response(export_service.to_json(export_service.strip_private(dossier)), media_type="application/json",
                        headers={"Content-Disposition": f'attachment; filename="{base}.json"'})
    if fmt == "zip":
        return Response(export_service.dossier_zip(dossier, pdf(), base), media_type="application/zip",
                        headers={"Content-Disposition": f'attachment; filename="{base}.zip"'})
    if fmt == "xlsx" and kind == "experiment":
        sheets = [("Stammdaten", ["Feld", "Wert"], [[k, v] for k, v in dossier["Stammdaten"].items()] +
                   [["Status", dossier["Status"]], ["Revision", dossier["Revision"]]])]
        if dossier["Rezeptur"]:
            pos = dossier["Rezeptur"]["Positionen"]
            if pos:
                sheets.append(("Rezeptur", list(pos[0].keys()), [list(p.values()) for p in pos]))
        if dossier["Prozessparameter"]:
            sheets.append(("Prozessparameter", ["Parameter", "Wert", "Einheit"],
                           [[p.get("name"), p.get("value"), p.get("unit")] for p in dossier["Prozessparameter"]]))
        for sec in dossier["Modulabschnitte"]:
            sheets.append((sec["title"][:31], sec["headers"], sec["rows"]))
        if dossier["Prüfungen"]:
            sheets.append(("Prüfungen", [k for k in dossier["Prüfungen"][0] if k != "Werte"],
                           [[v for k, v in p.items() if k != "Werte"] for p in dossier["Prüfungen"]]))
        if dossier["Audit-Trail-Auszug"]:
            sheets.append(("Audit Trail", list(dossier["Audit-Trail-Auszug"][0].keys()),
                           [list(a.values()) for a in dossier["Audit-Trail-Auszug"]]))
        return Response(export_service.to_xlsx(sheets),
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f'attachment; filename="{base}.xlsx"'})
    raise HTTPException(404)


@router.get("/versuche/{obj_id:int}/dossier.{fmt}")
def experiment_dossier(obj_id: int, fmt: str, ctx: Ctx = Depends(get_ctx)):
    return _dossier_response(ctx, "experiment", get_obj(ctx, EXP, obj_id), fmt)


@router.get("/auftraege/{obj_id:int}/dossier.{fmt}")
def order_dossier(obj_id: int, fmt: str, ctx: Ctx = Depends(get_ctx)):
    return _dossier_response(ctx, "order", get_obj(ctx, ORDER, obj_id), fmt)
