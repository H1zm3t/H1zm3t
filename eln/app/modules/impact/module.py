"""Fachmodul »Schlagzähigkeit« – Grundgerüst (deklarativ).

Charpy/Izod (ZwickRoell HIT 5.5).
Erfassung, Liste, Detailseite, Anhänge, Audit Trail, Versuchsverknüpfung und
Auswertung werden vom ELN-Kern bereitgestellt (app/core/declarative.py).
Für den fachlichen Ausbau siehe docs/PLUGIN_ENTWICKLUNG.md.
"""
from ...core.declarative import DeclarativeModule
from ...core.forms import FieldSpec as F


class ImpactModule(DeclarativeModule):
    key = "impact"
    slug = "schlagzaehigkeit"
    name = "Schlagzähigkeit"
    version = "0.1.0"
    description = "Charpy/Izod (ZwickRoell HIT 5.5)."
    category = "Mechanische Prüfung"
    maturity = "Grundgerüst"
    default_enabled = False
    record_label = "Datensatz"
    departments = ('Mechanische Prüfung',)
    fields = (
        F("method", "Verfahren", kind="select", options=('Charpy ungekerbt', 'Charpy gekerbt', 'Izod gekerbt')),
        F("pendulum", "Pendel", kind="text", unit="J"),
        F("temperature", "Prüftemperatur", kind="float", unit="°C"),
        F("impact_strength", "Schlagzähigkeit (Mittel)", kind="float", unit="kJ/m²"),
        F("break_type", "Bruchart", kind="select", options=('C – vollständig', 'H – Scharnier', 'P – partiell', 'N – kein Bruch')),
        F("n", "Anzahl", kind="int"),
        F("notes", "Bemerkungen", kind="textarea", width="full"),
    )


MODULE = ImpactModule()
