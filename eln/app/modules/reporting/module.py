"""Fachmodul »Berichtserstellung« – Grundgerüst (deklarativ).

Kundenberichte und Prüfberichte (Gliederung, Freigabe).
Erfassung, Liste, Detailseite, Anhänge, Audit Trail, Versuchsverknüpfung und
Auswertung werden vom ELN-Kern bereitgestellt (app/core/declarative.py).
Für den fachlichen Ausbau siehe docs/PLUGIN_ENTWICKLUNG.md.
"""
from ...core.declarative import DeclarativeModule
from ...core.forms import FieldSpec as F


class ReportingModule(DeclarativeModule):
    key = "reporting"
    slug = "berichte"
    name = "Berichtserstellung"
    version = "0.1.0"
    description = "Kundenberichte und Prüfberichte (Gliederung, Freigabe)."
    category = "Dokumentation"
    maturity = "Grundgerüst"
    default_enabled = False
    record_label = "Datensatz"
    departments = ()
    fields = (
        F("recipient", "Empfänger", kind="text"),
        F("report_type", "Berichtsart", kind="select", options=('Prüfbericht', 'Kundeninformation', 'interner Bericht')),
        F("summary", "Zusammenfassung", kind="textarea", width="full"),
        F("sent_on", "Versendet am", kind="date"),
    )


MODULE = ReportingModule()
