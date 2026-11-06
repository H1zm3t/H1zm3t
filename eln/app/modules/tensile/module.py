"""Fachmodul »Zugprüfung« – Grundgerüst (deklarativ).

Zugversuch nach ISO 527 (ZwickRoell Z010/Z020).
Erfassung, Liste, Detailseite, Anhänge, Audit Trail, Versuchsverknüpfung und
Auswertung werden vom ELN-Kern bereitgestellt (app/core/declarative.py).
Für den fachlichen Ausbau siehe docs/PLUGIN_ENTWICKLUNG.md.
"""
from ...core.declarative import DeclarativeModule
from ...core.forms import FieldSpec as F


class TensileModule(DeclarativeModule):
    key = "tensile"
    slug = "zugpruefung"
    name = "Zugprüfung"
    version = "0.1.0"
    description = "Zugversuch nach ISO 527 (ZwickRoell Z010/Z020)."
    category = "Mechanische Prüfung"
    maturity = "Grundgerüst"
    default_enabled = False
    record_label = "Datensatz"
    departments = ('Mechanische Prüfung',)
    fields = (
        F("standard", "Norm", kind="text"),
        F("test_speed", "Prüfgeschwindigkeit", kind="float", unit="mm/min"),
        F("conditioning", "Konditionierung", kind="text"),
        F("modulus", "E-Modul (Mittel)", kind="float", unit="MPa"),
        F("strength", "Zugfestigkeit (Mittel)", kind="float", unit="MPa"),
        F("elongation", "Bruchdehnung (Mittel)", kind="float", unit="%"),
        F("n", "Anzahl Prüfkörper", kind="int"),
        F("notes", "Bemerkungen", kind="textarea", width="full"),
    )


MODULE = TensileModule()
