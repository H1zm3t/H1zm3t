"""Deutsche Darstellung (TT.MM.JJJJ, HH:MM, Dezimalkomma) und tolerantes Einlesen."""
from __future__ import annotations

import math
from datetime import date, datetime


def de_date(value) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, str):
        try:
            value = date.fromisoformat(value[:10])
        except ValueError:
            return value
    return value.strftime("%d.%m.%Y")


def de_datetime(value) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return value
    if isinstance(value, datetime):
        return value.strftime("%d.%m.%Y %H:%M")
    return de_date(value)


def de_time(value) -> str:
    if not value:
        return ""
    return value.strftime("%H:%M")


def de_number(value, decimals: int | None = None) -> str:
    """12345.678 -> '12.345,678' (Tausenderpunkt, Dezimalkomma)."""
    if value is None or value == "":
        return ""
    try:
        num = float(value)
    except (TypeError, ValueError):
        return str(value)
    if math.isnan(num):
        return ""
    if decimals is None:
        if num == int(num) and abs(num) < 1e15:
            text = f"{int(num):,}"
        else:
            text = f"{num:,.6f}".rstrip("0").rstrip(".")
    else:
        text = f"{num:,.{decimals}f}"
    return text.replace(",", "§").replace(".", ",").replace("§", ".")


def de_input_number(value) -> str:
    """Zahl für Eingabefelder: Dezimalkomma, ohne Tausenderpunkte."""
    if value is None or value == "":
        return ""
    num = float(value)
    if num == int(num) and abs(num) < 1e15:
        return str(int(num))
    return repr(num).replace(".", ",")


def parse_number(text) -> float | None:
    """Liest '1.234,5', '1234,5', '1234.5' oder '1,234.5' ein."""
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return float(text)
    s = str(text).strip().replace(" ", "").replace(" ", "")
    if s == "":
        return None
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    value = float(s)
    if math.isnan(value) or math.isinf(value):
        raise ValueError("ungültige Zahl")
    return value


def parse_date(text) -> date | None:
    """Akzeptiert TT.MM.JJJJ und JJJJ-MM-TT."""
    if text is None:
        return None
    if isinstance(text, datetime):
        return text.date()
    if isinstance(text, date):
        return text
    s = str(text).strip()
    if not s:
        return None
    if "." in s:
        d, m, y = s.split(".")[:3]
        y = y.strip()[:4]
        if len(y) == 2:
            y = "20" + y
        return date(int(y), int(m), int(d))
    return date.fromisoformat(s[:10])


def parse_datetime(text) -> datetime | None:
    if text is None:
        return None
    if isinstance(text, datetime):
        return text
    s = str(text).strip()
    if not s:
        return None
    if "." in s.split(" ")[0]:
        dpart, _, tpart = s.partition(" ")
        d = parse_date(dpart)
        hh, mm = (tpart or "00:00").split(":")[:2]
        return datetime(d.year, d.month, d.day, int(hh), int(mm))
    return datetime.fromisoformat(s.replace("T", " ")[:16])


def file_size(num: int | None) -> str:
    if num is None:
        return ""
    size = float(num)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{de_number(size, 0 if unit == 'B' else 1)} {unit}"
        size /= 1024
    return str(num)
