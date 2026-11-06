"""Beispieldaten für Schulung und Abnahme.

Alle Daten werden über die regulären Services angelegt – damit entstehen auch
die zugehörigen Audit-Trail-Einträge. Die Demo-Benutzer erhalten ein
gemeinsames Passwort, das beim Aufruf angegeben wird (nie im Quellcode).
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta

from app.db import session_scope
from app.models import Material, MeasurementValue, ModuleState, User
from app.services import auth, records, recipes, workflow
from app.services.audit import Actor
from app.services.system_settings import set_setting

DEMO_USERS = [
    ("m.weber", "Dr. Martina Weber", "MW", ["leitung"]),
    ("s.keller", "Stefan Keller", "SK", ["wissenschaftler"]),
    ("t.braun", "Tobias Braun", "TB", ["labor"]),
    ("a.schulz", "Anna Schulz", "AS", ["pruefer", "wissenschaftler"]),
    ("gast", "Gast Leser", "GL", ["leser"]),
]

DEVICES = [
    ("Leistritz ZSE 27 MAXX", "Extruder", "Leistritz", "ZSE 27 MAXX", "Technikum Halle 2", 400, 120),
    ("Demag Spritzgussmaschine", "Spritzgussmaschine", "Demag", "IntElect 100", "Technikum Halle 2", 200, 300),
    ("Axxicon Werkzeug ISO-Prüfkörper", "Werkzeug", "Axxicon", "MIM ISO 294", "Technikum Halle 2", None, None),
    ("ZwickRoell Z020", "Zugprüfmaschine", "ZwickRoell", "Z020", "Prüflabor", 150, 20),
    ("ZwickRoell Z010", "Zugprüfmaschine", "ZwickRoell", "Z010", "Prüflabor", 150, -5),
    ("ZwickRoell HIT 5.5", "Pendelschlagwerk", "ZwickRoell", "HIT5.5P", "Prüflabor", 300, 200),
    ("ZwickRoell Mflow", "Fließprüfgerät", "ZwickRoell", "Mflow", "Prüflabor", 250, 90),
    ("Göttfert Rheograph RG20", "Kapillarrheometer", "Göttfert", "RG20", "Rheologielabor", 300, 150),
    ("NETZSCH DSC 214", "DSC", "NETZSCH", "DSC 214 Polyma", "Analytik", 120, 60),
    ("NETZSCH TGA 209", "TGA", "NETZSCH", "TG 209 F1", "Analytik", 120, 60),
    ("Malvern Mastersizer 3000", "Partikelmessgerät", "Malvern", "Mastersizer 3000", "Analytik", 200, 100),
    ("Alpine-Hosokawa Mühle", "Mühle", "Hosokawa Alpine", "UPZ 100", "Technikum Halle 1", 180, None),
    ("Mixaco Containermischer", "Mischer", "Mixaco", "CM 150", "Technikum Halle 1", 365, None),
    ("Wärmeschrank Alterung 1", "Ofen", "Binder", "FD 115", "Alterungslabor", 90, 30),
    ("Klimaschrank", "Klimaschrank", "Weiss", "WK3-180", "Alterungslabor", 120, 45),
    ("Laborautoklav", "Autoklav", "Systec", "VX-75", "Alterungslabor", 60, None),
    ("Dosierwaage Haupteinzug", "Dosiergerät", "Brabender", "DDW-MD2", "Technikum Halle 2", 200, 50),
]

METHODS = [
    ("Zugversuch Kunststoffe", "DIN EN ISO 527-1/-2", "Mechanische Prüfung", ["ZwickRoell Z020", "ZwickRoell Z010"]),
    ("Charpy-Schlagzähigkeit", "DIN EN ISO 179-1", "Mechanische Prüfung", ["ZwickRoell HIT 5.5"]),
    ("Schmelze-Volumenfließrate", "DIN EN ISO 1133-1", "Rheologie", ["ZwickRoell Mflow"]),
    ("DSC Kunststoffe", "DIN EN ISO 11357", "Thermische Analyse", ["NETZSCH DSC 214"]),
    ("Thermogravimetrie", "DIN EN ISO 11358", "Thermische Analyse", ["NETZSCH TGA 209"]),
    ("Ofenalterung", "DIN EN ISO 188 / IEC 60216", "Alterung / Klima / Autoklav", ["Wärmeschrank Alterung 1"]),
    ("Compoundierung Standard PP", "AA-CMP-001", "Compoundierung", ["Leistritz ZSE 27 MAXX"]),
    ("Spritzguss Prüfkörper 1A", "DIN EN ISO 294-1", "Spritzguss", ["Demag Spritzgussmaschine"]),
]

MATERIALS = [
    ("100230", "Polypropylen Homopolymer", "Moplen HP500N", "LyondellBasell", "Polymer", "Basispolymer"),
    ("100245", "Polypropylen Copolymer", "Moplen EP548R", "LyondellBasell", "Polymer", "Basispolymer"),
    ("200110", "Phenolisches Antioxidans", "AO-1010", "Additivhersteller A", "Antioxidans", "Primärantioxidans"),
    ("200115", "Phosphit-Stabilisator", "P-168", "Additivhersteller A", "Stabilisator", "Prozessstabilisator"),
    ("200300", "Calciumstearat", "CaSt Ph.Eur.", "Additivhersteller B", "Gleitmittel", "Säurefänger"),
    ("300050", "Talkum", "Talc 10 µm", "Mineralien GmbH", "Füllstoff", "Füllstoff / Nukleierung"),
    ("300210", "Glasfaser geschnitten", "GF 4,5 mm", "Glasfaserwerk", "Verstärkungsstoff", "Verstärkung"),
    ("400020", "Polyamid 6", "PA6 natur", "Polymerwerk", "Polymer", "Basispolymer"),
    ("500010", "Schwarz-Masterbatch", "MB Schwarz 40 %", "Farbmasterbatch AG", "Masterbatch", "Farbmittel"),
]


def _d(days: int) -> date:
    return date.today() + timedelta(days=days)


def seed(password: str) -> str:
    with session_scope() as db:
        if db.query(Material).count() > 0:
            return "Es sind bereits Daten vorhanden – keine Beispieldaten angelegt."
        admin = db.query(User).join(User.roles).filter_by(key="admin").first()
        sys_actor = Actor(admin, "lokal")
        users: dict[str, User] = {}
        for username, name, short, roles in DEMO_USERS:
            u = db.query(User).filter_by(username=username).first() or auth.create_user(
                db, sys_actor, username=username, full_name=name, password=password, role_keys=roles,
                short_name=short, department="Anwendungstechnik")
            users[username] = u
        sci, lab, rev, boss = (Actor(users[k], "lokal") for k in ("s.keller", "t.braun", "a.schulz", "m.weber"))

        for key in ("injection_molding", "tensile", "thermal_aging"):
            st = db.get(ModuleState, key)
            if st:
                st.enabled = True
        set_setting(db, "company_name", "Anwendungstechnik Kunststoffadditive")

        dev = {}
        for name, typ, man, model, loc, maint, calib in DEVICES:
            obj = records.create_record(db, sys_actor, "device", {
                "name": name, "device_type": typ, "manufacturer": man, "model": model, "location": loc,
                "serial_number": f"SN-{abs(hash(name)) % 900000 + 100000}", "status": "betriebsbereit",
                "responsible_id": users["t.braun"].id if typ != "Extruder" else users["s.keller"].id,
                "last_maintenance": _d(-200) if maint else None, "next_maintenance": _d(maint - 60) if maint else None,
                "last_calibration": _d(-300) if calib is not None else None,
                "next_calibration": _d(calib) if calib is not None else None})
            dev[name] = obj
        dev["Laborautoklav"].status = "gesperrt"
        dev["Laborautoklav"].notes = "Sicherheitsventil defekt – Reparatur beauftragt."

        meth = {}
        for name, std, cat, devices in METHODS:
            m = records.create_record(db, sys_actor, "method", {"name": name, "standard": std, "category": cat,
                                                                "status": "gültig"})
            meth[name] = m
            for dname in devices:
                dev[dname].methods.append(m)

        mat, bat = {}, {}
        for i, (num, name, trade, sup, typ, func) in enumerate(MATERIALS):
            m = records.create_record(db, sys_actor, "material", {
                "material_number": num, "name": name, "trade_name": trade, "manufacturer": sup, "supplier": sup,
                "material_type": typ, "function": func, "status": "aktiv"})
            mat[num] = m
            for j in range(2):
                b = records.create_record(db, sys_actor, "batch", {
                    "material_id": m.id, "batch_number": f"{num}-{2025 + j}{i:02d}{j + 1}",
                    "received_date": _d(-300 + j * 150), "expiry_date": _d(400 - j * 30 if i != 4 else -10),
                    "storage_location": f"Lager R{i + 1}/F{j + 1}", "quantity": 25.0 * (j + 1), "unit": "kg",
                    "status": "freigegeben"})
                bat[(num, j)] = b

        proj = records.create_record(db, sci, "project", {
            "name": "Stabilisierung PP-Compounds 2026", "customer": "diverse", "status": "aktiv",
            "responsible_id": users["m.weber"].id, "start_date": _d(-120), "tags": "PP, Stabilisierung, Langzeitwärme"})
        o1 = records.create_record(db, sci, "order", {
            "title": "Langzeitwärmestabilität PP-Homopolymer mit neuem AO-Paket", "external_number": "ACC-2026-0412",
            "project_id": proj.id, "client": "Produktmanagement Stabilisatoren", "customer": "Automobilzulieferer Süd",
            "priority": "hoch", "due_date": _d(30), "responsible_id": users["s.keller"].id,
            "participants": [users["t.braun"].id, users["a.schulz"].id], "status": "in Bearbeitung",
            "confidentiality": "vertraulich", "tags": "PP, Ofenalterung, AO",
            "task_description": "Vergleich des Standard-AO-Pakets mit einem neuen Paket bei 150 °C Ofenalterung.",
            "objective": "Nachweis einer um mindestens 30 % längeren Lebensdauer (50 % Bruchdehnung)."})
        o2 = records.create_record(db, sci, "order", {
            "title": "Kundenmuster PA6-GF30 schwarz", "external_number": "ACC-2026-0431", "project_id": proj.id,
            "client": "Vertrieb Engineering Plastics", "customer": "Elektrogerätehersteller",
            "priority": "normal", "due_date": _d(-3), "responsible_id": users["s.keller"].id,
            "participants": [users["t.braun"].id], "status": "offen", "confidentiality": "intern",
            "tags": "PA6, Glasfaser, Muster", "task_description": "Herstellung von 25 kg Mustermenge inkl. Prüfzeugnis.",
            "objective": "Lieferung an Kunden in KW 20."})

        r1 = records.create_record(db, sci, "recipe", {"name": "PP-H Referenz AO-Standard", "order_id": o1.id,
                                                       "status": "gültig", "target_total": 10.0, "total_unit": "kg"})
        recipes.replace_items(db, sci, r1, [
            {"position": 1, "material_id": mat["100230"].id, "batch_id": bat[("100230", 0)].id, "function": "Basispolymer",
             "target_amount": 9.955, "unit": "kg", "actual_amount": 9.956, "weight_percent": 99.55, "tolerance": 0.01,
             "remark": None},
            {"position": 2, "material_id": mat["200110"].id, "batch_id": bat[("200110", 0)].id, "function": "AO primär",
             "target_amount": 0.02, "unit": "kg", "actual_amount": 0.02, "weight_percent": 0.2, "tolerance": 0.001,
             "remark": None},
            {"position": 3, "material_id": mat["200115"].id, "batch_id": bat[("200115", 0)].id, "function": "AO sekundär",
             "target_amount": 0.015, "unit": "kg", "actual_amount": 0.015, "weight_percent": 0.15, "tolerance": 0.001,
             "remark": None},
            {"position": 4, "material_id": mat["200300"].id, "batch_id": bat[("200300", 0)].id, "function": "Säurefänger",
             "target_amount": 0.01, "unit": "kg", "actual_amount": 0.01, "weight_percent": 0.1, "tolerance": 0.001,
             "remark": None},
        ], "Erstanlage")
        r2 = recipes.copy_recipe(db, sci, r1, as_revision=False, reason="Neues AO-Paket", name="PP-H AO-Neu")
        r2.items[1].weight_percent, r2.items[1].target_amount = 0.3, 0.03
        r2.items[0].weight_percent, r2.items[0].target_amount = 99.45, 9.945
        r2.status = "gültig"
        r3 = records.create_record(db, sci, "recipe", {"name": "PA6-GF30 schwarz", "order_id": o2.id, "status": "Entwurf",
                                                       "target_total": 25.0, "total_unit": "kg"})
        recipes.replace_items(db, sci, r3, [
            {"position": 1, "material_id": mat["400020"].id, "batch_id": None, "function": "Basispolymer",
             "target_amount": 16.75, "unit": "kg", "actual_amount": None, "weight_percent": 67.0, "tolerance": None, "remark": None},
            {"position": 2, "material_id": mat["300210"].id, "batch_id": None, "function": "Verstärkung",
             "target_amount": 7.5, "unit": "kg", "actual_amount": None, "weight_percent": 30.0, "tolerance": None, "remark": None},
            {"position": 3, "material_id": mat["500010"].id, "batch_id": None, "function": "Farbe",
             "target_amount": 0.5, "unit": "kg", "actual_amount": None, "weight_percent": 2.0, "tolerance": None, "remark": None},
        ], "Erstanlage")

        series = records.create_record(db, sci, "series", {"name": "Ofenalterung 150 °C – AO-Vergleich",
                                                           "order_id": o1.id, "status": "aktiv"})

        def experiment(actor, title, recipe, status_path, **extra):
            values = {
                "title": title, "order_id": o1.id, "series_id": series.id, "experiment_type": "Rezepturentwicklung",
                "department": "Compoundierung", "responsible_id": users["s.keller"].id,
                "participants": [users["t.braun"].id], "planned_date": _d(-40), "actual_date": _d(-38),
                "objective": "Herstellung des Compounds und Ofenalterung bei 150 °C; Bewertung über Bruchdehnung.",
                "hypothesis": "Das höher dosierte AO-Paket verlängert die Zeit bis 50 % Restbruchdehnung.",
                "method_id": meth["Compoundierung Standard PP"].id, "recipe_id": recipe.id,
                "devices": [dev["Leistritz ZSE 27 MAXX"].id, dev["Dosierwaage Haupteinzug"].id],
                "materials": [i.material_id for i in recipe.items], "batches": [i.batch_id for i in recipe.items if i.batch_id],
                "process_steps": "1. Vormischung im Containermischer\n2. Compoundierung ZSE 27\n3. Spritzguss 1A-Stäbe\n4. Ofenalterung 150 °C\n5. Zugversuch",
                "tags": "PP, AO, 150 °C",
            }
            values.update(extra)
            e = records.create_record(db, actor, "experiment", values)
            e.process_parameters_json = json.dumps([
                {"name": "Vormischzeit", "value": "5", "unit": "min", "numeric": 5.0},
                {"name": "Trocknung", "value": "keine", "unit": ""}], ensure_ascii=False)
            for step in status_path:
                if step == "results":
                    e.results = "Ausgangsbruchdehnung > 400 %; Abfall auf 50 % nach ca. 1100 h (Referenz) bzw. 1550 h (neu)."
                    e.conclusion = "Das neue AO-Paket erfüllt das Ziel (+41 %)."
                    e.evaluation = "Ziel erreicht; Streuung der Einzelwerte unauffällig."
                    e.observations = "Strangabriss in Minute 12 einmalig; sonst stabiler Prozess."
                    continue
                act, action = step
                workflow.perform(db, act, e, action)
            return e

        e1 = experiment(sci, "Compoundierung Referenz AO-Standard", r1,
                        [(sci, "status:in Bearbeitung"), "results", (sci, "complete"), (sci, "submit"),
                         (rev, "review_approve")])
        e2 = experiment(sci, "Compoundierung AO-Neu 0,3 %", r2,
                        [(sci, "status:in Bearbeitung"), "results", (sci, "complete"), (sci, "submit")])
        e3 = experiment(lab, "Ofenalterung 150 °C – Zwischenauswertung", r2, [(lab, "status:in Bearbeitung")],
                        department="Alterung / Klima / Autoklav", experiment_type="Langzeitversuch",
                        devices=[dev["Wärmeschrank Alterung 1"].id, dev["ZwickRoell Z020"].id],
                        method_id=meth["Ofenalterung"].id, responsible_id=users["t.braun"].id)
        e4 = records.create_record(db, sci, "experiment", {
            "title": "Mustermenge PA6-GF30 schwarz 25 kg", "order_id": o2.id, "experiment_type": "Mustermengenherstellung",
            "department": "Compoundierung", "responsible_id": users["s.keller"].id, "planned_date": _d(5),
            "objective": "Herstellung 25 kg Kundenmuster.", "recipe_id": r3.id,
            "devices": [dev["Leistritz ZSE 27 MAXX"].id]})
        workflow.perform(db, sci, e4, "status:geplant")

        # Compoundierläufe
        from app.modules.compounding.service import save_run

        def run(e, recipe, title, temps, speed, torque, tp):
            values = {"title": title, "experiment_id": e.id, "recipe_id": recipe.id,
                      "device_id": dev["Leistritz ZSE 27 MAXX"].id, "operator_id": users["t.braun"].id,
                      "status": "durchgeführt", "start_time": datetime.combine(_d(-38), datetime.min.time()) + timedelta(hours=9),
                      "end_time": datetime.combine(_d(-38), datetime.min.time()) + timedelta(hours=10, minutes=5),
                      "screw_config": "Standard-PP-Konfiguration SK-27-03: 2 Knetblöcke, 1 Rückförderelement",
                      "throughput_set": tp, "throughput_actual": tp - 0.1, "screw_speed": speed, "torque": torque,
                      "melt_pressure": 38.0, "melt_temperature": 228.0, "vacuum": 150.0,
                      "cooling": "Wasserbad 25 °C, 3 m", "pelletizing": "Stranggranulator, 3 mm",
                      "observations": "Stabiler Prozess.", "disturbances": None, "deviations": None,
                      "sampling": "Proben nach 10, 30 und 50 min", "evaluation": "i. O."}
            names = ["Einzug", "Zone 1", "Zone 2", "Zone 3", "Zone 4", "Zone 5", "Zone 6", "Zone 7", "Zone 8", "Zone 9",
                     "Zone 10", "Adapter", "Düse"]
            tables = {
                "zones": [{"position": i + 1, "name": n, "set_temp": t, "actual_temp": t + (1 if i % 3 else -1)}
                          for i, (n, t) in enumerate(zip(names, temps))],
                "feeders": [{"position": 1, "feed_point": "Haupteinzug", "feeder": "Brabender DDW-MD2",
                             "material_id": mat["100230"].id, "component": None, "set_rate": tp, "actual_rate": tp - 0.1}],
                "readings": [{"minute": m, "screw_speed": speed, "torque": torque + (m % 20) / 10,
                              "melt_pressure": 37 + (m % 15) / 5, "melt_temperature": 226 + (m % 10) / 4,
                              "throughput": tp - 0.1, "remark": None} for m in range(0, 61, 10)],
            }
            r, _ = save_run(db, Actor(users["t.braun"], "lokal"), None, values, tables, None)
            return r

        # Läufe vor dem Einreichen anlegen ist fachlich richtig; e1/e2 sind bereits gesperrt -> Sperre kurz aufheben
        for e in (e1, e2):
            locked, e.locked = e.locked, False
            run(e, e.recipe, f"ZSE 27 – {e.recipe.name}", [40, 180, 200, 210, 210, 210, 210, 205, 205, 205, 210, 215, 220],
                400 if e is e1 else 450, 62.0 if e is e1 else 66.0, 12.0)
            e.locked = locked

        # Proben-Hierarchie und Messdaten
        def sample(actor, name, typ, e, parent=None, recipe=None, batch=None, qty=None, unit=None):
            return records.create_record(db, actor, "sample", {
                "name": name, "sample_type": typ, "origin": "Eigenherstellung", "order_id": e.order_id,
                "experiment_id": e.id, "parent_id": parent.id if parent else None, "recipe_id": recipe.id if recipe else None,
                "batch_id": batch.id if batch else None, "production_date": _d(-38), "quantity": qty, "unit": unit,
                "storage_location": "Probenlager T2", "status": "vorhanden"})

        tensile = dev["ZwickRoell Z020"]
        for e, rec, base in ((e1, r1, 1100), (e2, r2, 1550)):
            comp = sample(lab, f"Granulat {rec.name}", "Compound / Granulat", e, recipe=rec, qty=8.5, unit="kg")
            bars = sample(lab, f"1A-Stäbe {rec.name}", "Prüfkörper", e, parent=comp, recipe=rec, qty=60, unit="Stk.")
            aged = sample(lab, f"1A-Stäbe {rec.name} gealtert 150 °C", "gealterter Prüfkörper", e3, parent=bars,
                          recipe=rec, qty=40, unit="Stk.")
            m = records.create_record(db, lab, "measurement", {
                "name": f"Bruchdehnung nach Ofenalterung – {rec.name}", "property_name": "Bruchdehnung", "unit": "%",
                "x_name": "Alterungszeit", "x_unit": "h", "experiment_id": e3.id, "sample_id": aged.id,
                "device_id": tensile.id, "method_id": meth["Zugversuch Kunststoffe"].id, "measured_on": _d(-2),
                "conditions": "50 mm/min, 23 °C / 50 % r. F."})
            m.metadata_json = json.dumps({"Ofentemperatur_C": 150, "Prüfgeschwindigkeit": "50 mm/min"})
            for i, h in enumerate((0, 250, 500, 750, 1000, 1250, 1500)):
                val = max(5.0, 420 * (1 - (h / (base * 2)) ** 1.6))
                m.values.append(MeasurementValue(idx=i, x_value=float(h), value=round(val, 1), label=f"{h} h"))
            m2 = records.create_record(db, lab, "measurement", {
                "name": f"Zugfestigkeit ungealtert – {rec.name}", "property_name": "Zugfestigkeit", "unit": "MPa",
                "experiment_id": e.id, "sample_id": bars.id, "device_id": tensile.id,
                "method_id": meth["Zugversuch Kunststoffe"].id, "measured_on": _d(-35)})
            for i, v in enumerate((34.8, 35.1, 34.6, 35.3, 34.9) if e is e1 else (35.2, 35.0, 35.6, 35.1, 35.4)):
                m2.values.append(MeasurementValue(idx=i, value=v, label=f"Prüfkörper {i + 1}"))

        for title, who, due, prio, ent in (
            ("Prüfbericht AO-Vergleich erstellen", "s.keller", _d(10), "hoch", e3),
            ("Zwischenentnahme 1250 h durchführen", "t.braun", _d(-1), "dringend", e3),
            ("Versuch V AO-Neu prüfen", "a.schulz", _d(2), "normal", e2),
            ("Glasfaser-Charge bestellen", "s.keller", _d(3), "normal", o2),
        ):
            t = records.create_record(db, sci, "task", {"title": title, "assignee_id": users[who].id, "priority": prio,
                                                        "due_date": due, "status": "offen"})
            t.entity_type = "experiment" if ent in (e2, e3) else "order"
            t.entity_id = ent.id
        _ = boss
    return ("Beispieldaten angelegt. Demo-Benutzer: " + ", ".join(u[0] for u in DEMO_USERS)
            + " (gemeinsames Demo-Passwort wie eingegeben).")
