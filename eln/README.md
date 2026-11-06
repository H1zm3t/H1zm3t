# ELN Anwendungstechnik – Elektronisches Laborbuch

Lokal lauffähiges, modular erweiterbares elektronisches Laborbuch für die Anwendungstechnik (F&E) eines Chemieunternehmens:
Aufträge, Versuche, Rezepturen, Materialien/Chargen, Proben, Geräte, Anhänge, Audit Trail, Prüf- und Freigabeprozess,
Suche, Auswertungen, Berichte, Datensicherung – mit dem Fachmodul **Compoundierung** und Grundgerüsten für 13 weitere Module.

| | |
|---|---|
| Version | 1.0.0 |
| Technik | Python 3.10+ · FastAPI · SQLAlchemy 2 · Alembic · Pydantic 2 · Jinja2 · SQLite · Chart.js · Tabulator · ReportLab · openpyxl |
| Betrieb | lokal auf einem Windows-PC, Bedienung in Microsoft Edge unter `http://127.0.0.1:8000` |
| Sprache | Oberfläche vollständig Deutsch, Datum TT.MM.JJJJ, Zeit HH:MM, Dezimalkomma |

> **Wichtiger Hinweis zur Regulatorik:** Die Anwendung unterstützt die ALCOA+-Grundsätze (Audit Trail mit Hash-Kette,
> Änderungsgründe, elektronische Prüf-/Freigabevermerke, Sperre freigegebener Stände, Prüfsummen). Sie ist dadurch
> **nicht automatisch** GxP-validiert, FDA-21-CFR-Part-11- oder EU-GMP-konform. Dafür wären eine formelle
> Validierung (z. B. nach GAMP 5), Risikobewertung, Verfahrensanweisungen, Schulungen und organisatorische Kontrollen
> separat erforderlich. Details: [docs/DATENINTEGRITAET.md](docs/DATENINTEGRITAET.md).

---

## Inhalt

1. [Funktionsumfang](#1-funktionsumfang)
2. [Voraussetzungen](#2-voraussetzungen)
3. [Installation unter Windows](#3-installation-unter-windows)
4. [Starten, Anmelden, Beenden](#4-starten-anmelden-beenden)
5. [Beispieldaten und Demo-Benutzer](#5-beispieldaten-und-demo-benutzer)
6. [Kurzanleitung zur Bedienung](#6-kurzanleitung-zur-bedienung)
7. [Datensicherung und Wiederherstellung](#7-datensicherung-und-wiederherstellung)
8. [Konfiguration](#8-konfiguration)
9. [Fehlerbehebung](#9-fehlerbehebung)
10. [Verzeichnisstruktur](#10-verzeichnisstruktur)
11. [Tests und Abnahme](#11-tests-und-abnahme)
12. [Weiterführende Dokumentation](#12-weiterführende-dokumentation)

---

## 1. Funktionsumfang

**ELN-Kern**
- **Dashboard** abhängig von Rolle und Benutzer: offene Aufträge, laufende Versuche, Prüf- und Freigabewarteschlange,
  eigene und überfällige Aufgaben, Geräte mit fälliger Kalibrierung/Wartung, zuletzt bearbeitete Datensätze, Diagramme.
- **Projekte, Aufträge, Versuchsreihen, Versuche** mit automatischer ID (z. B. `A-2026-0001`, `V-2026-0001`),
  Verantwortlichen/Beteiligten, Prioritäten, Vertraulichkeitsstufen, Schlagwörtern, Prozessparametern,
  Beobachtungen, Ergebnissen, Bewertung, Schlussfolgerung, Folgeaktivitäten.
- **Status- und Freigabeprozess**: Entwurf → in Bearbeitung → abgeschlossen → zur Prüfung → (geprüft →) freigegeben;
  Zurückweisung mit Begründung, optionale zweite Freigabe durch die Abteilungsleitung, unabhängige Prüfung (Vier-Augen),
  Sperre ab Einreichung, Änderungen nach Freigabe nur über **neue Revision** mit Änderungsgrund; eingefrorene Stände
  (Snapshots) mit SHA-256.
- **Rezepturen**: tabellarische Positionen (Material-ID, Materialnummer, Name, Handelsname, Lieferant, Charge,
  Funktion, Soll/Ist, Einheit, Gew.-%, Toleranz, Bemerkung), automatische Summenprüfung gegen 100 Gew.-% (live und
  serverseitig), Berechnung der Anteile aus Mengen, Skalieren, Kopieren, Revisionen, farbiger Vergleich, CSV/Excel-Import
  und -Export.
- **Materialien und Chargen** getrennt verwaltet (Mindesthaltbarkeit, Lagerort, Status, SDB/CoA als Anhang).
- **Proben** mit hierarchischen Beziehungen (Compound → Prüfkörper → gealterter Prüfkörper → Prüfung).
- **Geräte und Methoden** inkl. Wartungs-/Kalibrierterminen; Warnung (oder per Einstellung Sperre) bei gesperrten
  Geräten oder überfälliger Kalibrierung.
- **Messdaten** als numerische Datensätze mit Einheit, Bezugsgröße (z. B. Alterungszeit) und Metadaten.
- **Anhänge**: Drag-and-drop-Mehrfachupload, Bild-/PDF-Vorschau, Galerie mit Bildunterschriften, Versionen,
  SHA-256, Duplikaterkennung, Archivieren/Ungültig-Setzen, kontrollierte Löschung, Textextraktion für die Suche.
  Ausführbare Dateien (EXE, BAT, CMD, PS1 …) werden abgelehnt – auch getarnt (Signaturprüfung).
- **Audit Trail**: Benutzer, Zeit, Aktion, Datensatz, Feld, alter/neuer Wert, Grund, IP, Version, Ergebnis;
  Hash-Kette, Datenbank-Trigger gegen Änderung/Löschung, Integritätsprüfung, Filter und Export.
- **Benutzer und Rollen**: Administrator, Abteilungsleitung, Wissenschaftler/Ingenieur, Labormitarbeiter, Prüfer, Leser;
  mehrere Rollen pro Person; Rechte je Rolle in einer Matrix änderbar.
- **Suche** über alle Datensätze, Anhänge (Dateiname, Beschreibung, Inhalt von PDF/Word/Excel/Text) und Module;
  Filter (Typ, Status, Verantwortliche, Datum, Versuchsart, Fachbereich, Gerät, Material, Charge, Auftraggeber,
  Schlagwörter), Sortierung, Seiten, gespeicherte Suchen.
- **Auswertungen**: Datenquellen (Versuche, Aufgaben, Messwerte, Materialverwendung, Rezepturpositionen,
  Compoundierläufe, Moduldaten), Gruppierung, Kennzahlen (Anzahl, Mittelwert, Median, Min, Max, Standardabweichung),
  Balken-/Linien-/Punkt-/Boxplot-Diagramme, Vorlagen, speicherbare Konfigurationen, Export CSV/Excel.
- **Import/Export**: CSV, JSON, Excel; Importvorlagen; Prüflauf mit Validierungsbericht (Import ist „alles oder nichts“);
  Versuchs- und Auftragsdossier als PDF, JSON, Excel und ZIP (inkl. Anhänge und Prüfsummenliste).
- **Datensicherung**: ZIP mit Zeitstempel (Datenbank, Dateien, Konfiguration, Modulkonfiguration, Manifest mit
  Prüfsummen), Vollständigkeitsprüfung, Sicherungsprotokoll, automatische Sicherung vor Migrationen und vor
  Wiederherstellungen, Wiederherstellung nur durch Administratoren.

**Fachmodule** (Plugin-Schnittstelle, aktivierbar unter *Administration → Module*)
- **Compoundierung** (produktiv): Extruder, Rezeptur, Schneckenkonfiguration, Dosierstellen/-geräte, Soll-/Ist-Durchsatz,
  Drehzahl, Drehmoment, Massedruck, Schmelzetemperatur, **frei konfigurierbare Temperaturzonen**, Vakuum, Kühlung,
  Granulierung, Start/Ende, Beobachtungen, Störungen, Abweichungen, Probenahmen, erzeugte Proben, Fotos/Prozessdateien,
  Bewertung, Prozessverlauf mit Diagramm, Vergleich mehrerer Läufe.
- **MVR/MFR** (Beispielmodul mit eigenem Datenmodell): zeigt, wie ein Modul eigene Tabellen, Masken, Validierung und
  Auswertungen mitbringt.
- **Grundgerüste**: Spritzguss, Zugprüfung, Schlagzähigkeit, Hochdruckkapillarrheometrie, DSC, TGA,
  Partikelgrößenverteilung, thermische Alterung, Klimaschrank, Autoklav, Rohstoffprüfung, Musterverwaltung,
  Berichtserstellung – sofort nutzbar zur strukturierten Erfassung, fachlich ausbaufähig.

## 2. Voraussetzungen

- Windows 10 oder 11 (64 Bit), Microsoft Edge
- **Python 3.11, 3.12 oder 3.13** von <https://www.python.org/downloads/windows/>
  – bei der Installation **„Add python.exe to PATH“** anhaken.
- Für die Einrichtung einmalig Internetzugang (Python-Pakete von PyPI). Danach läuft die Anwendung vollständig offline;
  alle Frontend-Bibliotheken liegen lokal in `app/static/vendor` (MIT-Lizenz, Lizenzdateien beigefügt).
- Ca. 300 MB freier Speicher zuzüglich Daten.

## 3. Installation unter Windows

1. Ordner `eln` an einen festen Ort kopieren, z. B. `C:\ELN\eln` (nicht in „Downloads“ oder einen temporären Ordner).
2. **Empfohlen:** In `.env.example` bzw. nach der Einrichtung in `.env` die Datenpfade festlegen, z. B.
   ```
   ELN_DATA_DIR=C:\ELN-Daten
   ELN_BACKUP_DIR=D:\ELN-Sicherungen
   ```
   (Standard: `data` und `backups` im Programmordner.)
3. Doppelklick auf **`setup.bat`**. Das Skript
   - prüft die Python-Version,
   - legt die virtuelle Umgebung `.venv` an und installiert die Pakete aus `requirements.txt`,
   - erzeugt `.env` aus `.env.example` (falls nicht vorhanden),
   - richtet die Datenbank über die Migrationen ein,
   - fragt Benutzername, Namen und Passwort des **ersten Administrators** ab (mind. 10 Zeichen),
   - bietet an, **Beispieldaten** anzulegen.

Manuelle Installation (Eingabeaufforderung im Ordner `eln`):
```bat
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
.venv\Scripts\python.exe manage.py init
.venv\Scripts\python.exe manage.py seed-demo      (optional)
```

## 4. Starten, Anmelden, Beenden

1. Doppelklick auf **`start.bat`** – ein Konsolenfenster öffnet sich (bitte offen lassen).
2. Microsoft Edge öffnet automatisch `http://127.0.0.1:8000`.
3. Mit dem Administrator anmelden. Neue Benutzer unter *Benutzer & Rollen* anlegen; sie müssen ihr Startpasswort bei
   der ersten Anmeldung ändern.
4. Beenden: Konsolenfenster schließen, `Strg+C` drücken oder **`stop.bat`** ausführen.

Die Sitzung läuft nach 60 Minuten Inaktivität ab. Nach 5 Fehlversuchen wird ein Konto 15 Minuten gesperrt.

## 5. Beispieldaten und Demo-Benutzer

`manage.py seed-demo` (oder die Abfrage in `setup.bat`) legt an: 17 Geräte (Leistritz ZSE 27 MAXX, Demag, ZwickRoell
Z020/Z010/HIT 5.5/Mflow, Göttfert RG20, NETZSCH DSC/TGA, Malvern, Hosokawa-Mühle, Mixaco, Öfen, Klimaschrank,
Autoklav …), Prüfmethoden, 9 Materialien mit Chargen, 2 Aufträge, 3 Rezepturen, 4 Versuche in verschiedenen Status
(u. a. ein freigegebener Versuch), Compoundierläufe, eine Probenhierarchie mit Alterungsmessreihen und Aufgaben.

Demo-Benutzer (gemeinsames Passwort wird bei der Anlage abgefragt, es steht nicht im Quellcode):

| Benutzer | Rolle |
|---|---|
| `m.weber` | Abteilungsleitung |
| `s.keller` | Wissenschaftler/Ingenieur |
| `t.braun` | Labormitarbeiter |
| `a.schulz` | Prüfer + Wissenschaftler |
| `gast` | Leser |

Beispieldaten nur in einer Test- oder Schulungsinstallation anlegen.

## 6. Kurzanleitung zur Bedienung

- **Auftrag anlegen:** *+ Neu → Auftrag*. Pflichtfelder sind mit * markiert. Auf der Auftragsseite direkt Versuche,
  Proben, Rezepturen oder Versuchsreihen anlegen; Auftragsdossier als PDF/ZIP exportieren.
- **Versuch dokumentieren:** Versuch anlegen → *Bearbeitung starten* → Felder, Prozessparameter, Proben, Messdaten,
  Anhänge ergänzen → *Abschließen* (Ergebnisse und Schlussfolgerung sind Pflicht) → *Zur Prüfung einreichen*.
- **Prüfen/Freigeben:** Prüfer sehen eingereichte Versuche im Dashboard → *Prüfung bestanden* oder *Zurückweisen*
  (mit Begründung). Ist die zusätzliche Freigabe aktiviert, gibt die Abteilungsleitung anschließend frei.
- **Nach der Freigabe ändern:** *Neue Revision anlegen* mit Änderungsgrund. Der freigegebene Stand bleibt als
  Snapshot erhalten (Versuchsseite → *Eingefrorene Stände*).
- **Rezeptur:** Rezeptur anlegen → *Positionen bearbeiten* (Live-Summe) → optional *Gew.-% aus Sollmengen berechnen*.
  Skalieren auf der Rezepturseite; *Neue Revision* bzw. *Kopieren*; *Vergleichen* hebt Unterschiede farbig hervor.
- **Compoundierung:** Auf der Versuchsseite im Abschnitt *Compoundierung* → *+ Compoundierlauf*. Zonen über
  *Zonenvorlage laden* oder frei anlegen; Prozessverlauf als Messpunkte; erzeugtes Granulat als Probe anlegen.
- **Dateien:** Im Reiter *Anhänge* Dateien in das Feld ziehen. Bei identischem Inhalt erscheint ein Hinweis.
  Neue Version, Archivieren und Ungültig-Setzen auf der Anhangseite.
- **Suche:** Suchfeld oben oder *Suche* mit Filtern; Suchen speichern.
- **Auswertungen:** Vorlage wählen oder Datenquelle/Gruppierung/Kennzahl/Diagramm einstellen; Ergebnis als Excel/CSV.
- **Hell/Dunkel:** Mondsymbol oben rechts.

Datumsfelder zeigen in Edge das Format TT.MM.JJJJ (abhängig von der Windows-Spracheinstellung „Deutsch“).
Zahlen werden mit Dezimalkomma eingegeben (`12,5`); intern wird sprachunabhängig gespeichert.

## 7. Datensicherung und Wiederherstellung

**Sicherung erstellen** – eine der Möglichkeiten:
- *Administration → Datensicherung → Sicherung jetzt erstellen*
- Doppelklick auf `backup.bat`
- automatisch vor jeder Datenbankmigration und vor jeder Wiederherstellung

Das ZIP `eln_sicherung_JJJJMMTT_HHMMSS.zip` enthält `database/eln.db` (konsistente Kopie über die SQLite-Backup-API,
auch im laufenden Betrieb), `files/` (alle Anhänge), `config/.env`, `config/modules.json` (Module und
Systemeinstellungen) und `manifest.json` mit SHA-256 aller Dateien. Nach dem Schreiben wird das Archiv vollständig
geprüft (Prüfsummen, Integritätsprüfung der Datenbank). Jede Sicherung wird in `backup_log.jsonl` im Sicherungsordner
und in der Datenbank protokolliert.

**Empfehlung:** `ELN_BACKUP_DIR` auf ein anderes Laufwerk oder ein gesichertes Netzlaufwerk legen und die Sicherung
über die Windows-Aufgabenplanung täglich ausführen (Programm: `C:\ELN\eln\backup.bat`, Zeitplan: täglich 12:30).
Sicherungen regelmäßig testweise wiederherstellen.

**Wiederherstellung** (nur Administratoren):
- Über die Oberfläche: *Datensicherung → Prüfen → Wiederherstellen*, Bestätigung durch Eingabe von `WIEDERHERSTELLEN`.
  Alle Benutzer werden abgemeldet.
- Über die Konsole (empfohlen, wenn die Anwendung nicht startet):
  1. `stop.bat` ausführen bzw. Startfenster schließen.
  2. `restore.bat "D:\ELN-Sicherungen\eln_sicherung_20260101_120000.zip"`
  3. `WIEDERHERSTELLEN` eingeben, danach `start.bat`.

Vor der Wiederherstellung wird der aktuelle Stand automatisch gesichert (`…_vor-wiederherstellung.zip`).
Die `.env` wird nicht überschrieben (liegt nur als Kopie im Archiv).

## 8. Konfiguration

Datei `.env` im Programmordner (Vorlage `.env.example`); Umgebungsvariablen haben Vorrang. Wichtige Werte:

| Variable | Standard | Bedeutung |
|---|---|---|
| `ELN_DATA_DIR` | `data` | Datenbank, Dateiablage (`files`), Protokolle (`logs`) |
| `ELN_FILES_DIR` | `<DATA>/files` | eigener Ablageort für Anhänge |
| `ELN_BACKUP_DIR` | `backups` | Sicherungsziel (möglichst anderes Laufwerk) |
| `ELN_DATABASE_URL` | SQLite im Datenverzeichnis | für PostgreSQL/SQL Server siehe docs |
| `ELN_HOST` / `ELN_PORT` | `127.0.0.1` / `8000` | Adresse; `127.0.0.1` = nur lokal erreichbar |
| `ELN_SESSION_TIMEOUT_MIN` | `60` | Sitzungsablauf |
| `ELN_MAX_UPLOAD_MB` | `100` | max. Dateigröße |
| `ELN_MAX_FAILED_LOGINS` / `ELN_LOCKOUT_MINUTES` | `5` / `15` | Kontosperre |
| `ELN_COOKIE_SECURE` | `0` | bei HTTPS auf `1` |

Fachliche Einstellungen (unabhängige Prüfung, zweite Freigabe, Pflicht-Änderungsgrund, Toleranz der Rezeptursumme,
Vorwarnzeit Kalibrierung, Sperre gesperrter Geräte, erlaubte Dateiendungen) unter *Administration → Einstellungen*.

## 9. Fehlerbehebung

| Problem | Lösung |
|---|---|
| `setup.bat`: „Python wurde nicht gefunden“ | Python von python.org installieren, „Add python.exe to PATH“ anhaken, neues Fenster öffnen. Unter *Einstellungen → Apps → Erweiterte App-Einstellungen → App-Ausführungsaliase* die Einträge „python.exe“ (Microsoft Store) deaktivieren. |
| Paketinstallation scheitert (Proxy/Firewall) | Im Firmennetz ggf. Proxy setzen: `set HTTPS_PROXY=http://proxy:port` vor `setup.bat`; oder IT um Freigabe von pypi.org/files.pythonhosted.org bitten. |
| Edge öffnet sich nicht | Manuell `http://127.0.0.1:8000` aufrufen. Automatisches Öffnen mit `ELN_OPEN_BROWSER=0` abschalten. |
| „Address already in use“ / Port belegt | Läuft das ELN schon? `stop.bat` ausführen oder in `.env` `ELN_PORT=8010` setzen. |
| Seite zeigt „Interner Fehler“ | Details in `data\logs\fehler.log` (technisches Fehlerprotokoll), allgemeines Protokoll `eln.log`. |
| Anmeldung gesperrt | 15 Minuten warten oder Administrator hebt die Sperre unter *Benutzer* auf. |
| Administrator-Passwort vergessen | `.venv\Scripts\python.exe manage.py create-admin` legt einen weiteren Administrator an. |
| Datei-Upload abgelehnt | Endung nicht erlaubt (Einstellungen), ausführbare Datei, Datei zu groß oder Versuch gesperrt. |
| Bearbeiten nicht möglich | Versuch ist eingereicht/freigegeben (gesperrt) → nach Freigabe *Neue Revision anlegen*. |
| „Datenbank ist gesperrt“ | Nur eine Instanz starten; Datenbank nicht auf ein Netzlaufwerk legen (siehe docs/MEHRBENUTZERBETRIEB.md). |
| Hash-Kette des Audit Trails gebrochen | Auf direkte Manipulation der Datenbankdatei hinweisend: Administration informieren, letzte gültige Sicherung prüfen. `manage.py verify-audit` |

## 10. Verzeichnisstruktur

```
eln/
├─ app/
│  ├─ config.py          Konfiguration (.env/Umgebungsvariablen)
│  ├─ db.py              Datenbankverbindung (SQLAlchemy)
│  ├─ bootstrap.py       Migrationen mit vorheriger Sicherung, Rollen, Module
│  ├─ logging_setup.py   technisches Protokoll (data/logs)
│  ├─ main.py            FastAPI-App, Sicherheitsheader, Fehlerseiten
│  ├─ models/            Datenmodelle (Benutzer, Stammdaten, Arbeitsdaten, Querschnitt)
│  ├─ core/              Sicherheit, Rechte, Formate, Formularvalidierung (Pydantic), Plugin-Schnittstelle
│  ├─ services/          Geschäftslogik (Audit, Workflow, Rezepturen, Dateien, Suche, Auswertung, Export,
│  │                     PDF-Berichte, Import, Sicherung)
│  ├─ web/               Routen der Oberfläche und JSON-API
│  ├─ modules/           Fachmodule (compounding, mvr, Grundgerüste, _template)
│  ├─ templates/         Jinja2-Vorlagen
│  └─ static/            CSS, JavaScript, lokale Bibliotheken (Chart.js, Tabulator)
├─ migrations/           Alembic-Migrationen
├─ scripts/seed_demo.py  Beispieldaten
├─ tests/                pytest-Tests
├─ docs/                 Architektur, Mehrbenutzerbetrieb, Plugins, Datenintegrität, Abnahme-Checkliste
├─ manage.py             Verwaltungsbefehle
├─ setup.bat · start.bat · stop.bat · backup.bat · restore.bat
├─ requirements.txt · .env.example · alembic.ini
```

Laufzeitdaten (`data/`, `backups/`, `.env`, `.venv/`) sind von der Versionsverwaltung ausgenommen.

## 11. Tests und Abnahme

```bat
.venv\Scripts\python.exe -m pytest -q
```
74 automatisierte Tests decken Anmeldung, Rollen/Rechte, Aufträge, Versuche, Rezeptursumme, Datei-Upload, Prüfsummen,
Versionen, Freigabeprozess, Audit Trail (inkl. Manipulationserkennung), Suche, Import/Export, Dossiers, Module und
Datensicherung/Wiederherstellung ab. Für die manuelle Abnahme: [docs/ABNAHME_CHECKLISTE.md](docs/ABNAHME_CHECKLISTE.md).

**PDF-Bibliothek:** Es wird ReportLab verwendet – reine Python-Bibliothek ohne Systemabhängigkeiten (WeasyPrint
benötigt unter Windows GTK und ist daher fehleranfälliger). Unter Windows wird Arial eingebettet, sonst Helvetica.

## 12. Weiterführende Dokumentation

- [docs/ARCHITEKTUR.md](docs/ARCHITEKTUR.md) – Architektur, Annahmen, Datenmodell, Risiken (Phase 1)
- [docs/MEHRBENUTZERBETRIEB.md](docs/MEHRBENUTZERBETRIEB.md) – PostgreSQL/SQL Server, Netzlaufwerk, Windows-Dienst,
  HTTPS/Reverse Proxy, Microsoft Entra ID
- [docs/PLUGIN_ENTWICKLUNG.md](docs/PLUGIN_ENTWICKLUNG.md) – neue Fachmodule anlegen, registrieren, aktivieren
- [docs/DATENINTEGRITAET.md](docs/DATENINTEGRITAET.md) – ALCOA+-Abbildung und Grenzen
- [docs/ABNAHME_CHECKLISTE.md](docs/ABNAHME_CHECKLISTE.md) – manuelle Abnahme
- [docs/ENTWICKLUNGSPROTOKOLL.md](docs/ENTWICKLUNGSPROTOKOLL.md) – Phasen, Annahmen, bekannte Einschränkungen
