"""Automatische, eindeutige Kennungen (z. B. A-2026-0001)."""
from __future__ import annotations

from datetime import date

from sqlalchemy import update
from sqlalchemy.orm import Session

from ..models import Counter

# Präfix, jährlicher Nummernkreis?, Stellen
SCHEMES: dict[str, tuple[str, bool, int]] = {
    "project": ("P", True, 3),
    "order": ("A", True, 4),
    "series": ("VR", True, 3),
    "experiment": ("V", True, 4),
    "recipe": ("R", False, 5),
    "material": ("M", False, 5),
    "batch": ("CH", False, 5),
    "sample": ("S", True, 5),
    "device": ("G", False, 3),
    "method": ("PM", False, 3),
    "measurement": ("D", True, 5),
    "task": ("T", True, 4),
}


def next_code(db: Session, scheme_key: str, prefix: str | None = None, yearly: bool | None = None,
              digits: int | None = None) -> str:
    """Erzeugt die nächste Kennung innerhalb der laufenden Transaktion."""
    p, y, d = SCHEMES.get(scheme_key, (scheme_key.upper(), True, 4))
    prefix = prefix or p
    yearly = y if yearly is None else yearly
    digits = digits or d
    year = date.today().year
    counter_key = f"{prefix}-{year}" if yearly else prefix
    result = db.execute(update(Counter).where(Counter.key == counter_key).values(value=Counter.value + 1))
    if result.rowcount == 0:
        db.add(Counter(key=counter_key, value=1))
        db.flush()
        value = 1
    else:
        value = db.get(Counter, counter_key, populate_existing=True).value
    number = str(value).zfill(digits)
    return f"{prefix}-{year}-{number}" if yearly else f"{prefix}-{number}"
