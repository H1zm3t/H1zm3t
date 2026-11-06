# Architektur (Phase 1)

## 1. Leitlinien

- **Einfach, robust, transparent:** serverseitig gerenderte Seiten (FastAPI + Jinja2), etwas JavaScript für Tabellen,
  Diagramme, Uploads und dynamische Zeilen. Kein SPA-Framework, kein Build-Schritt.
- **Offline-fähig:** alle Bibliotheken lokal (`app/static/vendor`), keine Cloud-Dienste.
- **Datenbankneutral:** ausschließlich SQLAlchemy-ORM/Ausdrücke, Migrationen mit Alembic; SQLite lokal,
  PostgreSQL/SQL Server später über `ELN_DATABASE_URL`.
- **Stabiler Kern + Fachmodule:** Module erweitern den Kern über eine dokumentierte Schnittstelle, ohne ihn zu ändern.
- **Nachvollziehbarkeit vor Bequemlichkeit:** jede schreibende Aktion läuft über einen Service, der den Audit Trail
  schreibt; Kern-Datensätze werden nie physisch gelöscht.

## 2. Schichten

| Schicht | Ort | Aufgabe |
|---|---|---|
| Konfiguration | `app/config.py`, `.env` | Pfade, Netzwerk, Sicherheitsparameter |
| Datenbankzugriff | `app/db.py` | Engine, Sitzungen, Transaktionen, SQLite-Pragmas (WAL, Fremdschlüssel) |
| Datenmodelle | `app/models/` | SQLAlchemy-Modelle des Kerns |
| Kernbausteine | `app/core/` | Passwort-Hashing, Rechte, Formate, deklarative Formulare/Validierung (Pydantic), Plugin-Schnittstelle |
| Geschäftslogik | `app/services/` | Anlegen/Ändern mit Audit, Workflow, Rezepturen, Dateien, Suche, Auswertung, Export/PDF, Import, Sicherung |
| Routen | `app/web/` | HTML-Seiten und JSON-API; Rechteprüfung, CSRF, Sitzung |
| Oberfläche | `app/templates/`, `app/static/` | Jinja2, CSS (Hell/Dunkel), JavaScript |
| Fachmodule | `app/modules/<key>/` | eigene Modelle, Routen, Templates, Auswertungen, Dossierabschnitte |
| Dateiablage | `<ELN_FILES_DIR>/JJJJ/MM/<uuid>.<ext>` | Anhänge (nicht in der Datenbank) |
| Protokollierung | `data/logs/eln.log`, `fehler.log` | technisches Protokoll (getrennt vom Audit Trail) |
| Migrationen | `migrations/` | Alembic, automatische Sicherung vor jeder Migration |
| Tests | `tests/` | pytest |

### Anfragefluss
Browser → FastAPI-Route (`web/*`) → `get_ctx` (Sitzung prüfen, Sitzungsablauf, CSRF bei POST) →
`ctx.require(recht)` → Service (`services/*`, schreibt Audit-Einträge in derselben Transaktion) →
Commit → Weiterleitung mit Toast-Nachricht bzw. Template-Rendering.

### Generische Datensatzseiten
`services/entities.py` beschreibt jeden Kern-Datensatztyp deklarativ (Felder als `FieldSpec`, Listenspalten, URL,
Rechte, Archivstatus). `web/records.py` erzeugt daraus Liste, Detailseite, Formular, Statuswechsel und Export.
Spezielle Logik (Prozessparameter, Messwerte, Workflow) wird über *Hooks* ergänzt (`web/experiments.py`,
`web/detail_hooks.py`). Dieselben `FieldSpec` erzeugen dynamisch Pydantic-Modelle zur Validierung von Formularen
und Importzeilen – mit deutschen Fehlermeldungen.

## 3. Annahmen

1. Ein Standort, eine Zeitzone; Zeitstempel werden als lokale Zeit ohne Zeitzone gespeichert.
2. Erste Version: ein Rechner, wenige gleichzeitige Benutzer im lokalen Browser; Mehrbenutzerbetrieb im Netz erst
   nach Umstieg auf PostgreSQL/SQL Server (siehe MEHRBENUTZERBETRIEB.md).
3. Auftragsnummern aus dem Access-System werden als „externe Auftragsnummer“ gespeichert; Austausch über CSV/JSON.
4. Vertraulichkeit „streng vertraulich“ schränkt die Sichtbarkeit von Aufträgen (und deren Versuchen, Proben,
   Messdaten, Rezepturen) auf Verantwortliche, Beteiligte, Ersteller, Abteilungsleitung und Administration ein.
   Die übrigen Stufen sind Kennzeichnungen.
5. Rezepturanteile beziehen sich auf Gewichtsprozent; Mengen in mg/g/kg/t werden für Berechnungen umgerechnet.
6. Ein Änderungsgrund ist Pflicht, sobald ein Datensatz nicht mehr in Bearbeitung ist (Versuche ab „abgeschlossen“
   oder ab Revision 2, Rezepturen ab „gültig“, Stammdaten immer); per Einstellung abschaltbar.
7. Die Prüfung „zur Prüfung → freigegeben“ erfolgt durch einen Prüfer; optional zweite Freigabe durch die Leitung.
8. Passwörter: PBKDF2-HMAC-SHA256 mit 600 000 Iterationen (Python-Standardbibliothek, keine Kompilierung unter
   Windows nötig).
9. Dateigrenze 100 MB je Datei (konfigurierbar).

## 4. Datenmodell (Kern)

```
users ─< user_roles >─ roles(permissions_json)
user_sessions (token_hash, csrf_token, last_seen, flash)

projects ─< orders ─< experiments >─ experiment_series
                 │         ├─ recipe → recipes ─< recipe_items → materials, batches
                 │         ├─ method → methods >─< devices (device_methods)
                 │         ├─< experiment_devices / _materials / _batches / _used_samples / _participants
                 │         └─< samples (parent_id → samples, Hierarchie) ─< measurements ─< measurement_values
                 └─< order_participants
materials ─< batches

attachments (entity_type, entity_id, sha256, storage_path, version, previous_id, status, extracted_text)
comments, tasks (optional entity_type/entity_id)
audit_log (hash-verkettet, Trigger gegen UPDATE/DELETE)
approval_records (Schritt, Entscheidung, Person, Snapshot) ─ record_snapshots (JSON + SHA-256)
entity_links (allgemeine, modulübergreifende Verknüpfungen)
system_settings, counters (Nummernkreise), saved_queries, backup_records
module_states (aktiv, Version, Konfiguration), module_records (Daten deklarativer Module als JSON)

Modul Compoundierung: mod_compounding_runs ─< mod_compounding_zones / _feeders / _readings
Modul MVR:            mod_mvr_tests
```

Alle Stammdaten tragen `created_at/by`, `updated_at/by` und einen Versionszähler.
Kennungen: `P-JJJJ-001` Projekt, `A-JJJJ-0001` Auftrag, `VR-…` Versuchsreihe, `V-…` Versuch, `R-00001` Rezeptur
(+Revision), `M-00001` Material, `CH-00001` Charge, `S-JJJJ-00001` Probe, `G-001` Gerät, `PM-001` Methode,
`D-JJJJ-00001` Messdatensatz, `T-…` Aufgabe, `C-JJJJ-0001` Compoundierlauf.

## 5. Sicherheit (Überblick)

- Sitzungstoken (zufällig, nur Hash gespeichert), HttpOnly-/SameSite-Cookie, Sitzungsablauf bei Inaktivität.
- CSRF-Token je Sitzung für alle schreibenden Anfragen (Formularfeld oder Header `X-CSRF-Token`).
- Sperre nach Fehlversuchen; alle Anmeldungen, Sperren, CSRF-Fehler im Audit Trail (`entity_type = security`).
- Rollenbasierte Rechte serverseitig in jeder Route; Vier-Augen-Prinzip im Workflow.
- Jinja2-Autoescaping, Content-Security-Policy ohne Inline-Skripte, `X-Frame-Options`, `nosniff`.
- Keine SQL-Zeichenketten aus Benutzereingaben; LIKE-Platzhalter werden maskiert.
- Uploads: Positivliste der Endungen, Sperrliste ausführbarer Typen (auch Doppelendungen), Signaturprüfung (MZ/ELF),
  Größenlimit, UUID-Dateinamen, Pfadprüfung, keine Ausführung hochgeladener Dateien.
- Keine Zugangsdaten im Quellcode; erster Administrator und Demo-Passwort werden bei der Einrichtung abgefragt.

## 6. Risiken und Gegenmaßnahmen

| Risiko | Gegenmaßnahme |
|---|---|
| SQLite bei parallelem Netzzugriff (Sperren, Beschädigung auf Netzlaufwerken) | lokal betreiben; für Mehrbenutzerbetrieb PostgreSQL/SQL Server (vorbereitet) |
| Datenverlust durch Hardwaredefekt | ZIP-Sicherungen mit Prüfung, Ziel auf anderem Laufwerk, Aufgabenplanung |
| Manipulation direkt in der Datenbankdatei | Hash-Kette + Trigger; Prüfung in *System* und `manage.py verify-audit`; Dateirechte des Datenordners einschränken |
| Fehlbedienung / unbemerkte Änderungen nach Freigabe | Sperre, Revisionen, Snapshots, Pflicht-Änderungsgrund |
| Wachsende Datenmengen (Suche über LIKE) | Suchservice gekapselt; Umstieg auf FTS5/tsvector ohne Oberflächenänderung |
| Regulatorische Erwartungen (GxP) | Dokumentierte Grenzen, Validierung separat erforderlich (DATENINTEGRITAET.md) |
| Abhängigkeit von Python-Umgebung | gepinnte Mindestversionen, virtuelle Umgebung, setup.bat |
