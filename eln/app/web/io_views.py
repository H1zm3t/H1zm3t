"""Import (CSV/JSON/Excel) mit Prüflauf und Validierungsbericht; Exportübersicht."""
from __future__ import annotations

import base64

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

from ..services import importer
from ..services.entities import ENTITY_DEFS
from ..services.records import RecordError
from .deps import Ctx, get_ctx

router = APIRouter()
MAX_IMPORT_BYTES = 20 * 1024 * 1024


@router.get("/import")
def import_page(ctx: Ctx = Depends(get_ctx)):
    ctx.require("import")
    return ctx.render("io/import.html", importable=importer.IMPORTABLE)


@router.post("/import")
async def do_import(request: Request, ctx: Ctx = Depends(get_ctx)):
    ctx.require("import")
    form = await request.form()
    key = form.get("entity", "")
    if key not in importer.IMPORTABLE:
        raise RecordError("Bitte einen Datensatztyp wählen.")
    commit = form.get("commit") == "1"
    if form.get("payload"):  # Bestätigung nach erfolgreichem Prüflauf
        content = base64.b64decode(form.get("payload"))
        filename = form.get("filename", "")
    else:
        up = form.get("file")
        if not hasattr(up, "filename") or not up.filename:
            raise RecordError("Bitte eine Datei auswählen.")
        content = await up.read()
        filename = up.filename
    if len(content) > MAX_IMPORT_BYTES:
        raise RecordError("Die Importdatei ist zu groß (max. 20 MB).")
    rows = importer.read_table(filename, content)
    if not rows:
        raise RecordError("Die Datei enthält keine Datenzeilen.")
    if key == "measurement":
        report = importer.import_measurements(ctx.db, ctx.actor, rows, commit)
    else:
        report = importer.import_entities(ctx.db, ctx.actor, key, rows, commit)
    if report.errors:
        ctx.db.rollback()
    if report.committed:
        ctx.flash("success", f"{report.created} Datensätze importiert.")
    payload = base64.b64encode(content).decode() if report.ok and not commit else None
    return ctx.render("io/report.html", title=f"Import {importer.IMPORTABLE[key]}", report=report, key=key,
                      payload=payload, filename=filename, back="/import",
                      target_url=ENTITY_DEFS[key].url if key in ENTITY_DEFS else "/")


@router.get("/import/vorlage/{key}.{fmt}")
def template(key: str, fmt: str, ctx: Ctx = Depends(get_ctx)):
    ctx.require("view")
    if key not in importer.IMPORTABLE and key != "recipe_items":
        raise HTTPException(404)
    if fmt == "xlsx":
        return Response(importer.template_xlsx(key),
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f'attachment; filename="vorlage_{key}.xlsx"'})
    return Response(importer.template_csv(key), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="vorlage_{key}.csv"'})


@router.get("/export")
def export_page(ctx: Ctx = Depends(get_ctx)):
    ctx.require("export")
    return ctx.render("io/export.html", defs=ENTITY_DEFS)
