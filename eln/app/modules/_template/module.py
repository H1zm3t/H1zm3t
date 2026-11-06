"""Vorlage für ein neues Fachmodul »Beispielmodul«.

Erzeugen:   python manage.py new-module <schluessel>
Danach:     Anwendung neu starten → Administration → Module → aktivieren.

Diese Vorlage ist sofort lauffähig (eigene Seite, Versuchspanel, Suche,
Dossierabschnitt) und benötigt keine eigene Tabelle. Für eigene Tabellen:
  1. models.py anlegen (siehe app/modules/mvr/models.py), Tabellennamen mit "mod_" beginnen
  2. models() unten zurückgeben lassen
  3. Migration erzeugen:  alembic revision --autogenerate -m "Modul beispielmodul"
     (die Anwendung sichert die Datenbank vor jeder Migration automatisch)
Ausführliche Beschreibung: docs/PLUGIN_ENTWICKLUNG.md
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends

from ...core.modules import DossierSection, ExperimentPanel, ModuleBase, NavEntry

BASE_URL = "/module/beispielmodul"


def build_router() -> APIRouter:
    # Importe innerhalb der Funktion vermeiden Zirkelbezüge beim Start
    from ...models import Experiment
    from ...web.deps import Ctx, get_ctx

    router = APIRouter(prefix=BASE_URL)

    @router.get("")
    def overview(ctx: Ctx = Depends(get_ctx)):
        ctx.require("view")
        experiments = ctx.db.query(Experiment).order_by(Experiment.id.desc()).limit(20).all()
        return ctx.render("beispielmodul/overview.html", experiments=experiments)

    return router


def _panel(db, experiment, user) -> dict:
    """Daten für den Abschnitt auf der Versuchsseite."""
    return {"experiment": experiment, "hinweis": f"Beispielmodul ist mit {experiment.code} verbunden."}


class BeispielmodulModule(ModuleBase):
    key = "beispielmodul"
    name = "Beispielmodul"
    version = "0.1.0"
    description = "Vorlage für neue Fachmodule."
    category = "Vorlage"
    maturity = "Grundgerüst"
    default_enabled = False
    links_to = ("order", "experiment", "sample", "device", "user")
    departments = ()  # leer = auf allen Versuchen anzeigen

    def router(self):
        return build_router()

    def templates_dir(self):
        return Path(__file__).parent / "templates"

    def nav_entries(self):
        return [NavEntry(self.name, BASE_URL)]

    def experiment_panels(self):
        return [ExperimentPanel(self.name, "beispielmodul/panel.html", _panel)]

    def dossier_sections(self, db, experiment):
        return [DossierSection(f"{self.name}", ["Feld", "Wert"], [["Versuch", experiment.code]])]


MODULE = BeispielmodulModule()
