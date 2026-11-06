"""Fachmodul »Partikelgrößenverteilung« – Grundgerüst (deklarativ).

Laserbeugung (Malvern).
Erfassung, Liste, Detailseite, Anhänge, Audit Trail, Versuchsverknüpfung und
Auswertung werden vom ELN-Kern bereitgestellt (app/core/declarative.py).
Für den fachlichen Ausbau siehe docs/PLUGIN_ENTWICKLUNG.md.
"""
from ...core.declarative import DeclarativeModule
from ...core.forms import FieldSpec as F


class ParticleSizeModule(DeclarativeModule):
    key = "particle_size"
    slug = "partikelgroesse"
    name = "Partikelgrößenverteilung"
    version = "0.1.0"
    description = "Laserbeugung (Malvern)."
    category = "Partikelanalytik"
    maturity = "Grundgerüst"
    default_enabled = False
    record_label = "Datensatz"
    departments = ('Partikelanalytik', 'Mischen / Mahlen')
    fields = (
        F("dispersion", "Dispergierung", kind="select", options=('trocken', 'nass')),
        F("d10", "d10", kind="float", unit="µm"),
        F("d50", "d50", kind="float", unit="µm"),
        F("d90", "d90", kind="float", unit="µm"),
        F("span", "Span", kind="float"),
        F("notes", "Bemerkungen", kind="textarea", width="full"),
    )


MODULE = ParticleSizeModule()
