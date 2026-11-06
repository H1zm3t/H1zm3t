"""Anlegen und Ändern von Aufträgen und Versuchen über die Oberfläche."""
from app.models import AuditLog, Experiment, Order


def test_create_order_via_form(client_factory, dbs):
    c = client_factory("wiss")
    r = c.post("/auftraege/neu", {"title": "Neuer Auftrag", "client": "PM", "priority": "hoch", "status": "offen",
                                  "confidentiality": "intern", "responsible_id": "3", "task_description": "Test",
                                  "due_date": "31.12.2026", "tags": "PP; PE, PP"})
    assert r.status_code == 303
    o = dbs.query(Order).filter_by(title="Neuer Auftrag").one()
    assert o.code.startswith("A-") and o.due_date.year == 2026 and o.tags == "PP, PE"
    assert dbs.query(AuditLog).filter_by(entity_type="order", entity_id=o.id, action="create").count() == 1
    assert c.get(r.headers["location"]).status_code == 200


def test_unique_ids(client_factory, dbs):
    c = client_factory("wiss")
    for i in range(3):
        c.post("/auftraege/neu", {"title": f"A{i}", "client": "x", "priority": "normal", "status": "offen",
                                  "confidentiality": "intern", "responsible_id": "3", "task_description": "t"})
    codes = [o.code for o in dbs.query(Order).all()]
    assert len(codes) == len(set(codes)) == 3


def test_validation_messages_german(client_factory):
    c = client_factory("wiss")
    r = c.post("/auftraege/neu", {"title": "", "client": "x", "priority": "normal", "status": "offen",
                                  "confidentiality": "intern", "responsible_id": "3", "due_date": "32.13.2026"})
    assert r.status_code == 200
    assert "Pflichtfeld – bitte ausfüllen." in r.text
    assert "gültiges Datum" in r.text


def test_create_experiment_with_parameters(client_factory, dbs, sample_data):
    c = client_factory("wiss")
    r = c.post("/versuche/neu", {
        "title": "Versuch 2", "order_id": str(sample_data["order"]), "experiment_type": "Kundenmuster",
        "department": "Compoundierung", "responsible_id": "3", "objective": "Ziel",
        "devices": str(sample_data["device"]), "param-0-name": "Drehzahl", "param-0-value": "400,5",
        "param-0-unit": "1/min"})
    assert r.status_code == 303, r.text
    e = dbs.query(Experiment).filter_by(title="Versuch 2").one()
    assert e.status == "Entwurf" and e.code.startswith("V-")
    assert e.process_parameters[0]["numeric"] == 400.5
    assert [d.id for d in e.devices] == [sample_data["device"]]


def test_update_increments_version_and_logs_fields(client_factory, dbs, sample_data):
    c = client_factory("wiss")
    eid = sample_data["experiment"]
    page = c.get(f"/versuche/{eid}/bearbeiten")
    assert page.status_code == 200
    data = {"title": "Compoundierung Referenz geändert", "order_id": str(sample_data["order"]),
            "experiment_type": "Rezepturentwicklung", "department": "Compoundierung", "responsible_id": "3",
            "objective": "Referenz herstellen", "devices": str(sample_data["device"]),
            "materials": str(sample_data["material"]), "batches": str(sample_data["batch"])}
    assert c.post(f"/versuche/{eid}/bearbeiten", data).status_code == 303
    dbs.expire_all()
    e = dbs.get(Experiment, eid)
    assert e.version == 2
    log = dbs.query(AuditLog).filter_by(entity_type="experiment", entity_id=eid, action="update").all()
    assert any(a.field == "Bezeichnung" and a.old_value == "Compoundierung Referenz" for a in log)


def test_reason_required_for_master_data(client_factory, dbs, sample_data):
    c = client_factory("admin")
    mid = sample_data["material"]
    data = {"name": "Polypropylen neu", "material_number": "100230", "material_type": "Polymer", "status": "aktiv"}
    r = c.post(f"/materialien/{mid}/bearbeiten", data)
    assert r.status_code == 200 and "Änderungsgrund" in r.text
    data["reason"] = "Bezeichnung vereinheitlicht"
    assert c.post(f"/materialien/{mid}/bearbeiten", data).status_code == 303
    a = dbs.query(AuditLog).filter_by(entity_type="material", entity_id=mid, action="update").one()
    assert a.reason == "Bezeichnung vereinheitlicht"


def test_device_warning_for_locked_device(client_factory, dbs, sample_data):
    from datetime import date, timedelta

    from app.models import Device

    d = dbs.get(Device, sample_data["device"])
    d.status = "gesperrt"
    d.next_calibration = date.today() - timedelta(days=3)
    dbs.commit()
    from app.services.records import device_warnings

    msgs = device_warnings(dbs, [d])
    assert any("gesperrt" in m for m in msgs) and any("überfällig" in m for m in msgs)
    r = client_factory("wiss").get(f"/versuche/{sample_data['experiment']}")
    assert "überfällig" in r.text


def test_sample_hierarchy(client_factory, dbs, sample_data):
    from app.models import Sample

    c = client_factory("wiss")
    c.post("/proben/neu", {"name": "Compound", "sample_type": "Compound / Granulat", "status": "vorhanden",
                           "experiment_id": str(sample_data["experiment"])})
    parent = dbs.query(Sample).filter_by(name="Compound").one()
    assert parent.order_id is None or parent.order_id
    c.post("/proben/neu", {"name": "Prüfkörper", "sample_type": "Prüfkörper", "status": "vorhanden",
                           "parent_id": str(parent.id)})
    child = dbs.query(Sample).filter_by(name="Prüfkörper").one()
    assert child.parent_id == parent.id
    assert "Prüfkörper" in c.get(f"/proben/{parent.id}").text
