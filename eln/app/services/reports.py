"""PDF-Berichte mit ReportLab.

Entscheidung: ReportLab ist eine reine Python-Bibliothek ohne externe
Systemabhängigkeiten (anders als WeasyPrint, das unter Windows GTK benötigt)
und läuft daher zuverlässig auf Windows-Arbeitsplätzen. Unter Windows wird –
falls vorhanden – Arial eingebettet, sonst die Standardschrift Helvetica.
"""
from __future__ import annotations

import io
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .export import fmt

_FONT = "Helvetica"
_FONT_BOLD = "Helvetica-Bold"


def _init_fonts() -> None:
    global _FONT, _FONT_BOLD
    candidates = [
        (Path("C:/Windows/Fonts/arial.ttf"), Path("C:/Windows/Fonts/arialbd.ttf")),
        (Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"), Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")),
    ]
    for regular, bold in candidates:
        if regular.exists() and bold.exists():
            try:
                pdfmetrics.registerFont(TTFont("ELN", str(regular)))
                pdfmetrics.registerFont(TTFont("ELN-Bold", str(bold)))
                _FONT, _FONT_BOLD = "ELN", "ELN-Bold"
                return
            except Exception:  # Schrift defekt -> Standardschrift verwenden
                continue


_init_fonts()

PRIMARY = colors.HexColor("#1F4E79")
LIGHT = colors.HexColor("#EEF3F8")


def _styles():
    ss = getSampleStyleSheet()
    base = ParagraphStyle("base", parent=ss["Normal"], fontName=_FONT, fontSize=9, leading=12, alignment=TA_LEFT)
    return {
        "base": base,
        "small": ParagraphStyle("small", parent=base, fontSize=7.5, leading=9.5),
        "title": ParagraphStyle("title", parent=base, fontName=_FONT_BOLD, fontSize=16, leading=20,
                                textColor=PRIMARY, spaceAfter=4),
        "h2": ParagraphStyle("h2", parent=base, fontName=_FONT_BOLD, fontSize=11.5, leading=15, textColor=PRIMARY,
                             spaceBefore=10, spaceAfter=4),
        "h3": ParagraphStyle("h3", parent=base, fontName=_FONT_BOLD, fontSize=10, leading=13, spaceBefore=6,
                             spaceAfter=2),
        "cell": ParagraphStyle("cell", parent=base, fontSize=8, leading=10),
        "cellb": ParagraphStyle("cellb", parent=base, fontName=_FONT_BOLD, fontSize=8, leading=10),
    }


def _p(text: Any, style) -> Paragraph:
    s = fmt(text)
    if _FONT == "Helvetica":  # Standardschrift kennt einige Zeichen nicht
        s = s.replace("→", "->").replace("≤", "<=").replace("≥", ">=").replace("±", "+/-")
    return Paragraph(escape(s).replace("\n", "<br/>"), style)


def _kv_table(data: dict, st, col1=45 * mm) -> Table:
    rows = [[_p(k, st["cellb"]), _p(v, st["cell"])] for k, v in data.items() if not str(k).startswith("_")]
    t = Table(rows, colWidths=[col1, 180 * mm - col1])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (0, -1), LIGHT),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#C8D3DF")),
        ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    return t


def _grid(headers: list[str], rows: list[list[Any]], st, widths: list[float] | None = None) -> Table:
    data = [[_p(h, st["cellb"]) for h in headers]] + [[_p(c, st["cell"]) for c in r] for r in rows]
    if widths is None:
        widths = [180 * mm / len(headers)] * len(headers)
    t = Table(data, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), LIGHT),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#C8D3DF")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    return t


def _list_of_dicts(items: list[dict], st, skip: tuple = ()) -> Table | Paragraph:
    if not items:
        return _p("– keine –", st["small"])
    headers = [k for k in items[0].keys() if not k.startswith("_") and k not in skip]
    return _grid(headers, [[it.get(h) for h in headers] for it in items], st)


def _text_block(title: str, text: Any, st, story: list) -> None:
    story.append(_p(title, st["h3"]))
    story.append(_p(text if text else "–", st["base"]))


def _footer(title: str):
    def draw(canvas, doc):
        canvas.saveState()
        canvas.setFont(_FONT, 7.5)
        canvas.setFillColor(colors.grey)
        canvas.drawString(15 * mm, 10 * mm, title)
        canvas.drawRightString(195 * mm, 10 * mm, f"Seite {doc.page}")
        canvas.restoreState()
    return draw


def _experiment_story(d: dict, st, story: list, heading_level: str = "title") -> None:
    story.append(_p(f"Versuchsdossier {d['Kennung']} – Rev. {d['Revision']}", st[heading_level]))
    story.append(_kv_table({"Status": d["Status"], "Version": d["Version"],
                            "Gesperrt": d["Gesperrt"], **d["Stammdaten"]}, st))
    story.append(_p("Zielsetzung", st["h2"]))
    _text_block("Ziel", d["Zielsetzung"]["Ziel"], st, story)
    _text_block("Hypothese", d["Zielsetzung"]["Hypothese"], st, story)
    story.append(_p("Geräte, Materialien und Chargen", st["h2"]))
    story.append(_list_of_dicts(d["Geräte"], st))
    story.append(Spacer(1, 4))
    story.append(_list_of_dicts(d["Materialien"], st))
    story.append(Spacer(1, 4))
    story.append(_list_of_dicts(d["Chargen"], st))
    story.append(_p("Rezeptur", st["h2"]))
    if d["Rezeptur"]:
        r = d["Rezeptur"]
        story.append(_p(f"{r['Kennung']} – {r['Name']} · Summe {fmt(r['Summe'])} Gew.-% · {r['Summenprüfung']}",
                        st["base"]))
        cols = ["Pos.", "Material-ID", "Materialnummer", "Material", "Charge", "Funktion", "Soll", "Ist", "Einheit",
                "Gew.-%"]
        widths = [10, 20, 22, 36, 20, 24, 14, 14, 10, 10]
        story.append(_grid(cols, [[it.get(c) for c in cols] for it in r["Positionen"]], st,
                           [w * mm for w in widths]))
    else:
        story.append(_p("– keine Rezeptur zugeordnet –", st["small"]))
    story.append(_p("Prozess", st["h2"]))
    _text_block("Prozessschritte", d["Prozessschritte"], st, story)
    if d["Prozessparameter"]:
        story.append(_p("Prozessparameter", st["h3"]))
        story.append(_grid(["Parameter", "Wert", "Einheit"],
                           [[p.get("name"), p.get("value"), p.get("unit")] for p in d["Prozessparameter"]], st))
    for sec in d["Modulabschnitte"]:
        story.append(KeepTogether([_p(f"{sec['module']}: {sec['title']}", st["h3"]),
                                   _grid(sec["headers"], sec["rows"], st) if sec["rows"] else _p("–", st["small"])]))
        if sec.get("note"):
            story.append(_p(sec["note"], st["small"]))
    story.append(_p("Durchführung", st["h2"]))
    for k, v in d["Durchführung"].items():
        _text_block(k, v, st, story)
    story.append(_p("Proben", st["h2"]))
    story.append(_list_of_dicts(d["Proben"], st))
    story.append(_p("Prüfungen und Messdaten", st["h2"]))
    story.append(_list_of_dicts(d["Prüfungen"], st, skip=("Werte",)))
    story.append(_p("Ergebnis und Bewertung", st["h2"]))
    for k, v in d["Ergebnis"].items():
        _text_block(k, v, st, story)
    story.append(_p("Anhangverzeichnis", st["h2"]))
    story.append(_list_of_dicts([{k: v for k, v in a.items() if k != "Größe (Bytes)"} for a in d["Anhänge"]], st))
    story.append(_p("Prüfung und Freigabe", st["h2"]))
    story.append(_list_of_dicts(d["Freigaben"], st))
    story.append(_p("Audit-Trail-Auszug", st["h2"]))
    story.append(_list_of_dicts(d["Audit-Trail-Auszug"], st))


def experiment_pdf(d: dict) -> bytes:
    st = _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=15 * mm,
                            bottomMargin=16 * mm, title=f"Versuchsdossier {d['Kennung']}", author=d["_meta"]["Erstellt von"])
    story: list = [_p(f"{d['_meta']['Anwendung']} · erstellt {d['_meta']['Erstellt']} von {d['_meta']['Erstellt von']}",
                      st["small"]), Spacer(1, 4)]
    _experiment_story(d, st, story)
    doc.build(story, onFirstPage=_footer(f"Versuchsdossier {d['Kennung']} Rev. {d['Revision']}"),
              onLaterPages=_footer(f"Versuchsdossier {d['Kennung']} Rev. {d['Revision']}"))
    return buf.getvalue()


def order_pdf(d: dict) -> bytes:
    st = _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=15 * mm,
                            bottomMargin=16 * mm, title=f"Auftragsdossier {d['Kennung']}")
    story: list = [_p(f"{d['_meta']['Anwendung']} · erstellt {d['_meta']['Erstellt']} von {d['_meta']['Erstellt von']}",
                      st["small"]), Spacer(1, 4),
                   _p(f"Auftragsdossier {d['Kennung']}", st["title"]),
                   _kv_table({"Status": d["Status"], "Version": d["Version"], **d["Stammdaten"]}, st)]
    _text_block("Aufgabenstellung", d["Aufgabenstellung"], st, story)
    _text_block("Zielsetzung", d["Zielsetzung"], st, story)
    story.append(_p("Versuche", st["h2"]))
    story.append(_list_of_dicts([{"ID": e["Kennung"], "Rev.": e["Revision"], "Bezeichnung": e["Stammdaten"]["Bezeichnung"],
                                  "Status": e["Status"]} for e in d["Versuche"]], st))
    story.append(_p("Proben", st["h2"]))
    story.append(_list_of_dicts(d["Proben"], st))
    story.append(_p("Anhänge des Auftrags", st["h2"]))
    story.append(_list_of_dicts(d["Anhänge"], st))
    story.append(_p("Audit-Trail-Auszug", st["h2"]))
    story.append(_list_of_dicts(d["Audit-Trail-Auszug"], st))
    for e in d["Versuche"]:
        story.append(PageBreak())
        _experiment_story(e, st, story, heading_level="h2")
    doc.build(story, onFirstPage=_footer(f"Auftragsdossier {d['Kennung']}"),
              onLaterPages=_footer(f"Auftragsdossier {d['Kennung']}"))
    return buf.getvalue()
