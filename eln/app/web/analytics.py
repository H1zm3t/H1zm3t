"""Allgemeine Auswertungsoberfläche."""
from __future__ import annotations

import json
from datetime import date
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response

from ..models import SavedQuery
from ..services import analytics as analytics_service
from ..services import export as export_service
from .deps import Ctx, get_ctx
from .search_views import _saved

router = APIRouter()

PRESETS = [
    ("Versuche pro Monat", {"dataset": "experiments", "group_by": "month", "chart": "line"}),
    ("Versuche nach Status", {"dataset": "experiments", "group_by": "status", "chart": "bar"}),
    ("Versuche nach Auftraggeber", {"dataset": "experiments", "group_by": "client", "chart": "bar"}),
    ("Versuche nach Mitarbeiter", {"dataset": "experiments", "group_by": "responsible", "chart": "bar"}),
    ("Versuche nach Gerät", {"dataset": "experiments", "group_by": "devices", "chart": "bar"}),
    ("Durchlaufzeit nach Fachbereich", {"dataset": "experiments", "group_by": "department", "metric": "mean",
                                        "value_field": "lead_time_days", "chart": "bar"}),
    ("Offene / überfällige Aufgaben", {"dataset": "tasks", "group_by": "assignee", "series_by": "overdue",
                                       "filter_field": "status", "filter_value": "offen", "chart": "bar"}),
    ("Materialverwendung", {"dataset": "material_usage", "group_by": "material", "chart": "bar"}),
    ("Prüfergebnisse je Probe (Boxplot)", {"dataset": "measurements", "group_by": "sample", "value_field": "value",
                                           "chart": "boxplot"}),
    ("Verlauf über Zeit/Temperatur", {"dataset": "measurements", "x_field": "x_value", "value_field": "value",
                                      "series_by": "sample", "chart": "scatter"}),
    ("Chargenvergleich (Mittelwert)", {"dataset": "measurements", "group_by": "batch", "series_by": "property",
                                       "metric": "mean", "value_field": "value", "chart": "bar"}),
    ("Rezepturvergleich Messwerte", {"dataset": "measurements", "group_by": "recipe", "series_by": "property",
                                     "metric": "mean", "value_field": "value", "chart": "bar"}),
]


@router.get("/auswertungen")
def analytics_page(request: Request, ctx: Ctx = Depends(get_ctx)):
    ctx.require("view")
    datasets = analytics_service.datasets(ctx.db)
    cfg = analytics_service.AnalysisConfig.from_mapping(request.query_params)
    if cfg.dataset not in datasets:
        cfg.dataset = "experiments"
    ds = datasets[cfg.dataset]
    if cfg.group_by not in ds.fields:
        cfg.group_by = next(iter(ds.fields))
    executed = "dataset" in request.query_params
    result = analytics_service.run(ctx.db, ctx.user, cfg) if executed else None
    meta = {k: {"label": d.label, "fields": d.fields, "numeric": d.numeric_fields} for k, d in datasets.items()}
    return ctx.render("analytics.html", cfg=cfg, ds=ds, datasets=datasets, result=result,
                      result_json=json.dumps(result or {}, ensure_ascii=False, default=str),
                      meta_json=json.dumps(meta, ensure_ascii=False), metrics=analytics_service.METRICS,
                      charts=analytics_service.CHARTS,
                      presets=[(name, urlencode(p)) for name, p in PRESETS if p["dataset"] in datasets],
                      query=urlencode(cfg.to_dict()), saved=_saved(ctx, "analysis"))


@router.post("/auswertungen/speichern")
async def save_analysis(request: Request, ctx: Ctx = Depends(get_ctx)):
    form = await request.form()
    name = (form.get("name") or "").strip()[:150]
    query = form.get("query") or ""
    if not name:
        return ctx.redirect("/auswertungen?" + query, "error", "Bitte einen Namen angeben.")
    ctx.db.add(SavedQuery(user_id=ctx.user.id, scope="analysis", name=name, query_json=json.dumps({"qs": query}),
                          is_shared=form.get("shared") == "1"))
    return ctx.redirect("/auswertungen?" + query, "success", f"Auswertung »{name}« gespeichert.")


@router.get("/auswertungen/export.{fmt}")
def export_analysis(fmt: str, request: Request, ctx: Ctx = Depends(get_ctx)):
    ctx.require("export")
    cfg = analytics_service.AnalysisConfig.from_mapping(request.query_params)
    result = analytics_service.run(ctx.db, ctx.user, cfg)
    headers = ["Gruppe", "Reihe", "Anzahl", "Mittelwert", "Median", "Minimum", "Maximum", "Standardabweichung"]
    rows = [[r.get("group"), r.get("series"), r.get("n"), r.get("mean"), r.get("median"), r.get("min"), r.get("max"),
             r.get("std")] for r in result.get("table", [])]
    name = f"auswertung_{cfg.dataset}_{date.today():%Y%m%d}"
    if fmt == "xlsx":
        return Response(export_service.to_xlsx([("Auswertung", headers, rows)]),
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f'attachment; filename="{name}.xlsx"'})
    return Response(export_service.to_csv(headers, rows), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{name}.csv"'})
