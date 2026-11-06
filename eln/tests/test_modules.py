"""Plugin-Schnittstelle und Compoundierungsmodul."""
from app.core.modules import get_registry
from app.models import Experiment, ModuleRecord, Sample


def test_registry_discovers_modules():
    reg = get_registry()
    keys = {m.key for m in reg.all()}
    assert {"compounding", "mvr", "tensile", "dsc", "tga", "injection_molding", "thermal_aging", "autoclave",
            "climate_chamber", "particle_size", "capillary_rheometry", "impact", "raw_material_testing",
            "sample_management", "reporting"} <= keys
    assert "_template" not in keys


def test_disable_module_hides_routes(client_factory, sample_data):
    admin = client_factory("admin")
    assert admin.get("/module/compoundierung").status_code == 200
    admin.post("/admin/module/compounding", {"enabled": "0"})
    assert admin.get("/module/compoundierung").status_code == 404
    admin.post("/admin/module/compounding", {"enabled": "1"})
    assert admin.get("/module/compoundierung").status_code == 200


def _run_form(sample_data, **extra):
    data = {"title": "Lauf 1", "experiment_id": str(sample_data["experiment"]), "device_id": str(sample_data["device"]),
            "status": "durchgeführt", "throughput_set": "12", "throughput_actual": "11,8", "screw_speed": "400",
            "torque": "62,5", "melt_temperature": "228", "start_time": "2026-05-01T09:00", "end_time": "2026-05-01T10:00",
            "feeder-0-feed_point": "Haupteinzug", "feeder-0-material_id": str(sample_data["material"]),
            "feeder-0-set_rate": "12", "feeder-0-actual_rate": "11,8",
            "reading-0-minute": "0", "reading-0-torque": "60", "reading-1-minute": "10", "reading-1-torque": "63"}
    zones = extra.pop("zones", ["Einzug", "Z1", "Z2", "Düse"])
    for i, z in enumerate(zones):
        data[f"zone-{i}-name"] = z
        data[f"zone-{i}-set_temp"] = str(180 + i * 10)
    data.update(extra)
    return data


def test_compounding_run_dynamic_zones_and_compare(client_factory, dbs, sample_data):
    from app.modules.compounding.models import CompoundingRun

    c = client_factory("wiss")
    assert c.post("/module/compoundierung/neu", _run_form(sample_data)).status_code == 303
    assert c.post("/module/compoundierung/neu", _run_form(sample_data, title="Lauf 2", screw_speed="450",
                                                          zones=[f"Zone {i}" for i in range(1, 15)])).status_code == 303
    runs = dbs.query(CompoundingRun).order_by(CompoundingRun.id).all()
    assert [len(r.zones) for r in runs] == [4, 14]
    assert runs[0].duration_min == 60 and runs[0].torque == 62.5 and len(runs[0].readings) == 2
    r = c.get(f"/module/compoundierung/vergleich?ids={runs[0].id}&ids={runs[1].id}")
    assert r.status_code == 200 and "Drehzahl" in r.text
    detail = c.get(f"/versuche/{sample_data['experiment']}")
    assert runs[0].code in detail.text  # Modulpanel auf der Versuchsseite
    r = c.post(f"/module/compoundierung/{runs[0].id}/probe", {"name": "Granulat", "quantity": "8,5", "unit": "kg"})
    assert r.status_code == 303
    s = dbs.query(Sample).filter_by(name="Granulat").one()
    assert s.experiment_id == sample_data["experiment"] and s.quantity == 8.5
    d = c.get(f"/versuche/{sample_data['experiment']}/dossier.json").json()
    assert any("Compoundierlauf" in s["title"] for s in d["Modulabschnitte"])


def test_compounding_blocked_when_locked(client_factory, dbs, sample_data):
    e = dbs.get(Experiment, sample_data["experiment"])
    e.locked, e.status = True, "freigegeben"
    dbs.commit()
    r = client_factory("wiss").post("/module/compoundierung/neu", _run_form(sample_data))
    assert r.status_code == 200 and "gesperrt" in r.text


def test_declarative_module_record(client_factory, dbs, sample_data):
    admin = client_factory("admin")
    admin.post("/admin/module/tensile", {"enabled": "1"})
    c = client_factory("wiss")
    r = c.post("/module/zugpruefung/neu", {"title": "Zugversuch PP", "experiment_id": str(sample_data["experiment"]),
                                           "strength": "35,2", "n": "5"})
    assert r.status_code == 303
    rec = dbs.query(ModuleRecord).one()
    assert rec.data["strength"] == 35.2 and rec.data["n"] == 5
    assert c.get(f"/moduldatensatz/{rec.id}", follow_redirects=True).status_code == 200


def test_mvr_example_module(client_factory, dbs, sample_data):
    from app.models import Measurement

    c = client_factory("wiss")
    c.post("/proben/neu", {"name": "Granulat", "sample_type": "Compound / Granulat", "status": "vorhanden",
                           "experiment_id": str(sample_data["experiment"])})
    sid = dbs.query(Sample).one().id
    bad = c.post("/module/mvr/neu", {"sample_id": str(sid), "temperature_c": "999", "load_kg": "2,16", "values": "x"})
    assert bad.status_code == 200 and "außerhalb" in bad.text
    r = c.post("/module/mvr/neu", {"sample_id": str(sid), "temperature_c": "230", "load_kg": "2,16",
                                   "melt_density": "0,739", "values": "12,1; 12,4\n12,3"})
    assert r.status_code == 303
    c.post(r.headers["location"] + "/uebernehmen")
    m = dbs.query(Measurement).one()
    assert m.property_name == "MVR" and len(m.values) == 3


def test_module_import_handler(client_factory, dbs, sample_data):
    import io

    from app.modules.mvr.models import MvrTest

    c = client_factory("wiss")
    c.post("/proben/neu", {"name": "Granulat", "sample_type": "Compound / Granulat", "status": "vorhanden"})
    code = dbs.query(Sample).one().code
    assert "Modul MVR / MFR: Einzelwerte" in c.get("/import").text
    csv = f"sample;temperature_c;load_kg;value\n{code};230;2,16;12,1\n{code};230;2,16;12,3\n"
    r = c.post("/import", {"entity": "mod:mvr:Einzelwerte", "commit": "1", "filename": "m.csv",
                           "payload": __import__("base64").b64encode(csv.encode()).decode()})
    assert "1 Datensätze importiert" in r.text
    assert dbs.query(MvrTest).one().values == [12.1, 12.3]


def test_module_config_editable(client_factory, dbs):
    import json

    from app.models import ModuleState

    c = client_factory("admin")
    cfg = {"default_zones": ["Einzug", "Z1", "Düse"], "zone_templates": {}}
    assert c.post("/admin/module/compounding/konfiguration", {"config": json.dumps(cfg)}).status_code == 303
    dbs.expire_all()
    assert dbs.get(ModuleState, "compounding").config["default_zones"] == ["Einzug", "Z1", "Düse"]
    r = c.post("/admin/module/compounding/konfiguration", {"config": "[kaputt"}, follow=True)
    assert "Ungültiges JSON" in r.text
