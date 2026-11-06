"""Weboberfläche des Compoundierungsmoduls."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Request

from ...core.forms import raw_from_form, validate_values
from ...core.formatting import de_input_number
from ...models import Device, EntityLink, Experiment, Material, Sample
from ...services import audit
from ...services import records as rec
from ...services.entities import can_see, ref_options
from ...services.records import RecordError
from ...web.deps import Ctx, get_ctx
from ...web.records import related_panels
from . import service
from .models import CompoundingRun

router = APIRouter(prefix="/module/compoundierung")
BASE = "/module/compoundierung"


def _config(ctx: Ctx) -> dict:
    from ...models import ModuleState

    st = ctx.db.get(ModuleState, "compounding")
    return st.config if st else {}


def _get(ctx: Ctx, run_id: int) -> CompoundingRun:
    run = ctx.db.get(CompoundingRun, run_id)
    if run is None:
        raise HTTPException(404, "Compoundierlauf nicht gefunden.")
    if not can_see(ctx.db, ctx.user, "experiment", run.experiment):
        raise HTTPException(403, "Der zugehörige Auftrag ist vertraulich.")
    return run


def _form_values(run: CompoundingRun | None, raw: dict | None, ctx: Ctx, preset: dict) -> dict:
    values = {}
    for spec in service.RUN_FIELDS:
        if raw is not None and spec.name in raw:
            values[spec.name] = raw[spec.name]
        elif run is not None:
            v = getattr(run, spec.name)
            if spec.kind == "datetime":
                v = v.strftime("%Y-%m-%dT%H:%M") if v else ""
            elif spec.kind == "float":
                v = de_input_number(v)
            values[spec.name] = "" if v is None else v
        else:
            values[spec.name] = preset.get(spec.name, "")
    return values


def _render_form(ctx: Ctx, run, raw=None, errors=None, tables=None, preset=None, reason=""):
    preset = preset or {}
    values = _form_values(run, raw, ctx, preset)
    options = {s.name: ref_options(ctx.db, s.ref, [int(values[s.name])] if str(values.get(s.name, "")).isdigit() else [])
               for s in service.RUN_FIELDS if s.kind == "ref"}
    groups: dict[str, list] = {}
    for s in service.RUN_FIELDS:
        groups.setdefault(s.group or "", []).append(s)
    if tables is None:
        if run is not None:
            tables = {
                "zones": [{"name": z.name, "set_temp": de_input_number(z.set_temp),
                           "actual_temp": de_input_number(z.actual_temp)} for z in run.zones],
                "feeders": [{"feed_point": f.feed_point, "feeder": f.feeder or "", "material_id": f.material_id or "",
                             "component": f.component or "", "set_rate": de_input_number(f.set_rate),
                             "actual_rate": de_input_number(f.actual_rate)} for f in run.feeders],
                "readings": [{k: de_input_number(getattr(r, k)) for k in ("minute", "screw_speed", "torque",
                                                                          "melt_pressure", "melt_temperature",
                                                                          "throughput")} | {"remark": r.remark or ""}
                             for r in run.readings],
            }
        else:
            device = ctx.db.get(Device, int(preset["device_id"])) if str(preset.get("device_id", "")).isdigit() else None
            tables = {"zones": [{"name": n, "set_temp": "", "actual_temp": ""}
                                for n in service.zone_template(ctx.db, device, _config(ctx))],
                      "feeders": [{"feed_point": "Haupteinzug", "feeder": "", "material_id": "", "component": "",
                                   "set_rate": "", "actual_rate": ""}],
                      "readings": []}
    cfg = _config(ctx)
    return ctx.render("compounding/form.html", run=run, groups=groups, values=values, options=options,
                      errors=errors or {}, tables=tables, reason=reason,
                      materials=ctx.db.query(Material).order_by(Material.name).all(),
                      zone_templates_json=json.dumps(cfg.get("zone_templates", {}), ensure_ascii=False),
                      default_zones_json=json.dumps(cfg.get("default_zones") or service.DEFAULT_ZONES,
                                                    ensure_ascii=False))


@router.get("")
def list_runs(request: Request, ctx: Ctx = Depends(get_ctx)):
    ctx.require("view")
    runs = [r for r in ctx.db.query(CompoundingRun).order_by(CompoundingRun.id.desc()).all()
            if can_see(ctx.db, ctx.user, "experiment", r.experiment)]
    return ctx.render("compounding/list.html", runs=runs)


@router.get("/neu")
def new_run(request: Request, ctx: Ctx = Depends(get_ctx)):
    ctx.require("create")
    preset = {"status": "geplant", "operator_id": str(ctx.user.id)}
    exp_id = request.query_params.get("experiment_id", "")
    if exp_id.isdigit():
        exp = ctx.db.get(Experiment, int(exp_id))
        if exp is not None:
            service.check_editable(None, exp)
            preset.update({"experiment_id": str(exp.id), "title": f"Compoundierung {exp.title}"[:200],
                           "recipe_id": str(exp.recipe_id or "")})
            extruder = next((d for d in exp.devices if d.device_type == "Extruder"), None)
            if extruder:
                preset["device_id"] = str(extruder.id)
    if request.query_params.get("device_id", "").isdigit():
        preset["device_id"] = request.query_params["device_id"]
    return _render_form(ctx, None, preset=preset)


async def _save(request: Request, ctx: Ctx, run: CompoundingRun | None):
    form = await request.form()
    raw = raw_from_form(service.RUN_FIELDS, form)
    values, errors = validate_values(service.RUN_FIELDS, raw, "CompoundingRun")
    tables, table_errors = service.parse_tables(ctx.db, form)
    reason = (form.get("reason") or "").strip() or None
    raw_tables = {
        "zones": service._rows(form, "zone", ("name", "set_temp", "actual_temp")),
        "feeders": service._rows(form, "feeder", ("feed_point", "feeder", "material_id", "component", "set_rate",
                                                   "actual_rate")),
        "readings": service._rows(form, "reading", ("minute", "screw_speed", "torque", "melt_pressure",
                                                     "melt_temperature", "throughput", "remark")),
    }
    if errors or table_errors:
        if table_errors:
            errors = {**(errors or {}), "__all__": " ".join(table_errors)}
        ctx.flash("error", "Bitte prüfen Sie die Eingaben.")
        return None, _render_form(ctx, run, raw=raw, errors=errors, tables=raw_tables, reason=reason or "")
    try:
        saved, warnings = service.save_run(ctx.db, ctx.actor, run, values, tables, reason)
    except RecordError as exc:
        ctx.db.rollback()
        fresh = ctx.db.get(CompoundingRun, run.id) if run is not None else None
        return None, _render_form(ctx, fresh, raw=raw, errors={"__all__": str(exc)}, tables=raw_tables,
                                  reason=reason or "")
    for w in warnings:
        ctx.flash("warning", w)
    return saved, None


@router.post("/neu")
async def create_run(request: Request, ctx: Ctx = Depends(get_ctx)):
    ctx.require("create")
    run, resp = await _save(request, ctx, None)
    if run is None:
        return resp
    return ctx.redirect(f"{BASE}/{run.id}", "success", f"Compoundierlauf {run.code} angelegt.")


@router.get("/vergleich")
def compare(request: Request, ctx: Ctx = Depends(get_ctx)):
    ctx.require("view")
    ids = [int(i) for i in request.query_params.getlist("ids") if i.isdigit()]
    all_runs = [r for r in ctx.db.query(CompoundingRun).order_by(CompoundingRun.code).all()
                if can_see(ctx.db, ctx.user, "experiment", r.experiment)]
    result = None
    if len(ids) >= 2:
        runs = [r for r in all_runs if r.id in ids]
        result = service.comparison(runs)
    elif ids:
        ctx.flash("info", "Bitte mindestens zwei Läufe auswählen.")
    return ctx.render("compounding/compare.html", all_runs=all_runs, ids=ids, result=result,
                      chart_json=json.dumps(result["chart"] if result else {}, ensure_ascii=False))


@router.get("/{run_id:int}")
def detail(run_id: int, ctx: Ctx = Depends(get_ctx)):
    ctx.require("view")
    run = _get(ctx, run_id)
    links = ctx.db.query(EntityLink).filter(EntityLink.source_type == "compounding_run",
                                            EntityLink.source_id == run.id, EntityLink.target_type == "sample").all()
    samples = [ctx.db.get(Sample, link.target_id) for link in links]
    chart = {
        "zones": {"labels": [z.name for z in run.zones], "set": [z.set_temp for z in run.zones],
                  "actual": [z.actual_temp for z in run.zones]},
        "readings": {"minutes": [r.minute for r in run.readings],
                     "series": {label: [getattr(r, attr) for r in run.readings] for attr, label in
                                (("screw_speed", "Drehzahl [1/min]"), ("torque", "Drehmoment [%]"),
                                 ("melt_pressure", "Massedruck [bar]"), ("melt_temperature", "Schmelzetemp. [°C]"),
                                 ("throughput", "Durchsatz [kg/h]"))}},
    }
    feed_total = sum(f.actual_rate or 0 for f in run.feeders)
    return ctx.render("compounding/detail.html", run=run, samples=[s for s in samples if s], chart_json=json.dumps(chart),
                      feed_total=feed_total, can_edit=ctx.user.has("edit") and not run.experiment.locked,
                      device_warnings=rec.device_warnings(ctx.db, [run.device]) if run.device else [],
                      params=service.NUMERIC_PARAMS, obj=run, **related_panels(ctx, "compounding_run", run))


@router.get("/{run_id:int}/bearbeiten")
def edit_run(run_id: int, ctx: Ctx = Depends(get_ctx)):
    ctx.require("edit")
    run = _get(ctx, run_id)
    service.check_editable(run, None)
    return _render_form(ctx, run)


@router.post("/{run_id:int}/bearbeiten")
async def update_run(run_id: int, request: Request, ctx: Ctx = Depends(get_ctx)):
    ctx.require("edit")
    run = _get(ctx, run_id)
    saved, resp = await _save(request, ctx, run)
    if saved is None:
        return resp
    return ctx.redirect(f"{BASE}/{saved.id}", "success", f"Compoundierlauf {saved.code} gespeichert.")


@router.post("/{run_id:int}/probe")
async def create_sample(run_id: int, request: Request, ctx: Ctx = Depends(get_ctx)):
    """Erzeugte Charge/Probe (Granulat) anlegen und mit dem Lauf verknüpfen."""
    ctx.require("create")
    run = _get(ctx, run_id)
    form = await request.form()
    name = (form.get("name") or "").strip() or f"Granulat {run.code}"
    try:
        from ...core.formatting import parse_number

        qty = parse_number(form.get("quantity"))
    except ValueError:
        raise RecordError("Ungültige Menge.") from None
    exp = run.experiment
    sample = rec.create_record(ctx.db, ctx.actor, "sample", {
        "name": name[:200], "sample_type": "Compound / Granulat", "origin": f"Compoundierung {run.code}",
        "order_id": exp.order_id, "experiment_id": exp.id, "recipe_id": run.recipe_id,
        "production_date": (run.start_time.date() if run.start_time else None), "quantity": qty,
        "unit": form.get("unit") or "kg", "storage_location": (form.get("storage_location") or "").strip() or None,
        "status": "vorhanden",
    })
    ctx.db.add(EntityLink(source_type="compounding_run", source_id=run.id, target_type="sample",
                          target_id=sample.id, relation="erzeugt", created_by_id=ctx.user.id))
    audit.log(ctx.db, ctx.actor, "link", entity_type="compounding_run", entity=run, field="Erzeugte Probe",
              new=sample.code)
    return ctx.redirect(f"{BASE}/{run.id}", "success", f"Probe {sample.code} angelegt und verknüpft.")
