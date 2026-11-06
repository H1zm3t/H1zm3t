"""Fachmodul »Rohstoffprüfung« – Grundgerüst (deklarativ).

Eingangs- und Rohstoffprüfung.
Erfassung, Liste, Detailseite, Anhänge, Audit Trail, Versuchsverknüpfung und
Auswertung werden vom ELN-Kern bereitgestellt (app/core/declarative.py).
Für den fachlichen Ausbau siehe docs/PLUGIN_ENTWICKLUNG.md.
"""
from ...core.declarative import DeclarativeModule
from ...core.forms import FieldSpec as F


class RawMaterialTestingModule(DeclarativeModule):
    key = "raw_material_testing"
    slug = "rohstoffpruefung"
    name = "Rohstoffprüfung"
    version = "0.1.0"
    description = "Eingangs- und Rohstoffprüfung."
    category = "Rohstoffprüfung"
    maturity = "Grundgerüst"
    default_enabled = False
    record_label = "Datensatz"
    departments = ('Rohstoffprüfung',)
    fields = (
        F("spec", "Spezifikation", kind="text"),
        F("moisture", "Feuchte", kind="float", unit="%"),
        F("bulk_density", "Schüttdichte", kind="float", unit="g/l"),
        F("result", "Ergebnis", kind="select", options=('i. O.', 'n. i. O.', 'Sonderfreigabe')),
        F("notes", "Bemerkungen", kind="textarea", width="full"),
    )


MODULE = RawMaterialTestingModule()
