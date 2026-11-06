"""Zusatzinhalte für Detailseiten der Stammdaten, Proben, Messdaten und Aufgaben."""
from __future__ import annotations

import json

from ..core.formatting import de_input_number, parse_number
from ..models import (Batch, Device, Experiment, Measurement, MeasurementValue, Method, Order, Recipe, RecipeItem,
                      Sample, Task, experiment_batches, experiment_devices, experiment_materials)
from ..services import audit
from ..services import records as rec
from .deps import Ctx
from .records import hooks


def _project(ctx: Ctx, p) -> dict:
    return {"orders": ctx.db.query(Order).filter(Order.project_id == p.id).order_by(Order.code.desc()).all()}


def _series(ctx: Ctx, s) -> dict:
    return {"experiments": ctx.db.query(Experiment).filter(Experiment.series_id == s.id).order_by(Experiment.code).all()}


def _material(ctx: Ctx, m) -> dict:
    db = ctx.db
    recipe_ids = [r[0] for r in db.query(RecipeItem.recipe_id).filter(RecipeItem.material_id == m.id).distinct()]
    exps = db.query(Experiment).filter(
        (Experiment.id.in_(db.query(experiment_materials.c.experiment_id)
                           .filter(experiment_materials.c.material_id == m.id)))
        | (Experiment.recipe_id.in_(recipe_ids))).order_by(Experiment.code.desc()).all()
    return {"batches": m.batches, "recipes": db.query(Recipe).filter(Recipe.id.in_(recipe_ids)).all(),
            "experiments": exps}


def _batch(ctx: Ctx, b) -> dict:
    db = ctx.db
    exps = db.query(Experiment).filter(Experiment.id.in_(
        db.query(experiment_batches.c.experiment_id).filter(experiment_batches.c.batch_id == b.id))).all()
    return {"samples": db.query(Sample).filter(Sample.batch_id == b.id).all(), "experiments": exps}


def _device(ctx: Ctx, d) -> dict:
    db = ctx.db
    exps = db.query(Experiment).filter(Experiment.id.in_(
        db.query(experiment_devices.c.experiment_id).filter(experiment_devices.c.device_id == d.id))) \
        .order_by(Experiment.code.desc()).all()
    return {"experiments": exps, "device_warnings": rec.device_warnings(db, [d]),
            "measurements": db.query(Measurement).filter(Measurement.device_id == d.id).all()}


def _method(ctx: Ctx, m) -> dict:
    return {"experiments": ctx.db.query(Experiment).filter(Experiment.method_id == m.id).all()}


def _sample(ctx: Ctx, s: Sample) -> dict:
    ancestors = []
    cur = s.parent
    seen = set()
    while cur is not None and cur.id not in seen:
        seen.add(cur.id)
        ancestors.insert(0, cur)
        cur = cur.parent

    def tree(node, depth=0, acc=None):
        acc = acc if acc is not None else []
        for c in sorted(node.children, key=lambda x: x.code):
            acc.append((depth, c))
            if depth < 10:
                tree(c, depth + 1, acc)
        return acc

    return {"ancestors": ancestors, "descendants": tree(s),
            "measurements": ctx.db.query(Measurement).filter(Measurement.sample_id == s.id).all()}


def _sample_prefill(ctx: Ctx, raw: dict) -> dict:
    """Unterprobe: Werte der übergeordneten Probe übernehmen."""
    pid = raw.get("parent_id")
    if pid and str(pid).isdigit():
        parent = ctx.db.get(Sample, int(pid))
        if parent:
            for attr in ("order_id", "experiment_id", "material_id", "recipe_id", "batch_id"):
                if not raw.get(attr) and getattr(parent, attr):
                    raw[attr] = str(getattr(parent, attr))
    if raw.get("experiment_id") and str(raw["experiment_id"]).isdigit() and not raw.get("order_id"):
        exp = ctx.db.get(Experiment, int(raw["experiment_id"]))
        if exp and exp.order_id:
            raw["order_id"] = str(exp.order_id)
    return raw


# --- Messdaten: Werte-Editor ------------------------------------------------------

def _meas_form_context(ctx: Ctx, m) -> dict:
    lines = []
    if m is not None:
        for v in m.values:
            parts = [de_input_number(v.x_value) if v.x_value is not None else "", de_input_number(v.value)]
            if v.label:
                parts.append(v.label)
            lines.append(";".join(parts))
    meta = json.dumps(m.meta, ensure_ascii=False, indent=1) if m is not None and m.meta else ""
    return {"values_text": "\n".join(lines), "meta_text": meta}


def _meas_parse(ctx: Ctx, form, m) -> tuple[dict, dict]:
    text = form.get("values_text") or ""
    values, errors = [], {}
    for n, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.replace("\t", ";").split(";")]
        try:
            if len(parts) == 1:
                x, y, label = None, parse_number(parts[0]), None
            else:
                x, y = parse_number(parts[0]), parse_number(parts[1])
                label = parts[2] if len(parts) > 2 and parts[2] else None
            if y is None:
                raise ValueError
        except ValueError:
            errors["values_text"] = f"Zeile {n}: »{line}« ist ungültig. Format: Wert  oder  x;Wert;Bezeichnung"
            break
        values.append((x, y, label))
    meta_text = (form.get("meta_text") or "").strip()
    meta = {}
    if meta_text:
        try:
            meta = json.loads(meta_text)
            if not isinstance(meta, dict):
                raise ValueError
        except ValueError:
            meta = {}
            for line in meta_text.splitlines():
                if "=" in line or ":" in line:
                    k, _, v = line.replace(":", "=", 1).partition("=")
                    meta[k.strip()] = v.strip()
    return {"values": values, "meta": meta}, errors


def _meas_apply(ctx: Ctx, m: Measurement, extra: dict, reason: str | None) -> None:
    new_vals = extra.get("values", [])
    old_vals = [(v.x_value, v.value, v.label) for v in m.values]
    if new_vals != old_vals:
        m.values.clear()
        ctx.db.flush()
        for i, (x, y, label) in enumerate(new_vals):
            m.values.append(MeasurementValue(idx=i, x_value=x, value=y, label=label))
        audit.log(ctx.db, ctx.actor, "update", entity_type="measurement", entity=m, field="Messwerte",
                  old="; ".join(f"{x}|{y}" for x, y, _ in old_vals) or None,
                  new="; ".join(f"{x}|{y}" for x, y, _ in new_vals) or None, reason=reason)
    new_meta = json.dumps(extra.get("meta", {}), ensure_ascii=False, sort_keys=True)
    if new_meta != json.dumps(m.meta, ensure_ascii=False, sort_keys=True):
        audit.log(ctx.db, ctx.actor, "update", entity_type="measurement", entity=m, field="Metadaten",
                  old=m.metadata_json, new=new_meta, reason=reason)
        m.metadata_json = new_meta


def _meas_detail(ctx: Ctx, m: Measurement) -> dict:
    points = [{"x": v.x_value if v.x_value is not None else i + 1, "y": v.value} for i, v in enumerate(m.values)]
    return {"stats": m.stats, "chart_json": json.dumps({"points": points, "x_label": m.x_name or "Nr.",
                                                        "y_label": f"{m.property_name} [{m.unit or '-'}]"})}


def _meas_validate(ctx: Ctx, values: dict, obj) -> dict:
    return {}


def _task_prefill(ctx: Ctx, raw: dict) -> dict:
    raw.setdefault("assignee_id", str(ctx.user.id))
    return raw


def _task_list(ctx: Ctx, q):
    if ctx.request.query_params.get("offen") == "1":
        q = q.filter(Task.status != "erledigt")
    return q


hooks("project").detail_context = _project
hooks("series").detail_context = _series
hooks("material").detail_context = _material
hooks("batch").detail_context = _batch
hooks("device").detail_context = _device
hooks("method").detail_context = _method
hooks("sample").detail_context = _sample
hooks("sample").prefill = _sample_prefill
mh = hooks("measurement")
mh.form_template = "records/_measurement_extra.html"
mh.form_context = _meas_form_context
mh.parse_extra = _meas_parse
mh.apply_extra = _meas_apply
mh.detail_context = _meas_detail
hooks("task").prefill = _task_prefill
hooks("task").list_query = _task_list


# --- Aufgaben: Bezug zu einem Datensatz ------------------------------------------

def _task_form_context(ctx: Ctx, t) -> dict:
    et = t.entity_type if t is not None else ctx.request.query_params.get("entity_type", "")
    eid = t.entity_id if t is not None else ctx.request.query_params.get("entity_id", "")
    return {"task_entity_type": et or "", "task_entity_id": eid or ""}


def _task_parse(ctx: Ctx, form, t) -> tuple[dict, dict]:
    from ..services.entities import get_entity

    et = (form.get("task_entity_type") or "").strip()
    eid = (form.get("task_entity_id") or "").strip()
    if et and eid.isdigit() and get_entity(ctx.db, et, int(eid)) is not None:
        return {"entity_type": et, "entity_id": int(eid)}, {}
    return {}, {}


def _task_apply(ctx: Ctx, t: Task, extra: dict, reason) -> None:
    if extra and t.entity_type is None:
        t.entity_type, t.entity_id = extra["entity_type"], extra["entity_id"]


def _task_detail(ctx: Ctx, t: Task) -> dict:
    from ..services.entities import entity_url, get_entity

    if t.entity_type and t.entity_id:
        obj = get_entity(ctx.db, t.entity_type, t.entity_id)
        if obj is not None:
            return {"task_target": {"url": entity_url(t.entity_type, t.entity_id),
                                    "label": getattr(obj, "label", getattr(obj, "code", ""))}}
    return {"task_target": None}


th = hooks("task")
th.form_template = "records/_task_extra.html"
th.form_context = _task_form_context
th.parse_extra = _task_parse
th.apply_extra = _task_apply
th.detail_context = _task_detail
