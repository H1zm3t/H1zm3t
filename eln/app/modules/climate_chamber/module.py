"""Fachmodul »Klimaschrank« – Grundgerüst (deklarativ).

Klimaschrankversuche (Temperatur/Feuchte/Zyklen).
Erfassung, Liste, Detailseite, Anhänge, Audit Trail, Versuchsverknüpfung und
Auswertung werden vom ELN-Kern bereitgestellt (app/core/declarative.py).
Für den fachlichen Ausbau siehe docs/PLUGIN_ENTWICKLUNG.md.
"""
from ...core.declarative import DeclarativeModule
from ...core.forms import FieldSpec as F


class ClimateChamberModule(DeclarativeModule):
    key = "climate_chamber"
    slug = "klimaschrank"
    name = "Klimaschrank"
    version = "0.1.0"
    description = "Klimaschrankversuche (Temperatur/Feuchte/Zyklen)."
    category = "Alterung / Klima / Autoklav"
    maturity = "Grundgerüst"
    default_enabled = False
    record_label = "Datensatz"
    departments = ('Alterung / Klima / Autoklav',)
    fields = (
        F("temperature", "Temperatur", kind="float", unit="°C"),
        F("humidity", "Relative Feuchte", kind="float", unit="%"),
        F("cycles", "Zyklen", kind="int"),
        F("duration", "Dauer", kind="float", unit="h"),
        F("notes", "Bemerkungen", kind="textarea", width="full"),
    )


MODULE = ClimateChamberModule()
