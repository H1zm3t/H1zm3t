"""Audit-Trail-Ansicht (nur lesend) mit Filtern, Export und Integritätsprüfung."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response

from ..core.formatting import parse_date
from ..models import AuditLog
from ..services import audit as audit_service
from ..services import export as export_service
from ..services.entities import ENTITY_DEFS
from .deps import Ctx, get_ctx

router = APIRouter()
PAGE = 50


def _query(ctx: Ctx, qp):
    q = ctx.db.query(AuditLog)
    errors = []
    try:
        if qp.get("von"):
            q = q.filter(AuditLog.timestamp >= datetime.combine(parse_date(qp["von"]), datetime.min.time()))
        if qp.get("bis"):
            q = q.filter(AuditLog.timestamp < datetime.combine(parse_date(qp["bis"]) + timedelta(days=1),
                                                               datetime.min.time()))
    except (ValueError, TypeError):
        errors.append("Ungültiger Zeitraum.")
    if qp.get("benutzer"):
        q = q.filter(AuditLog.username == qp["benutzer"])
    if qp.get("typ"):
        q = q.filter(AuditLog.entity_type == qp["typ"])
    if qp.get("kennung"):
        val = qp["kennung"].strip()
        q = q.filter((AuditLog.entity_code == val) | (AuditLog.entity_id == (int(val) if val.isdigit() else -1)))
    if qp.get("aktion"):
        q = q.filter(AuditLog.action == qp["aktion"])
    return q, errors


@router.get("/audit")
def audit_view(request: Request, ctx: Ctx = Depends(get_ctx)):
    ctx.require("view_audit")
    qp = request.query_params
    q, errors = _query(ctx, qp)
    total = q.count()
    try:
        page = max(1, int(qp.get("page", 1)))
    except ValueError:
        page = 1
    pages = max(1, (total + PAGE - 1) // PAGE)
    page = min(page, pages)
    entries = q.order_by(AuditLog.id.desc()).offset((page - 1) * PAGE).limit(PAGE).all()
    users = [u[0] for u in ctx.db.query(AuditLog.username).distinct().order_by(AuditLog.username) if u[0]]
    types = [t[0] for t in ctx.db.query(AuditLog.entity_type).distinct() if t[0]]
    actions = [a[0] for a in ctx.db.query(AuditLog.action).distinct().order_by(AuditLog.action)]
    base_qs = urlencode([(k, v) for k, v in qp.multi_items() if k != "page"])
    for e in errors:
        ctx.flash("error", e)
    return ctx.render("audit.html", entries=entries, total=total, page=page, pages=pages, users=users,
                      types=sorted(types), actions=actions, f=dict(qp), base_qs=base_qs)


@router.get("/audit/pruefen")
def verify(ctx: Ctx = Depends(get_ctx)):
    ctx.require("view_audit")
    result = audit_service.verify_chain(ctx.db)
    return ctx.redirect("/audit", "success" if result["ok"] else "error", result["message"])


@router.get("/audit/export.{fmt}")
def export(fmt: str, request: Request, ctx: Ctx = Depends(get_ctx)):
    ctx.require("view_audit")
    ctx.require("export")
    q, _ = _query(ctx, request.query_params)
    headers = ["Nr.", "Zeitpunkt", "Benutzer", "Aktion", "Typ", "Kennung", "DB-ID", "Feld", "Alter Wert", "Neuer Wert",
               "Grund", "IP", "Version", "Ergebnis", "Hash"]
    rows = [[a.id, a.timestamp, a.username, audit_service.ACTION_LABELS.get(a.action, a.action), a.entity_type,
             a.entity_code, a.entity_id, a.field, a.old_value, a.new_value, a.reason, a.ip_address, a.record_version,
             a.result, a.entry_hash] for a in q.order_by(AuditLog.id).limit(100000)]
    name = f"audit_trail_{date.today():%Y%m%d}"
    if fmt == "xlsx":
        return Response(export_service.to_xlsx([("Audit Trail", headers, rows)]),
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f'attachment; filename="{name}.xlsx"'})
    return Response(export_service.to_csv(headers, [[x.isoformat(sep=" ") if isinstance(x, datetime) else x
                                                     for x in r] for r in rows]),
                    media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{name}.csv"'})
