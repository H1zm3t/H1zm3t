"""Rezepturen: Positionstabelle, Summenprüfung, Skalierung, Kopie/Revision, Vergleich, Import/Export."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from fastapi.responses import Response

from ..core.formatting import de_input_number, parse_number
from ..core.vocab import UNITS
from ..models import Batch, Experiment, Material, Recipe, Sample
from ..services import export as export_service
from ..services import importer, recipes as recipe_service
from ..services.entities import ENTITY_DEFS
from ..services.records import RecordError, ensure_editable, reason_required
from .deps import Ctx, get_ctx
from .records import _ascii, get_obj, hooks

router = APIRouter()
RECIPE = ENTITY_DEFS["recipe"]


def _recipe_detail(ctx: Ctx, recipe: Recipe) -> dict:
    db = ctx.db
    revisions = db.query(Recipe).filter(Recipe.code == recipe.code).order_by(Recipe.revision).all()
    scale_rows = None
    scale_error = None
    total_raw = ctx.request.query_params.get("skalieren")
    unit = ctx.request.query_params.get("einheit", recipe.total_unit or "kg")
    if total_raw:
        try:
            total = parse_number(total_raw)
            scale_rows = recipe_service.scaled_amounts(recipe, total or 0, unit)
        except (ValueError, RecordError) as exc:
            scale_error = str(exc)
    return {
        "sum_check": recipe_service.check_sum(db, recipe), "revisions": revisions,
        "experiments": db.query(Experiment).filter(Experiment.recipe_id == recipe.id).all(),
        "samples": db.query(Sample).filter(Sample.recipe_id == recipe.id).all(),
        "scale_rows": scale_rows, "scale_error": scale_error, "scale_total": total_raw or "", "scale_unit": unit,
        "other_recipes": db.query(Recipe).filter(Recipe.id != recipe.id).order_by(Recipe.code, Recipe.revision).all(),
        "can_edit_items": ctx.user.has("edit") and recipe.status not in ("ersetzt", "archiviert"),
    }


hooks("recipe").detail_context = _recipe_detail
hooks("recipe").extra_columns = []


def _item_editor_context(ctx: Ctx, recipe: Recipe, rows=None, errors=None) -> dict:
    materials = ctx.db.query(Material).filter(Material.status != "ausgelaufen").order_by(Material.name).all()
    batches = ctx.db.query(Batch).order_by(Batch.batch_number).all()
    if rows is None:
        rows = [{"material_id": i.material_id, "batch_id": i.batch_id or "", "function": i.function or "",
                 "target_amount": de_input_number(i.target_amount), "unit": i.unit or "",
                 "actual_amount": de_input_number(i.actual_amount), "weight_percent": de_input_number(i.weight_percent),
                 "tolerance": de_input_number(i.tolerance), "remark": i.remark or ""} for i in recipe.items]
    return {"recipe": recipe, "rows": rows, "errors": errors or [], "materials": materials, "batches": batches,
            "units": UNITS, "reason_required": reason_required(ctx.db, "recipe", recipe),
            "batch_map": [{"id": b.id, "material_id": b.material_id, "label": b.batch_number} for b in batches]}


@router.get("/rezepturen/{obj_id:int}/positionen")
def edit_items(obj_id: int, ctx: Ctx = Depends(get_ctx)):
    ctx.require("edit")
    recipe = get_obj(ctx, RECIPE, obj_id)
    ensure_editable("recipe", recipe)
    return ctx.render("recipes/items.html", **_item_editor_context(ctx, recipe))


@router.post("/rezepturen/{obj_id:int}/positionen")
async def save_items(obj_id: int, request: Request, ctx: Ctx = Depends(get_ctx)):
    ctx.require("edit")
    recipe = get_obj(ctx, RECIPE, obj_id)
    ensure_editable("recipe", recipe)
    form = await request.form()
    rows, errors = recipe_service.parse_item_rows(ctx.db, form)
    reason = (form.get("reason") or "").strip() or None
    if reason_required(ctx.db, "recipe", recipe) and not reason:
        errors.append("Bitte einen Änderungsgrund angeben.")
    if errors:
        raw_rows = []
        idx = sorted({int(k.split("-")[1]) for k in form.keys() if k.startswith("item-") and k.count("-") >= 2})
        for i in idx:
            raw_rows.append({f: form.get(f"item-{i}-{f}", "") for f in recipe_service.ITEM_FIELDS})
        ctx.flash("error", "Die Positionen konnten nicht gespeichert werden.")
        return ctx.render("recipes/items.html", **_item_editor_context(ctx, recipe, raw_rows, errors))
    changed = recipe_service.replace_items(ctx.db, ctx.actor, recipe, rows, reason)
    if form.get("calc_percent") == "1":
        try:
            percents = recipe_service.percents_from_amounts(recipe.items)
            for item, p in zip(recipe.items, percents):
                item.weight_percent = p
            from ..services import audit

            audit.log(ctx.db, ctx.actor, "update", entity_type="recipe", entity=recipe, field="Gew.-%",
                      new="aus Sollmengen berechnet", reason=reason)
            changed = True
        except RecordError as exc:
            ctx.flash("warning", str(exc))
    check = recipe_service.check_sum(ctx.db, recipe)
    ctx.flash("success" if check.ok else "warning",
              ("Positionen gespeichert. " if changed else "Keine Änderungen. ") + check.message)
    return ctx.redirect(f"/rezepturen/{recipe.id}")


@router.post("/rezepturen/{obj_id:int}/kopie")
async def copy(obj_id: int, request: Request, ctx: Ctx = Depends(get_ctx)):
    ctx.require("create")
    recipe = get_obj(ctx, RECIPE, obj_id)
    form = await request.form()
    as_revision = form.get("mode") == "revision"
    scale = None
    if form.get("scale_total"):
        try:
            total = parse_number(form.get("scale_total"))
        except ValueError:
            raise RecordError("Ungültige Gesamtmenge.") from None
        scale = (total, form.get("scale_unit") or "kg")
    new = recipe_service.copy_recipe(ctx.db, ctx.actor, recipe, as_revision=as_revision,
                                     reason=(form.get("reason") or "").strip() or None,
                                     name=(form.get("name") or "").strip() or None, scale=scale)
    text = f"Revision {new.revision} angelegt." if as_revision else f"Kopie {new.code} angelegt."
    return ctx.redirect(f"/rezepturen/{new.id}", "success", text)


@router.get("/rezepturen/vergleich")
def compare(request: Request, ctx: Ctx = Depends(get_ctx)):
    ctx.require("view")
    ids = [int(i) for i in request.query_params.getlist("ids") if i.isdigit()]
    all_recipes = ctx.db.query(Recipe).order_by(Recipe.code, Recipe.revision).all()
    result = None
    if len(ids) >= 2:
        selected = [ctx.db.get(Recipe, i) for i in ids]
        selected = [r for r in selected if r is not None]
        result = recipe_service.compare(selected)
    elif ids:
        ctx.flash("info", "Bitte mindestens zwei Rezepturen auswählen.")
    return ctx.render("recipes/compare.html", all_recipes=all_recipes, ids=ids, result=result)


@router.post("/rezepturen/{obj_id:int}/import")
async def import_items(obj_id: int, file: UploadFile, request: Request, ctx: Ctx = Depends(get_ctx)):
    ctx.require("edit")
    recipe = get_obj(ctx, RECIPE, obj_id)
    ensure_editable("recipe", recipe)
    form = await request.form()
    content = await file.read()
    rows = importer.read_table(file.filename or "", content)
    items, errors = importer.recipe_rows_from_table(ctx.db, rows)
    if errors:
        return ctx.render("io/report.html", title=f"Import Rezeptur {recipe.code}",
                          report=importer.ImportReport(total_rows=len(rows), errors=errors),
                          back=f"/rezepturen/{recipe.id}")
    reason = (form.get("reason") or "").strip() or "Import aus Datei"
    recipe_service.replace_items(ctx.db, ctx.actor, recipe, items, reason)
    check = recipe_service.check_sum(ctx.db, recipe)
    return ctx.redirect(f"/rezepturen/{recipe.id}", "success" if check.ok else "warning",
                        f"{len(items)} Positionen importiert. {check.message}")


@router.get("/rezepturen/{obj_id:int}/export.{fmt}")
def export_items(obj_id: int, fmt: str, ctx: Ctx = Depends(get_ctx)):
    ctx.require("export")
    recipe = get_obj(ctx, RECIPE, obj_id)
    headers = importer.RECIPE_ITEM_COLUMNS + ["material_name", "trade_name", "supplier", "material_code"]
    rows = [[i.material.material_number or i.material.code, i.batch.batch_number if i.batch else None, i.function,
             i.target_amount, i.unit, i.actual_amount, i.weight_percent, i.tolerance, i.remark, i.material.name,
             i.material.trade_name, i.material.supplier, i.material.code] for i in recipe.items]
    base = _ascii(f"Rezeptur_{recipe.code}_Rev{recipe.revision}")
    if fmt == "csv":
        return Response(export_service.to_csv(headers, rows), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="{base}.csv"'})
    if fmt == "xlsx":
        return Response(export_service.to_xlsx([(f"{recipe.code} Rev {recipe.revision}", headers, rows)]),
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f'attachment; filename="{base}.xlsx"'})
    raise HTTPException(404)
