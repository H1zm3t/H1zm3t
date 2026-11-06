"""Geschäftslogik Compoundierung: Anlegen/Ändern mit Audit Trail, Tabellenzeilen, Vergleich."""
from __future__ import annotations

from sqlalchemy.orm import Session

from ...core.forms import FieldSpec as F
from ...core.formatting import parse_number
from ...models import Device, Material
from ...services import audit
from ...services.audit import Actor
from ...services.numbering import next_code
from ...services.records import RecordError, device_warnings
from .models import CompoundingFeeder, CompoundingReading, CompoundingRun, CompoundingZone

STATUS = ("geplant", "durchgeführt", "bewertet", "verworfen")

RUN_FIELDS = [
    F("title", "Bezeichnung", required=True, width="full", group="Allgemein"),
    F("experiment_id", "Versuch", kind="ref", ref="experiment", required=True, group="Allgemein"),
    F("recipe_id", "Rezeptur", kind="ref", ref="recipe", group="Allgemein"),
    F("device_id", "Extruder", kind="ref", ref="device", group="Allgemein"),
    F("operator_id", "Anlagenfahrer", kind="ref", ref="user", group="Allgemein"),
    F("status", "Status", kind="select", options=STATUS, required=True, group="Allgemein"),
    F("start_time", "Startzeit", kind="datetime", group="Allgemein"),
    F("end_time", "Endzeit", kind="datetime", group="Allgemein"),
    F("screw_config", "Schneckenkonfiguration", kind="textarea", width="full", group="Allgemein",
      help="Beschreibung; Konfigurationsdatei bitte als Anhang mit Kategorie »Schneckenkonfiguration« hochladen."),
    F("throughput_set", "Durchsatz Soll", kind="float", unit="kg/h", width="third", group="Prozessparameter"),
    F("throughput_actual", "Durchsatz Ist", kind="float", unit="kg/h", width="third", group="Prozessparameter"),
    F("screw_speed", "Drehzahl", kind="float", unit="1/min", width="third", group="Prozessparameter"),
    F("torque", "Drehmoment", kind="float", unit="%", width="third", group="Prozessparameter"),
    F("melt_pressure", "Massedruck", kind="float", unit="bar", width="third", group="Prozessparameter"),
    F("melt_temperature", "Schmelzetemperatur", kind="float", unit="°C", width="third", group="Prozessparameter"),
    F("vacuum", "Vakuum", kind="float", unit="mbar", width="third", group="Prozessparameter"),
    F("cooling", "Kühlung", kind="textarea", group="Prozessparameter", help="z. B. Wasserbad 25 °C, Länge 3 m"),
    F("pelletizing", "Granulierung", kind="textarea", group="Prozessparameter",
      help="z. B. Stranggranulator, Granulatlänge 3 mm"),
    F("observations", "Prozessbeobachtungen", kind="textarea", width="full", group="Dokumentation"),
    F("disturbances", "Störungen", kind="textarea", width="full", group="Dokumentation"),
    F("deviations", "Abweichungen", kind="textarea", width="full", group="Dokumentation"),
    F("sampling", "Probenahmen", kind="textarea", width="full", group="Dokumentation"),
    F("evaluation", "Bewertung", kind="textarea", width="full", group="Dokumentation"),
]
LABELS = {f.name: f.label for f in RUN_FIELDS}

NUMERIC_PARAMS = [("throughput_actual", "Durchsatz Ist", "kg/h"), ("screw_speed", "Drehzahl", "1/min"),
                  ("torque", "Drehmoment", "%"), ("melt_pressure", "Massedruck", "bar"),
                  ("melt_temperature", "Schmelzetemperatur", "°C"), ("vacuum", "Vakuum", "mbar")]

DEFAULT_ZONES = ["Einzug", "Zone 1", "Zone 2", "Zone 3", "Zone 4", "Zone 5", "Zone 6", "Zone 7", "Zone 8",
                 "Zone 9", "Zone 10", "Düse"]


def _num(v):
    try:
        return parse_number(v)
    except ValueError:
        raise RecordError(f"»{v}« ist keine gültige Zahl.") from None


def _rows(form, prefix: str, fields: tuple[str, ...]) -> list[dict]:
    idx = sorted({int(k.split("-")[1]) for k in form.keys() if k.startswith(prefix + "-") and k.count("-") >= 2})
    out = []
    for i in idx:
        row = {f: (form.get(f"{prefix}-{i}-{f}") or "").strip() for f in fields}
        if any(row.values()):
            out.append(row)
    return out


def parse_tables(db: Session, form) -> tuple[dict, list[str]]:
    errors: list[str] = []
    zones, feeders, readings = [], [], []
    try:
        for n, r in enumerate(_rows(form, "zone", ("name", "set_temp", "actual_temp")), start=1):
            if not r["name"]:
                errors.append(f"Temperaturzone {n}: Bezeichnung fehlt.")
                continue
            zones.append({"position": n, "name": r["name"][:60], "set_temp": _num(r["set_temp"]),
                          "actual_temp": _num(r["actual_temp"])})
        for n, r in enumerate(_rows(form, "feeder", ("feed_point", "feeder", "material_id", "component", "set_rate",
                                                      "actual_rate")), start=1):
            if not r["feed_point"]:
                errors.append(f"Dosierung {n}: Dosierstelle fehlt.")
                continue
            mat = None
            if r["material_id"]:
                mat = db.get(Material, int(r["material_id"])) if r["material_id"].isdigit() else None
                if mat is None:
                    errors.append(f"Dosierung {n}: Material nicht gefunden.")
                    continue
            feeders.append({"position": n, "feed_point": r["feed_point"][:60], "feeder": r["feeder"][:120] or None,
                            "material_id": mat.id if mat else None, "component": r["component"][:200] or None,
                            "set_rate": _num(r["set_rate"]), "actual_rate": _num(r["actual_rate"])})
        for n, r in enumerate(_rows(form, "reading", ("minute", "screw_speed", "torque", "melt_pressure",
                                                       "melt_temperature", "throughput", "remark")), start=1):
            minute = _num(r["minute"])
            if minute is None:
                errors.append(f"Prozessverlauf Zeile {n}: Zeitpunkt (min) fehlt.")
                continue
            readings.append({"minute": minute, **{k: _num(r[k]) for k in ("screw_speed", "torque", "melt_pressure",
                                                                           "melt_temperature", "throughput")},
                             "remark": r["remark"][:200] or None})
    except RecordError as exc:
        errors.append(str(exc))
    readings.sort(key=lambda x: x["minute"])
    return {"zones": zones, "feeders": feeders, "readings": readings}, errors


def _table_text(rows: list, keys: tuple) -> str | None:
    return "\n".join("; ".join(f"{k}={r.get(k) if isinstance(r, dict) else getattr(r, k)}" for k in keys)
                     for r in rows) or None


def _apply_tables(db: Session, actor: Actor, run: CompoundingRun, tables: dict, reason: str | None) -> bool:
    changed = False
    specs = [("zones", CompoundingZone, ("name", "set_temp", "actual_temp"), "Temperaturzonen"),
             ("feeders", CompoundingFeeder, ("feed_point", "feeder", "material_id", "component", "set_rate",
                                             "actual_rate"), "Dosierungen"),
             ("readings", CompoundingReading, ("minute", "screw_speed", "torque", "melt_pressure", "melt_temperature",
                                               "throughput", "remark"), "Prozessverlauf")]
    for attr, model, keys, label in specs:
        old = _table_text(getattr(run, attr), keys)
        new = _table_text(tables[attr], keys)
        if old == new:
            continue
        getattr(run, attr).clear()
        db.flush()
        for r in tables[attr]:
            getattr(run, attr).append(model(**r))
        if run.id:
            audit.log(db, actor, "update", entity_type="compounding_run", entity=run, field=label, old=old, new=new,
                      reason=reason)
        changed = True
    return changed


def check_editable(run: CompoundingRun | None, experiment) -> None:
    exp = experiment or (run.experiment if run else None)
    if exp is not None and exp.locked:
        raise RecordError(f"Versuch {exp.code} ist gesperrt (»{exp.status}«). Compoundierdaten können erst nach "
                          "Anlage einer neuen Revision geändert werden.")


def save_run(db: Session, actor: Actor, run: CompoundingRun | None, values: dict, tables: dict,
             reason: str | None) -> tuple[CompoundingRun, list[str]]:
    from ...models import Experiment

    exp = db.get(Experiment, values["experiment_id"])
    if exp is None:
        raise RecordError("Der Versuch existiert nicht.")
    check_editable(run, exp)
    if values.get("start_time") and values.get("end_time") and values["end_time"] < values["start_time"]:
        raise RecordError("Die Endzeit liegt vor der Startzeit.")
    if run is None:
        run = CompoundingRun(code=next_code(db, "compounding", prefix="C"), created_by_id=actor.user_id)
        for k, v in values.items():
            setattr(run, k, v)
        run.updated_by_id = actor.user_id
        db.add(run)
        db.flush()
        _apply_tables(db, actor, run, tables, reason)
        audit.log(db, actor, "create", entity_type="compounding_run", entity=run,
                  new=f"{run.label} (Versuch {exp.code})")
    else:
        if run.experiment.status not in ("Entwurf", "geplant", "in Bearbeitung", "pausiert") and not reason:
            raise RecordError("Bitte einen Änderungsgrund angeben.")
        changed = False
        for k, v in values.items():
            old = getattr(run, k)
            if old != v:
                audit.log(db, actor, "update", entity_type="compounding_run", entity=run, field=LABELS.get(k, k),
                          old=old, new=v, reason=reason)
                setattr(run, k, v)
                changed = True
        changed = _apply_tables(db, actor, run, tables, reason) or changed
        if changed:
            run.version += 1
            run.updated_by_id = actor.user_id
    warnings = device_warnings(db, [run.device]) if run.device else []
    if run.device and run.device.device_type and run.device.device_type != "Extruder":
        warnings.append(f"Gerät {run.device.code} ist nicht als Extruder klassifiziert.")
    return run, warnings


def zone_template(db: Session, device: Device | None, config: dict) -> list[str]:
    templates = config.get("zone_templates", {})
    if device is not None:
        for key in (device.code, device.name, device.model or ""):
            if key in templates:
                return templates[key]
    return config.get("default_zones") or DEFAULT_ZONES


def comparison(runs: list[CompoundingRun]) -> dict:
    zone_names: list[str] = []
    for r in runs:
        for z in r.zones:
            if z.name not in zone_names:
                zone_names.append(z.name)
    params = []
    for attr, label, unit in [("throughput_set", "Durchsatz Soll", "kg/h")] + NUMERIC_PARAMS:
        vals = [getattr(r, attr) for r in runs]
        present = [v for v in vals if v is not None]
        params.append({"label": label, "unit": unit, "values": vals,
                       "differs": len(set(present)) > 1 or (0 < len(present) < len(vals))})
    zone_rows = []
    for name in zone_names:
        vals = []
        for r in runs:
            z = next((z for z in r.zones if z.name == name), None)
            vals.append((z.set_temp, z.actual_temp) if z else (None, None))
        set_vals = [v[0] for v in vals if v[0] is not None]
        zone_rows.append({"name": name, "values": vals, "differs": len(set(set_vals)) > 1})
    chart = {"zones": zone_names,
             "runs": [{"label": r.code, "set": [next((z.set_temp for z in r.zones if z.name == n), None)
                                                for n in zone_names],
                       "actual": [next((z.actual_temp for z in r.zones if z.name == n), None) for n in zone_names]}
                      for r in runs],
             "params": [{"label": f"{p['label']} [{p['unit']}]", "values": p["values"]} for p in params]}
    return {"runs": runs, "params": params, "zone_rows": zone_rows, "chart": chart}
