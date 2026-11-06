"""JSON-Schnittstelle (für Oberfläche, Schnittstellen zum Access-System und spätere Integrationen).

Authentifizierung über die Anmeldesitzung; schreibende Zugriffe benötigen den CSRF-Header.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..models import Batch, Device
from ..services import records as rec
from ..services.entities import ENTITY_DEFS, apply_visibility, can_see
from ..services.export import entity_export_rows
from .deps import Ctx, get_ctx

router = APIRouter(prefix="/api/v1")


@router.get("/batches")
def batches(material_id: int | None = None, ctx: Ctx = Depends(get_ctx)):
    ctx.require("view")
    q = ctx.db.query(Batch)
    if material_id:
        q = q.filter(Batch.material_id == material_id)
    return [{"id": b.id, "code": b.code, "batch_number": b.batch_number, "status": b.status,
             "material_id": b.material_id} for b in q.order_by(Batch.batch_number)]


@router.get("/devices/check")
def device_check(ids: str = "", ctx: Ctx = Depends(get_ctx)):
    ctx.require("view")
    id_list = [int(i) for i in ids.split(",") if i.strip().isdigit()]
    devices = ctx.db.query(Device).filter(Device.id.in_(id_list)).all() if id_list else []
    return {"warnings": rec.device_warnings(ctx.db, devices),
            "blocking": rec.blocking_device_problems(ctx.db, devices)}


@router.get("/{key}")
def list_entities(key: str, ctx: Ctx = Depends(get_ctx)):
    ctx.require("view")
    if key not in ENTITY_DEFS:
        raise HTTPException(404, "Unbekannter Datensatztyp.")
    names, _labels, rows = entity_export_rows(ctx.db, ctx.user, key)
    return {"type": key, "count": len(rows), "rows": [dict(zip(names, r)) for r in rows]}


@router.get("/{key}/{obj_id:int}")
def get_entity(key: str, obj_id: int, ctx: Ctx = Depends(get_ctx)):
    ctx.require("view")
    if key not in ENTITY_DEFS:
        raise HTTPException(404, "Unbekannter Datensatztyp.")
    d = ENTITY_DEFS[key]
    obj = apply_visibility(ctx.db, ctx.user, key, ctx.db.query(d.model)).filter(d.model.id == obj_id).first()
    if obj is None or not can_see(ctx.db, ctx.user, key, obj):
        raise HTTPException(404, "Nicht gefunden.")
    names, _labels, rows = entity_export_rows(ctx.db, ctx.user, key)
    for r in rows:
        if r[0] == obj_id:
            return dict(zip(names, r))
    raise HTTPException(404, "Nicht gefunden.")
