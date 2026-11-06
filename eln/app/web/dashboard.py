"""Dashboard – Inhalte abhängig von Rolle und angemeldetem Benutzer."""
from __future__ import annotations

import json
from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, or_

from ..core.vocab import EXPERIMENT_STATUS
from ..models import AuditLog, Device, Experiment, Order, Task
from ..services.entities import ENTITY_DEFS, entity_url, restricted_order_ids
from ..services.system_settings import get_setting
from .deps import Ctx, get_ctx

router = APIRouter()


@router.get("/")
def dashboard(ctx: Ctx = Depends(get_ctx)):
    ctx.require("view")
    db, user = ctx.db, ctx.user
    hidden = restricted_order_ids(db, user)

    def visible(q, model):
        if hidden and hasattr(model, "order_id"):
            q = q.filter(or_(model.order_id.is_(None), ~model.order_id.in_(hidden)))
        if hidden and model is Order:
            q = q.filter(~Order.id.in_(hidden))
        return q

    open_orders = visible(db.query(Order).filter(Order.status.in_(("offen", "in Bearbeitung", "pausiert"))), Order)
    my_orders_only = not user.role_keys & {"admin", "leitung", "pruefer", "leser"}
    orders = open_orders.order_by(Order.due_date.is_(None), Order.due_date).limit(8).all()
    running = visible(db.query(Experiment).filter(Experiment.status.in_(("in Bearbeitung", "geplant", "pausiert"))),
                      Experiment)
    if my_orders_only:
        running = running.filter(or_(Experiment.responsible_id == user.id,
                                     Experiment.participants.any(id=user.id)))
    running_list = running.order_by(Experiment.updated_at.desc()).limit(8).all()
    to_review = visible(db.query(Experiment).filter(Experiment.status == "zur Prüfung"), Experiment) \
        .order_by(Experiment.submitted_at).all()
    to_approve = visible(db.query(Experiment).filter(Experiment.status == "geprüft"), Experiment) \
        .order_by(Experiment.reviewed_at).all()
    corrections = visible(db.query(Experiment).filter(Experiment.status == "Korrektur erforderlich",
                                                      Experiment.responsible_id == user.id), Experiment).all()
    my_tasks = (db.query(Task).filter(Task.assignee_id == user.id, Task.status != "erledigt")
                .order_by(Task.due_date.is_(None), Task.due_date).limit(10).all())
    overdue = db.query(Task).filter(Task.status != "erledigt", Task.due_date < date.today())
    if not user.role_keys & {"admin", "leitung"}:
        overdue = overdue.filter(Task.assignee_id == user.id)
    overdue_tasks = overdue.order_by(Task.due_date).limit(10).all()

    status_counts = dict(visible(db.query(Experiment.status, func.count(Experiment.id)), Experiment)
                         .group_by(Experiment.status).all())
    dept_counts = dict(visible(db.query(Experiment.department, func.count(Experiment.id)), Experiment)
                       .group_by(Experiment.department).all())
    since = date.today().replace(day=1) - timedelta(days=330)
    monthly: dict[str, int] = {}
    for (created,) in visible(db.query(Experiment.created_at).filter(Experiment.created_at >= since), Experiment):
        key = created.strftime("%Y-%m")
        monthly[key] = monthly.get(key, 0) + 1
    months = []
    d = since.replace(day=1)
    while d <= date.today():
        months.append(d.strftime("%Y-%m"))
        d = (d + timedelta(days=32)).replace(day=1)

    warn_days = get_setting(db, "calibration_warning_days")
    device_alerts = db.query(Device).filter(
        Device.status != "außer Betrieb",
        or_(Device.status == "gesperrt", Device.next_calibration <= date.today() + timedelta(days=warn_days),
            Device.next_maintenance <= date.today() + timedelta(days=warn_days))).order_by(Device.next_calibration).all()

    recent_rows = (db.query(AuditLog).filter(AuditLog.entity_type.in_(list(ENTITY_DEFS)),
                                             AuditLog.action.in_(("create", "update", "status", "submit",
                                                                  "approve", "file_upload")))
                   .order_by(AuditLog.id.desc()).limit(80).all())
    recent, seen = [], set()
    for a in recent_rows:
        k = (a.entity_type, a.entity_id)
        if k in seen or a.entity_id is None:
            continue
        if a.entity_type in ("order", "experiment") and a.entity_id in hidden:
            continue
        seen.add(k)
        recent.append({"code": a.entity_code, "type": ENTITY_DEFS[a.entity_type].label, "url": entity_url(*k),
                       "user": a.username, "time": a.timestamp, "action": a.action})
        if len(recent) >= 10:
            break

    open_total = sum(v for k, v in status_counts.items() if k not in ("freigegeben", "archiviert", "abgebrochen"))
    charts = {
        "status": {"labels": [s for s in EXPERIMENT_STATUS if status_counts.get(s)],
                   "data": [status_counts[s] for s in EXPERIMENT_STATUS if status_counts.get(s)]},
        "departments": {"labels": [k or "(ohne)" for k in dept_counts], "data": list(dept_counts.values())},
        "monthly": {"labels": [f"{m[5:]}.{m[:4]}" for m in months], "data": [monthly.get(m, 0) for m in months]},
    }
    return ctx.render(
        "dashboard.html", orders=orders, open_orders_count=open_orders.count(), running=running_list,
        running_count=running.count(), to_review=to_review, to_approve=to_approve, corrections=corrections,
        my_tasks=my_tasks, overdue_tasks=overdue_tasks, recent=recent, device_alerts=device_alerts,
        open_total=open_total, charts_json=json.dumps(charts, ensure_ascii=False),
        show_review=user.has("review"), alert_limit=date.today() + timedelta(days=warn_days), show_approve=user.has("approve"),
    )
