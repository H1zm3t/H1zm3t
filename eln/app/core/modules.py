"""Plugin-Schnittstelle für Fachmodule.

Ein Fachmodul ist ein Python-Paket unter ``app/modules/<schluessel>/`` mit einer
Datei ``module.py``, die ein Objekt ``MODULE`` (Unterklasse von ``ModuleBase``)
bereitstellt. Module werden beim Start automatisch gefunden und registriert.
Ob ein Modul aktiv ist, wird in der Tabelle ``module_states`` gespeichert und
in der Modulverwaltung geändert.

Ausführliche Anleitung: docs/PLUGIN_ENTWICKLUNG.md
"""
from __future__ import annotations

import importlib
import logging
import pkgutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:  # pragma: no cover
    from fastapi import APIRouter
    from sqlalchemy.orm import Session

    from ..models import Experiment, User
    from .forms import FieldSpec

log = logging.getLogger("eln.modules")

# Kern-Datensätze, mit denen ein Modul verbunden sein kann
CORE_LINK_TARGETS = ("order", "experiment", "sample", "material", "device", "user")


@dataclass
class NavEntry:
    label: str
    url: str
    icon: str = "module"
    permission: str = "view"


@dataclass
class ExperimentPanel:
    """Abschnitt, den ein Modul auf der Versuchsseite einblendet."""

    title: str
    template: str
    context: Callable[["Session", "Experiment", "User"], dict]


@dataclass
class DossierSection:
    """Tabellarischer Abschnitt für Versuchsdossier (PDF/JSON/Excel)."""

    title: str
    headers: list[str]
    rows: list[list[Any]]
    note: str | None = None


@dataclass
class SearchHit:
    entity_type: str
    entity_id: int
    code: str
    title: str
    url: str
    snippet: str = ""
    status: str | None = None
    date: Any = None
    type_label: str = ""


@dataclass
class AnalysisDataset:
    """Datenquelle für die allgemeine Auswertung."""

    key: str
    label: str
    fields: dict[str, str]  # feldname -> Bezeichnung
    numeric_fields: list[str]
    loader: Callable[["Session", "User"], list[dict]]
    date_field: str | None = None


class ModuleBase:
    key: str = ""
    name: str = ""
    version: str = "0.1.0"
    description: str = ""
    category: str = "Fachmodul"
    maturity: str = "Grundgerüst"  # produktiv | Beispiel | Grundgerüst
    default_enabled: bool = False
    icon: str = "module"
    links_to: tuple[str, ...] = ("order", "experiment", "sample", "device", "user")
    # Fachbereich(e) der Versuche, für die das Modul vorgesehen ist
    departments: tuple[str, ...] = ()

    # --- Erweiterungspunkte (alle optional) ---------------------------------
    def models(self) -> list[type]:
        """Eigene SQLAlchemy-Modelle (werden für Migrationen importiert)."""
        return []

    def router(self) -> "APIRouter | None":
        return None

    def templates_dir(self) -> Path | None:
        return None

    def nav_entries(self) -> list[NavEntry]:
        return []

    def experiment_panels(self) -> list[ExperimentPanel]:
        return []

    def dossier_sections(self, db: "Session", experiment: "Experiment") -> list[DossierSection]:
        return []

    def search(self, db: "Session", term: str, user: "User") -> list[SearchHit]:
        return []

    def analysis_datasets(self) -> list[AnalysisDataset]:
        return []

    def import_handlers(self) -> dict[str, Callable]:
        """Importfunktionen für die Importseite.

        Rückgabe: {Bezeichnung: funktion(db, actor, rows, commit) -> services.importer.ImportReport}.
        Bei ``commit=False`` nur prüfen. Erscheinen unter Import als »Modul: Bezeichnung«.
        """
        return {}

    def default_config(self) -> dict:
        return {}

    def on_enable(self, db: "Session") -> None:
        """Wird beim Aktivieren aufgerufen."""

    def on_disable(self, db: "Session") -> None:
        """Wird beim Deaktivieren aufgerufen."""

    def info(self) -> dict:
        return {
            "key": self.key,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "category": self.category,
            "maturity": self.maturity,
            "links_to": self.links_to,
        }


class ModuleRegistry:
    def __init__(self) -> None:
        self._modules: dict[str, ModuleBase] = {}
        self._enabled_cache: set[str] | None = None

    def register(self, module: ModuleBase) -> None:
        if not module.key or not module.key.isidentifier():
            raise ValueError(f"Ungültiger Modulschlüssel: {module.key!r}")
        if module.key in self._modules:
            raise ValueError(f"Modul {module.key!r} ist bereits registriert")
        self._modules[module.key] = module

    def discover(self, package: str = "app.modules") -> None:
        pkg = importlib.import_module(package)
        for info in pkgutil.iter_modules(pkg.__path__):
            if not info.ispkg or info.name.startswith("_"):
                continue
            if info.name in self._modules:
                continue
            try:
                mod = importlib.import_module(f"{package}.{info.name}.module")
            except ModuleNotFoundError as exc:
                log.warning("Modulpaket %s ohne module.py übersprungen: %s", info.name, exc)
                continue
            module_obj = getattr(mod, "MODULE", None)
            if isinstance(module_obj, ModuleBase):
                self.register(module_obj)
            else:
                log.warning("Modulpaket %s stellt kein MODULE-Objekt bereit", info.name)

    def all(self) -> list[ModuleBase]:
        return sorted(self._modules.values(), key=lambda m: (m.maturity != "produktiv", m.name))

    def get(self, key: str) -> ModuleBase | None:
        return self._modules.get(key)

    # --- Aktivierung ---------------------------------------------------------
    def invalidate(self) -> None:
        self._enabled_cache = None

    def enabled_keys(self, db: "Session") -> set[str]:
        if self._enabled_cache is None:
            from ..models import ModuleState

            states = {s.key: s.enabled for s in db.query(ModuleState).all()}
            self._enabled_cache = {
                k for k, m in self._modules.items() if states.get(k, m.default_enabled)
            }
        return self._enabled_cache

    def enabled(self, db: "Session") -> list[ModuleBase]:
        keys = self.enabled_keys(db)
        return [m for m in self.all() if m.key in keys]

    def is_enabled(self, db: "Session", key: str) -> bool:
        return key in self.enabled_keys(db)

    def sync_states(self, db: "Session") -> None:
        """Legt für neu gefundene Module einen Eintrag an."""
        import json

        from ..models import ModuleState

        for m in self._modules.values():
            st = db.get(ModuleState, m.key)
            if st is None:
                db.add(
                    ModuleState(
                        key=m.key,
                        enabled=m.default_enabled,
                        installed_version=m.version,
                        config_json=json.dumps(m.default_config(), ensure_ascii=False),
                    )
                )
            elif st.installed_version != m.version:
                st.installed_version = m.version
        db.flush()
        self.invalidate()


registry = ModuleRegistry()


def get_registry() -> ModuleRegistry:
    if not registry._modules:
        registry.discover()
    return registry
