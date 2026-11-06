"""Import aus CSV, JSON und Excel mit Validierungsbericht.

Grundsatz: Ein Import ist eine Transaktion. Enthält auch nur eine Zeile einen
Fehler, wird nichts gespeichert und ein Validierungsbericht angezeigt.

Referenzen werden über fachliche Kennungen aufgelöst (z. B. Material über
interne ID »M-00001« oder Materialnummer, Benutzer über den Benutzernamen).
"""
from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass, field
from typing import Any

from openpyxl import Workbook, load_workbook
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..core.forms import FieldSpec, validate_values
from ..core.formatting import parse_number
from ..models import Batch, Device, Experiment, Material, Measurement, MeasurementValue, Method, Recipe, Sample, User
from . import audit, records
from .audit import Actor
from .entities import ENTITY_DEFS
from .numbering import next_code
from .records import RecordError

IMPORTABLE = {
    "material": "Materialien", "batch": "Chargen", "device": "Geräte", "method": "Methoden",
    "project": "Projekte", "order": "Aufträge", "sample": "Proben", "measurement": "Messdaten (Messwerte)",
}

MEASUREMENT_COLUMNS = ["measurement_name", "property_name", "unit", "x_name", "x_unit", "sample", "experiment",
                       "device", "method", "measured_on", "x_value", "value", "label", "meta_pruefbedingung"]
RECIPE_ITEM_COLUMNS = ["material", "batch", "function", "target_amount", "unit", "actual_amount", "weight_percent",
                       "tolerance", "remark"]


@dataclass
class ImportReport:
    total_rows: int = 0
    created: int = 0
    errors: list[tuple[int, str, str]] = field(default_factory=list)  # (zeile, feld, meldung)
    committed: bool = False
    created_codes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def read_table(filename: str, content: bytes) -> list[dict]:
    name = filename.lower()
    if name.endswith(".json"):
        data = json.loads(content.decode("utf-8-sig"))
        if isinstance(data, dict):
            data = data.get("rows") or data.get("data") or []
        if not isinstance(data, list) or not all(isinstance(r, dict) for r in data):
            raise RecordError("JSON muss eine Liste von Objekten enthalten (oder {\"rows\": [...]}).")
        return data
    if name.endswith(".xlsx") or name.endswith(".xlsm"):
        wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        ws = wb.worksheets[0]
        rows = list(ws.iter_rows(values_only=True))
        wb.close()
        if not rows:
            return []
        headers = [str(h).strip() if h is not None else "" for h in rows[0]]
        out = []
        for r in rows[1:]:
            if all(v is None or str(v).strip() == "" for v in r):
                continue
            out.append({headers[i]: r[i] for i in range(min(len(headers), len(r))) if headers[i]})
        return out
    if name.endswith(".csv") or name.endswith(".txt"):
        for enc in ("utf-8-sig", "cp1252"):
            try:
                text = content.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            raise RecordError("Die Datei konnte nicht gelesen werden (Zeichensatz).")
        sample = text[:4096]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=";,\t")
        except csv.Error:
            dialect = csv.excel
            dialect.delimiter = ";"
        reader = csv.DictReader(io.StringIO(text), dialect=dialect)
        return [{(k or "").strip(): v for k, v in row.items()} for row in reader
                if any((v or "").strip() for v in row.values() if isinstance(v, str))]
    raise RecordError("Unterstützte Formate: CSV, JSON, XLSX.")


def _header_map(specs: list[FieldSpec]) -> dict[str, str]:
    m = {}
    for s in specs:
        m[s.name.lower()] = s.name
        m[s.label.lower()] = s.name
        if s.name.endswith("_id"):
            m[s.name[:-3].lower()] = s.name
    return m


def resolve_ref(db: Session, ref: str, value: Any) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    text = str(value).strip()
    if ref == "user":
        u = db.query(User).filter(or_(User.username == text.lower(), User.full_name == text)).first()
        return u.id if u else None
    model = ENTITY_DEFS[ref].model
    cond = [model.code == text]
    if ref == "material":
        cond.append(Material.material_number == text)
    if ref == "batch":
        cond.append(Batch.batch_number == text)
    obj = db.query(model).filter(or_(*cond)).first()
    return obj.id if obj else None


def _uniqueness(db: Session, key: str, values: dict) -> str | None:
    if key == "material" and values.get("material_number"):
        if db.query(Material).filter(Material.material_number == values["material_number"]).first():
            return f"Materialnummer {values['material_number']} existiert bereits."
    if key == "batch":
        if db.query(Batch).filter(Batch.material_id == values.get("material_id"),
                                  Batch.batch_number == values.get("batch_number")).first():
            return f"Charge {values.get('batch_number')} existiert für dieses Material bereits."
    return None


def import_entities(db: Session, actor: Actor, key: str, rows: list[dict], commit: bool) -> ImportReport:
    d = ENTITY_DEFS[key]
    specs = list(d.fields)
    hmap = _header_map(specs)
    report = ImportReport(total_rows=len(rows))
    prepared: list[dict] = []
    seen_numbers: set = set()
    for n, row in enumerate(rows, start=2):
        raw: dict = {}
        for h, v in row.items():
            name = hmap.get(str(h).strip().lower())
            if not name:
                continue
            spec = next(s for s in specs if s.name == name)
            if spec.kind == "ref":
                if v not in (None, ""):
                    rid = resolve_ref(db, spec.ref, v)
                    if rid is None:
                        report.errors.append((n, spec.label, f"»{v}« wurde nicht gefunden."))
                        continue
                    raw[name] = rid
            elif spec.kind == "multi_ref":
                ids = []
                for part in str(v or "").replace(";", ",").split(","):
                    if part.strip():
                        rid = resolve_ref(db, spec.ref, part)
                        if rid is None:
                            report.errors.append((n, spec.label, f"»{part.strip()}« wurde nicht gefunden."))
                        else:
                            ids.append(rid)
                raw[name] = ids
            else:
                raw[name] = v if not hasattr(v, "isoformat") or spec.kind in ("date", "datetime") else v
        for k, dv in d.default_values.items():
            if raw.get(k) in (None, ""):
                raw[k] = dv
        values, errors = validate_values(specs, raw, f"Import_{key}")
        for fname, msg in errors.items():
            label = next((s.label for s in specs if s.name == fname), fname)
            report.errors.append((n, label, msg))
        if values is None:
            continue
        dup = _uniqueness(db, key, values)
        uniq_key = (values.get("material_number") if key == "material" else
                    (values.get("material_id"), values.get("batch_number")) if key == "batch" else None)
        if uniq_key and uniq_key in seen_numbers:
            dup = "Doppelter Eintrag innerhalb der Importdatei."
        if uniq_key:
            seen_numbers.add(uniq_key)
        if dup:
            report.errors.append((n, "Eindeutigkeit", dup))
            continue
        prepared.append(values)
    if report.errors or not commit:
        return report
    for values in prepared:
        obj = records.create_record(db, actor, key, values)
        report.created += 1
        report.created_codes.append(obj.code)
    audit.log(db, actor, "import", entity_type=key, new=f"{report.created} Datensätze importiert")
    report.committed = True
    return report


def _ref_by_code(db: Session, model, value) -> Any:
    if value in (None, ""):
        return None
    return db.query(model).filter(model.code == str(value).strip()).first()


def import_measurements(db: Session, actor: Actor, rows: list[dict], commit: bool) -> ImportReport:
    report = ImportReport(total_rows=len(rows))
    groups: dict[tuple, dict] = {}
    for n, row in enumerate(rows, start=2):
        r = {str(k).strip().lower(): v for k, v in row.items()}
        name = str(r.get("measurement_name") or "").strip()
        prop = str(r.get("property_name") or "").strip()
        if not name or not prop:
            report.errors.append((n, "measurement_name/property_name", "Pflichtfeld – bitte ausfüllen."))
            continue
        try:
            value = parse_number(r.get("value"))
            x_value = parse_number(r.get("x_value"))
        except ValueError:
            report.errors.append((n, "value/x_value", "Bitte eine gültige Zahl eingeben (z. B. 12,5)."))
            continue
        if value is None:
            report.errors.append((n, "value", "Messwert fehlt."))
            continue
        links = {}
        for col, model in (("sample", Sample), ("experiment", Experiment), ("device", Device), ("method", Method)):
            obj = _ref_by_code(db, model, r.get(col))
            if r.get(col) not in (None, "") and obj is None:
                report.errors.append((n, col, f"»{r.get(col)}« wurde nicht gefunden."))
            links[col] = obj
        measured_on = None
        if r.get("measured_on") not in (None, ""):
            from ..core.formatting import parse_date

            try:
                measured_on = parse_date(r.get("measured_on"))
            except (ValueError, TypeError):
                report.errors.append((n, "measured_on", "Bitte ein gültiges Datum eingeben (TT.MM.JJJJ)."))
        key = (name, prop, getattr(links["sample"], "id", None), getattr(links["experiment"], "id", None))
        g = groups.setdefault(key, {"name": name, "property": prop, "unit": r.get("unit"), "x_name": r.get("x_name"),
                                    "x_unit": r.get("x_unit"), "links": links, "measured_on": measured_on,
                                    "meta": {}, "values": []})
        for k, v in r.items():
            if k.startswith("meta_") and v not in (None, ""):
                g["meta"][k[5:]] = v
        g["values"].append((x_value, value, r.get("label")))
    if report.errors or not commit:
        return report
    for g in groups.values():
        m = Measurement(code=next_code(db, "measurement"), name=g["name"], property_name=g["property"],
                        unit=g["unit"] or None, x_name=g["x_name"] or None, x_unit=g["x_unit"] or None,
                        experiment=g["links"]["experiment"], sample=g["links"]["sample"],
                        device=g["links"]["device"], method=g["links"]["method"], measured_on=g["measured_on"],
                        metadata_json=json.dumps(g["meta"], ensure_ascii=False), source="Import",
                        created_by_id=actor.user_id, updated_by_id=actor.user_id)
        for idx, (x, v, label) in enumerate(g["values"]):
            m.values.append(MeasurementValue(idx=idx, x_value=x, value=v, label=str(label) if label else None))
        db.add(m)
        db.flush()
        audit.log(db, actor, "create", entity_type="measurement", entity=m,
                  new=f"Import: {len(g['values'])} Werte, {g['property']} [{g['unit'] or '-'}]")
        report.created += 1
        report.created_codes.append(m.code)
    report.committed = True
    return report


def recipe_rows_from_table(db: Session, rows: list[dict]) -> tuple[list[dict], list[tuple[int, str, str]]]:
    out, errors = [], []
    for n, row in enumerate(rows, start=2):
        r = {str(k).strip().lower(): v for k, v in row.items()}
        mat_text = r.get("material") or r.get("material_number") or r.get("materialnummer")
        mat_id = resolve_ref(db, "material", mat_text)
        if mat_id is None:
            errors.append((n, "material", f"Material »{mat_text}« wurde nicht gefunden."))
            continue
        batch_id = None
        if r.get("batch") not in (None, ""):
            batch = db.query(Batch).filter(Batch.material_id == mat_id,
                                           or_(Batch.batch_number == str(r["batch"]).strip(),
                                               Batch.code == str(r["batch"]).strip())).first()
            if batch is None:
                errors.append((n, "batch", f"Charge »{r['batch']}« zu diesem Material nicht gefunden."))
                continue
            batch_id = batch.id
        item = {"position": len(out) + 1, "material_id": mat_id, "batch_id": batch_id,
                "function": (str(r.get("function")).strip() if r.get("function") else None),
                "unit": (str(r.get("unit")).strip() if r.get("unit") else None),
                "remark": (str(r.get("remark")).strip() if r.get("remark") else None)}
        try:
            for f in ("target_amount", "actual_amount", "weight_percent", "tolerance"):
                item[f] = parse_number(r.get(f))
        except ValueError:
            errors.append((n, "Zahl", "Bitte gültige Zahlen eingeben (z. B. 12,5)."))
            continue
        out.append(item)
    return out, errors


def template_columns(key: str) -> list[str]:
    if key == "measurement":
        return MEASUREMENT_COLUMNS
    if key == "recipe_items":
        return RECIPE_ITEM_COLUMNS
    return [f.name[:-3] if f.kind == "ref" and f.name.endswith("_id") else f.name for f in ENTITY_DEFS[key].fields]


def template_xlsx(key: str) -> bytes:
    cols = template_columns(key)
    wb = Workbook()
    ws = wb.active
    ws.title = "Import"
    ws.append(cols)
    if key in ENTITY_DEFS:
        info = wb.create_sheet("Hinweise")
        info.append(["Spalte", "Bezeichnung", "Pflicht", "Typ / erlaubte Werte"])
        for f in ENTITY_DEFS[key].fields:
            col = f.name[:-3] if f.kind == "ref" and f.name.endswith("_id") else f.name
            typ = {"ref": f"Kennung ({f.ref})", "multi_ref": f"Kennungen kommagetrennt ({f.ref})",
                   "date": "Datum TT.MM.JJJJ", "float": "Zahl", "int": "ganze Zahl",
                   "select": "; ".join(f.options)}.get(f.kind, "Text")
            info.append([col, f.label, "ja" if f.required else "", typ])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def template_csv(key: str) -> bytes:
    return ("﻿" + ";".join(template_columns(key)) + "\n").encode("utf-8")
