# Fachmodule entwickeln (Plugin-Schnittstelle)

Fachmodule erweitern den ELN-Kern, ohne ihn umzubauen. Jedes Modul ist ein Python-Paket unter
`app/modules/<schluessel>/` mit einer Datei `module.py`, die ein Objekt `MODULE` bereitstellt. Beim Start werden alle
Pakete automatisch gefunden (`core/modules.py → ModuleRegistry.discover`), in `module_states` eingetragen und können
unter *Administration → Module* aktiviert bzw. deaktiviert werden. Deaktivierte Module sind nicht erreichbar
(Routen liefern 404), erscheinen nicht in Navigation, Suche, Auswertung und Versuchsseite; ihre Daten bleiben erhalten.

## 1. Drei Reifegrade

| Art | Beispiel | Wann |
|---|---|---|
| **Deklaratives Modul** | `tensile`, `dsc`, … (13 Grundgerüste) | Strukturierte Erfassung einiger Felder genügt. Nur `fields` definieren – Liste, Formular, Detailseite, Anhänge, Audit Trail, Versuchspanel, Suche und Auswertung kommen aus `core/declarative.py`. Daten in `module_records` (JSON). |
| **Modul mit eigener Logik** | `_template` | Eigene Seiten/Berechnungen ohne eigene Tabellen. |
| **Vollständiges Modul** | `mvr` (klein), `compounding` (groß) | Eigene Tabellen, Masken, Validierung, Auswertungen, Importe, Dossierabschnitte. |

## 2. Neues Modul anlegen (Schritt für Schritt)

```bat
.venv\Scripts\python.exe manage.py new-module schmelzindex
```
1. Es entsteht `app/modules/schmelzindex/` aus der Vorlage `_template` (lauffähig: Übersichtsseite, Versuchspanel,
   Dossierabschnitt).
2. `module.py` anpassen: `name`, `description`, `departments` (Fachbereiche, auf deren Versuchen das Panel erscheint).
3. Anwendung neu starten → *Administration → Module* → **Aktivieren**.

### Eigene Tabellen ergänzen
1. `models.py` anlegen (Tabellenname mit Präfix `mod_`, Basisklasse `Base`, für Stammdatenfelder `TrackedMixin`).
   Verknüpfung zum Kern über Fremdschlüssel (`experiments.id`, `samples.id`, `devices.id`, `materials.id`, `users.id`,
   `orders.id`) oder über die allgemeine Tabelle `entity_links`.
2. In `module.py` `def models(self): return [MeineTabelle]`.
3. Migration erzeugen und prüfen:
   ```bat
   .venv\Scripts\python.exe -m alembic revision --autogenerate -m "Modul schmelzindex"
   ```
   Die Datei unter `migrations/versions/` kontrollieren. Beim nächsten Start (oder `manage.py migrate`) wird die
   Datenbank **nach einer automatischen Sicherung** migriert.

## 3. Erweiterungspunkte (`ModuleBase`)

| Methode/Attribut | Zweck |
|---|---|
| `key`, `name`, `version`, `description`, `category`, `maturity`, `default_enabled` | Metadaten für die Modulverwaltung |
| `links_to` | dokumentiert, mit welchen Kern-Datensätzen das Modul verbunden ist |
| `departments` | Fachbereiche, für die das Versuchspanel angezeigt wird (leer = alle) |
| `models()` | eigene SQLAlchemy-Modelle (für Migrationen) |
| `router()` | FastAPI-Router (Präfix `/module/<name>`); wird automatisch mit Aktivierungsprüfung eingebunden |
| `templates_dir()` | eigener Template-Ordner (Unterordner = Modulname, um Namenskonflikte zu vermeiden) |
| `nav_entries()` | Einträge in der Seitennavigation |
| `experiment_panels()` | Abschnitte auf der Versuchsseite (`ExperimentPanel(title, template, context_func)`) |
| `dossier_sections(db, experiment)` | Tabellen für Versuchsdossier PDF/JSON/Excel |
| `search(db, term, user)` | Treffer für die zentrale Suche (`SearchHit`) |
| `analysis_datasets()` | Datenquellen für die allgemeine Auswertung (`AnalysisDataset`) |
| `import_handlers()` | Importfunktionen `(db, rows, user) -> (anzahl, fehler)` |
| `default_config()` | Startkonfiguration (gespeichert in `module_states.config_json`, Teil der Sicherung) |
| `on_enable(db)`, `on_disable(db)` | Aktionen beim (De-)Aktivieren |
| `get_entity(db, type, id)`, `entity_url(type, id)` | Auflösung eigener Datensatztypen für Anhänge, Audit Trail, Aufgaben |

## 4. Regeln für Module

- **Schreibende Aktionen immer mit Audit Trail:** `services.audit.log(db, ctx.actor, aktion, entity_type=…, entity=…,
  field=…, old=…, new=…, reason=…)`.
- **Sperre respektieren:** Daten zu einem gesperrten Versuch (`experiment.locked`) nicht ändern
  (siehe `compounding/service.check_editable`).
- **Rechte prüfen:** `ctx.require("create")`, `ctx.require("edit")` usw. in jeder Route.
- **Sichtbarkeit:** vertrauliche Aufträge über `services.entities.can_see` / `restricted_order_ids` berücksichtigen.
- **Formulare:** `core/forms.FieldSpec` + `validate_values` (Pydantic) für Validierung mit deutschen Meldungen;
  CSRF-Feld `{{ csrf() }}` aus `partials/macros.html`.
- **Anhänge:** `{% include "partials/panels.html" %}` mit `related_panels(ctx, "<entity_type>", obj)` liefert Upload,
  Galerie, Kommentare, Aufgaben und Historie ohne eigenen Code.
- **Kein Inline-JavaScript** (Content-Security-Policy). Daten über `<script type="application/json">` übergeben,
  Logik in `app/static/js/app.js` oder einer eigenen statischen Datei.
- **Nummernkreis:** `services.numbering.next_code(db, "<key>", prefix="XYZ")`.

## 5. Beispiel: Grundgerüst zum vollständigen Modul ausbauen

1. `fields` des deklarativen Moduls in ein SQLAlchemy-Modell überführen (`models.py`).
2. Routen nach dem Muster `mvr/module.py` (klein) oder `compounding/routes.py` (groß) schreiben.
3. Datenübernahme aus `module_records` (Spalte `data_json`) in die neue Tabelle als Alembic-Datenmigration.
4. Basisklasse von `DeclarativeModule` auf `ModuleBase` ändern.

## 6. Geplante Fachmodule (Grundgerüste vorhanden)

Spritzguss (`injection_molding`), Zugprüfung (`tensile`), Schlagzähigkeit (`impact`), MVR/MFR (`mvr`, Beispiel),
Hochdruckkapillarrheometrie (`capillary_rheometry`), DSC (`dsc`), TGA (`tga`), Partikelgrößenverteilung
(`particle_size`), thermische Alterung (`thermal_aging`), Klimaschrank (`climate_chamber`), Autoklav (`autoclave`),
Rohstoffprüfung (`raw_material_testing`), Musterverwaltung (`sample_management`), Berichtserstellung (`reporting`).

Sinnvolle nächste Ausbaustufen: Geräte-Importfilter (ZwickRoell testXpert-Export, NETZSCH ASCII, Malvern CSV) als
`import_handlers`, die Messwerte direkt als `Measurement` mit Metadaten anlegen; Alterungsmodul mit
Entnahmeplan, das automatisch Unterproben und Aufgaben erzeugt.
