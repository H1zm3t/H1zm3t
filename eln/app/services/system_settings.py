"""Systemeinstellungen (in der Datenbank, über die Oberfläche änderbar)."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from ..models import SystemSetting


@dataclass(frozen=True)
class SettingDef:
    key: str
    label: str
    kind: str  # bool, int, float, text
    default: str
    help: str = ""


SETTING_DEFS: list[SettingDef] = [
    SettingDef("company_name", "Organisationseinheit", "text", "Anwendungstechnik",
               "Wird in Kopfzeile und Berichten angezeigt."),
    SettingDef("require_independent_review", "Unabhängige Prüfung erzwingen", "bool", "1",
               "Verantwortliche bzw. Einreichende dürfen ihren eigenen Versuch nicht prüfen oder freigeben."),
    SettingDef("require_manager_approval", "Zusätzliche Freigabe durch Abteilungsleitung", "bool", "0",
               "Nach der Prüfung ist eine weitere Freigabe durch die Rolle »Abteilungsleitung« nötig."),
    SettingDef("reason_required_for_edits", "Änderungsgrund verpflichtend", "bool", "1",
               "Bei Änderungen an Datensätzen außerhalb des Entwurfsstatus muss ein Grund angegeben werden."),
    SettingDef("recipe_sum_tolerance", "Toleranz Rezeptursumme (Gew.-%)", "float", "0.01",
               "Zulässige Abweichung der Summe der Anteile von 100 Gew.-%."),
    SettingDef("calibration_warning_days", "Vorwarnzeit Kalibrierung/Wartung (Tage)", "int", "14",
               "Ab wie vielen Tagen vor Fälligkeit gewarnt wird."),
    SettingDef("block_locked_devices", "Gesperrte Geräte blockieren", "bool", "0",
               "Wenn aktiv, können gesperrte oder überfällig kalibrierte Geräte nicht zugeordnet werden (sonst nur Warnung)."),
    SettingDef("allowed_extensions", "Erlaubte Dateiendungen", "text",
               "pdf,png,jpg,jpeg,gif,bmp,tif,tiff,webp,xlsx,xls,xlsm,docx,doc,pptx,csv,txt,json,xml,zip,"
               "dat,raw,asc,ngb-dsv,ngb-ss3,ngb-taa,dsv,tsv,log,mtx,zs2,rpt,ini,md",
               "Kommagetrennt, ohne Punkt. Ausführbare Dateien sind immer gesperrt."),
]

_DEFS = {d.key: d for d in SETTING_DEFS}


def get_setting(db: Session, key: str):
    definition = _DEFS[key]
    row = db.get(SystemSetting, key)
    raw = row.value if row else definition.default
    if definition.kind == "bool":
        return raw in ("1", "true", "True")
    if definition.kind == "int":
        return int(raw)
    if definition.kind == "float":
        return float(raw)
    return raw


def all_settings(db: Session) -> list[tuple[SettingDef, object]]:
    return [(d, get_setting(db, d.key)) for d in SETTING_DEFS]


def set_setting(db: Session, key: str, value) -> tuple[str, str]:
    """Speichert einen Wert und gibt (alt, neu) als Text zurück."""
    definition = _DEFS[key]
    if definition.kind == "bool":
        new = "1" if value in (True, "1", "on", "true") else "0"
    elif definition.kind == "int":
        new = str(int(value))
    elif definition.kind == "float":
        new = str(float(value))
    else:
        new = str(value).strip()
    row = db.get(SystemSetting, key)
    old = row.value if row else definition.default
    if row is None:
        db.add(SystemSetting(key=key, value=new))
    else:
        row.value = new
    db.flush()
    return old, new
