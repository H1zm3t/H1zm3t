"""Import des Excel-Auftragsformulars »Compoundierplan« und Auftragsplanung.

Die Testdatei wird hier mit erfundenen Daten im Layout des Formulars erzeugt.
"""
import io
import re
from datetime import date, datetime, time

from conftest import actor
from openpyxl import Workbook

from app.models import (Attachment, Batch, Material, Order, OrderActivity, OrderLogEntry, OrderMaterial, Recipe)
from app.services import awt_import, planning


def build_workbook(done: int = 2, with_protocol: bool = False, extra_activity: bool = False) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Auftrag"
    ws["A3"], ws["B3"], ws["C3"] = "Auftraggeber", "Kunde", "intern + Testkunde"
    ws["B4"], ws["C4"], ws["E4"], ws["H4"] = "Anfrage am", datetime(2026, 3, 2), "Ansprechperson (intern)", "ABC"
    ws["F5"], ws["H5"] = "Cluster", "2026_Test_1"
    ws["B6"], ws["B7"] = "Kurzbeschreibung / Hintergrund und Ziel des Auftrags", "Vergleich zweier Stabilisator-MB in PA66"
    ws["B8"], ws["B9"] = "Auftrag (genaue Angaben über die geplante Vorgehensweise)", "1. MB Herstellung\n2. Compoundherstellung"
    ws["A27"], ws["B27"] = "FEA", "Bemerkungen (von FEA auszufüllen)"
    ws["B28"], ws["D28"] = "AWT-NR:", "26-999"
    ws["B29"] = "Priorität hoch"
    ws["B33"], ws["E33"], ws["F33"], ws["J33"] = datetime(2026, 3, 2), "wiss", datetime(2026, 3, 3), "LAB"
    ws["B34"], ws["F34"] = "Datum, Anfrage von (Kürzel)", "Datum, Geprüft von (Kürzel)"

    d = wb.create_sheet("Auftragdetails")
    d["A3"], d["B3"] = "AWT-Nummer", "26-999"
    d["A4"], d["B4"], d["D4"], d["E4"] = "Verantwortlich", "wiss", "Gesamtstatus", "in Bearbeitung"
    d.append([])
    d.append([])
    d["A7"], d["B7"], d["C7"], d["D7"], d["E7"], d["F7"], d["G7"], d["H7"], d["I7"], d["J7"], d["K7"], d["L7"] = (
        "Nr.", "Kategorie", "Tätigkeit", "Probe / Rezeptur", "Zuständig", "Geplant am", "Begonnen am", "Erledigt am",
        "Dokumentiert am", "Status", "Ergebnis / Ablage", "Bemerkung")
    acts = [("Vorbereitung und Rohstoffe", "Auftrag prüfen"), ("Vorbereitung und Rohstoffe", "Rohstoffe bereitstellen"),
            ("Compoundierung und Verarbeitung", "Masterbatchherstellung"), ("Analytik", "RFA")]
    if extra_activity:
        acts.append(("Mechanische Prüfungen", "Zugeigenschaften"))
    for i, (cat, act) in enumerate(acts, start=1):
        row = [i, cat, act, "PA66" if act == "RFA" else None, "LAB"]
        if i <= done:
            row += [datetime(2026, 3, 3), datetime(2026, 3, 3), datetime(2026, 3, 4), datetime(2026, 3, 4), "abgeschlossen"]
        d.append(row)
    for i in range(len(acts) + 1, 30):
        d.append([i])  # leere, vornummerierte Zeilen wie im Formular

    r = wb.create_sheet("Rohstoffliste")
    r.append([None, "ID bzw Materialnummer", "Bezeichnung", "Lot Nr / Charge", "Datum", "Bemerkungen"])
    r.append(["Rohstoffe für Compound Herstellung", None, "Polyamid 66 Test"])
    r.append([None, None, "Glasfaser Test"])
    r.append(["Rohstoffe für MB Herstellung", "100230", "Polypropylen", "CH4711"])
    r.append([None, "079999", "Kupferiodid", "LOT-77", datetime(2026, 3, 1), "trocken lagern"])
    for _ in range(10):
        r.append([])
    r.append(["Datum", "Bezeichnung", "ID bzw\nMaterialNr", "Feuchtigkeit", None, "Messprogramm", None, None, "Bemerkung"])
    r.append([datetime(2026, 3, 5), "Polyamid 66 Test", None, 0.08, None, "P1"])

    lg = wb.create_sheet("Durchführung")
    lg.append(["Arbeitsschritt", "von", "Datum", "Bemerkungen"])
    lg.append(["Extruder gereinigt", "LAB", datetime(2026, 3, 4), None])

    def recipe_sheet(title, names, comps, n_template):
        s = wb.create_sheet(title)
        s["B3"] = "Rezeptur"
        s["B48"] = "Rezeptur"
        all_names = names + [f"X{i}" for i in range(n_template)]
        for j, n in enumerate(all_names):
            s.cell(row=3, column=4 + j, value=n)
            s.cell(row=48, column=4 + j, value=n)
            s.cell(row=45, column=4 + j, value=7000)
            s.cell(row=25, column=4 + j, value=5)
        s["C45"], s["B25"], s["B26"] = "Summe pro Ansatz [g]", "benötigte Menge [kg]", "Bemerkungen zur Rezeptur"
        s["D26"] = "Referenz"
        for i, (comp, values) in enumerate(comps):
            s.cell(row=4 + i, column=3, value=comp)
            s.cell(row=49 + i, column=3, value=comp)
            for j in range(len(all_names)):
                v = values[j] if j < len(values) else (1 if i == 0 else None)
                if v:
                    s.cell(row=4 + i, column=4 + j, value=v)
                    s.cell(row=49 + i, column=4 + j, value=v * 7000)
        s["C22"], s["C67"] = "Kontrolle", "Kontrolle"
        return s

    recipe_sheet("Rezeptur-MB", ["MB26-999_1", "MB26-999_2"],
                 [("Polypropylen", [0.9, 0.8]), ("Kupferiodid", [0.1, 0.2])], n_template=3)
    recipe_sheet("Rezeptur-Comp", ["R01", "R02", "R03"],
                 [("Polyamid 66 Test", [0.7, 0.694, 1]), ("Glasfaser Test", [0.3, 0.3, None]),
                  ("MB26-999_1", [None, 0.006, None])], n_template=2)
    # R03 = reines Polymer, liegt aber NACH einer echten Rezeptur? -> als Vorlage am Ende ignoriert

    m = wb.create_sheet("M26-999_1")
    m["A1"], m["B1"], m["A2"], m["B2"], m["A3"], m["B3"] = "Mischungsbezeichnung", "M26-999_1", "Sollmenge [g]", 1000, "Datum", datetime(2026, 3, 4)
    m["A4"], m["B4"], m["A5"], m["B5"] = "Waage (PMFEA)", "019", "Kürzel", "LAB"
    m["A8"], m["B8"], m["C8"], m["D8"], m["E8"] = "Rohstoff", "[Gew.-%]", "[Gew.-%]", "SOLL-Einwaage", "IST-Einwaage"
    m["A9"], m["B9"], m["D9"], m["E9"] = "Kupferiodid", 100, 1000, 1000.4
    m["A19"], m["B19"] = "Gesamt", 100
    hidden = wb.create_sheet("Mischung X")
    hidden["A1"], hidden["B1"] = "Mischungsbezeichnung", "Vorlage"
    hidden.sheet_state = "hidden"

    p = wb.create_sheet("Extr.-Prot.MB")
    p.append(["AWT-Nr", "Rezeptur", "MB26-999_1", "MB26-999_2", "X0"])
    rows = [("26-999", "Datum", datetime(2026, 3, 5)), ("Uhrzeit", "von", time(9, 0)), (None, "bis", time(10, 30)),
            ("Granulatdosierer", "[kg/h]", 9.0), (None, "Anteil [%]", 90), ("MiniTwin", "Additiv", "M26-999_1"),
            (None, "[kg/h]", 1.0), ("Schneckendrehzahl", "[U/min]", 300), ("M Extruder", "[%]", 55),
            ("Gesamtdurchsatz", "[kg/h]", 10), ("Massedruck", "[bar]", 22), ("Massetemperatur (Anzeige)", "[°C]", 231),
            ("Düse", "Auswahl", "2-Loch"), ("Temperaturprofil\n Extruder [SOLL]", "Zone 1 [°C]", 180),
            (None, "Zone 2 [°C]", 200), (None, "Düse [°C]", 220), ("Vakuum", "[mbar]", 150),
            ("Wasserbad", "[Auswahl]", "kurz"), ("Reihenfolge Herstellung", None, 0), ("Bemerkungen", None, "ruhig")]
    for a, b, v in rows:
        p.append([a, b, v if with_protocol else (0 if a == "Reihenfolge Herstellung" else None)])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_parse_reads_all_sheets():
    plan = awt_import.parse(build_workbook(with_protocol=True))
    assert plan.awt_number == "26-999" and plan.client == "intern + Testkunde"
    assert plan.request_date == date(2026, 3, 2) and plan.contact_person == "ABC" and plan.cluster == "2026_Test_1"
    assert plan.checked_by == "LAB" and plan.checked_on == date(2026, 3, 3) and plan.requested_by == "wiss"
    assert "MB Herstellung" in plan.task and plan.fea_remarks == "Priorität hoch"
    assert len(plan.activities) == 4 and [a["status"] for a in plan.activities][:2] == ["abgeschlossen"] * 2
    assert [m["name"] for m in plan.materials] == ["Polyamid 66 Test", "Glasfaser Test", "Polypropylen", "Kupferiodid"]
    assert plan.materials[3]["section"] == "Rohstoffe für MB Herstellung" and plan.materials[3]["lot"] == "LOT-77"
    assert len(plan.moisture) == 1 and len(plan.log) == 1
    by_type = {}
    for r in plan.recipes:
        by_type.setdefault(r["type"], []).append(r["name"])
    assert by_type == {"Masterbatch": ["MB26-999_1", "MB26-999_2"], "Compound": ["R01", "R02"],
                       "Pulvermischung": ["M26-999_1"]}  # Vorlagenspalten und ausgeblendete Blätter ignoriert
    mb = plan.recipes[0]
    assert [(i["name"], i["percent"], i["grams"]) for i in mb["items"]] == [("Polypropylen", 90.0, 6300.0),
                                                                             ("Kupferiodid", 10.0, 700.0)]
    assert plan.recipes[-1]["items"][0]["actual"] == 1000.4
    assert len(plan.protocols) == 1 and plan.protocols[0]["recipe"] == "MB26-999_1"


def test_not_a_plan_is_rejected():
    import pytest

    from app.services.records import RecordError

    wb = Workbook()
    buf = io.BytesIO()
    wb.save(buf)
    with pytest.raises(RecordError):
        awt_import.parse(buf.getvalue())
    with pytest.raises(RecordError):
        awt_import.parse(b"kein excel")


def _import(client, content, name="26-999_Compoundierplan.xlsx"):
    r = client.post("/auftraege/compoundierplan", files={"file": (name, io.BytesIO(content))})
    assert r.status_code == 200, r.text[:300]
    token = re.search(r'name="token" value="([0-9a-f]+)"', r.text).group(1)
    r2 = client.post("/auftraege/compoundierplan", {"token": token, "filename": name})
    assert r2.status_code == 303, r2.text[:500]
    return r, r2.headers["location"]


def test_import_creates_order_with_everything(client_factory, dbs, sample_data):
    c = client_factory("wiss")
    preview, loc = _import(c, build_workbook(with_protocol=True))
    assert "neuer Auftrag" in preview.text and "Kupferiodid" in preview.text  # neues Material angekündigt
    o = dbs.query(Order).filter_by(external_number="26-999").one()
    assert o.client == "intern + Testkunde" and o.cluster == "2026_Test_1" and o.status == "in Bearbeitung"
    assert o.responsible.username == "wiss" and o.checked_by == "LAB"
    acts = planning.activities(dbs, o.id)
    assert len(acts) == 4 and planning.summary(acts) == {"total": 4, "done": 2, "open": 2, "progress": 50.0,
                                                          "status": "in Bearbeitung"}
    assert acts[0].responsible_text == "LAB" and acts[3].subject == "PA66"
    # Rohstoffliste: vorhandenes Material (100230) wiederverwendet, Charge CH4711 nicht doppelt
    assert dbs.query(Material).filter_by(material_number="100230").count() == 1
    assert dbs.query(Batch).filter_by(batch_number="CH4711").count() == 1
    assert dbs.query(Batch).filter_by(batch_number="LOT-77").one().material.material_number == "079999"
    assert dbs.query(OrderMaterial).filter_by(order_id=o.id).count() == 4
    assert dbs.query(OrderLogEntry).filter_by(order_id=o.id).count() == 2  # Arbeitsschritt + Feuchtemessung
    recipes = {r.name: r for r in dbs.query(Recipe).filter_by(order_id=o.id)}
    assert set(recipes) == {"MB26-999_1", "MB26-999_2", "R01", "R02", "M26-999_1"}
    r02 = recipes["R02"]
    assert r02.recipe_type == "Compound" and round(r02.percent_sum, 6) == 100
    mb_item = [i for i in r02.items if i.source_recipe_id][0]
    assert mb_item.source_recipe.name == "MB26-999_1" and mb_item.target_amount == 42.0
    resolved = {m.name: round(p, 4) for m, p in planning.resolved_composition(r02).values()}
    assert resolved == {"Polyamid 66 Test": 69.4, "Glasfaser Test": 30.0, "Polypropylen": 0.54, "Kupferiodid": 0.06}
    # Extrusionsprotokoll -> Compoundierlauf
    from app.modules.compounding.models import CompoundingRun

    run = dbs.query(CompoundingRun).one()
    assert run.title == "MB26-999_1" and run.screw_speed == 300 and run.torque == 55 and run.melt_temperature == 231
    assert run.start_time == datetime(2026, 3, 5, 9, 0) and run.duration_min == 90
    assert [z.name for z in run.zones] == ["Zone 1", "Zone 2", "Düse"] and run.zones[2].set_temp == 220
    assert [(f.feed_point, f.actual_rate) for f in run.feeders] == [("Granulatdosierer", 9.0), ("MiniTwin", 1.0)]
    assert any("Düse" in label for label, _ in run.protocol)
    assert dbs.query(Attachment).filter_by(entity_type="order", entity_id=o.id, category="Compoundierplan").count() == 1
    page = c.get(loc).text
    for text in ("Arbeitsplan", "Status nach Kategorien", "Rohstoffliste", "Durchführung", "Zusammensetzungen",
                 "MB26-999_1", "Extruder gereinigt", "2 von 4"):
        assert text in page, text


def test_reimport_updates_without_duplicates(client_factory, dbs, sample_data):
    c = client_factory("wiss")
    _import(c, build_workbook(done=2))
    o = dbs.query(Order).filter_by(external_number="26-999").one()
    planning.add_log(dbs, actor(dbs, "wiss"), o, "Manueller Eintrag im ELN", None, None, None)
    dbs.commit()
    n_recipes, n_mats = dbs.query(Recipe).count(), dbs.query(Material).count()
    preview, _ = _import(c, build_workbook(done=3, extra_activity=True))
    assert "wird <strong>aktualisiert</strong>" in preview.text
    dbs.expire_all()
    assert dbs.query(Order).filter_by(external_number="26-999").count() == 1
    assert dbs.query(Recipe).count() == n_recipes and dbs.query(Material).count() == n_mats
    acts = planning.activities(dbs, o.id)
    assert len(acts) == 5 and planning.summary(acts)["done"] == 3
    steps = [e.step for e in planning.log_entries(dbs, o.id)]
    assert "Manueller Eintrag im ELN" in steps and steps.count("Extruder gereinigt") == 1
    # geänderte Datei -> neue Dateiversion, alte bleibt erhalten
    atts = dbs.query(Attachment).filter_by(entity_type="order", entity_id=o.id).order_by(Attachment.id).all()
    assert [a.version for a in atts] == [1, 2] and atts[0].status == "ersetzt"


def test_planning_without_excel(client_factory, dbs, sample_data):
    """Auftrag direkt im System planen – ohne Excel."""
    c = client_factory("wiss")
    oid = sample_data["order"]
    r = c.post(f"/auftraege/{oid}/taetigkeiten", {"category": "Analytik", "activity": "DSC", "responsible": "labor",
                                                    "planned_on": "2026-05-01", "status": "geplant"})
    assert r.status_code == 303
    act = dbs.query(OrderActivity).one()
    assert act.responsible.username == "labor" and act.status == "geplant" and act.planned_on == date(2026, 5, 1)
    assert c.post(f"/auftraege/{oid}/taetigkeiten/{act.id}/status", {"status": "abgeschlossen"}).status_code == 303
    dbs.expire_all()
    act = dbs.get(OrderActivity, act.id)
    assert act.status == "abgeschlossen" and act.done_on == date.today() and act.started_on == date.today()
    assert c.post(f"/auftraege/{oid}/taetigkeiten/{act.id}", {
        "category": "Analytik", "activity": "DSC", "status": "entfallen", "remark": "nicht nötig"}).status_code == 303
    dbs.expire_all()
    assert planning.summary(planning.activities(dbs, oid))["total"] == 0  # »entfallen« zählt nicht
    assert c.post(f"/auftraege/{oid}/durchfuehrung", {"step": "Rohstoffe geholt", "by": "labor"}).status_code == 303
    assert c.post(f"/auftraege/{oid}/rohstoffe", {"section": "weitere benötigte Rohstoffe",
                                                   "material_id": str(sample_data["material"]),
                                                   "batch_id": str(sample_data["batch"])}).status_code == 303
    page = c.get(f"/auftraege/{oid}").text
    assert "Rohstoffe geholt" in page and "CH4711" in page and "entfallen" in page
    # Leser darf nicht planen
    assert client_factory("leser").post(f"/auftraege/{oid}/taetigkeiten", {"category": "Analytik",
                                                                            "activity": "TGA"}).status_code == 403
    assert client_factory("leser").get("/auftraege/compoundierplan").status_code == 403


def test_migration_0002_from_existing_database(env):
    """Die Migration ergänzt eine bestehende Datenbank (Stand 0001) ohne Datenverlust."""
    from alembic import command
    from sqlalchemy import text

    from app import db as db_module
    from app.bootstrap import alembic_config, migration_status, run_migrations

    command.downgrade(alembic_config(), "0001")
    with db_module.session_scope() as db:
        users_before = db.execute(text("select count(*) from users")).scalar()
        assert "request_date" not in [r[1] for r in db.execute(text("pragma table_info(orders)"))]
    db_module.reset_engine()
    run_migrations()
    assert migration_status()[0] == migration_status()[1]
    with db_module.session_scope() as db:
        assert db.execute(text("select count(*) from users")).scalar() == users_before
        assert "request_date" in [r[1] for r in db.execute(text("pragma table_info(orders)"))]
    assert any("vor-migration" in p.name for p in env.backup_dir.glob("*.zip"))
