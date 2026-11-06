"""Deklarative Fachmodule (Grundgerüste).

Ein deklaratives Modul beschreibt nur seine Felder (``FieldSpec``). Erfassung,
Liste, Detailseite, Audit Trail, Anhänge, Versuchsverknüpfung, Dossier und
Auswertung werden automatisch bereitgestellt. Die Daten liegen in der
generischen Tabelle ``module_records`` (JSON). Sobald ein Modul eigene
Logik oder Tabellen benötigt, wird es wie das Compoundierungsmodul zu einem
vollständigen Modul ausgebaut.
"""
from __future__ import annotations

import json
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Request

from .forms import FieldSpec, raw_from_form, validate_values
from .formatting import de_date, de_datetime, de_input_number, de_number
from .modules import AnalysisDataset, DossierSection, ExperimentPanel, ModuleBase, NavEntry, SearchHit

LINK_FIELDS = (
    FieldSpec("title", "Bezeichnung", required=True, width="full", group="Zuordnung"),
    FieldSpec("experiment_id", "Versuch", kind="ref", ref="experiment", group="Zuordnung"),
    FieldSpec("sample_id", "Probe", kind="ref", ref="sample", group="Zuordnung"),
    FieldSpec("device_id", "Gerät", kind="ref", ref="device", group="Zuordnung"),
)


def _jsonable(v):
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    return v


class DeclarativeModule(ModuleBase):
    slug: str = ""
    fields: tuple[FieldSpec, ...] = ()
    record_label: str = "Datensatz"

    def all_fields(self) -> tuple[FieldSpec, ...]:
        return LINK_FIELDS + tuple(self.fields)

    @property
    def base_url(self) -> str:
        return f"/module/{self.slug}"

    def nav_entries(self):
        return [NavEntry(self.name, self.base_url, icon=self.icon)]

    def experiment_panels(self):
        module = self

        def ctx(db, experiment, user):
            from ..models import ModuleRecord

            recs = db.query(ModuleRecord).filter(ModuleRecord.module_key == module.key,
                                                 ModuleRecord.experiment_id == experiment.id).all()
            return {"records": recs, "module": module, "experiment": experiment}

        return [ExperimentPanel(self.name, "module_records/panel.html", ctx)]

    def search(self, db, term, user):
        from ..models import ModuleRecord

        like = f"%{term}%"
        q = db.query(ModuleRecord).filter(ModuleRecord.module_key == self.key,
                                          (ModuleRecord.title.ilike(like)) | (ModuleRecord.data_json.ilike(like)))
        return [SearchHit("module_record", r.id, r.code, r.title, f"{self.base_url}/{r.id}", status=r.status,
                          date=r.created_at, type_label=self.name) for r in q.limit(50)]

    def analysis_datasets(self):
        numeric = [f.name for f in self.fields if f.kind in ("float", "int")]
        if not numeric:
            return []
        module = self

        def loader(db, user):
            from ..models import ModuleRecord

            rows = []
            for r in db.query(ModuleRecord).filter(ModuleRecord.module_key == module.key):
                row = {"code": r.code, "experiment": r.experiment.code if r.experiment else "(ohne)",
                       "sample": r.sample.code if r.sample else "(ohne)",
                       "device": r.device.name if r.device else "(ohne)", "created": r.created_at.date()}
                for f in module.fields:
                    row[f.name] = r.data.get(f.name)
                rows.append(row)
            return rows

        fields = {"experiment": "Versuch", "sample": "Probe", "device": "Gerät"}
        fields.update({f.name: f.label + (f" [{f.unit}]" if f.unit else "") for f in self.fields})
        return [AnalysisDataset(f"mod_{self.key}", self.name, fields, numeric, loader, date_field="created")]

    def dossier_sections(self, db, experiment):
        return []  # Moduldatensätze werden im Kern-Dossier generisch ausgegeben

    def get_entity(self, db, entity_type, entity_id):
        if entity_type == "module_record":
            from ..models import ModuleRecord

            r = db.get(ModuleRecord, entity_id)
            return r if r is not None and r.module_key == self.key else None
        return None

    def entity_url(self, entity_type, entity_id):
        return None  # über get_record_url aufgelöst (siehe unten)

    def router(self):
        return build_router(self)


def display_value(spec: FieldSpec, value) -> str:
    if value in (None, ""):
        return ""
    if spec.kind == "float":
        return de_number(value)
    if spec.kind == "date":
        return de_date(value)
    if spec.kind == "datetime":
        return de_datetime(value)
    if spec.kind == "bool":
        return "Ja" if value else "Nein"
    return str(value)


def build_router(module: DeclarativeModule) -> APIRouter:
    from ..models import ModuleRecord
    from ..services import audit
    from ..services.entities import can_see, ref_options
    from ..services.numbering import next_code
    from ..services.records import RecordError
    from ..web.deps import Ctx, get_ctx
    from ..web.records import related_panels

    router = APIRouter(prefix=module.base_url)
    specs = module.all_fields()
    link_names = {f.name for f in LINK_FIELDS}

    def get_rec(ctx: Ctx, rid: int) -> ModuleRecord:
        r = ctx.db.get(ModuleRecord, rid)
        if r is None or r.module_key != module.key:
            raise HTTPException(404)
        if r.experiment is not None and not can_see(ctx.db, ctx.user, "experiment", r.experiment):
            raise HTTPException(403)
        return r

    def form_values(r, raw):
        vals = {}
        for s in specs:
            if raw is not None and s.name in raw:
                vals[s.name] = raw[s.name]
                continue
            if r is None:
                vals[s.name] = ""
                continue
            v = getattr(r, s.name) if s.name in link_names else r.data.get(s.name)
            if s.kind == "float":
                v = de_input_number(v)
            vals[s.name] = "" if v is None else v
        return vals

    def render_form(ctx: Ctx, r, raw=None, errors=None):
        values = form_values(r, raw)
        options = {s.name: ref_options(ctx.db, s.ref) for s in specs if s.kind == "ref"}
        groups: dict[str, list] = {}
        for s in specs:
            groups.setdefault(s.group or "Messdaten", []).append(s)
        return ctx.render("module_records/form.html", module=module, rec=r, groups=groups, values=values,
                          options=options, errors=errors or {})

    def check_lock(ctx: Ctx, experiment_id):
        if experiment_id:
            from ..models import Experiment

            exp = ctx.db.get(Experiment, experiment_id)
            if exp is not None and exp.locked:
                raise RecordError(f"Versuch {exp.code} ist gesperrt (»{exp.status}«).")

    @router.get("")
    def list_view(ctx: Ctx = Depends(get_ctx)):
        ctx.require("view")
        recs = ctx.db.query(ModuleRecord).filter(ModuleRecord.module_key == module.key) \
            .order_by(ModuleRecord.id.desc()).all()
        recs = [r for r in recs if r.experiment is None or can_see(ctx.db, ctx.user, "experiment", r.experiment)]
        cols = [f for f in module.fields if f.kind in ("float", "int", "text", "select", "date")][:5]
        return ctx.render("module_records/list.html", module=module, records=recs, cols=cols,
                          display_value=display_value)

    @router.get("/neu")
    def new_view(request: Request, ctx: Ctx = Depends(get_ctx)):
        ctx.require("create")
        raw = {k: v for k, v in request.query_params.items() if k in link_names}
        if raw.get("experiment_id", "").isdigit():
            check_lock(ctx, int(raw["experiment_id"]))
        return render_form(ctx, None, raw)

    async def save(request: Request, ctx: Ctx, r):
        form = await request.form()
        raw = raw_from_form(specs, form)
        values, errors = validate_values(specs, raw, f"Mod_{module.key}")
        if errors:
            ctx.flash("error", "Bitte prüfen Sie die markierten Felder.")
            return None, render_form(ctx, r, raw, errors)
        check_lock(ctx, values.get("experiment_id"))
        if r is not None:
            check_lock(ctx, r.experiment_id)
        data = {s.name: _jsonable(values[s.name]) for s in module.fields}
        reason = (form.get("reason") or "").strip() or None
        if r is None:
            r = ModuleRecord(code=next_code(ctx.db, module.key, prefix=module.key[:3].upper()),
                             module_key=module.key, title=values["title"], experiment_id=values["experiment_id"],
                             sample_id=values["sample_id"], device_id=values["device_id"],
                             data_json=json.dumps(data, ensure_ascii=False), created_by_id=ctx.user.id,
                             updated_by_id=ctx.user.id)
            ctx.db.add(r)
            ctx.db.flush()
            audit.log(ctx.db, ctx.actor, "create", entity_type="module_record", entity=r,
                      new=f"{module.name}: {r.title}")
            return r, None
        old = r.data
        changed = False
        for name in ("title", "experiment_id", "sample_id", "device_id"):
            if getattr(r, name) != values[name]:
                audit.log(ctx.db, ctx.actor, "update", entity_type="module_record", entity=r, field=name,
                          old=getattr(r, name), new=values[name], reason=reason)
                setattr(r, name, values[name])
                changed = True
        for s in module.fields:
            if old.get(s.name) != data.get(s.name):
                audit.log(ctx.db, ctx.actor, "update", entity_type="module_record", entity=r, field=s.label,
                          old=old.get(s.name), new=data.get(s.name), reason=reason)
                changed = True
        if changed:
            r.data_json = json.dumps(data, ensure_ascii=False)
            r.version += 1
            r.updated_by_id = ctx.user.id
        return r, None

    @router.post("/neu")
    async def create(request: Request, ctx: Ctx = Depends(get_ctx)):
        ctx.require("create")
        r, resp = await save(request, ctx, None)
        if r is None:
            return resp
        return ctx.redirect(f"{module.base_url}/{r.id}", "success", f"{module.record_label} {r.code} angelegt.")

    @router.get("/{rid:int}")
    def detail(rid: int, ctx: Ctx = Depends(get_ctx)):
        ctx.require("view")
        r = get_rec(ctx, rid)
        rows = [(s, display_value(s, r.data.get(s.name))) for s in module.fields]
        return ctx.render("module_records/detail.html", module=module, rec=r, rows=rows, obj=r,
                          **related_panels(ctx, "module_record", r))

    @router.get("/{rid:int}/bearbeiten")
    def edit(rid: int, ctx: Ctx = Depends(get_ctx)):
        ctx.require("edit")
        r = get_rec(ctx, rid)
        check_lock(ctx, r.experiment_id)
        return render_form(ctx, r)

    @router.post("/{rid:int}/bearbeiten")
    async def update(rid: int, request: Request, ctx: Ctx = Depends(get_ctx)):
        ctx.require("edit")
        r = get_rec(ctx, rid)
        saved, resp = await save(request, ctx, r)
        if saved is None:
            return resp
        return ctx.redirect(f"{module.base_url}/{saved.id}", "success", "Gespeichert.")

    return router


def module_record_url(db, entity_id: int) -> str | None:
    from ..models import ModuleRecord
    from .modules import get_registry

    r = db.get(ModuleRecord, entity_id)
    if r is None:
        return None
    m = get_registry().get(r.module_key)
    return f"{m.base_url}/{r.id}" if isinstance(m, DeclarativeModule) else None
