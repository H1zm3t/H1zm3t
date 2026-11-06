"""Fachmodul »Spritzguss« – Grundgerüst (deklarativ).

Herstellung genormter Prüfkörper (Demag, Axxicon-Werkzeuge).
Erfassung, Liste, Detailseite, Anhänge, Audit Trail, Versuchsverknüpfung und
Auswertung werden vom ELN-Kern bereitgestellt (app/core/declarative.py).
Für den fachlichen Ausbau siehe docs/PLUGIN_ENTWICKLUNG.md.
"""
from ...core.declarative import DeclarativeModule
from ...core.forms import FieldSpec as F


class InjectionMoldingModule(DeclarativeModule):
    key = "injection_molding"
    slug = "spritzguss"
    name = "Spritzguss"
    version = "0.1.0"
    description = "Herstellung genormter Prüfkörper (Demag, Axxicon-Werkzeuge)."
    category = "Verarbeitung"
    maturity = "Grundgerüst"
    default_enabled = False
    record_label = "Datensatz"
    departments = ('Spritzguss', 'Musterherstellung')
    fields = (
        F("tool", "Werkzeug / Form", kind="text"),
        F("specimen_type", "Prüfkörpertyp", kind="select", options=('1A (ISO 527)', 'Stab 80x10x4', 'Platte 60x60x2', 'Sonstiges')),
        F("melt_temp", "Massetemperatur", kind="float", unit="°C"),
        F("mold_temp", "Werkzeugtemperatur", kind="float", unit="°C"),
        F("injection_speed", "Einspritzgeschwindigkeit", kind="float", unit="mm/s"),
        F("holding_pressure", "Nachdruck", kind="float", unit="bar"),
        F("cycle_time", "Zykluszeit", kind="float", unit="s"),
        F("count", "Anzahl Prüfkörper", kind="int"),
        F("notes", "Bemerkungen", kind="textarea", width="full"),
    )


MODULE = InjectionMoldingModule()
