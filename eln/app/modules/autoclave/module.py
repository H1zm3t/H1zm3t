"""Fachmodul »Autoklav« – Grundgerüst (deklarativ).

Autoklavenversuche (Druck/Temperatur/Medium).
Erfassung, Liste, Detailseite, Anhänge, Audit Trail, Versuchsverknüpfung und
Auswertung werden vom ELN-Kern bereitgestellt (app/core/declarative.py).
Für den fachlichen Ausbau siehe docs/PLUGIN_ENTWICKLUNG.md.
"""
from ...core.declarative import DeclarativeModule
from ...core.forms import FieldSpec as F


class AutoclaveModule(DeclarativeModule):
    key = "autoclave"
    slug = "autoklav"
    name = "Autoklav"
    version = "0.1.0"
    description = "Autoklavenversuche (Druck/Temperatur/Medium)."
    category = "Alterung / Klima / Autoklav"
    maturity = "Grundgerüst"
    default_enabled = False
    record_label = "Datensatz"
    departments = ('Alterung / Klima / Autoklav',)
    fields = (
        F("medium", "Medium", kind="text"),
        F("temperature", "Temperatur", kind="float", unit="°C"),
        F("pressure", "Druck", kind="float", unit="bar"),
        F("duration", "Dauer", kind="float", unit="h"),
        F("notes", "Bemerkungen", kind="textarea", width="full"),
    )


MODULE = AutoclaveModule()
