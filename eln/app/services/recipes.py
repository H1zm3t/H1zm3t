"""Rezepturen: Positionen, Summenprüfung, Skalierung, Vergleich, Revisionen."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from ..core.formatting import parse_number
from ..core.vocab import MASS_UNITS
from ..models import Batch, Material, Recipe, RecipeItem
from . import audit
from .audit import Actor
from .numbering import next_code
from .records import RecordError
from .system_settings import get_setting

ITEM_FIELDS = ("material_id", "batch_id", "function", "target_amount", "unit", "actual_amount",
               "weight_percent", "tolerance", "remark")


@dataclass
class SumCheck:
    total: float
    ok: bool
    deviation: float
    message: str
    level: str  # ok | warning | error


def check_sum(db: Session, recipe: Recipe) -> SumCheck:
    tol = get_setting(db, "recipe_sum_tolerance")
    if not recipe.items:
        return SumCheck(0.0, False, -100.0, "Die Rezeptur enthält noch keine Positionen.", "warning")
    if any(i.weight_percent is None for i in recipe.items):
        total = recipe.percent_sum
        return SumCheck(total, False, total - 100,
                        "Nicht alle Positionen haben einen Anteil in Gew.-%. Anteile ggf. aus Mengen berechnen.",
                        "warning")
    total = recipe.percent_sum
    dev = round(total - 100.0, 6)
    if abs(dev) <= tol:
        return SumCheck(total, True, dev, "Summe der Anteile = 100 Gew.-%.", "ok")
    return SumCheck(total, False, dev, f"Summe der Anteile weicht um {dev:+.4f} Gew.-% von 100 ab.".replace(".", ","),
                    "error")


def to_grams(amount: float | None, unit: str | None) -> float | None:
    if amount is None or unit not in MASS_UNITS:
        return None
    return amount * MASS_UNITS[unit]


def percents_from_amounts(items: list[RecipeItem]) -> list[float]:
    grams = [to_grams(i.target_amount, i.unit) for i in items]
    if any(g is None for g in grams):
        raise RecordError("Für die Berechnung benötigt jede Position eine Sollmenge mit Masseneinheit (mg, g, kg, t).")
    total = sum(grams)
    if total <= 0:
        raise RecordError("Die Summe der Sollmengen muss größer als 0 sein.")
    return [round(g / total * 100.0, 6) for g in grams]


def scaled_amounts(recipe: Recipe, total: float, unit: str) -> list[dict]:
    """Mengen für eine gewünschte Gesamtmenge aus den Gew.-%-Anteilen."""
    if unit not in MASS_UNITS:
        raise RecordError("Bitte eine Masseneinheit für die Gesamtmenge wählen.")
    if total <= 0:
        raise RecordError("Die Gesamtmenge muss größer als 0 sein.")
    if any(i.weight_percent is None for i in recipe.items):
        raise RecordError("Skalierung benötigt für jede Position einen Anteil in Gew.-%.")
    rows = []
    for i in recipe.items:
        amount = total * (i.weight_percent or 0) / 100.0
        rows.append({"item": i, "amount": round(amount, 6), "unit": unit})
    return rows


def parse_item_rows(db: Session, form) -> tuple[list[dict], list[str]]:
    """Liest die Positionstabelle des Rezepturformulars (Felder item-<n>-<feld>)."""
    indices = sorted({int(k.split("-")[1]) for k in form.keys() if k.startswith("item-") and k.count("-") >= 2})
    rows, errors = [], []
    pos = 0
    for idx in indices:
        g = lambda f: (form.get(f"item-{idx}-{f}") or "").strip()  # noqa: E731
        if not any(g(f) for f in ITEM_FIELDS):
            continue
        pos += 1
        row: dict = {"position": pos}
        mat_id = g("material_id")
        if not mat_id:
            errors.append(f"Position {pos}: Material fehlt.")
            continue
        material = db.get(Material, int(mat_id))
        if material is None:
            errors.append(f"Position {pos}: Material existiert nicht.")
            continue
        row["material_id"] = material.id
        batch_id = g("batch_id")
        if batch_id:
            batch = db.get(Batch, int(batch_id))
            if batch is None or batch.material_id != material.id:
                errors.append(f"Position {pos}: Die Charge gehört nicht zum Material {material.name}.")
                continue
            row["batch_id"] = batch.id
        else:
            row["batch_id"] = None
        for f in ("target_amount", "actual_amount", "weight_percent", "tolerance"):
            try:
                row[f] = parse_number(g(f))
            except ValueError:
                errors.append(f"Position {pos}: »{g(f)}« ist keine gültige Zahl.")
                row[f] = None
            if row[f] is not None and row[f] < 0:
                errors.append(f"Position {pos}: Negative Werte sind nicht zulässig.")
        if row.get("weight_percent") is not None and row["weight_percent"] > 100:
            errors.append(f"Position {pos}: Anteil über 100 Gew.-%.")
        row["unit"] = g("unit") or None
        row["function"] = g("function") or None
        row["remark"] = g("remark") or None
        rows.append(row)
    return rows, errors


def _item_text(i: RecipeItem | dict, db: Session | None = None) -> str:
    if isinstance(i, dict):
        mat = db.get(Material, i["material_id"]) if db else None
        name = mat.code if mat else i["material_id"]
        return (f"{name}: {i.get('weight_percent')} % / {i.get('target_amount')} {i.get('unit') or ''}"
                f" / Ist {i.get('actual_amount')}")
    return (f"{i.material.code}: {i.weight_percent} % / {i.target_amount} {i.unit or ''} / Ist {i.actual_amount}")


def replace_items(db: Session, actor: Actor, recipe: Recipe, rows: list[dict], reason: str | None) -> bool:
    old = [_item_text(i) for i in recipe.items]
    new = [_item_text(r, db) for r in rows]
    if old == new and [i.function for i in recipe.items] == [r["function"] for r in rows] and \
            [i.batch_id for i in recipe.items] == [r["batch_id"] for r in rows] and \
            [i.remark for i in recipe.items] == [r["remark"] for r in rows] and \
            [i.tolerance for i in recipe.items] == [r["tolerance"] for r in rows]:
        return False
    recipe.items.clear()
    db.flush()
    for r in rows:
        recipe.items.append(RecipeItem(**r))
    recipe.version += 1
    recipe.updated_by_id = actor.user_id
    audit.log(db, actor, "update", entity_type="recipe", entity=recipe, field="Positionen",
              old="\n".join(old) or None, new="\n".join(new) or None, reason=reason)
    db.flush()
    return True


def copy_recipe(db: Session, actor: Actor, recipe: Recipe, *, as_revision: bool, reason: str | None,
                name: str | None = None, scale: tuple[float, str] | None = None) -> Recipe:
    """Kopie (neue ID) oder neue Revision (gleiche ID, Revision + 1)."""
    if as_revision:
        if not reason:
            raise RecordError("Bitte einen Grund für die neue Revision angeben.")
        latest = db.query(Recipe).filter(Recipe.code == recipe.code).order_by(Recipe.revision.desc()).first()
        code, revision = recipe.code, latest.revision + 1
    else:
        code, revision = next_code(db, "recipe"), 1
    new = Recipe(code=code, revision=revision, name=name or recipe.name, description=recipe.description,
                 order_id=recipe.order_id, parent_id=recipe.id, target_total=recipe.target_total,
                 total_unit=recipe.total_unit, status="Entwurf", revision_reason=reason,
                 created_by_id=actor.user_id, updated_by_id=actor.user_id)
    scaled = {}
    if scale:
        total, unit = scale
        scaled = {r["item"].id: r for r in scaled_amounts(recipe, total, unit)}
        new.target_total, new.total_unit = total, unit
    for i in recipe.items:
        item = RecipeItem(position=i.position, material_id=i.material_id, batch_id=i.batch_id, function=i.function,
                          target_amount=i.target_amount, unit=i.unit, actual_amount=None,
                          weight_percent=i.weight_percent, tolerance=i.tolerance, remark=i.remark)
        if i.id in scaled:
            item.target_amount = scaled[i.id]["amount"]
            item.unit = scaled[i.id]["unit"]
        new.items.append(item)
    db.add(new)
    db.flush()
    if as_revision:
        old_status = recipe.status
        for r in db.query(Recipe).filter(Recipe.code == recipe.code, Recipe.id != new.id, Recipe.status == "gültig"):
            r.status = "ersetzt"
            audit.log(db, actor, "status", entity_type="recipe", entity=r, field="Status", old=old_status,
                      new="ersetzt", reason=f"Ersetzt durch Revision {revision}")
        audit.log(db, actor, "new_revision", entity_type="recipe", entity=new, field="Revision",
                  old=str(recipe.revision), new=str(revision), reason=reason)
    else:
        audit.log(db, actor, "create", entity_type="recipe", entity=new,
                  new=f"Kopie von {recipe.code} Rev. {recipe.revision}" + (" (skaliert)" if scale else ""),
                  reason=reason)
    return new


def compare(recipes: list[Recipe]) -> dict:
    """Vergleichsmatrix: Material × Rezeptur (Gew.-%), mit Kennzeichnung von Differenzen."""
    materials: dict[int, dict] = {}
    for r in recipes:
        for i in r.items:
            entry = materials.setdefault(i.material_id, {"material": i.material, "values": {}})
            entry["values"][r.id] = (entry["values"].get(r.id) or 0) + (i.weight_percent or 0)
    rows = []
    for mid, entry in materials.items():
        vals = [entry["values"].get(r.id) for r in recipes]
        present = [v for v in vals if v is not None]
        differs = len(present) != len(vals) or (max(present) - min(present) > 1e-9 if present else False)
        base = vals[0]
        cells = []
        for v in vals:
            if v is None:
                cls = "diff-missing"
            elif base is None:
                cls = "diff-new"
            elif v > base + 1e-9:
                cls = "diff-up"
            elif v < base - 1e-9:
                cls = "diff-down"
            else:
                cls = ""
            cells.append({"value": v, "cls": cls, "delta": (v - base) if (v is not None and base is not None) else None})
        rows.append({"material": entry["material"], "cells": cells, "differs": differs})
    rows.sort(key=lambda r: (-(r["cells"][0]["value"] or 0), r["material"].name))
    totals = [r.percent_sum for r in recipes]
    return {"recipes": recipes, "rows": rows, "totals": totals}
