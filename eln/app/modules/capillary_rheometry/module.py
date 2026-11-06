"""Fachmodul »Hochdruckkapillarrheometrie« – Grundgerüst (deklarativ).

Göttfert Rheograph RG20.
Erfassung, Liste, Detailseite, Anhänge, Audit Trail, Versuchsverknüpfung und
Auswertung werden vom ELN-Kern bereitgestellt (app/core/declarative.py).
Für den fachlichen Ausbau siehe docs/PLUGIN_ENTWICKLUNG.md.
"""
from ...core.declarative import DeclarativeModule
from ...core.forms import FieldSpec as F


class CapillaryRheometryModule(DeclarativeModule):
    key = "capillary_rheometry"
    slug = "kapillarrheometrie"
    name = "Hochdruckkapillarrheometrie"
    version = "0.1.0"
    description = "Göttfert Rheograph RG20."
    category = "Rheologie"
    maturity = "Grundgerüst"
    default_enabled = False
    record_label = "Datensatz"
    departments = ('Rheologie',)
    fields = (
        F("temperature", "Temperatur", kind="float", unit="°C"),
        F("die", "Kapillare (L/D)", kind="text"),
        F("shear_rate_min", "Scherrate min", kind="float", unit="1/s"),
        F("shear_rate_max", "Scherrate max", kind="float", unit="1/s"),
        F("viscosity_ref", "Viskosität bei Referenzscherrate", kind="float", unit="Pa·s"),
        F("notes", "Bemerkungen", kind="textarea", width="full"),
    )


MODULE = CapillaryRheometryModule()
