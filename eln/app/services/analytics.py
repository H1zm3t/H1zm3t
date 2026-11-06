"""Allgemeine Auswertungen: Datenquellen, Filter, Gruppierung, Kennzahlen, Diagrammdaten."""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from sqlalchemy.orm import Session

from ..core.formatting import parse_date
from ..core.modules import AnalysisDataset, get_registry
from ..models import Experiment, Measurement, Recipe, Task, User
from .entities import restricted_order_ids

METRICS = {"count": "Anzahl", "mean": "Mittelwert", "median": "Median", "min": "Minimum", "max": "Maximum",
           "std": "Standardabweichung", "sum": "Summe"}
CHARTS = {"bar": "Balken", "line": "Linie", "scatter": "Punkte (x/y)", "boxplot": "Boxplot", "none": "nur Tabelle"}


def _month(d) -> str | None:
    return d.strftime("%Y-%m") if d else None


def _experiments(db: Session, user: User) -> list[dict]:
    hidden = restricted_order_ids(db, user)
    rows = []
    for e in db.query(Experiment).all():
        if e.order_id in hidden:
            continue
        end = e.approved_at or e.completed_at
        rows.append({
            "code": e.code, "title": e.title, "status": e.status, "department": e.department,
            "experiment_type": e.experiment_type,
            "responsible": e.responsible.full_name if e.responsible else "(ohne)",
            "client": (e.order.client if e.order else None) or "(ohne Auftrag)",
            "order": e.order.code if e.order else "(ohne)",
            "devices": [d.name for d in e.devices] or ["(kein Gerät)"],
            "month": _month(e.created_at), "year": str(e.created_at.year),
            "created": e.created_at.date(), "revision": e.revision,
            "lead_time_days": round((end - e.created_at).total_seconds() / 86400, 2) if end else None,
            "is_open": "offen" if e.status not in ("freigegeben", "archiviert", "abgebrochen") else "erledigt",
        })
    return rows


def _tasks(db: Session, user: User) -> list[dict]:
    rows = []
    for t in db.query(Task).all():
        rows.append({
            "code": t.code, "title": t.title, "status": t.status, "priority": t.priority,
            "assignee": t.assignee.full_name if t.assignee else "(niemand)",
            "overdue": "überfällig" if t.is_overdue else "im Plan",
            "month": _month(t.due_date), "created": t.created_at.date(),
            "open_days": ((t.completed_at or datetime.now()) - t.created_at).days,
        })
    return rows


def _measurement_values(db: Session, user: User) -> list[dict]:
    hidden = restricted_order_ids(db, user)
    rows = []
    for m in db.query(Measurement).all():
        if m.experiment and m.experiment.order_id in hidden:
            continue
        base = {
            "measurement": m.code, "name": m.name, "property": f"{m.property_name} [{m.unit or '-'}]",
            "unit": m.unit, "x_name": m.x_name, "sample": m.sample.code if m.sample else "(ohne)",
            "sample_name": m.sample.name if m.sample else "(ohne)",
            "batch": (m.sample.batch.batch_number if m.sample and m.sample.batch else "(ohne)"),
            "recipe": (m.sample.recipe.label if m.sample and m.sample.recipe else "(ohne)"),
            "experiment": m.experiment.code if m.experiment else "(ohne)",
            "device": m.device.name if m.device else "(ohne)", "method": m.method.name if m.method else "(ohne)",
            "month": _month(m.measured_on), "created": m.measured_on or m.created_at.date(),
        }
        for k, v in m.meta.items():
            base[f"meta_{k}"] = v
        for v in m.values:
            rows.append({**base, "value": v.value, "x_value": v.x_value, "label": v.label})
    return rows


def _material_usage(db: Session, user: User) -> list[dict]:
    hidden = restricted_order_ids(db, user)
    rows = []
    for e in db.query(Experiment).filter(Experiment.recipe_id.isnot(None)).all():
        if e.order_id in hidden:
            continue
        for i in e.recipe.items:
            rows.append({
                "material": i.material.name, "material_number": i.material.material_number or "(ohne)",
                "material_type": i.material.material_type, "batch": i.batch.batch_number if i.batch else "(ohne)",
                "recipe": e.recipe.label, "experiment": e.code, "weight_percent": i.weight_percent,
                "month": _month(e.created_at), "created": e.created_at.date(),
            })
    return rows


def _recipe_items(db: Session, user: User) -> list[dict]:
    rows = []
    for r in db.query(Recipe).all():
        for i in r.items:
            rows.append({"recipe": r.label, "recipe_code": r.code, "material": i.material.name,
                         "weight_percent": i.weight_percent, "batch": i.batch.batch_number if i.batch else "(ohne)",
                         "status": r.status, "created": r.created_at.date()})
    return rows


CORE_DATASETS = [
    AnalysisDataset(
        "experiments", "Versuche",
        {"status": "Status", "department": "Fachbereich", "experiment_type": "Versuchsart",
         "responsible": "Mitarbeiter", "client": "Auftraggeber", "order": "Auftrag", "devices": "Gerät",
         "month": "Monat", "year": "Jahr", "is_open": "offen/erledigt", "revision": "Revision",
         "lead_time_days": "Durchlaufzeit (Tage)"},
        ["lead_time_days", "revision"], _experiments, date_field="created"),
    AnalysisDataset(
        "tasks", "Aufgaben",
        {"status": "Status", "priority": "Priorität", "assignee": "Zuständig", "overdue": "Termintreue",
         "month": "Fälligkeitsmonat", "open_days": "Offen seit (Tage)"},
        ["open_days"], _tasks, date_field="created"),
    AnalysisDataset(
        "measurements", "Messwerte / Prüfergebnisse",
        {"property": "Messgröße", "measurement": "Datensatz", "sample": "Probe", "sample_name": "Probenname",
         "batch": "Charge", "recipe": "Rezeptur", "experiment": "Versuch", "device": "Gerät", "method": "Methode",
         "month": "Monat", "x_value": "Bezugsgröße x (Zeit/Temperatur)", "value": "Messwert"},
        ["value", "x_value"], _measurement_values, date_field="created"),
    AnalysisDataset(
        "material_usage", "Materialverwendung in Versuchen",
        {"material": "Material", "material_number": "Materialnummer", "material_type": "Materialtyp",
         "batch": "Charge", "recipe": "Rezeptur", "experiment": "Versuch", "month": "Monat",
         "weight_percent": "Anteil Gew.-%"},
        ["weight_percent"], _material_usage, date_field="created"),
    AnalysisDataset(
        "recipe_items", "Rezepturpositionen",
        {"recipe": "Rezeptur", "material": "Material", "batch": "Charge", "status": "Status",
         "weight_percent": "Anteil Gew.-%"},
        ["weight_percent"], _recipe_items, date_field="created"),
]


def datasets(db: Session) -> dict[str, AnalysisDataset]:
    result = {d.key: d for d in CORE_DATASETS}
    for module in get_registry().enabled(db):
        for d in module.analysis_datasets():
            result[d.key] = d
    return result


@dataclass
class AnalysisConfig:
    dataset: str = "experiments"
    group_by: str = "status"
    series_by: str = ""
    metric: str = "count"
    value_field: str = ""
    x_field: str = ""
    chart: str = "bar"
    date_from: str = ""
    date_to: str = ""
    filter_field: str = ""
    filter_value: str = ""

    @classmethod
    def from_mapping(cls, m) -> "AnalysisConfig":
        cfg = cls()
        for k in cfg.__dataclass_fields__:
            v = m.get(k) if hasattr(m, "get") else None
            if v is not None:
                setattr(cfg, k, str(v).strip())
        return cfg

    def to_dict(self) -> dict:
        return dict(self.__dict__)


def _stat(values: list[float], metric: str):
    if metric == "count":
        return len(values)
    if not values:
        return None
    return {
        "mean": statistics.fmean, "median": statistics.median, "min": min, "max": max, "sum": sum,
        "std": lambda v: statistics.stdev(v) if len(v) > 1 else 0.0,
    }[metric](values)


def _quartiles(values: list[float]) -> dict:
    v = sorted(values)
    if len(v) == 1:
        return {"min": v[0], "q1": v[0], "median": v[0], "q3": v[0], "max": v[0]}
    q = statistics.quantiles(v, n=4, method="inclusive")
    return {"min": v[0], "q1": q[0], "median": q[1], "q3": q[2], "max": v[-1]}


def _key(v: Any) -> str:
    if v is None or v == "":
        return "(leer)"
    if isinstance(v, float):
        return f"{v:g}"
    return str(v)


def _sort_key(text: str):
    try:
        return (0, float(text.replace(",", ".")), "")
    except ValueError:
        return (1, 0.0, text)


def run(db: Session, user: User, cfg: AnalysisConfig) -> dict:
    all_ds = datasets(db)
    ds = all_ds.get(cfg.dataset)
    if ds is None:
        return {"error": "Unbekannte Datenquelle."}
    rows = ds.loader(db, user)
    # Filter
    df, dt = None, None
    try:
        df = parse_date(cfg.date_from) if cfg.date_from else None
        dt = parse_date(cfg.date_to) if cfg.date_to else None
    except (ValueError, TypeError):
        return {"error": "Ungültiger Datumsbereich."}
    if ds.date_field and (df or dt):
        rows = [r for r in rows if r.get(ds.date_field) and (not df or r[ds.date_field] >= df)
                and (not dt or r[ds.date_field] <= dt)]
    if cfg.filter_field and cfg.filter_value:
        fv = cfg.filter_value.lower()
        rows = [r for r in rows if fv in _key(r.get(cfg.filter_field)).lower()
                or (isinstance(r.get(cfg.filter_field), list) and any(fv in _key(x).lower() for x in r[cfg.filter_field]))]
    metric = cfg.metric if cfg.metric in METRICS else "count"
    value_field = cfg.value_field if cfg.value_field in ds.numeric_fields else ""
    if metric != "count" and not value_field:
        return {"error": "Für diese Kennzahl bitte ein numerisches Wertfeld wählen."}
    if cfg.chart == "boxplot" and not value_field:
        return {"error": "Für einen Boxplot bitte ein numerisches Wertfeld wählen."}

    # Zeilen mit Listenfeldern (z. B. Geräte) aufteilen
    expanded = []
    for r in rows:
        g = r.get(cfg.group_by)
        if isinstance(g, list):
            for item in g:
                expanded.append({**r, cfg.group_by: item})
        else:
            expanded.append(r)
    rows = expanded

    if cfg.chart == "scatter":
        xf = cfg.x_field if cfg.x_field in ds.numeric_fields else ""
        if not xf or not value_field:
            return {"error": "Für ein Punktdiagramm bitte x-Feld und Wertfeld (numerisch) wählen."}
        series: dict[str, list] = {}
        for r in rows:
            if r.get(xf) is None or r.get(value_field) is None:
                continue
            s = _key(r.get(cfg.series_by)) if cfg.series_by else ds.fields.get(value_field, value_field)
            series.setdefault(s, []).append({"x": r[xf], "y": r[value_field]})
        table = []
        for s, pts in series.items():
            vals = [p["y"] for p in pts]
            table.append({"group": s, "series": "", "n": len(vals), **{k: _stat(vals, k) for k in
                          ("mean", "median", "min", "max", "std")}})
        return {"chart": "scatter", "series": series, "table": table, "row_count": len(rows),
                "x_label": ds.fields.get(xf, xf), "y_label": ds.fields.get(value_field, value_field)}

    groups: dict[tuple[str, str], list[float]] = {}
    counts: dict[tuple[str, str], int] = {}
    for r in rows:
        g = _key(r.get(cfg.group_by))
        s = _key(r.get(cfg.series_by)) if cfg.series_by else ""
        counts[(g, s)] = counts.get((g, s), 0) + 1
        if value_field and r.get(value_field) is not None:
            groups.setdefault((g, s), []).append(float(r[value_field]))
        else:
            groups.setdefault((g, s), [])
    labels = sorted({g for g, _ in groups}, key=_sort_key)
    series_names = sorted({s for _, s in groups}, key=_sort_key)
    table = []
    for g in labels:
        for s in series_names:
            if (g, s) not in groups:
                continue
            vals = groups[(g, s)]
            entry = {"group": g, "series": s, "n": counts[(g, s)]}
            if value_field:
                entry.update({k: _stat(vals, k) for k in ("mean", "median", "min", "max", "std")})
                entry["n"] = len(vals)
            table.append(entry)
    result = {"chart": cfg.chart, "labels": labels, "table": table, "row_count": len(rows),
              "metric_label": METRICS[metric] + (f" {ds.fields.get(value_field, '')}" if value_field else ""),
              "series_names": series_names}
    if cfg.chart == "boxplot":
        result["boxes"] = [
            {"label": g, **_quartiles(groups[(g, "")] if (g, "") in groups else
                                       [v for (gg, _), vals in groups.items() if gg == g for v in vals])}
            for g in labels if any(groups.get((g, s)) for s in series_names)
        ]
    else:
        result["datasets"] = [
            {"label": s or result["metric_label"],
             "data": [(_stat(groups[(g, s)], metric) if metric != "count" else counts.get((g, s), 0))
                      if (g, s) in groups else None for g in labels]}
            for s in series_names
        ]
    return result
