# Entwicklungsprotokoll Version 1.0.0

## Phase 1 – Architektur
- Architektur, Verzeichnisstruktur, Datenmodell, Annahmen und Risiken: siehe [ARCHITEKTUR.md](ARCHITEKTUR.md).
- Frontend-Bibliotheken lokal eingebunden: Chart.js 4.4.1, Tabulator 6.2.5 (MIT).

## Phase 2 – Grundgerüst
- Konfiguration (`.env`), SQLAlchemy-Anbindung (SQLite mit WAL, Fremdschlüssel), Alembic-Migration `0001` inkl.
  Audit-Trigger, automatische Sicherung vor Migrationen.
- Anmeldung mit PBKDF2-Passwörtern, serverseitigen Sitzungen, Sitzungsablauf, Kontosperre, CSRF-Schutz,
  Sicherheitsheadern (CSP ohne Inline-Skripte), Fehlerseiten und technischem Fehlerprotokoll.
- Rollen und Rechte (6 Standardrollen, 15 Rechte, mehrere Rollen je Benutzer, Rechte-Matrix).
- `manage.py` (init, migrate, create-admin, seed-demo, run, stop, backup, verify-backup, restore, verify-audit, new-module),
  `setup.bat`, `start.bat`, `stop.bat`, `backup.bat`, `restore.bat`.

## Phase 3 – ELN-Kern
- Generische, deklarative Datensatzseiten für Projekte, Aufträge, Versuchsreihen, Versuche, Rezepturen, Materialien,
  Chargen, Proben, Geräte, Methoden, Messdaten, Aufgaben (Liste mit Tabulator, Detail, Formular, Status, Export).
- Workflow mit Prüfung, Zurückweisung, zweiter Freigabe, Sperre, Revisionen, Snapshots.
- Rezepturen (Summenprüfung, Berechnung, Skalierung, Kopie, Revision, Vergleich, Import/Export).
- Dateiablage mit SHA-256, Versionen, Duplikaterkennung, Sperrliste, Signaturprüfung, Textextraktion, Galerie, Vorschau.
- Audit Trail mit Hash-Kette, Filteransicht, Export, Integritätsprüfung.

## Phase 4 – Compoundierung, Suche, Auswertungen
- Plugin-Schnittstelle (`core/modules.py`), deklarative Module (`core/declarative.py`), Modulvorlage `_template`.
- Compoundierungsmodul mit eigenen Tabellen, dynamischen Zonen, Dosierung, Prozessverlauf, Diagrammen, Vergleich,
  Probenanlage, Dossier, Suche, Auswertung, Modulkonfiguration (Zonenvorlagen).
- Beispielmodul MVR/MFR mit eigenem Datenmodell und eigener Importfunktion; 13 Grundgerüste.
- Zentrale Suche mit Filtern, Anhangsinhalt, gespeicherten Suchen; allgemeine Auswertungen mit Vorlagen.

## Phase 5 – Export, Berichte, Sicherung, Tests
- CSV/JSON/Excel-Export, Importe mit Prüflauf und Validierungsbericht, Importvorlagen.
- Versuchs- und Auftragsdossier (PDF via ReportLab, JSON, Excel, ZIP mit Anhängen und Prüfsummen).
- Datensicherung (ZIP, Manifest, Prüfung, Protokoll) und Wiederherstellung (Oberfläche und Konsole).
- 74 pytest-Tests (inzwischen 81).

## Phase 6 – Gesamtprüfung
- Automatischer Durchlauf aller verlinkten Seiten (325 Seiten) als Administrator ohne Fehler, alle Exporte/Dossiers
  geprüft; Browsertest mit Chromium (keine JavaScript- oder CSP-Fehler); gefundene Fehler behoben
  (Excel-Blattnamen, Metadaten-Schreibweise beim Import, Darstellung mehrzeiliger Texte).
- README und Abnahme-Checkliste vervollständigt.

## Erweiterung 1.1 – Auftragsplanung und Compoundierplan-Import
- Neue Tabellen `order_activities`, `order_materials`, `order_log_entries`; neue Auftragsfelder (Anfrage am,
  Ansprechperson, Cluster, Bemerkungen, Prüfvermerk); `recipes.recipe_type`; `recipe_items.source_recipe_id`
  (Komponente ist selbst eine Rezeptur); `mod_compounding_runs.protocol_json`. Migration `0002` (mit automatischer
  Sicherung vorher, an einer bestehenden Datenbank getestet).
- `services/awt_import.py`: Excel-Leser, der Zellen über ihre Beschriftungen findet; Vorschau und Übernahme in einer
  Transaktion; wiederholbar (Zuordnung über AWT-Nummer).
- `services/planning.py`, `web/planning.py`: Arbeitsplan, Fortschritt, Status je Kategorie, Rohstoffliste,
  Durchführung, Zusammensetzungsmatrix und aufgelöste Zusammensetzung; alles auch ohne Excel direkt erfassbar.
- Auftragsdossier (PDF/JSON) um Arbeitsplan, Rohstoffliste, Durchführung und Zusammensetzungen erweitert.
- Regeln des Imports: Vorlagenspalten am Ende der Rezepturblätter (nur Trägermaterial 100 %, ohne Bemerkung)
  werden ignoriert; ausgeblendete Blätter werden nicht gelesen; der Reiter »Gesamtstatus« wird berechnet statt
  gelesen; fehlende Materialien und Chargen werden als Stammdaten angelegt; manuell im ELN ergänzte
  Durchführungseinträge bleiben bei einem erneuten Import erhalten, Tätigkeiten und Rohstoffliste werden ersetzt.

## Bekannte Einschränkungen (Version 1.0.0)
- Mehrbenutzerbetrieb im Netz erst nach Umstieg auf PostgreSQL/SQL Server bzw. mit einem zentralen ELN-Server (siehe
  MEHRBENUTZERBETRIEB.md); integrierte Sicherung nur für SQLite.
- Suche über LIKE-Abfragen (für einige zehntausend Datensätze ausreichend); Volltextindex ist vorbereitet, nicht aktiv.
  Gescannte PDFs (Bilder) werden nicht per OCR erfasst.
- Grundgerüst-Module speichern Fachdaten als JSON; spezifische Gerätedatei-Importe (testXpert, NETZSCH, Malvern) sind
  noch nicht implementiert.
- Boxplot wird aus schwebenden Balken dargestellt (keine zusätzliche Bibliothek); Ausreißer werden nicht separat markiert.
- Datumsfelder nutzen die Browser-Datumsauswahl; die Anzeige TT.MM.JJJJ setzt eine deutsche Spracheinstellung von
  Windows/Edge voraus (die Verarbeitung akzeptiert TT.MM.JJJJ und JJJJ-MM-TT).
- Elektronische Prüf-/Freigabevermerke sind keine qualifizierten elektronischen Signaturen; keine erneute
  Passwortabfrage bei der Freigabe.
- Keine E-Mail-Benachrichtigungen.
- Zeitstempel ohne Zeitzone (ein Standort).
