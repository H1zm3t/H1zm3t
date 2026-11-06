"""Fachmodul »TGA« – Grundgerüst (deklarativ).

Thermogravimetrie (NETZSCH).
Erfassung, Liste, Detailseite, Anhänge, Audit Trail, Versuchsverknüpfung und
Auswertung werden vom ELN-Kern bereitgestellt (app/core/declarative.py).
Für den fachlichen Ausbau siehe docs/PLUGIN_ENTWICKLUNG.md.
"""
from ...core.declarative import DeclarativeModule
from ...core.forms import FieldSpec as F


class TgaModule(DeclarativeModule):
    key = "tga"
    slug = "tga"
    name = "TGA"
    version = "0.1.0"
    description = "Thermogravimetrie (NETZSCH)."
    category = "Thermische Analyse"
    maturity = "Grundgerüst"
    default_enabled = False
    record_label = "Datensatz"
    departments = ('Thermische Analyse',)
    fields = (
        F("atmosphere", "Atmosphäre", kind="select", options=('Stickstoff', 'Luft', 'Sauerstoff')),
        F("heating_rate", "Heizrate", kind="float", unit="K/min"),
        F("t5", "T(5 % Masseverlust)", kind="float", unit="°C"),
        F("residue", "Rückstand", kind="float", unit="%"),
        F("notes", "Bemerkungen", kind="textarea", width="full"),
    )


MODULE = TgaModule()
