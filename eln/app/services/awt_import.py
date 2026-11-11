"""Import des Excel-Auftragsformulars »Compoundierplan« (F030).

Gelesen werden die Reiter Auftrag, Auftragdetails, Rohstoffliste, Durchführung,
Rezeptur-MB, Rezeptur-Comp, Extr.-Prot.MB, Extr.-Prot.Comp sowie die
Mischungsblätter (Pulvervormischungen). Der Reiter Gesamtstatus wird nicht
gelesen – er wird im ELN aus den Tätigkeiten berechnet.

Der Import ist wiederholbar: Wird dieselbe AWT-Nummer erneut hochgeladen,
werden Auftrag, Tätigkeiten, Rohstoffliste, Durchführung, Rezepturen und
Extrusionsprotokolle auf den Stand der Datei gebracht. Die Datei selbst wird
als Anhang (mit Versionen) am Auftrag abgelegt.

Die Zellen werden über ihre Beschriftungen gesucht, nicht über feste
Positionen – so funktionieren auch leicht abweichende Formularstände.
"""
from __future__ import annotations

import io
import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Any

from openpyxl import load_workbook
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..core import vocab
from ..models import (Attachment, Batch, Experiment, Material, Order, OrderActivity, OrderLogEntry, OrderMaterial,
                      Recipe)
from . import audit, files, planning, records
from . import recipes as recipe_service
from .audit import Actor
from .numbering import next_code
from .records import RecordError

IMPORT_REASON = "Import Compoundierplan"


@dataclass
class Plan:
    awt_number: str = ""
    client: str | None = None
    request_date: date | None = None
    contact_person: str | None = None
    cluster: str | None = None
    background: str | None = None
    task: str | None = None
    fea_remarks: str | None = None
    requested_by: str | None = None
    checked_by: str | None = None
    checked_on: date | None = None
    responsible: str | None = None
    overall_status: str | None = None
    activities: list[dict] = field(default_factory=list)
    materials: list[dict] = field(default_factory=list)
    moisture: list[dict] = field(default_factory=list)
    log: list[dict] = field(default_factory=list)
    recipes: list[dict] = field(default_factory=list)
    protocols: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    sheets_found: list[str] = field(default_factory=list)


# --- Hilfsfunktionen -----------------------------------------------------------

def _s(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v == int(v):
        v = int(v)
    return str(v).strip()


def _d(v: Any) -> date | None:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if isinstance(v, str) and v.strip():
        from ..core.formatting import parse_date

        try:
            return parse_date(v)
        except (ValueError, TypeError):
            return None
    return None


def _f(v: Any) -> float | None:
    if isinstance(v, bool) or v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    from ..core.formatting import parse_number

    try:
        return parse_number(v)
    except (ValueError, TypeError):
        return None


def _norm(name: str) -> str:
    return re.sub(r"[\s\-_.]+", "", name).casefold()


def _sheet(wb, *names: str):
    wanted = {_norm(n) for n in names}
    for ws in wb.worksheets:
        if _norm(ws.title) in wanted:
            return ws
    return None


def _find(ws, text: str, max_row: int = 120, max_col: int = 14):
    """Erste Zelle, deren Text mit ``text`` beginnt (ohne Groß-/Kleinschreibung)."""
    t = text.casefold()
    for row in ws.iter_rows(min_row=1, max_row=min(ws.max_row, max_row), max_col=max_col):
        for c in row:
            if isinstance(c.value, str) and c.value.strip().casefold().startswith(t):
                return c
    return None


def _right_of(ws, cell, max_col: int = 14):
    if cell is None:
        return None
    for col in range(cell.column + 1, max_col + 1):
        v = ws.cell(row=cell.row, column=col).value
        if v not in (None, ""):
            return v
    return None


def _below(ws, cell, max_rows: int = 3):
    if cell is None:
        return None
    for r in range(cell.row + 1, cell.row + 1 + max_rows):
        v = ws.cell(row=r, column=cell.column).value
        if v not in (None, ""):
            return v
    return None


# --- Lesen ---------------------------------------------------------------------

def parse(content: bytes) -> Plan:
    try:
        wb = load_workbook(io.BytesIO(content), data_only=True)
    except Exception as exc:  # beschädigte oder falsche Datei
        raise RecordError(f"Die Datei konnte nicht als Excel-Arbeitsmappe gelesen werden ({exc}).") from None
    plan = Plan()
    ws_order = _sheet(wb, "Auftrag")
    ws_details = _sheet(wb, "Auftragdetails", "Auftragsdetails")
    if ws_order is None and ws_details is None:
        raise RecordError("Das ist kein Compoundierplan: Die Reiter »Auftrag« und »Auftragdetails« fehlen.")
    if ws_order is not None:
        plan.sheets_found.append("Auftrag")
        _parse_order(ws_order, plan)
    if ws_details is not None:
        plan.sheets_found.append("Auftragdetails")
        _parse_details(ws_details, plan)
    if not plan.awt_number:
        raise RecordError("Die AWT-Nummer wurde nicht gefunden (Reiter »Auftrag«, Feld »AWT-NR:«).")
    ws = _sheet(wb, "Rohstoffliste")
    if ws is not None:
        plan.sheets_found.append("Rohstoffliste")
        _parse_materials(ws, plan)
    ws = _sheet(wb, "Durchführung")
    if ws is not None:
        plan.sheets_found.append("Durchführung")
        _parse_log(ws, plan)
    for names, kind in ((("Rezeptur-MB",), "Masterbatch"), (("Rezeptur-Comp",), "Compound")):
        ws = _sheet(wb, *names)
        if ws is not None:
            plan.sheets_found.append(ws.title)
            _parse_recipes(ws, kind, plan)
    for ws in wb.worksheets:
        if ws.sheet_state == "visible" and _s(ws["A1"].value).casefold() == "mischungsbezeichnung":
            _parse_mixture(ws, plan)
    for names, kind in ((("Extr.-Prot.MB",), "Masterbatch"), (("Extr.-Prot.Comp",), "Compound")):
        ws = _sheet(wb, *names)
        if ws is not None:
            plan.sheets_found.append(ws.title)
            _parse_protocol(ws, kind, plan)
    return plan


def _parse_order(ws, plan: Plan) -> None:
    plan.client = _s(_right_of(ws, _find(ws, "Kunde"))) or None
    plan.request_date = _d(_right_of(ws, _find(ws, "Anfrage am")))
    plan.contact_person = _s(_right_of(ws, _find(ws, "Ansprechperson"))) or None
    plan.cluster = _s(_right_of(ws, _find(ws, "Cluster"))) or None
    plan.background = _s(_below(ws, _find(ws, "Kurzbeschreibung"))) or None
    plan.task = _s(_below(ws, _find(ws, "Auftrag (genaue"))) or None
    awt_cell = _find(ws, "AWT-NR")
    plan.awt_number = _s(_right_of(ws, awt_cell))
    sig = _find(ws, "Datum, Anfrage von")
    if awt_cell is not None:
        end = sig.row - 1 if sig is not None else awt_cell.row + 6
        texts = [_s(ws.cell(row=r, column=awt_cell.column).value) for r in range(awt_cell.row + 1, end)]
        plan.fea_remarks = "\n".join(t for t in texts if t) or None
    if sig is not None:
        vals = [c.value for c in ws[sig.row - 1] if c.value not in (None, "")]
        dates = [_d(v) for v in vals if _d(v) and not isinstance(v, str)]
        names = [_s(v) for v in vals if isinstance(v, str)]
        if dates and not plan.request_date:
            plan.request_date = dates[0]
        plan.requested_by = names[0] if names else None
        plan.checked_by = names[1] if len(names) > 1 else None
        plan.checked_on = dates[1] if len(dates) > 1 else None


def _parse_details(ws, plan: Plan) -> None:
    if not plan.awt_number:
        plan.awt_number = _s(_right_of(ws, _find(ws, "AWT-Nummer")))
    plan.responsible = _s(_right_of(ws, _find(ws, "Verantwortlich"), max_col=3)) or None
    plan.overall_status = _s(_right_of(ws, _find(ws, "Gesamtstatus"), max_col=6)) or None
    head = _find(ws, "Kategorie", max_row=20)
    if head is None:
        plan.warnings.append("Auftragdetails: Tabellenkopf »Kategorie« nicht gefunden – keine Tätigkeiten gelesen.")
        return
    cols = {_s(c.value).casefold(): c.column for c in ws[head.row] if c.value}
    col = lambda *keys: next((cols[k] for k in keys if k in cols), None)  # noqa: E731
    mapping = {"category": col("kategorie"), "activity": col("tätigkeit"), "subject": col("probe / rezeptur", "probe/rezeptur"),
               "responsible": col("zuständig"), "planned_on": col("geplant am"), "started_on": col("begonnen am"),
               "done_on": col("erledigt am"), "documented_on": col("dokumentiert am"), "status": col("status"),
               "result": col("ergebnis / ablage", "ergebnis/ablage"), "remark": col("bemerkung")}
    for r in range(head.row + 1, ws.max_row + 1):
        get = lambda k: ws.cell(row=r, column=mapping[k]).value if mapping[k] else None  # noqa: E731
        cat, act = _s(get("category")), _s(get("activity"))
        if not cat and not act:
            continue
        status = _s(get("status")) or None
        if status and status not in vocab.ACTIVITY_STATUS:
            plan.warnings.append(f"Auftragdetails Zeile {r}: unbekannter Status »{status}« übernommen als Bemerkung.")
        plan.activities.append({
            "category": cat or "Sonstiges", "activity": act or "(ohne Bezeichnung)", "subject": _s(get("subject")) or None,
            "responsible": _s(get("responsible")) or None, "planned_on": _d(get("planned_on")),
            "started_on": _d(get("started_on")), "done_on": _d(get("done_on")),
            "documented_on": _d(get("documented_on")),
            "status": status if status in vocab.ACTIVITY_STATUS else None,
            "result": _s(get("result")) or None,
            "remark": (_s(get("remark")) + (f" [Status laut Excel: {status}]" if status and status not in vocab.ACTIVITY_STATUS else "")).strip() or None,
        })


def _parse_materials(ws, plan: Plan) -> None:
    section = vocab.MATERIAL_SECTIONS[0]
    moisture_row = None
    for r in range(2, ws.max_row + 1):
        a, b, c = (_s(ws.cell(row=r, column=i).value) for i in (1, 2, 3))
        if a.casefold() == "datum" and b.casefold() == "bezeichnung":
            moisture_row = r
            break
        if a:
            section = a
        if not c:
            continue
        plan.materials.append({"section": section, "number": b or None, "name": c,
                               "lot": _s(ws.cell(row=r, column=4).value) or None,
                               "date": _d(ws.cell(row=r, column=5).value),
                               "remark": _s(ws.cell(row=r, column=6).value) or None})
    if moisture_row:
        for r in range(moisture_row + 1, ws.max_row + 1):
            name = _s(ws.cell(row=r, column=2).value)
            value = ws.cell(row=r, column=4).value
            if not name and value in (None, ""):
                continue
            plan.moisture.append({"date": _d(ws.cell(row=r, column=1).value), "name": name,
                                  "number": _s(ws.cell(row=r, column=3).value) or None, "value": _s(value),
                                  "program": _s(ws.cell(row=r, column=6).value) or None,
                                  "remark": _s(ws.cell(row=r, column=9).value) or None})


def _parse_log(ws, plan: Plan) -> None:
    for r in range(2, ws.max_row + 1):
        step = _s(ws.cell(row=r, column=1).value)
        if not step:
            continue
        plan.log.append({"step": step, "by": _s(ws.cell(row=r, column=2).value) or None,
                         "date": _d(ws.cell(row=r, column=3).value), "remark": _s(ws.cell(row=r, column=4).value) or None})


def _parse_recipes(ws, kind: str, plan: Plan) -> None:
    heads = [c for c in ws["B"] if _s(c.value).casefold() == "rezeptur"]
    if not heads:
        plan.warnings.append(f"{ws.title}: Kopfzeile »Rezeptur« nicht gefunden.")
        return
    head = heads[0].row
    names = {c.column: _s(c.value) for c in ws[head] if c.column >= 4 and _s(c.value)}

    def block(start: int) -> dict[str, int]:
        rows = {}
        for r in range(start + 1, min(ws.max_row, start + 40) + 1):
            label = _s(ws.cell(row=r, column=3).value)
            if label.casefold() == "kontrolle":
                break
            if label:
                rows[label] = r
        return rows

    pct_rows = block(head)
    gram_rows = block(heads[1].row) if len(heads) > 1 else {}

    def label_row(text: str) -> int | None:
        for c in ws["B"]:
            if _s(c.value).casefold().startswith(text.casefold()):
                return c.row
        return None

    r_need, r_rem, r_gen, r_seq = (label_row(t) for t in ("benötigte Menge", "Bemerkungen zur Rezeptur",
                                                           "Bemerkungen (allgemein)", "Reihenfolge Extrusion"))
    total_cell = _find(ws, "Summe pro", max_row=80, max_col=3)
    columns = []
    for col, name in names.items():
        comps = [(label, _f(ws.cell(row=r, column=col).value)) for label, r in pct_rows.items()]
        comps = [(lb, v) for lb, v in comps if v]
        noted = any(_s(ws.cell(row=r, column=col).value) for r in (r_rem, r_gen, r_seq) if r)
        columns.append((col, name, comps, noted))
    # Vorlagenspalten am Ende (nur Trägermaterial = 100 %, ohne Bemerkung/Reihenfolge) gehören nicht zum Auftrag
    last_real = max((i for i, (_, _, comps, noted) in enumerate(columns) if len(comps) >= 2 or noted), default=-1)
    columns = [(c, n, comps) for c, n, comps, _ in columns]
    for col, name, comps in columns[: last_real + 1]:
        if not comps:
            continue
        total = sum(v for _, v in comps)
        factor = 100.0 if total <= 1.5 else 1.0
        items = []
        for label, v in comps:
            grams = _f(ws.cell(row=gram_rows[label], column=col).value) if label in gram_rows else None
            items.append({"name": label, "percent": round(v * factor, 6),
                          "grams": round(grams, 4) if grams is not None else None, "actual": None, "remark": None})
        get = lambda r: ws.cell(row=r, column=col).value if r else None  # noqa: E731
        remark = "\n".join(t for t in (_s(get(r_rem)), _s(get(r_gen))) if t) or None
        plan.recipes.append({
            "type": kind, "name": name, "items": items, "remark": remark, "required_kg": _f(get(r_need)),
            "total_g": _f(ws.cell(row=total_cell.row, column=col).value) if total_cell is not None else None,
            "sequence": _s(get(r_seq)) or None, "date": None, "by": None,
        })


def _parse_mixture(ws, plan: Plan) -> None:
    name = _s(ws["B1"].value)
    if not name:
        return
    head = _find(ws, "Rohstoff", max_row=15, max_col=1)
    items = []
    if head is not None:
        for r in range(head.row + 1, ws.max_row + 1):
            label = _s(ws.cell(row=r, column=1).value)
            if label.casefold() == "gesamt":
                break
            pct = _f(ws.cell(row=r, column=2).value)
            if label and pct:
                grams = _f(ws.cell(row=r, column=4).value)
                items.append({"name": label, "percent": round(pct, 6), "grams": round(grams, 4) if grams is not None else None,
                              "actual": _f(ws.cell(row=r, column=5).value), "remark": None})
    flow = _find(ws, "Fließhilfsmittel", max_row=30, max_col=1)
    if flow is not None:
        for r in range(flow.row + 1, flow.row + 4):
            label = _s(ws.cell(row=r, column=1).value)
            if label and not label.casefold().startswith("zusammensetzung"):
                items.append({"name": label, "percent": _f(ws.cell(row=r, column=2).value),
                              "grams": _f(ws.cell(row=r, column=3).value), "actual": _f(ws.cell(row=r, column=4).value),
                              "remark": "Fließhilfsmittel"})
    if not items:
        return
    plan.sheets_found.append(ws.title)
    scale = _s(ws["B4"].value)
    plan.recipes.append({"type": "Pulvermischung", "name": name, "items": items,
                         "remark": f"Waage (PMFEA): {scale}" if scale else None, "required_kg": None,
                         "total_g": _f(ws["B2"].value), "sequence": None, "date": _d(ws["B3"].value),
                         "by": _s(ws["B5"].value) or None})


def _parse_protocol(ws, kind: str, plan: Plan) -> None:
    real = {r["name"] for r in plan.recipes if r["type"] == kind}
    names = {c.column: _s(c.value) for c in ws[1] if c.column >= 3 and _s(c.value) in real}
    labels: list[tuple[int, str, str]] = []
    group = ""
    for r in range(2, ws.max_row + 1):
        a, b = _s(ws.cell(row=r, column=1).value), _s(ws.cell(row=r, column=2).value)
        if a and r > 2:
            group = a.replace("\n", " ")
        elif r == 2:
            group = ""
        if r == 2:
            b = b or "Datum"
        if a.casefold().startswith("bemerkungen"):
            labels.append((r, "Bemerkungen", ""))
            break
        if a or b:
            labels.append((r, group, b.replace("\n", " ")))
    for col, name in names.items():
        rows, has_data = [], False
        for r, grp, sub in labels:
            v = ws.cell(row=r, column=col).value
            if v in (None, "") or (isinstance(v, (int, float)) and not isinstance(v, bool) and v == 0):
                continue
            has_data = True
            rows.append((grp, sub, v))
        if has_data:
            plan.protocols.append({"type": kind, "recipe": name, "rows": rows})


# --- Vorschau ------------------------------------------------------------------

def find_order(db: Session, awt_number: str) -> Order | None:
    return db.query(Order).filter(Order.external_number == awt_number).order_by(Order.id).first()


def _find_material(db: Session, name: str, number: str | None = None) -> Material | None:
    if number:
        m = db.query(Material).filter(Material.material_number == number).first()
        if m is not None:
            return m
    key = name.strip().casefold()
    return (db.query(Material).filter(func.lower(Material.name) == key).first()
            or next((m for m in db.query(Material).all()
                     if (m.name or "").casefold() == key or (m.trade_name or "").casefold() == key), None))


def preview(db: Session, plan: Plan) -> dict:
    order = find_order(db, plan.awt_number)
    names: dict[str, str | None] = {}
    for m in plan.materials:
        names.setdefault(m["name"], m["number"])
    for r in plan.recipes:
        for i in r["items"]:
            names.setdefault(i["name"], None)
    new_materials = [n for n, num in names.items() if _find_material(db, n, num) is None]
    acts = [OrderActivity(category=a["category"], activity=a["activity"], status=a["status"],
                          started_on=a["started_on"], done_on=a["done_on"]) for a in plan.activities]
    by_type: dict[str, list[dict]] = {}
    for r in plan.recipes:
        by_type.setdefault(r["type"], []).append(r)
    return {"order": order, "new_materials": new_materials, "summary": planning.summary(acts),
            "recipes_by_type": by_type,
            "existing_activities": db.query(OrderActivity).filter_by(order_id=order.id).count() if order else 0}


# --- Übernehmen ----------------------------------------------------------------

def _guess_type(name: str) -> str:
    n = name.casefold()
    if "(mb)" in n or re.match(r"^mb\d", n):
        return "Masterbatch"
    if "glasfaser" in n or n.startswith("gf "):
        return "Verstärkungsstoff"
    if any(k in n for k in ("ultramid", "pa6", "pa 6", "polyamid", "lucofin", "elvaloy", "polyprop", "polyethylen")):
        return "Polymer"
    return "Additiv"


def _get_material(db: Session, actor: Actor, name: str, number: str | None, created: list[str],
                  mtype: str | None = None) -> Material:
    mat = _find_material(db, name, number)
    if mat is None:
        mat = records.create_record(db, actor, "material", {
            "name": name[:200], "material_number": number, "material_type": mtype or _guess_type(name),
            "status": "aktiv", "remarks": "Automatisch angelegt beim Import eines Compoundierplans."})
        created.append(mat.label)
    elif number and not mat.material_number:
        mat.material_number = number
        audit.log(db, actor, "update", entity_type="material", entity=mat, field="Materialnummer", new=number,
                  reason=IMPORT_REASON)
    return mat


def apply(db: Session, actor: Actor, plan: Plan, filename: str, content: bytes) -> dict:
    """Übernimmt den Plan in die Datenbank (eine Transaktion)."""
    reason = f"{IMPORT_REASON} {filename}"
    report: dict[str, Any] = {"created_materials": [], "recipes_new": 0, "recipes_updated": 0, "runs": 0,
                              "messages": list(plan.warnings)}
    order = find_order(db, plan.awt_number)
    responsible = planning.find_user(db, plan.responsible) or actor.user
    values = {
        "client": plan.client or "(nicht angegeben)", "request_date": plan.request_date,
        "contact_person": plan.contact_person, "cluster": plan.cluster, "objective": plan.background,
        "task_description": plan.task or plan.background or "(siehe Compoundierplan)",
        "internal_remarks": plan.fea_remarks, "requested_by": plan.requested_by, "checked_by": plan.checked_by,
        "checked_on": plan.checked_on,
    }
    if order is None:
        headline = (plan.background or plan.task or "").split("\n")[0].strip()
        if len(headline) > 90:
            headline = headline[:88].rsplit(" ", 1)[0] + " …"
        title = f"AWT {plan.awt_number}" + (f" – {headline}" if headline else "")
        order = records.create_record(db, actor, "order", {
            **values, "title": title[:240], "external_number": plan.awt_number, "priority": "normal",
            "responsible_id": responsible.id, "status": "offen", "confidentiality": "intern"})
        report["order_created"] = True
    else:
        records.update_record(db, actor, "order", order, values, reason)
        report["order_created"] = False

    # Rohstoffliste (Stammdaten anlegen/ergänzen, Zeilen ersetzen)
    material_by_name: dict[str, Material] = {}
    db.query(OrderMaterial).filter_by(order_id=order.id).delete()
    for pos, m in enumerate(plan.materials, start=1):
        mat = _get_material(db, actor, m["name"], m["number"], report["created_materials"])
        material_by_name[m["name"].casefold()] = mat
        batch = None
        if m["lot"]:
            batch = db.query(Batch).filter_by(material_id=mat.id, batch_number=m["lot"]).first()
            if batch is None:
                batch = records.create_record(db, actor, "batch", {"material_id": mat.id, "batch_number": m["lot"],
                                                                   "received_date": m["date"], "status": "freigegeben"})
        db.add(OrderMaterial(order_id=order.id, position=pos, section=m["section"], material_id=mat.id,
                             batch_id=batch.id if batch else None, entry_date=m["date"], remark=m["remark"]))

    # Tätigkeiten (Stand der Datei ersetzt den bisherigen Stand)
    old_summary = planning.summary(planning.activities(db, order.id))
    db.query(OrderActivity).filter_by(order_id=order.id).delete()
    for pos, a in enumerate(plan.activities, start=1):
        user = planning.find_user(db, a["responsible"])
        db.add(OrderActivity(order_id=order.id, position=pos, category=a["category"][:80], activity=a["activity"][:200],
                             subject=a["subject"], responsible_id=user.id if user else None,
                             responsible_text=None if user else a["responsible"], planned_on=a["planned_on"],
                             started_on=a["started_on"], done_on=a["done_on"], documented_on=a["documented_on"],
                             status=a["status"], result=a["result"], remark=a["remark"]))
    db.flush()
    new_summary = planning.summary(planning.activities(db, order.id))
    audit.log(db, actor, "import", entity_type="order", entity=order, field="Tätigkeiten",
              old=f"{old_summary['done']}/{old_summary['total']} erledigt",
              new=f"{new_summary['done']}/{new_summary['total']} erledigt", reason=reason)
    if order.status == "offen" and new_summary["status"] == "in Bearbeitung":
        records.set_status(db, actor, "order", order, "in Bearbeitung", reason)

    # Durchführung (importierte Einträge ersetzen, manuelle bleiben)
    db.query(OrderLogEntry).filter_by(order_id=order.id, source="Import").delete()
    pos = db.query(OrderLogEntry).filter_by(order_id=order.id).count()
    for e in plan.log:
        pos += 1
        user = planning.find_user(db, e["by"])
        db.add(OrderLogEntry(order_id=order.id, position=pos, step=e["step"], done_by_id=user.id if user else None,
                             done_by_text=None if user else e["by"], entry_date=e["date"], remark=e["remark"],
                             source="Import"))
    for m in plan.moisture:
        pos += 1
        db.add(OrderLogEntry(order_id=order.id, position=pos, entry_date=m["date"], source="Import",
                             step=f"Feuchtigkeitsbestimmung {m['name']}: {m['value']}"
                                  + (f" (Messprogramm {m['program']})" if m["program"] else ""),
                             remark=m["remark"]))

    # Rezepturen: zuerst Masterbatche/Mischungen, dann Compounds (die darauf verweisen)
    recipe_by_name: dict[str, Recipe] = {}
    for r in sorted(plan.recipes, key=lambda x: x["type"] == "Compound"):
        recipe = (db.query(Recipe).filter(Recipe.order_id == order.id, Recipe.name == r["name"],
                                          Recipe.recipe_type == r["type"]).order_by(Recipe.revision.desc()).first())
        desc_parts = [r["remark"], f"Benötigte Menge: {r['required_kg']:g} kg" if r["required_kg"] else None,
                      f"Reihenfolge Extrusion: {r['sequence']}" if r["sequence"] else None,
                      f"Hergestellt am {r['date']:%d.%m.%Y}" + (f" von {r['by']}" if r["by"] else "") if r["date"] else None]
        description = "\n".join(p for p in desc_parts if p) or None
        if recipe is None:
            recipe = Recipe(code=next_code(db, "recipe"), revision=1, name=r["name"], order_id=order.id,
                            recipe_type=r["type"], status="Entwurf", description=description,
                            target_total=r["total_g"], total_unit="g", created_by_id=actor.user_id,
                            updated_by_id=actor.user_id)
            db.add(recipe)
            db.flush()
            audit.log(db, actor, "create", entity_type="recipe", entity=recipe, new=recipe.label, reason=reason)
            report["recipes_new"] += 1
            is_new = True
        else:
            is_new = False
            if recipe.status in ("ersetzt", "archiviert"):
                report["messages"].append(f"Rezeptur {recipe.label} ist {recipe.status} und wurde nicht geändert.")
                recipe_by_name[r["name"].casefold()] = recipe
                continue
            for attr, val in (("description", description), ("target_total", r["total_g"])):
                if getattr(recipe, attr) != val:
                    audit.log(db, actor, "update", entity_type="recipe", entity=recipe, field=attr,
                              old=getattr(recipe, attr), new=val, reason=reason)
                    setattr(recipe, attr, val)
        rows = []
        for n, it in enumerate(r["items"], start=1):
            source = recipe_by_name.get(it["name"].casefold())
            mat = material_by_name.get(it["name"].casefold()) or _get_material(
                db, actor, it["name"], None, report["created_materials"],
                mtype=(source.recipe_type if source is not None and source.recipe_type in vocab.MATERIAL_TYPES else None))
            material_by_name[it["name"].casefold()] = mat
            rows.append({"position": n, "material_id": mat.id, "batch_id": None, "function": None,
                         "target_amount": it["grams"], "unit": "g" if it["grams"] is not None else None,
                         "actual_amount": it["actual"], "weight_percent": it["percent"], "tolerance": None,
                         "remark": it["remark"], "source_recipe_id": source.id if source is not None else None})
        changed = recipe_service.replace_items(db, actor, recipe, rows, reason)
        if changed and not is_new:
            report["recipes_updated"] += 1
        recipe_by_name[r["name"].casefold()] = recipe

    # Extrusionsprotokolle -> Compoundierläufe
    if plan.recipes:
        _apply_protocols(db, actor, plan, order, recipe_by_name, responsible, reason, report)

    # Originaldatei als Anhang (neue Version, falls sich der Inhalt geändert hat)
    import hashlib

    sha = hashlib.sha256(content).hexdigest()
    previous = (db.query(Attachment).filter_by(entity_type="order", entity_id=order.id, category="Compoundierplan",
                                               status="aktiv").order_by(Attachment.id.desc()).first())
    if previous is None or previous.sha256 != sha:
        files.save_upload(db, actor, stream=io.BytesIO(content), filename=filename, entity_type="order",
                          entity_id=order.id, description="Excel-Auftragsformular (Compoundierplan), importiert",
                          category="Compoundierplan", previous=previous, reason=reason)
        report["file_saved"] = True
    else:
        report["file_saved"] = False
    db.flush()
    report.update({"order": order, "activities": len(plan.activities), "materials": len(plan.materials),
                   "log": len(plan.log) + len(plan.moisture), "summary": new_summary})
    return report


def _apply_protocols(db: Session, actor: Actor, plan: Plan, order: Order, recipe_by_name: dict, responsible,
                     reason: str, report: dict) -> None:
    from ..modules.compounding.models import CompoundingRun
    from ..modules.compounding.service import save_run

    titles = {"Masterbatch": "Masterbatchherstellung", "Compound": "Compoundherstellung"}
    experiments: dict[str, Experiment] = {}
    for kind, label in titles.items():
        if not any(r["type"] == kind for r in plan.recipes):
            continue
        title = f"{label} AWT {plan.awt_number}"
        exp = db.query(Experiment).filter(Experiment.order_id == order.id, Experiment.title == title).first()
        if exp is None:
            exp = records.create_record(db, actor, "experiment", {
                "title": title, "order_id": order.id, "experiment_type": "Mustermengenherstellung",
                "department": "Compoundierung", "responsible_id": responsible.id,
                "objective": f"{label} gemäß Compoundierplan AWT {plan.awt_number}.",
                "tags": f"AWT {plan.awt_number}"})
        experiments[kind] = exp

    for proto in plan.protocols:
        exp = experiments.get(proto["type"])
        recipe = recipe_by_name.get(proto["recipe"].casefold())
        if exp is None:
            continue
        if exp.locked:
            report["messages"].append(f"Extrusionsprotokoll {proto['recipe']}: Versuch {exp.code} ist gesperrt – übersprungen.")
            continue
        values, tables = _run_from_protocol(proto, exp, recipe, actor)
        run = db.query(CompoundingRun).filter_by(experiment_id=exp.id, title=proto["recipe"]).first()
        saved, _ = save_run(db, actor, run, values, tables, reason)
        protocol = json.dumps([[f"{g} {s}".strip(), _s(v) if not isinstance(v, (datetime, date, time)) else str(v)]
                               for g, s, v in proto["rows"]], ensure_ascii=False)
        if saved.protocol_json != protocol:
            saved.protocol_json = protocol
        report["runs"] += 1


def _run_from_protocol(proto: dict, exp: Experiment, recipe: Recipe | None, actor: Actor) -> tuple[dict, dict]:
    def get(group: str, sub: str = ""):
        for g, s, v in proto["rows"]:
            if g.casefold().startswith(group.casefold()) and s.casefold().startswith(sub.casefold()):
                return v
        return None

    day = _d(get("", "Datum"))

    def at(v) -> datetime | None:
        if day is None:
            return None
        if isinstance(v, datetime):
            v = v.time()
        if isinstance(v, time):
            return datetime.combine(day, v)
        m = re.match(r"^(\d{1,2})[:.](\d{2})", _s(v))
        return datetime.combine(day, time(int(m.group(1)), int(m.group(2)))) if m else datetime.combine(day, time(0, 0))

    feeders = []
    for n, grp in enumerate(("Granulatdosierer", "MiniTwin", "Dosierer 3", "Dosierer 4", "Dosierer 5"), start=1):
        rate, additive = _f(get(grp, "[kg/h]")), _s(get(grp, "Additiv"))
        if rate is None and not additive:
            continue
        extras = [f"{lab} {_s(get(grp, key))}" for key, lab in (("Anteil", "Anteil %"), ("Torque", "Torque %"),
                                                                 ("Schnecke", "Schnecke"), ("Zone", "Zone"),
                                                                 ("Dosierrohr", "Dosierrohr")) if _s(get(grp, key))]
        feeders.append({"position": n, "feed_point": grp, "feeder": ", ".join(extras)[:120] or None, "material_id": None,
                        "component": additive or None, "set_rate": None, "actual_rate": rate})
    zones = []
    for g, s, v in proto["rows"]:
        if g.casefold().startswith("temperaturprofil") and _f(v) is not None:
            zones.append({"position": len(zones) + 1, "name": s.replace("[°C]", "").strip() or f"Zone {len(zones) + 1}",
                          "set_temp": _f(v), "actual_temp": None})
    bath = [_s(get("Wasserbad")), f"{_s(get('Wasserbad-Temperatur'))} °C" if _s(get("Wasserbad-Temperatur")) else ""]
    pellet = [f"{g} {s}: {_s(v)}" for g, s, v in proto["rows"] if g.casefold().startswith("granulierer")]
    measured = _f(get("Massetemperatur (gemessen)"))
    values = {
        "title": proto["recipe"], "experiment_id": exp.id, "recipe_id": recipe.id if recipe else None,
        "device_id": next((d.id for d in exp.devices if d.device_type == "Extruder"), None),
        "operator_id": actor.user_id, "status": "durchgeführt" if day else "geplant",
        "start_time": at(get("Uhrzeit", "von")) if day else None, "end_time": at(get("", "bis")) if day else None,
        "screw_config": None, "throughput_set": None, "throughput_actual": _f(get("Gesamtdurchsatz")),
        "screw_speed": _f(get("Schneckendrehzahl")), "torque": _f(get("M Extruder")),
        "melt_pressure": _f(get("Massedruck")),
        "melt_temperature": _f(get("Massetemperatur (Anzeige)")) or measured, "vacuum": _f(get("Vakuum")),
        "cooling": ", ".join(b for b in bath if b) or None, "pelletizing": "; ".join(pellet) or None,
        "observations": _s(get("Bemerkungen")) or None, "disturbances": None, "deviations": None, "sampling": None,
        "evaluation": None,
    }
    if values["start_time"] and values["end_time"] and values["end_time"] < values["start_time"]:
        values["end_time"] = None
    return values, {"zones": zones, "feeders": feeders, "readings": []}
