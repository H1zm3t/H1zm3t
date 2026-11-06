"""Export: CSV, JSON, Excel sowie Versuchs- und Auftragsdossiers."""
from __future__ import annotations

import csv
import io
import json
import zipfile
from datetime import date, datetime
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from sqlalchemy.orm import Session

from ..config import APP_NAME, APP_VERSION
from ..core.formatting import de_date, de_datetime, de_number
from ..core.modules import get_registry
from ..models import ApprovalRecord, Attachment, AuditLog, Experiment, Measurement, ModuleRecord, Order, Sample, User
from .entities import ENTITY_DEFS, apply_visibility, resolve_path
from .files import absolute_path, can_view_attachment
from .recipes import check_sum


def _plain(v: Any) -> Any:
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, (list, tuple, set)):
        return [_plain(x) for x in v]
    if hasattr(v, "code"):
        return v.code
    if hasattr(v, "username"):
        return v.username
    return v


def entity_export_rows(db: Session, user: User, key: str) -> tuple[list[str], list[str], list[list[Any]]]:
    """Alle Felder eines Datensatztyps: (feldnamen, bezeichnungen, zeilen mit Rohwerten)."""
    d = ENTITY_DEFS[key]
    names = ["id", "code"] + [f.name for f in d.fields] + ["created_at", "updated_at", "version"]
    labels = ["DB-ID", "Kennung"] + [f.label for f in d.fields] + ["Angelegt", "Geändert", "Version"]
    if key == "recipe":
        names.insert(2, "revision")
        labels.insert(2, "Revision")
    if key == "experiment":
        names += ["status", "revision"]
        labels += ["Status", "Revision"]
    q = apply_visibility(db, user, key, db.query(d.model)).order_by(d.model.id)
    rows = []
    for obj in q.all():
        row = []
        for n in names:
            v = getattr(obj, n, None)
            spec = next((f for f in d.fields if f.name == n), None)
            if spec is not None and spec.kind == "ref" and v:
                target = resolve_path(obj, n[:-3]) if n.endswith("_id") else None
                v = getattr(target, "code", None) or getattr(target, "username", None) or v
            row.append(_plain(v))
        rows.append(row)
    return names, labels, rows


def to_csv(headers: list[str], rows: list[list[Any]], german: bool = True) -> bytes:
    """CSV mit Semikolon und Dezimalkomma (öffnet direkt in deutschem Excel)."""
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";" if german else ",", quoting=csv.QUOTE_MINIMAL)
    w.writerow(headers)
    for r in rows:
        out = []
        for v in r:
            if isinstance(v, list):
                v = ", ".join(str(x) for x in v)
            if isinstance(v, float) and german:
                v = repr(v).replace(".", ",")
            out.append("" if v is None else v)
        w.writerow(out)
    return ("﻿" + buf.getvalue()).encode("utf-8")


def to_xlsx(sheets: list[tuple[str, list[str], list[list[Any]]]]) -> bytes:
    wb = Workbook()
    wb.remove(wb.active)
    head_fill = PatternFill("solid", fgColor="1F4E79")
    for title, headers, rows in sheets:
        ws = wb.create_sheet(title=title[:31] or "Daten")
        ws.append(headers)
        for c in ws[1]:
            c.font = Font(bold=True, color="FFFFFF")
            c.fill = head_fill
            c.alignment = Alignment(vertical="center", wrap_text=True)
        for r in rows:
            out = []
            for v in r:
                if isinstance(v, list):
                    v = ", ".join(str(x) for x in v)
                if isinstance(v, str) and len(v) > 32000:
                    v = v[:32000]
                out.append(v)
            ws.append(out)
        for i, h in enumerate(headers, start=1):
            width = max([len(str(h))] + [len(str(r[i - 1])) for r in rows[:200] if i - 1 < len(r) and r[i - 1] is not None])
            ws.column_dimensions[get_column_letter(i)].width = min(60, max(10, width + 2))
            for cell in ws.iter_cols(min_col=i, max_col=i, min_row=2):
                for c in cell:
                    if isinstance(c.value, datetime):
                        c.number_format = "DD.MM.YYYY HH:MM"
                    elif isinstance(c.value, date):
                        c.number_format = "DD.MM.YYYY"
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def to_json(data: Any) -> bytes:
    return json.dumps(data, ensure_ascii=False, indent=2, default=str).encode("utf-8")


# --- Dossiers ----------------------------------------------------------------

def _audit_excerpt(db: Session, entity_type: str, entity_id: int, limit: int = 200) -> list[dict]:
    rows = (db.query(AuditLog).filter(AuditLog.entity_type == entity_type, AuditLog.entity_id == entity_id)
            .order_by(AuditLog.id.desc()).limit(limit).all())
    return [{"Zeitpunkt": de_datetime(a.timestamp), "Benutzer": a.username, "Aktion": a.action, "Feld": a.field,
             "Alt": a.old_value, "Neu": a.new_value, "Grund": a.reason, "Version": a.record_version}
            for a in reversed(rows)]


def _attachments(db: Session, user: User, entity_type: str, entity_id: int) -> list[Attachment]:
    return [a for a in db.query(Attachment).filter(Attachment.entity_type == entity_type,
                                                    Attachment.entity_id == entity_id).order_by(Attachment.id)
            if can_view_attachment(user, a)]


def experiment_dossier(db: Session, user: User, exp: Experiment) -> dict:
    samples = db.query(Sample).filter(Sample.experiment_id == exp.id).order_by(Sample.code).all()
    measurements = db.query(Measurement).filter(Measurement.experiment_id == exp.id).order_by(Measurement.code).all()
    approvals = (db.query(ApprovalRecord).filter(ApprovalRecord.entity_type == "experiment",
                                                 ApprovalRecord.entity_id == exp.id).order_by(ApprovalRecord.id).all())
    module_records = db.query(ModuleRecord).filter(ModuleRecord.experiment_id == exp.id).all()
    sections = []
    for module in get_registry().enabled(db):
        for s in module.dossier_sections(db, exp):
            sections.append({"module": module.name, "title": s.title, "headers": s.headers,
                             "rows": [[_plain(c) for c in r] for r in s.rows], "note": s.note})
    for rec in module_records:
        module = get_registry().get(rec.module_key)
        sections.append({"module": module.name if module else rec.module_key, "title": f"{rec.code} – {rec.title}",
                         "headers": ["Parameter", "Wert"],
                         "rows": [[k, v] for k, v in rec.data.items()], "note": None})
    recipe = None
    if exp.recipe:
        sc = check_sum(db, exp.recipe)
        recipe = {
            "Kennung": f"{exp.recipe.code} Rev. {exp.recipe.revision}", "Name": exp.recipe.name,
            "Summe": sc.total, "Summenprüfung": sc.message,
            "Positionen": [{"Pos.": i.position, "Material-ID": i.material.code,
                            "Materialnummer": i.material.material_number, "Material": i.material.name,
                            "Handelsname": i.material.trade_name, "Lieferant": i.material.supplier,
                            "Charge": i.batch.batch_number if i.batch else None, "Funktion": i.function,
                            "Soll": i.target_amount, "Ist": i.actual_amount, "Einheit": i.unit,
                            "Gew.-%": i.weight_percent, "Toleranz": i.tolerance, "Bemerkung": i.remark}
                           for i in exp.recipe.items],
        }
    return {
        "_meta": {"Anwendung": f"{APP_NAME} {APP_VERSION}", "Erstellt": de_datetime(datetime.now()),
                  "Erstellt von": user.full_name, "Typ": "Versuchsdossier"},
        "Kennung": exp.code, "Revision": exp.revision, "Version": exp.version, "Status": exp.status,
        "Gesperrt": exp.locked,
        "Stammdaten": {
            "Bezeichnung": exp.title, "Auftrag": exp.order.label if exp.order else None,
            "Auftraggeber": exp.order.client if exp.order else None,
            "Versuchsreihe": exp.series.label if exp.series else None, "Versuchsart": exp.experiment_type,
            "Fachbereich": exp.department, "Verantwortlich": exp.responsible.full_name if exp.responsible else None,
            "Beteiligte": ", ".join(u.full_name for u in exp.participants),
            "Geplantes Datum": de_date(exp.planned_date), "Tatsächliches Datum": de_date(exp.actual_date),
            "Methode": exp.method.label if exp.method else None, "Schlagwörter": exp.tags,
            "Angelegt": de_datetime(exp.created_at),
        },
        "Zielsetzung": {"Ziel": exp.objective, "Hypothese": exp.hypothesis},
        "Geräte": [{"ID": d.code, "Gerät": d.name, "Status": d.status,
                    "Nächste Kalibrierung": de_date(d.next_calibration)} for d in exp.devices],
        "Materialien": [{"ID": m.code, "Materialnummer": m.material_number, "Name": m.name,
                         "Lieferant": m.supplier} for m in exp.materials],
        "Chargen": [{"ID": b.code, "Charge": b.batch_number, "Material": b.material.name} for b in exp.batches],
        "Rezeptur": recipe,
        "Prozessschritte": exp.process_steps,
        "Prozessparameter": exp.process_parameters,
        "Durchführung": {"Beobachtungen": exp.observations, "Abweichungen": exp.deviations,
                         "Rohdaten": exp.raw_data},
        "Proben": [{"ID": s.code, "Bezeichnung": s.name, "Art": s.sample_type,
                    "Übergeordnet": s.parent.code if s.parent else None, "Menge": s.quantity, "Einheit": s.unit,
                    "Lagerort": s.storage_location, "Status": s.status} for s in samples],
        "Prüfungen": [{"ID": m.code, "Bezeichnung": m.name, "Messgröße": m.property_name, "Einheit": m.unit,
                       "Probe": m.sample.code if m.sample else None, "n": m.stats["n"], "Mittelwert": m.stats["mean"],
                       "Std.-Abw.": m.stats["std"], "Min": m.stats["min"], "Max": m.stats["max"],
                       "Werte": [[v.x_value, v.value] for v in m.values]} for m in measurements],
        "Modulabschnitte": sections,
        "Ergebnis": {"Ergebnisse": exp.results, "Bewertung": exp.evaluation, "Schlussfolgerung": exp.conclusion,
                     "Folgeaktivitäten": exp.follow_up},
        "Anhänge": [{"Datei": a.original_filename, "Version": a.version, "Kategorie": a.category,
                     "Größe (Bytes)": a.size_bytes, "SHA-256": a.sha256, "Status": a.status,
                     "Hochgeladen": de_datetime(a.created_at),
                     "von": a.created_by.full_name if a.created_by else None, "_path": a.storage_path,
                     "_uid": a.file_uid, "_ext": a.extension}
                    for a in _attachments(db, user, "experiment", exp.id)],
        "Freigaben": [{"Schritt": r.step, "Entscheidung": r.decision, "Person": r.user.full_name,
                       "Zeitpunkt": de_datetime(r.timestamp), "Revision": r.revision, "Kommentar": r.comment,
                       "Snapshot SHA-256": r.snapshot.sha256 if r.snapshot else None} for r in approvals],
        "Audit-Trail-Auszug": _audit_excerpt(db, "experiment", exp.id),
    }


def order_dossier(db: Session, user: User, order: Order) -> dict:
    experiments = [experiment_dossier(db, user, e) for e in order.experiments]
    samples = db.query(Sample).filter(Sample.order_id == order.id).order_by(Sample.code).all()
    return {
        "_meta": {"Anwendung": f"{APP_NAME} {APP_VERSION}", "Erstellt": de_datetime(datetime.now()),
                  "Erstellt von": user.full_name, "Typ": "Auftragsdossier"},
        "Kennung": order.code, "Version": order.version, "Status": order.status,
        "Stammdaten": {
            "Titel": order.title, "Externe Nummer": order.external_number,
            "Projekt": order.project.label if order.project else None, "Auftraggeber": order.client,
            "Kundenbezug": order.customer, "Priorität": order.priority,
            "Verantwortlich": order.responsible.full_name if order.responsible else None,
            "Beteiligte": ", ".join(u.full_name for u in order.participants),
            "Erstellt": de_datetime(order.created_at), "Termin": de_date(order.due_date),
            "Vertraulichkeit": order.confidentiality, "Schlagwörter": order.tags,
        },
        "Aufgabenstellung": order.task_description, "Zielsetzung": order.objective,
        "Versuche": experiments,
        "Proben": [{"ID": s.code, "Bezeichnung": s.name, "Art": s.sample_type, "Status": s.status} for s in samples],
        "Anhänge": [{"Datei": a.original_filename, "Version": a.version, "SHA-256": a.sha256, "Status": a.status,
                     "_path": a.storage_path, "_uid": a.file_uid, "_ext": a.extension}
                    for a in _attachments(db, user, "order", order.id)],
        "Audit-Trail-Auszug": _audit_excerpt(db, "order", order.id),
    }


def strip_private(data: Any) -> Any:
    if isinstance(data, dict):
        return {k: strip_private(v) for k, v in data.items() if not k.startswith("_") or k == "_meta"}
    if isinstance(data, list):
        return [strip_private(v) for v in data]
    return data


def dossier_zip(dossier: dict, pdf_bytes: bytes, base_name: str) -> bytes:
    """ZIP mit PDF, JSON und allen (sichtbaren) Anhängen inkl. Prüfsummenliste."""
    buf = io.BytesIO()
    checksums = []
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{base_name}.pdf", pdf_bytes)
        zf.writestr(f"{base_name}.json", to_json(strip_private(dossier)))

        def add_atts(items, folder):
            for a in items:
                from ..models import Attachment as A  # noqa: N814

                path = absolute_path(A(storage_path=a["_path"]))
                if path.exists():
                    name = f"{folder}/{a['_uid'][:8]}_{a['Datei']}"
                    zf.write(path, name)
                    checksums.append(f"{a['SHA-256']}  {name}")

        add_atts(dossier.get("Anhänge", []), "anhaenge")
        for e in dossier.get("Versuche", []):
            add_atts(e.get("Anhänge", []), f"anhaenge/{e['Kennung']}")
        zf.writestr("SHA256SUMS.txt", "\n".join(checksums) + "\n")
    return buf.getvalue()


def fmt(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "Ja" if v else "Nein"
    if isinstance(v, float):
        return de_number(v)
    if isinstance(v, (list, tuple)):
        return ", ".join(fmt(x) for x in v)
    return str(v)
