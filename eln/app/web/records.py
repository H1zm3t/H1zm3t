"""Generische Seiten für alle Kern-Datensatztypen: Liste, Detail, Anlegen, Bearbeiten, Status, Export.

Spezielle Datensatztypen (Versuch, Rezeptur, Messdaten) ergänzen über Hooks
zusätzliche Formularteile und Detailinhalte.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from jinja2 import TemplateNotFound

from ..core.forms import raw_from_form, validate_values
from ..core.formatting import de_date, de_number
from ..models import ApprovalRecord, AuditLog, Comment, Task
from ..services import export as export_service
from ..services import files as file_service
from ..services import records as rec
from ..services.entities import ENTITY_DEFS, EntityDef, apply_visibility, can_see, ref_options, resolve_path
from .deps import Ctx, get_ctx, json_dumps, templates

router = APIRouter()


@dataclass
class EntityHooks:
    # zusätzliche Formularteile: (template, parse(ctx, form, obj) -> (extra, errors), apply(ctx, obj, extra, reason))
    form_template: str | None = None
    form_context: Callable[[Ctx, Any], dict] | None = None
    parse_extra: Callable[[Ctx, Any, Any], tuple[dict, dict]] | None = None
    apply_extra: Callable[[Ctx, Any, dict, str | None], None] | None = None
    after_save: Callable[[Ctx, Any, dict], list[str]] | None = None
    validate: Callable[[Ctx, dict, Any], dict] | None = None
    detail_context: Callable[[Ctx, Any], dict] | None = None
    prefill: Callable[[Ctx, dict], dict] | None = None
    list_query: Callable[[Ctx, Any], Any] | None = None
    extra_columns: list[tuple[str, str, str]] = field(default_factory=list)


HOOKS: dict[str, EntityHooks] = {}


def hooks(key: str) -> EntityHooks:
    return HOOKS.setdefault(key, EntityHooks())


# --- Hilfsfunktionen für Templates --------------------------------------------

def _cell(obj, path: str, fmt: str, d: EntityDef):
    v = resolve_path(obj, path)
    if fmt == "date":
        return de_date(v)
    if fmt == "number":
        return de_number(v, 2) if v is not None else ""
    if fmt == "link":
        return {"text": v, "url": d.url_for(obj)}
    if v is None:
        return ""
    return v if isinstance(v, (int, float)) else str(v)


def list_rows(d: EntityDef, objs, columns) -> list[dict]:
    rows = []
    for o in objs:
        row = {"_url": d.url_for(o)}
        for i, (path, _label, fmt) in enumerate(columns):
            val = _cell(o, path, fmt, d)
            row[f"c{i}"] = val["text"] if isinstance(val, dict) else val
        rows.append(row)
    return rows


def field_display(ctx: Ctx, d: EntityDef, obj) -> list[dict]:
    """Aufbereitete Felder für die Detailansicht (gruppiert)."""
    out = []
    for spec in d.fields:
        value = getattr(obj, spec.name, None)
        item: dict[str, Any] = {"spec": spec, "group": spec.group or "Angaben", "kind": spec.kind}
        if spec.kind == "ref":
            target = getattr(obj, spec.name[:-3], None) if spec.name.endswith("_id") else None
            item["text"] = getattr(target, "label", None) or getattr(target, "full_name", None) or ""
            item["url"] = (ENTITY_DEFS[spec.ref].url_for(target) if target is not None and spec.ref in ENTITY_DEFS
                           else None)
        elif spec.kind == "multi_ref":
            item["items"] = [{"text": getattr(t, "label", str(t)),
                              "url": ENTITY_DEFS[spec.ref].url_for(t) if spec.ref in ENTITY_DEFS else None}
                             for t in (value or [])]
        elif spec.kind == "date":
            item["text"] = de_date(value)
        elif spec.kind == "float":
            item["text"] = de_number(value)
        elif spec.kind == "bool":
            item["text"] = "Ja" if value else "Nein"
        else:
            item["text"] = value or ""
        out.append(item)
    return out


def form_state(ctx: Ctx, d: EntityDef, obj=None, raw: dict | None = None) -> dict:
    """Werte und Auswahllisten für das Formular."""
    values: dict[str, Any] = {}
    options: dict[str, list] = {}
    for spec in d.fields:
        if raw is not None and spec.name in raw:
            values[spec.name] = raw[spec.name]
        elif obj is not None:
            v = getattr(obj, spec.name, None)
            if spec.kind == "multi_ref":
                v = [str(i.id) for i in (v or [])]
            elif spec.kind == "date":
                v = v.isoformat() if v else ""
            elif spec.kind == "float":
                from ..core.formatting import de_input_number

                v = de_input_number(v)
            values[spec.name] = "" if v is None else v
        else:
            values[spec.name] = d.default_values.get(spec.name, "")
        if spec.kind in ("ref", "multi_ref"):
            current = values.get(spec.name)
            ids = current if isinstance(current, list) else [current]
            ids = [int(i) for i in ids if str(i).isdigit()]
            options[spec.name] = ref_options(ctx.db, spec.ref, ids)
    return {"values": values, "options": options}


def get_obj(ctx: Ctx, d: EntityDef, obj_id: int):
    obj = ctx.db.get(d.model, obj_id)
    if obj is None:
        raise HTTPException(404, f"{d.label} wurde nicht gefunden.")
    if not can_see(ctx.db, ctx.user, d.key, obj):
        raise HTTPException(403, "Dieser Datensatz ist vertraulich.")
    return obj


def related_panels(ctx: Ctx, entity_type: str, obj) -> dict:
    db = ctx.db
    attachments = [a for a in file_service.list_for(db, entity_type, obj.id)
                   if file_service.can_view_attachment(ctx.user, a)]
    history = (db.query(AuditLog).filter(AuditLog.entity_type == entity_type, AuditLog.entity_id == obj.id)
               .order_by(AuditLog.id.desc()).limit(300).all())
    comments = (db.query(Comment).filter(Comment.entity_type == entity_type, Comment.entity_id == obj.id)
                .order_by(Comment.created_at).all())
    tasks = (db.query(Task).filter(Task.entity_type == entity_type, Task.entity_id == obj.id)
             .order_by(Task.status.desc(), Task.due_date).all())
    approvals = (db.query(ApprovalRecord).filter(ApprovalRecord.entity_type == entity_type,
                                                 ApprovalRecord.entity_id == obj.id).order_by(ApprovalRecord.id).all())
    locked_msg = file_service.entity_locked(db, entity_type, obj.id)
    from ..core.vocab import ATTACHMENT_CATEGORIES, CONFIDENTIALITY

    return {
        "entity_type": entity_type, "attachments": attachments,
        "images": [a for a in attachments if a.extension in file_service.PREVIEW_IMAGE_EXT and a.status != "ungültig"],
        "history": history, "comments": comments, "tasks": tasks, "approvals": approvals,
        "upload_locked": locked_msg, "attachment_categories": ATTACHMENT_CATEGORIES,
        "confidentiality_levels": CONFIDENTIALITY,
    }


# --- Routen-Fabrik --------------------------------------------------------------

def _make_routes(d: EntityDef) -> None:
    key = d.key

    @router.get(d.url, name=f"{key}_list")
    def list_view(request: Request, ctx: Ctx = Depends(get_ctx)):
        ctx.require("view")
        q = ctx.db.query(d.model)
        q = apply_visibility(ctx.db, ctx.user, key, q)
        show_all = request.query_params.get("alle") == "1"
        status = request.query_params.get("status", "")
        h = hooks(key)
        if h.list_query:
            q = h.list_query(ctx, q)
        if status and d.status_field:
            q = q.filter(getattr(d.model, d.status_field) == status)
        elif not show_all and d.archive_status and d.status_field:
            q = q.filter(getattr(d.model, d.status_field) != d.archive_status)
        mine = request.query_params.get("meine") == "1"
        if mine:
            for attr in ("responsible_id", "assignee_id", "created_by_id"):
                if hasattr(d.model, attr):
                    q = q.filter(getattr(d.model, attr) == ctx.user.id)
                    break
        objs = q.order_by(d.model.id.desc()).limit(5000).all()
        columns = d.columns + h.extra_columns
        status_options = []
        if d.status_field:
            spec = next((f for f in d.fields if f.name == d.status_field), None)
            status_options = list(spec.options) if spec else []
            if key == "experiment":
                from ..core.vocab import EXPERIMENT_STATUS

                status_options = list(EXPERIMENT_STATUS)
        return ctx.render("records/list.html", d=d, columns=columns, rows_json=json_dumps(list_rows(d, objs, columns)),
                          count=len(objs), show_all=show_all, status=status, status_options=status_options, mine=mine,
                          can_create=ctx.user.has(d.create_permission))

    def _render_form(ctx: Ctx, obj, raw=None, errors=None, reason="", extra_ctx=None):
        state = form_state(ctx, d, obj, raw)
        h = hooks(key)
        extra = h.form_context(ctx, obj) if h.form_context else {}
        if extra_ctx:
            extra.update(extra_ctx)
        groups: dict[str, list] = {}
        for spec in d.fields:
            if obj is None and key == "experiment" and spec.name == "status":
                continue
            groups.setdefault(spec.group or "", []).append(spec)
        return ctx.render("records/form.html", d=d, obj=obj, groups=groups, errors=errors or {}, reason=reason,
                          reason_required=rec.reason_required(ctx.db, key, obj) if obj else False,
                          extra_template=h.form_template, **state, **extra)

    @router.get(d.url + "/neu", name=f"{key}_new")
    def new_form(request: Request, ctx: Ctx = Depends(get_ctx)):
        ctx.require(d.create_permission)
        raw = {k: v for k, v in request.query_params.items() if any(f.name == k for f in d.fields)}
        for f in d.fields:
            if f.kind == "multi_ref" and f.name in request.query_params:
                raw[f.name] = request.query_params.getlist(f.name)
        h = hooks(key)
        if h.prefill:
            raw = h.prefill(ctx, raw)
        merged = {**d.default_values, **raw}
        return _render_form(ctx, None, raw=merged)

    async def _save(request: Request, ctx: Ctx, obj):
        form = await request.form()
        raw = raw_from_form(d.fields, form)
        values, errors = validate_values(d.fields, raw, f"Form_{key}")
        h = hooks(key)
        extra: dict = {}
        if h.parse_extra:
            extra, extra_errors = h.parse_extra(ctx, form, obj)
            errors = {**(errors or {}), **extra_errors}
        if values is not None and h.validate:
            errors.update(h.validate(ctx, values, obj))
        reason = (form.get("reason") or "").strip()
        if errors:
            ctx.flash("error", "Bitte prüfen Sie die markierten Felder.")
            return None, _render_form(ctx, obj, raw=raw, errors=errors, reason=reason,
                                      extra_ctx={"extra_raw": extra})
        try:
            if obj is None:
                obj = rec.create_record(ctx.db, ctx.actor, key, values)
                changed = True
            else:
                changed = bool(rec.update_record(ctx.db, ctx.actor, key, obj, values, reason))
            if h.apply_extra:
                h.apply_extra(ctx, obj, extra, reason or None)
            warnings = h.after_save(ctx, obj, values) if h.after_save else []
        except rec.RecordError as exc:
            ctx.db.rollback()
            ctx.flash("error", str(exc))
            fresh = ctx.db.get(d.model, obj.id) if obj is not None and obj.id else None
            return None, _render_form(ctx, fresh, raw=raw, errors={"__all__": str(exc)}, reason=reason,
                                      extra_ctx={"extra_raw": extra})
        for w in warnings:
            ctx.flash("warning", w)
        return obj, changed

    @router.post(d.url + "/neu")
    async def create(request: Request, ctx: Ctx = Depends(get_ctx)):
        ctx.require(d.create_permission)
        obj, result = await _save(request, ctx, None)
        if obj is None:
            return result
        return ctx.redirect(d.url_for(obj), "success", f"{d.label} {obj.code} wurde angelegt.")

    @router.get(d.url + "/{obj_id:int}", name=f"{key}_detail")
    def detail(obj_id: int, ctx: Ctx = Depends(get_ctx)):
        ctx.require("view")
        obj = get_obj(ctx, d, obj_id)
        h = hooks(key)
        extra = h.detail_context(ctx, obj) if h.detail_context else {}
        detail_template = f"records/detail_{key}.html"
        try:
            templates().env.get_template(detail_template)
        except TemplateNotFound:
            detail_template = None
        status_targets = []
        if d.status_field and key != "experiment":
            spec = next((f for f in d.fields if f.name == d.status_field), None)
            status_targets = [s for s in (spec.options if spec else []) if s != getattr(obj, d.status_field)]
        return ctx.render("records/detail.html", d=d, obj=obj, fields=field_display(ctx, d, obj),
                          detail_template=detail_template, status_targets=status_targets,
                          can_edit=ctx.user.has(d.edit_permission), **related_panels(ctx, key, obj), **extra)

    @router.get(d.url + "/{obj_id:int}/bearbeiten", name=f"{key}_edit")
    def edit_form(obj_id: int, ctx: Ctx = Depends(get_ctx)):
        ctx.require(d.edit_permission)
        obj = get_obj(ctx, d, obj_id)
        rec.ensure_editable(key, obj)
        return _render_form(ctx, obj)

    @router.post(d.url + "/{obj_id:int}/bearbeiten")
    async def update(obj_id: int, request: Request, ctx: Ctx = Depends(get_ctx)):
        ctx.require(d.edit_permission)
        obj = get_obj(ctx, d, obj_id)
        saved, result = await _save(request, ctx, obj)
        if saved is None:
            return result
        if result:
            return ctx.redirect(d.url_for(saved), "success", f"Änderungen an {saved.code} gespeichert "
                                                             f"(Version {saved.version}).")
        return ctx.redirect(d.url_for(saved), "info", "Keine Änderungen vorgenommen.")

    @router.post(d.url + "/{obj_id:int}/status")
    async def change_status(obj_id: int, request: Request, ctx: Ctx = Depends(get_ctx)):
        obj = get_obj(ctx, d, obj_id)
        form = await request.form()
        new_status = form.get("status", "")
        spec = next((f for f in d.fields if f.name == d.status_field), None)
        if key == "experiment" or spec is None or new_status not in spec.options:
            raise rec.RecordError("Ungültiger Status.")
        ctx.require("archive" if new_status == d.archive_status else d.edit_permission)
        reason = (form.get("reason") or "").strip() or None
        if (new_status == d.archive_status or rec.reason_required(ctx.db, key, obj)) and not reason:
            return ctx.redirect(d.url_for(obj), "error", "Bitte eine Begründung angeben.")
        rec.set_status(ctx.db, ctx.actor, key, obj, new_status, reason)
        if key == "task" and new_status == "erledigt":
            obj.completed_at = datetime.now().replace(microsecond=0)
        return ctx.redirect(d.url_for(obj), "success", f"Status auf »{new_status}« gesetzt.")

    @router.get(d.url + "/export.{fmt}", name=f"{key}_export")
    def export(fmt: str, ctx: Ctx = Depends(get_ctx)):
        ctx.require("export")
        names, labels, rows = export_service.entity_export_rows(ctx.db, ctx.user, key)
        stamp = date.today().strftime("%Y%m%d")
        from ..services import audit

        audit.log(ctx.db, ctx.actor, "export", entity_type=key, new=f"{len(rows)} Datensätze als {fmt.upper()}")
        ctx.db.commit()
        fname = f"{d.plural.lower()}_{stamp}"
        if fmt == "csv":
            return Response(export_service.to_csv(labels, rows), media_type="text/csv; charset=utf-8",
                            headers={"Content-Disposition": f'attachment; filename="{_ascii(fname)}.csv"'})
        if fmt == "xlsx":
            return Response(export_service.to_xlsx([(d.plural, labels, rows)]),
                            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            headers={"Content-Disposition": f'attachment; filename="{_ascii(fname)}.xlsx"'})
        if fmt == "json":
            data = [dict(zip(names, r)) for r in rows]
            return Response(export_service.to_json({"type": key, "count": len(data), "rows": data}),
                            media_type="application/json",
                            headers={"Content-Disposition": f'attachment; filename="{_ascii(fname)}.json"'})
        raise HTTPException(404)


def _ascii(name: str) -> str:
    return (name.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
            .encode("ascii", "ignore").decode())


def register_all() -> None:
    for d in ENTITY_DEFS.values():
        _make_routes(d)


register_all()
