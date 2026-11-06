"""Beispielmodul MVR/MFR (ZwickRoell Mflow).

Zeigt die vollständige Struktur eines Fachmoduls mit eigenem Datenmodell,
eigener Eingabemaske, eigener Validierung, eigener Auswertung (Kennwerte, MFR-
Berechnung) und Verknüpfung zu Probe, Versuch, Gerät sowie Übergabe der
Ergebnisse als Messdatensatz in den ELN-Kern. Siehe docs/PLUGIN_ENTWICKLUNG.md.
"""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request

from ...core.formatting import parse_number
from ...core.modules import DossierSection, ExperimentPanel, ModuleBase, NavEntry
from .models import MvrTest


def build_router() -> APIRouter:
    from ...models import Device, Experiment, Measurement, MeasurementValue, Sample
    from ...services import audit
    from ...services.entities import ref_options
    from ...services.numbering import next_code
    from ...services.records import RecordError, device_warnings
    from ...web.deps import Ctx, get_ctx

    router = APIRouter(prefix="/module/mvr")

    def validate(form) -> tuple[dict, dict]:
        errors, data = {}, {}
        for name, label, required in (("temperature_c", "Prüftemperatur", True), ("load_kg", "Prüflast", True),
                                      ("melt_density", "Schmelzedichte", False)):
            try:
                data[name] = parse_number(form.get(name))
            except ValueError:
                errors[name] = "Bitte eine gültige Zahl eingeben (z. B. 2,16)."
                continue
            if required and data[name] is None:
                errors[name] = "Pflichtfeld – bitte ausfüllen."
        if data.get("temperature_c") is not None and not (100 <= data["temperature_c"] <= 450):
            errors["temperature_c"] = "Prüftemperatur außerhalb 100–450 °C."
        if data.get("load_kg") is not None and not (0.1 <= data["load_kg"] <= 30):
            errors["load_kg"] = "Prüflast außerhalb 0,1–30 kg."
        values = []
        for part in (form.get("values") or "").replace("\n", ";").split(";"):
            if part.strip():
                try:
                    values.append(parse_number(part))
                except ValueError:
                    errors["values"] = f"»{part.strip()}« ist keine gültige Zahl."
        if not values:
            errors.setdefault("values", "Mindestens ein Messwert ist erforderlich.")
        data["values"] = values
        sid = form.get("sample_id", "")
        if not sid.isdigit():
            errors["sample_id"] = "Bitte eine Probe auswählen."
        data["sample_id"] = int(sid) if sid.isdigit() else None
        data["device_id"] = int(form["device_id"]) if (form.get("device_id") or "").isdigit() else None
        data["remark"] = (form.get("remark") or "").strip() or None
        return data, errors

    def options(ctx):
        return {"samples": ref_options(ctx.db, "sample"), "devices": ref_options(ctx.db, "device")}

    @router.get("")
    def list_view(ctx: Ctx = Depends(get_ctx)):
        ctx.require("view")
        return ctx.render("mvr/list.html", tests=ctx.db.query(MvrTest).order_by(MvrTest.id.desc()).all())

    @router.get("/neu")
    def new_view(request: Request, ctx: Ctx = Depends(get_ctx)):
        ctx.require("create")
        values = {"temperature_c": "230", "load_kg": "2,16", "sample_id": request.query_params.get("sample_id", ""),
                  "device_id": "", "values": "", "melt_density": "", "remark": ""}
        mflow = ctx.db.query(Device).filter(Device.name.ilike("%mflow%")).first()
        if mflow:
            values["device_id"] = str(mflow.id)
        return ctx.render("mvr/form.html", values=values, errors={}, **options(ctx))

    @router.post("/neu")
    async def create(request: Request, ctx: Ctx = Depends(get_ctx)):
        ctx.require("create")
        form = await request.form()
        data, errors = validate(form)
        if errors:
            return ctx.render("mvr/form.html", values=dict(form), errors=errors, **options(ctx))
        sample = ctx.db.get(Sample, data["sample_id"])
        if sample is None:
            raise RecordError("Probe nicht gefunden.")
        if sample.experiment is not None and sample.experiment.locked:
            raise RecordError(f"Versuch {sample.experiment.code} ist gesperrt.")
        t = MvrTest(code=next_code(ctx.db, "mvr", prefix="MVR"), sample_id=sample.id,
                    experiment_id=sample.experiment_id, device_id=data["device_id"],
                    temperature_c=data["temperature_c"], load_kg=data["load_kg"], melt_density=data["melt_density"],
                    values_json=json.dumps(data["values"]), remark=data["remark"], created_by_id=ctx.user.id,
                    updated_by_id=ctx.user.id)
        ctx.db.add(t)
        ctx.db.flush()
        audit.log(ctx.db, ctx.actor, "create", entity_type="mvr_test", entity=t,
                  new=f"Probe {sample.code}; {len(data['values'])} Werte; Mittel {t.stats['mean']:.3f}")
        if t.device:
            for w in device_warnings(ctx.db, [t.device]):
                ctx.flash("warning", w)
        return ctx.redirect(f"/module/mvr/{t.id}", "success", f"MVR-Prüfung {t.code} gespeichert.")

    @router.get("/{tid:int}")
    def detail(tid: int, ctx: Ctx = Depends(get_ctx)):
        ctx.require("view")
        t = ctx.db.get(MvrTest, tid)
        if t is None:
            raise HTTPException(404)
        return ctx.render("mvr/detail.html", t=t)

    @router.post("/{tid:int}/uebernehmen")
    def to_measurement(tid: int, ctx: Ctx = Depends(get_ctx)):
        """Ergebnis als Messdatensatz in den ELN-Kern übernehmen (für Auswertungen)."""
        ctx.require("create")
        t = ctx.db.get(MvrTest, tid)
        if t is None:
            raise HTTPException(404)
        if t.measurement_id:
            return ctx.redirect(f"/messdaten/{t.measurement_id}", "info", "Bereits übernommen.")
        m = Measurement(code=next_code(ctx.db, "measurement"), name=f"MVR {t.sample.code}", property_name="MVR",
                        unit="cm³/10 min", experiment_id=t.experiment_id, sample_id=t.sample_id,
                        device_id=t.device_id, source="Modul MVR",
                        metadata_json=json.dumps({"Temperatur_C": t.temperature_c, "Last_kg": t.load_kg,
                                                  "MVR-Prüfung": t.code}, ensure_ascii=False),
                        conditions=f"{t.temperature_c:g} °C / {t.load_kg:g} kg (ISO 1133)",
                        created_by_id=ctx.user.id, updated_by_id=ctx.user.id)
        for i, v in enumerate(t.values):
            m.values.append(MeasurementValue(idx=i, value=v))
        ctx.db.add(m)
        ctx.db.flush()
        t.measurement_id = m.id
        audit.log(ctx.db, ctx.actor, "create", entity_type="measurement", entity=m, new=f"aus {t.code} übernommen")
        return ctx.redirect(f"/messdaten/{m.id}", "success", f"Messdatensatz {m.code} angelegt.")

    return router


def import_values(db, actor, rows, commit):
    """Import von MVR-Einzelwerten (eine Zeile je Wert; gleiche Probe/Bedingung = eine Prüfung)."""
    from ...models import Sample
    from ...services import audit
    from ...services.importer import ImportReport
    from ...services.numbering import next_code

    report = ImportReport(total_rows=len(rows))
    groups: dict[tuple, dict] = {}
    for n, row in enumerate(rows, start=2):
        r = {str(k).strip().lower(): v for k, v in row.items()}
        sample = db.query(Sample).filter(Sample.code == str(r.get("sample") or "").strip()).first()
        if sample is None:
            report.errors.append((n, "sample", f"Probe »{r.get('sample')}« nicht gefunden."))
            continue
        try:
            temp, load = parse_number(r.get("temperature_c")), parse_number(r.get("load_kg"))
            value, dens = parse_number(r.get("value")), parse_number(r.get("melt_density"))
        except ValueError:
            report.errors.append((n, "Zahl", "Bitte gültige Zahlen eingeben (z. B. 2,16)."))
            continue
        if temp is None or load is None or value is None:
            report.errors.append((n, "temperature_c/load_kg/value", "Pflichtfeld – bitte ausfüllen."))
            continue
        if sample.experiment is not None and sample.experiment.locked:
            report.errors.append((n, "sample", f"Versuch {sample.experiment.code} ist gesperrt."))
            continue
        g = groups.setdefault((sample.id, temp, load), {"sample": sample, "density": dens, "values": []})
        g["values"].append(value)
    if report.errors or not commit:
        return report
    for (sid, temp, load), g in groups.items():
        t = MvrTest(code=next_code(db, "mvr", prefix="MVR"), sample_id=sid, experiment_id=g["sample"].experiment_id,
                    temperature_c=temp, load_kg=load, melt_density=g["density"], values_json=json.dumps(g["values"]),
                    remark="Import", created_by_id=actor.user_id, updated_by_id=actor.user_id)
        db.add(t)
        db.flush()
        audit.log(db, actor, "create", entity_type="mvr_test", entity=t, new=f"Import: {len(g['values'])} Werte")
        report.created += 1
        report.created_codes.append(t.code)
    report.committed = True
    return report


def _panel(db, experiment, user):
    return {"tests": db.query(MvrTest).filter(MvrTest.experiment_id == experiment.id).all()}


class MvrModule(ModuleBase):
    key = "mvr"
    name = "MVR / MFR"
    version = "0.9.0"
    description = ("Beispielmodul mit eigenem Datenmodell: Schmelze-Volumenfließrate nach ISO 1133 mit "
                   "Kennwerten, MFR-Berechnung und Übernahme als Messdatensatz.")
    category = "Rheologie"
    maturity = "Beispiel"
    default_enabled = True
    links_to = ("experiment", "sample", "device", "user")

    def models(self):
        return [MvrTest]

    def router(self):
        return build_router()

    def templates_dir(self):
        return Path(__file__).parent / "templates"

    def nav_entries(self):
        return [NavEntry("MVR / MFR", "/module/mvr")]

    def experiment_panels(self):
        return [ExperimentPanel("MVR / MFR", "mvr/panel.html", _panel)]

    def import_handlers(self):
        return {"Einzelwerte": import_values}

    def dossier_sections(self, db, experiment):
        tests = db.query(MvrTest).filter(MvrTest.experiment_id == experiment.id).all()
        if not tests:
            return []
        return [DossierSection("MVR/MFR-Prüfungen", ["ID", "Probe", "Bedingung", "n", "MVR Mittel", "Std.-Abw.", "MFR"],
                               [[t.code, t.sample.code, f"{t.temperature_c:g} °C/{t.load_kg:g} kg", t.stats["n"],
                                 t.stats["mean"], t.stats["std"], t.mfr] for t in tests])]


MODULE = MvrModule()
