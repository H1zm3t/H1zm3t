"""Fachmodul »Musterverwaltung« – Grundgerüst (deklarativ).

Versand und Verfolgung von Kundenmustern.
Erfassung, Liste, Detailseite, Anhänge, Audit Trail, Versuchsverknüpfung und
Auswertung werden vom ELN-Kern bereitgestellt (app/core/declarative.py).
Für den fachlichen Ausbau siehe docs/PLUGIN_ENTWICKLUNG.md.
"""
from ...core.declarative import DeclarativeModule
from ...core.forms import FieldSpec as F


class SampleManagementModule(DeclarativeModule):
    key = "sample_management"
    slug = "musterverwaltung"
    name = "Musterverwaltung"
    version = "0.1.0"
    description = "Versand und Verfolgung von Kundenmustern."
    category = "Musterherstellung"
    maturity = "Grundgerüst"
    default_enabled = False
    record_label = "Datensatz"
    departments = ()
    fields = (
        F("recipient", "Empfänger", kind="text"),
        F("quantity", "Menge", kind="float", unit="kg"),
        F("ship_date", "Versanddatum", kind="date"),
        F("tracking", "Sendungsnummer", kind="text"),
        F("notes", "Bemerkungen", kind="textarea", width="full"),
    )


MODULE = SampleManagementModule()
