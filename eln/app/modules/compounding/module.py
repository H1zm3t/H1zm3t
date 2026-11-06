"""Fachmodul Compoundierung – Registrierung und Erweiterungspunkte."""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import or_

from ...core.modules import AnalysisDataset, DossierSection, ExperimentPanel, ModuleBase, NavEntry, SearchHit
from ...services.entities import restricted_order_ids
from .models import CompoundingFeeder, CompoundingReading, CompoundingRun, CompoundingZone


def _panel_context(db, experiment, user) -> dict:
    runs = db.query(CompoundingRun).filter(CompoundingRun.experiment_id == experiment.id) \
        .order_by(CompoundingRun.code).all()
    return {"runs": runs, "experiment": experiment}


def _dataset(db, user) -> list[dict]:
    hidden = restricted_order_ids(db, user)
    rows = []
    for r in db.query(CompoundingRun).all():
        if r.experiment.order_id in hidden:
            continue
        base = {
            "code": r.code, "experiment": r.experiment.code, "extruder": r.device.name if r.device else "(ohne)",
            "recipe": r.recipe.label if r.recipe else "(ohne)", "status": r.status,
            "month": r.start_time.strftime("%Y-%m") if r.start_time else None,
            "created": (r.start_time or r.created_at).date(),
            "throughput_actual": r.throughput_actual, "screw_speed": r.screw_speed, "torque": r.torque,
            "melt_pressure": r.melt_pressure, "melt_temperature": r.melt_temperature, "vacuum": r.vacuum,
            "duration_min": r.duration_min,
        }
        rows.append(base)
    return rows


class CompoundingModule(ModuleBase):
    key = "compounding"
    name = "Compoundierung"
    version = "1.0.0"
    description = ("Dokumentation von Compoundierversuchen auf dem Doppelschneckenextruder: Rezeptur, "
                   "Schneckenkonfiguration, Dosierung, dynamische Temperaturzonen, Prozessparameter und -verlauf, "
                   "Probenahmen, erzeugte Proben, Vergleich mehrerer Läufe.")
    category = "Verarbeitung"
    maturity = "produktiv"
    default_enabled = True
    icon = "extruder"
    links_to = ("order", "experiment", "sample", "material", "device", "user")
    departments = ("Compoundierung", "Musterherstellung", "Mischen / Mahlen")

    def models(self):
        return [CompoundingRun, CompoundingZone, CompoundingFeeder, CompoundingReading]

    def router(self):
        from .routes import router

        return router

    def templates_dir(self):
        return Path(__file__).parent / "templates"

    def nav_entries(self):
        return [NavEntry("Compoundierung", "/module/compoundierung", icon="extruder")]

    def experiment_panels(self):
        return [ExperimentPanel("Compoundierung", "compounding/panel.html", _panel_context)]

    def default_config(self) -> dict:
        return {
            "default_zones": ["Einzug", "Zone 1", "Zone 2", "Zone 3", "Zone 4", "Zone 5", "Zone 6", "Zone 7",
                              "Zone 8", "Zone 9", "Zone 10", "Düse"],
            "zone_templates": {
                "Leistritz ZSE 27 MAXX": ["Einzug", "Zone 1", "Zone 2", "Zone 3", "Zone 4", "Zone 5", "Zone 6",
                                          "Zone 7", "Zone 8", "Zone 9", "Zone 10", "Adapter", "Düse"],
            },
        }

    def dossier_sections(self, db, experiment):
        sections = []
        for r in db.query(CompoundingRun).filter(CompoundingRun.experiment_id == experiment.id).order_by(CompoundingRun.code):
            sections.append(DossierSection(
                f"Compoundierlauf {r.code} – {r.title}", ["Parameter", "Wert"],
                [["Extruder", r.device.name if r.device else None],
                 ["Rezeptur", r.recipe.label if r.recipe else None],
                 ["Start / Ende", f"{r.start_time:%d.%m.%Y %H:%M}" if r.start_time else None],
                 ["Dauer (min)", r.duration_min], ["Schneckenkonfiguration", r.screw_config],
                 ["Durchsatz Soll/Ist (kg/h)", f"{r.throughput_set} / {r.throughput_actual}"],
                 ["Drehzahl (1/min)", r.screw_speed], ["Drehmoment (%)", r.torque],
                 ["Massedruck (bar)", r.melt_pressure], ["Schmelzetemperatur (°C)", r.melt_temperature],
                 ["Vakuum (mbar)", r.vacuum], ["Kühlung", r.cooling], ["Granulierung", r.pelletizing],
                 ["Beobachtungen", r.observations], ["Störungen", r.disturbances], ["Abweichungen", r.deviations],
                 ["Probenahmen", r.sampling], ["Bewertung", r.evaluation]]))
            if r.zones:
                sections.append(DossierSection(f"{r.code}: Zylindertemperaturen", ["Zone", "Soll °C", "Ist °C"],
                                               [[z.name, z.set_temp, z.actual_temp] for z in r.zones]))
            if r.feeders:
                sections.append(DossierSection(
                    f"{r.code}: Dosierung", ["Dosierstelle", "Dosiergerät", "Komponente", "Soll kg/h", "Ist kg/h"],
                    [[f.feed_point, f.feeder, f.material.name if f.material else f.component, f.set_rate,
                      f.actual_rate] for f in r.feeders]))
            if r.readings:
                sections.append(DossierSection(
                    f"{r.code}: Prozessverlauf", ["min", "Drehzahl", "Drehmoment %", "Druck bar", "T Schmelze °C",
                                                  "Durchsatz kg/h"],
                    [[x.minute, x.screw_speed, x.torque, x.melt_pressure, x.melt_temperature, x.throughput]
                     for x in r.readings]))
        return sections

    def search(self, db, term, user):
        like = f"%{term}%"
        hidden = restricted_order_ids(db, user)
        hits = []
        q = db.query(CompoundingRun).filter(or_(CompoundingRun.code.ilike(like), CompoundingRun.title.ilike(like),
                                                CompoundingRun.observations.ilike(like),
                                                CompoundingRun.disturbances.ilike(like),
                                                CompoundingRun.deviations.ilike(like),
                                                CompoundingRun.evaluation.ilike(like),
                                                CompoundingRun.screw_config.ilike(like)))
        for r in q.limit(100):
            if r.experiment.order_id in hidden:
                continue
            hits.append(SearchHit("compounding_run", r.id, r.code, r.title, f"/module/compoundierung/{r.id}",
                                  snippet=(r.observations or r.evaluation or "")[:160], status=r.status,
                                  date=r.created_at, type_label="Compoundierlauf"))
        return hits

    def analysis_datasets(self):
        return [AnalysisDataset(
            "compounding_runs", "Compoundierläufe",
            {"extruder": "Extruder", "recipe": "Rezeptur", "experiment": "Versuch", "status": "Status",
             "month": "Monat", "throughput_actual": "Durchsatz Ist [kg/h]", "screw_speed": "Drehzahl [1/min]",
             "torque": "Drehmoment [%]", "melt_pressure": "Massedruck [bar]",
             "melt_temperature": "Schmelzetemperatur [°C]", "vacuum": "Vakuum [mbar]", "duration_min": "Dauer [min]"},
            ["throughput_actual", "screw_speed", "torque", "melt_pressure", "melt_temperature", "vacuum",
             "duration_min"], _dataset, date_field="created")]

    # Auflösung für Anhänge, Audit Trail und Aufgaben
    def get_entity(self, db, entity_type, entity_id):
        if entity_type == "compounding_run":
            return db.get(CompoundingRun, entity_id)
        return None

    def entity_url(self, entity_type, entity_id):
        if entity_type == "compounding_run":
            return f"/module/compoundierung/{entity_id}"
        return None


MODULE = CompoundingModule()
