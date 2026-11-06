"""Fachmodul »Thermische Alterung« – Grundgerüst (deklarativ).

Ofenalterung mit Entnahmezeitpunkten.
Erfassung, Liste, Detailseite, Anhänge, Audit Trail, Versuchsverknüpfung und
Auswertung werden vom ELN-Kern bereitgestellt (app/core/declarative.py).
Für den fachlichen Ausbau siehe docs/PLUGIN_ENTWICKLUNG.md.
"""
from ...core.declarative import DeclarativeModule
from ...core.forms import FieldSpec as F


class ThermalAgingModule(DeclarativeModule):
    key = "thermal_aging"
    slug = "thermische-alterung"
    name = "Thermische Alterung"
    version = "0.1.0"
    description = "Ofenalterung mit Entnahmezeitpunkten."
    category = "Alterung / Klima / Autoklav"
    maturity = "Grundgerüst"
    default_enabled = False
    record_label = "Datensatz"
    departments = ('Alterung / Klima / Autoklav',)
    fields = (
        F("oven", "Ofen", kind="text"),
        F("temperature", "Temperatur", kind="float", unit="°C"),
        F("start", "Beginn", kind="date"),
        F("duration", "Gesamtdauer", kind="float", unit="h"),
        F("intervals", "Entnahmeintervalle", kind="text", unit="h"),
        F("notes", "Bemerkungen", kind="textarea", width="full"),
    )


MODULE = ThermalAgingModule()
