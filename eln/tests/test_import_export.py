"""Import (mit Validierungsbericht) und Export."""
import base64
import io
import json

from openpyxl import load_workbook

from app.models import Material, Measurement


def test_csv_import_validation_then_commit(client_factory, dbs, sample_data):
    c = client_factory("wiss")
    bad = "name;material_number;material_type;status\nTalkum;300050;Füllstoff;aktiv\n;300051;Unbekannt;aktiv\n"
    r = c.post("/import", {"entity": "material"}, files=[("file", ("m.csv", io.BytesIO(bad.encode()), "text/csv"))])
    assert r.status_code == 200 and "Fehler gefunden" in r.text and "Zeile" in r.text
    assert dbs.query(Material).filter_by(material_number="300050").count() == 0  # nichts gespeichert
    good = "Name;Materialnummer;Materialtyp;Status\nTalkum;300050;Füllstoff;aktiv\nKreide;300060;Füllstoff;aktiv\n"
    r = c.post("/import", {"entity": "material"}, files=[("file", ("m.csv", io.BytesIO(good.encode("cp1252")), "text/csv"))])
    assert "Prüfung erfolgreich" in r.text
    r = c.post("/import", {"entity": "material", "commit": "1", "filename": "m.csv",
                           "payload": base64.b64encode(good.encode("cp1252")).decode()})
    assert "2 Datensätze importiert" in r.text
    assert dbs.query(Material).filter(Material.material_number.in_(["300050", "300060"])).count() == 2


def test_duplicate_material_number_rejected(dbs, sample_data):
    from conftest import actor

    from app.services import importer

    rep = importer.import_entities(dbs, actor(dbs, "admin"), "material",
                                   [{"name": "X", "material_number": "100230", "material_type": "Polymer"}], True)
    assert not rep.ok and "existiert bereits" in rep.errors[0][2]


def test_measurement_import_groups_values(dbs, sample_data):
    from conftest import actor

    from app.services import importer

    rows = [{"measurement_name": "Zug", "property_name": "Zugfestigkeit", "unit": "MPa", "value": v,
             "meta_Geschwindigkeit": "50 mm/min"} for v in ("35,1", "34,9", "35.3")]
    rep = importer.import_measurements(dbs, actor(dbs, "wiss"), rows, True)
    assert rep.ok and rep.created == 1
    m = dbs.query(Measurement).one()
    assert [v.value for v in m.values] == [35.1, 34.9, 35.3] and m.meta["Geschwindigkeit"] == "50 mm/min"
    assert round(m.stats["mean"], 3) == 35.1


def test_exports(client_factory, sample_data):
    c = client_factory("wiss")
    r = c.get("/materialien/export.csv")
    assert r.status_code == 200 and r.content.startswith("﻿".encode()) and b";" in r.content
    r = c.get("/versuche/export.xlsx")
    wb = load_workbook(io.BytesIO(r.content))
    assert wb.active.max_row == 2
    data = json.loads(c.get("/auftraege/export.json").content)
    assert data["count"] == 1 and data["rows"][0]["code"].startswith("A-")
    assert client_factory("labor").get("/materialien/export.csv").status_code == 403


def test_dossiers(client_factory, sample_data):
    c = client_factory("wiss")
    eid, oid = sample_data["experiment"], sample_data["order"]
    pdf = c.get(f"/versuche/{eid}/dossier.pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    d = json.loads(c.get(f"/versuche/{eid}/dossier.json").content)
    for key in ("Stammdaten", "Zielsetzung", "Rezeptur", "Prozessparameter", "Proben", "Prüfungen", "Ergebnis",
                "Anhänge", "Freigaben", "Audit-Trail-Auszug"):
        assert key in d
    assert c.get(f"/auftraege/{oid}/dossier.zip").content[:2] == b"PK"
    assert c.get(f"/auftraege/{oid}/dossier.pdf").content.startswith(b"%PDF")
