"""Zentrale Suche mit Filtern und gespeicherten Suchabfragen."""
from __future__ import annotations

import json
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request

from ..core import vocab
from ..models import SavedQuery
from ..services import search as search_service
from ..services.entities import ENTITY_DEFS, ref_options
from .deps import Ctx, get_ctx

router = APIRouter()


def _saved(ctx: Ctx, scope: str):
    return (ctx.db.query(SavedQuery).filter(SavedQuery.scope == scope,
                                            (SavedQuery.user_id == ctx.user.id) | (SavedQuery.is_shared.is_(True)))
            .order_by(SavedQuery.name).all())


@router.get("/suche")
def search_page(request: Request, ctx: Ctx = Depends(get_ctx)):
    ctx.require("view")
    params = search_service.SearchParams.from_mapping(request.query_params)
    executed = bool(params.q or params.has_filters or params.types)
    result = search_service.search(ctx.db, ctx.user, params) if executed else None
    qs = dict(request.query_params)
    qs.pop("page", None)
    base_qs = urlencode([(k, v) for k, v in request.query_params.multi_items() if k != "page"])
    return ctx.render(
        "search.html", p=params, result=result, executed=executed, base_qs=base_qs,
        types=[(k, ENTITY_DEFS[k].plural) for k in search_service.SEARCHABLE_TYPES],
        statuses=sorted(set(vocab.EXPERIMENT_STATUS + vocab.ORDER_STATUS + vocab.SAMPLE_STATUS + vocab.BATCH_STATUS
                            + vocab.DEVICE_STATUS + vocab.TASK_STATUS + vocab.RECIPE_STATUS)),
        users=ref_options(ctx.db, "user"), devices=ref_options(ctx.db, "device"),
        materials=ref_options(ctx.db, "material"), batches=ref_options(ctx.db, "batch"),
        experiment_types=vocab.EXPERIMENT_TYPES, departments=vocab.DEPARTMENTS, sorts=search_service.SORTS,
        saved=_saved(ctx, "search"),
    )


@router.post("/suche/speichern")
async def save_search(request: Request, ctx: Ctx = Depends(get_ctx)):
    form = await request.form()
    name = (form.get("name") or "").strip()[:150]
    query = form.get("query") or ""
    if not name:
        return ctx.redirect("/suche?" + query, "error", "Bitte einen Namen für die Suche angeben.")
    ctx.db.add(SavedQuery(user_id=ctx.user.id, scope="search", name=name,
                          query_json=json.dumps({"qs": query}), is_shared=form.get("shared") == "1"))
    return ctx.redirect("/suche?" + query, "success", f"Suche »{name}« gespeichert.")


@router.get("/suche/gespeichert/{qid:int}")
def run_saved(qid: int, ctx: Ctx = Depends(get_ctx)):
    sq = ctx.db.get(SavedQuery, qid)
    if sq is None or (sq.user_id != ctx.user.id and not sq.is_shared):
        raise HTTPException(404)
    target = "/suche?" if sq.scope == "search" else "/auswertungen?"
    return ctx.redirect(target + sq.query.get("qs", ""))


@router.post("/suche/gespeichert/{qid:int}/loeschen")
def delete_saved(qid: int, ctx: Ctx = Depends(get_ctx)):
    sq = ctx.db.get(SavedQuery, qid)
    if sq is None or sq.user_id != ctx.user.id:
        raise HTTPException(404)
    target = "/suche" if sq.scope == "search" else "/auswertungen"
    ctx.db.delete(sq)
    return ctx.redirect(target, "success", "Gespeicherte Abfrage gelöscht.")
