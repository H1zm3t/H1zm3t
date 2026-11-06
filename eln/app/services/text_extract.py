"""Einfache lokale Textextraktion für die Suche in Anhängen.

Unterstützt: PDF (pypdf), DOCX/PPTX (ZIP/XML), XLSX (openpyxl), Text, CSV, JSON, XML.
Später kann hier eine leistungsfähigere Volltextsuche (z. B. SQLite FTS5,
PostgreSQL tsvector oder ein Suchserver) angebunden werden.
"""
from __future__ import annotations

import re
import zipfile
from pathlib import Path

MAX_CHARS = 200_000
TEXT_EXT = {"txt", "csv", "tsv", "json", "xml", "log", "md", "ini", "asc"}


def _clean(text: str) -> str:
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()[:MAX_CHARS]


def _xml_text(data: bytes) -> str:
    text = re.sub(rb"<[^>]+>", b" ", data).decode("utf-8", errors="ignore")
    return re.sub(r"\s+", " ", text)


def extract_text(path: Path, ext: str) -> str | None:
    ext = ext.lower()
    if ext in TEXT_EXT:
        raw = path.read_bytes()[: MAX_CHARS * 2]
        for enc in ("utf-8", "cp1252", "latin-1"):
            try:
                return _clean(raw.decode(enc))
            except UnicodeDecodeError:
                continue
        return None
    if ext == "pdf":
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        parts = []
        for page in reader.pages[:200]:
            parts.append(page.extract_text() or "")
            if sum(len(p) for p in parts) > MAX_CHARS:
                break
        return _clean("\n".join(parts)) or None
    if ext in ("docx", "pptx"):
        with zipfile.ZipFile(path) as zf:
            names = [n for n in zf.namelist()
                     if (n.startswith("word/") and n.endswith(".xml")) or (n.startswith("ppt/slides/slide"))]
            return _clean(" ".join(_xml_text(zf.read(n)) for n in names)) or None
    if ext in ("xlsx", "xlsm"):
        from openpyxl import load_workbook

        wb = load_workbook(path, read_only=True, data_only=True)
        parts = []
        for ws in wb.worksheets[:20]:
            for row in ws.iter_rows(values_only=True, max_row=5000):
                vals = [str(v) for v in row if v is not None]
                if vals:
                    parts.append(" ".join(vals))
            if sum(len(p) for p in parts) > MAX_CHARS:
                break
        wb.close()
        return _clean("\n".join(parts)) or None
    return None
