"""Rezepturen: Summenprüfung, Berechnung, Skalierung, Revision, Vergleich, Import."""
import pytest
from conftest import actor

from app.models import Recipe
from app.services import importer, records, recipes
from app.services.records import RecordError


def _recipe(db, sample_data, items):
    a = actor(db, "wiss")
    r = records.create_record(db, a, "recipe", {"name": "PP Test", "status": "Entwurf", "total_unit": "kg"})
    rows = [{"position": i + 1, "material_id": sample_data["material" if i == 0 else "material2"], "batch_id": None,
             "function": None, "unit": u, "target_amount": amt, "actual_amount": None, "weight_percent": pct,
             "tolerance": None, "remark": None} for i, (amt, u, pct) in enumerate(items)]
    recipes.replace_items(db, a, r, rows, None)
    db.commit()
    return r


def test_sum_ok_and_deviation(dbs, sample_data):
    r = _recipe(dbs, sample_data, [(9.8, "kg", 98.0), (0.2, "kg", 2.0)])
    assert recipes.check_sum(dbs, r).ok
    r.items[1].weight_percent = 1.5
    chk = recipes.check_sum(dbs, r)
    assert not chk.ok and chk.level == "error" and round(chk.deviation, 3) == -0.5


def test_percent_from_amounts_with_mixed_units(dbs, sample_data):
    r = _recipe(dbs, sample_data, [(9.9, "kg", None), (100, "g", None)])
    assert recipes.percents_from_amounts(r.items) == [99.0, 1.0]
    r.items[1].unit = "Stk."
    with pytest.raises(RecordError):
        recipes.percents_from_amounts(r.items)


def test_scaling(dbs, sample_data):
    r = _recipe(dbs, sample_data, [(9.8, "kg", 98.0), (0.2, "kg", 2.0)])
    rows = recipes.scaled_amounts(r, 250, "g")
    assert [x["amount"] for x in rows] == [245.0, 5.0]
    copy = recipes.copy_recipe(dbs, actor(dbs, "wiss"), r, as_revision=False, reason="skaliert", scale=(250, "g"))
    assert copy.code != r.code and copy.items[0].target_amount == 245.0 and copy.target_total == 250


def test_revision_and_compare(dbs, sample_data):
    r = _recipe(dbs, sample_data, [(9.8, "kg", 98.0), (0.2, "kg", 2.0)])
    r.status = "gültig"
    with pytest.raises(RecordError):
        recipes.copy_recipe(dbs, actor(dbs, "wiss"), r, as_revision=True, reason=None)
    rev = recipes.copy_recipe(dbs, actor(dbs, "wiss"), r, as_revision=True, reason="AO erhöht")
    rev.items[1].weight_percent = 3.0
    rev.items[0].weight_percent = 97.0
    dbs.commit()
    assert rev.code == r.code and rev.revision == 2 and r.status == "ersetzt"
    cmp = recipes.compare([r, rev])
    row = [x for x in cmp["rows"] if x["material"].id == sample_data["material2"]][0]
    assert row["differs"] and row["cells"][1]["cls"] == "diff-up"
    with pytest.raises(RecordError):
        records.ensure_editable("recipe", r)


def test_item_editor_and_live_page(client_factory, dbs, sample_data):
    c = client_factory("wiss")
    c.post("/rezepturen/neu", {"name": "Editor", "status": "Entwurf", "total_unit": "kg"})
    r = dbs.query(Recipe).filter_by(name="Editor").one()
    resp = c.post(f"/rezepturen/{r.id}/positionen", {
        "item-0-material_id": str(sample_data["material"]), "item-0-target_amount": "9,5", "item-0-unit": "kg",
        "item-0-batch_id": str(sample_data["batch"]),
        "item-1-material_id": str(sample_data["material2"]), "item-1-target_amount": "500", "item-1-unit": "g",
        "calc_percent": "1"})
    assert resp.status_code == 303
    dbs.expire_all()
    r = dbs.get(Recipe, r.id)
    assert [i.weight_percent for i in r.items] == [95.0, 5.0]
    assert recipes.check_sum(dbs, r).ok
    # Charge, die nicht zum Material gehört
    bad = c.post(f"/rezepturen/{r.id}/positionen", {"item-0-material_id": str(sample_data["material2"]),
                                                    "item-0-batch_id": str(sample_data["batch"])})
    assert bad.status_code == 200 and "gehört nicht" in bad.text


def test_recipe_import_rows(dbs, sample_data):
    rows = importer.read_table("r.csv", "material;weight_percent;unit\n100230;99,5;kg\n200110;0,5;kg\n".encode())
    items, errors = importer.recipe_rows_from_table(dbs, rows)
    assert not errors and [i["weight_percent"] for i in items] == [99.5, 0.5]
    items, errors = importer.recipe_rows_from_table(dbs, [{"material": "999999", "weight_percent": "1"}])
    assert errors and "nicht gefunden" in errors[0][2]
