"""Fachmodul »DSC« – Grundgerüst (deklarativ).

Dynamische Differenzkalorimetrie (NETZSCH).
Erfassung, Liste, Detailseite, Anhänge, Audit Trail, Versuchsverknüpfung und
Auswertung werden vom ELN-Kern bereitgestellt (app/core/declarative.py).
Für den fachlichen Ausbau siehe docs/PLUGIN_ENTWICKLUNG.md.
"""
from ...core.declarative import DeclarativeModule
from ...core.forms import FieldSpec as F


class DscModule(DeclarativeModule):
    key = "dsc"
    slug = "dsc"
    name = "DSC"
    version = "0.1.0"
    description = "Dynamische Differenzkalorimetrie (NETZSCH)."
    category = "Thermische Analyse"
    maturity = "Grundgerüst"
    default_enabled = False
    record_label = "Datensatz"
    departments = ('Thermische Analyse',)
    fields = (
        F("program", "Temperaturprogramm", kind="text"),
        F("heating_rate", "Heizrate", kind="float", unit="K/min"),
        F("tm", "Schmelztemperatur Tm", kind="float", unit="°C"),
        F("tc", "Kristallisationstemperatur Tc", kind="float", unit="°C"),
        F("dhm", "Schmelzenthalpie ΔHm", kind="float", unit="J/g"),
        F("oit", "OIT", kind="float", unit="min"),
        F("notes", "Bemerkungen", kind="textarea", width="full"),
    )


MODULE = DscModule()
