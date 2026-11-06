"""Anbindung der Fachmodule an die Weboberfläche."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..core.modules import get_registry
from .deps import Ctx, get_ctx


def module_router_guard(key: str):
    """Abhängigkeit für Modulrouten: deaktivierte Module sind nicht erreichbar."""

    def guard(ctx: Ctx = Depends(get_ctx)) -> None:
        if not get_registry().is_enabled(ctx.db, key):
            raise HTTPException(404, "Dieses Modul ist deaktiviert. Aktivierung unter Administration → Module.")

    return Depends(guard)


router = APIRouter()


@router.get("/moduldatensatz/{rid:int}")
def module_record_redirect(rid: int, ctx: Ctx = Depends(get_ctx)):
    from ..core.declarative import module_record_url

    url = module_record_url(ctx.db, rid)
    if url is None:
        raise HTTPException(404)
    return ctx.redirect(url)
