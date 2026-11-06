# Abnahme-Checkliste (manuell)

Durchführung in einer Testinstallation mit Beispieldaten (`setup.bat` → Beispieldaten „J“).
Ergebnis je Punkt: ☐ erfüllt · ☐ nicht erfüllt (Bemerkung). Prüfer, Datum und Version oben eintragen.

Prüfer: ______________________  Datum: ____________  Version: 1.0.0

## A. Installation und Start
- [ ] A1 `setup.bat` läuft ohne Fehler; Administrator wird abgefragt; Beispieldaten werden angelegt.
- [ ] A2 `start.bat` startet die Anwendung; Microsoft Edge öffnet `http://127.0.0.1:8000`.
- [ ] A3 Datenbank, Dateien und Protokolle liegen im konfigurierten `ELN_DATA_DIR`, nicht im Programmordner (falls umkonfiguriert).
- [ ] A4 `stop.bat` beendet die Anwendung.
- [ ] A5 Ohne Internetverbindung funktionieren alle Seiten inkl. Diagrammen und Tabellen.

## B. Anmeldung und Sicherheit
- [ ] B1 Anmeldung mit falschem Passwort wird abgelehnt; nach 5 Fehlversuchen ist das Konto gesperrt; Ereignisse im Audit Trail (Typ „Sicherheit“).
- [ ] B2 Neuer Benutzer muss das Startpasswort bei der ersten Anmeldung ändern; zu kurze Passwörter werden abgelehnt.
- [ ] B3 Nach Inaktivität (Sitzungsablauf) wird zur Anmeldung umgeleitet.
- [ ] B4 Benutzer `gast` (Leser) sieht Daten, kann aber nichts anlegen oder ändern (Schaltflächen fehlen, direkte URL → „Keine Berechtigung“).
- [ ] B5 Benutzer `t.braun` (Labor) kann keine Stammdaten anlegen und hat keinen Zugriff auf Administration und Audit Trail.
- [ ] B6 Rollenrechte lassen sich unter *Benutzer & Rollen → Rollen & Rechte* ändern und wirken sofort.
- [ ] B7 Ein „streng vertraulicher“ Auftrag ist für nicht beteiligte Labormitarbeiter weder in Listen noch in der Suche sichtbar.

## C. Dashboard und Navigation
- [ ] C1 Dashboard zeigt Kennzahlen, Prüf-/Freigabewarteschlange (für Prüfer/Leitung), eigene/überfällige Aufgaben, Gerätewarnungen, Diagramme.
- [ ] C2 Inhalte unterscheiden sich je nach angemeldetem Benutzer (z. B. `a.schulz` vs. `t.braun`).
- [ ] C3 Breadcrumbs, globale Suche, „+ Neu“-Menü, Hell-/Dunkelmodus funktionieren; Darstellung auf Tablet-Breite (Menü einklappbar).

## D. Aufträge, Versuche, Workflow
- [ ] D1 Auftrag anlegen: automatische ID `A-JJJJ-NNNN`, Pflichtfelder markiert, verständliche Fehlermeldungen (leeres Pflichtfeld, Datum 32.13.2026).
- [ ] D2 Auf der Auftragsseite Versuch anlegen → Auftrag ist vorbelegt; Versuch erscheint unter „Verknüpfte Versuche“.
- [ ] D3 Versuch: Prozessparameter-Tabelle (Zeilen hinzufügen/entfernen), Geräte-, Material-, Chargenauswahl; Auswahl eines gesperrten Geräts zeigt eine Warnung.
- [ ] D4 Bearbeitung starten → Abschließen ohne Ergebnis wird abgelehnt → mit Ergebnis/Schlussfolgerung abschließen → einreichen. Versuch ist gesperrt.
- [ ] D5 Der Verantwortliche kann den eigenen Versuch nicht prüfen (Einstellung „Unabhängige Prüfung“).
- [ ] D6 Prüfer weist zurück (Begründung Pflicht) → Status „Korrektur erforderlich“ → erneut einreichen → Prüfer bestätigt → „freigegeben“.
- [ ] D7 Einstellung „Zusätzliche Freigabe durch Abteilungsleitung“ aktivieren: nach Prüfung Status „geprüft“, Freigabe nur durch `m.weber`.
- [ ] D8 Freigegebener Versuch: Bearbeiten nicht möglich; „Neue Revision“ verlangt Änderungsgrund; Revision 2 ist bearbeitbar; Snapshot der Rev. 1 ist abrufbar und die Prüfsumme wird als intakt angezeigt.
- [ ] D9 Historie zeigt jede Feldänderung mit altem/neuem Wert, Grund, Benutzer, Zeit, Version.

## E. Rezepturen, Materialien, Chargen
- [ ] E1 Rezepturpositionen erfassen: Live-Summe, Warnung bei ≠ 100 Gew.-%, Chargenauswahl nur passend zum Material.
- [ ] E2 „Gew.-% aus Sollmengen berechnen“ (gemischte Einheiten g/kg) ergibt korrekte Anteile.
- [ ] E3 Skalieren auf 25 kg zeigt die Mengen; „Als neue Rezeptur speichern“ erzeugt eine Kopie.
- [ ] E4 Neue Revision mit Grund; Vorgänger wird „ersetzt“ und ist nicht mehr änderbar.
- [ ] E5 Vergleich von drei Rezepturen hebt Unterschiede farbig hervor.
- [ ] E6 Rezeptur-Import aus der Excel-Vorlage; fehlerhafte Materialnummer erzeugt Validierungsbericht ohne Änderung.
- [ ] E7 Material und Chargen getrennt; Charge mit abgelaufener Mindesthaltbarkeit wird markiert; SDB als Anhang (Kategorie Sicherheitsdatenblatt).

## F. Proben, Geräte, Messdaten
- [ ] F1 Probenhierarchie: Compound → Prüfkörper (Unterprobe) → gealterter Prüfkörper; Hierarchie auf der Probenseite sichtbar.
- [ ] F2 Gerät mit überfälliger Kalibrierung/gesperrtem Status erscheint im Dashboard und als Warnung im Versuch.
- [ ] F3 Messdatensatz mit Werten „x;Wert“ erfassen; Statistik (n, Mittelwert, Median, s, Min, Max) und Diagramm korrekt (Stichprobe nachrechnen).

## G. Dateien und Anhänge
- [ ] G1 Mehrere Dateien per Drag-and-drop hochladen; Fortschrittsanzeige; Bilder erscheinen in der Galerie mit Bildunterschrift; PDF-Vorschau.
- [ ] G2 Identische Datei erneut hochladen → Hinweis „inhaltsgleich (SHA-256)“.
- [ ] G3 `.exe`, `.bat`, `.ps1`, `rechnung.pdf.exe` und eine umbenannte EXE (`.txt`) werden abgelehnt.
- [ ] G4 Neue Version hochladen (Grund Pflicht): alte Version bleibt als „ersetzt“ abrufbar.
- [ ] G5 „Prüfsumme prüfen“ meldet „unverändert“. Archivieren/Ungültig setzen nur mit Recht und Begründung.
- [ ] G6 Bei eingereichtem/freigegebenem Versuch ist kein Upload möglich; Dateien eingereichter Stände lassen sich nicht löschen.

## H. Audit Trail
- [ ] H1 Ansicht mit Filtern Zeitraum, Benutzer, Datensatztyp, Kennung, Aktion; Export CSV/Excel.
- [ ] H2 „Integrität prüfen“ meldet „Kette intakt“.
- [ ] H3 Es gibt keine Möglichkeit, Einträge über die Oberfläche zu ändern oder zu löschen.

## I. Suche und Auswertungen
- [ ] I1 Suche nach Beobachtungstext, Materialnummer, Chargennummer, Dateiname und Text in einer hochgeladenen PDF/Word/Excel-Datei.
- [ ] I2 Kombinierte Filter (Status + Gerät + Zeitraum), Sortierung, Seitenwechsel, Suche speichern und erneut aufrufen.
- [ ] I3 Vorlagen „Versuche pro Monat“, „Versuche nach Gerät“, „Verlauf über Zeit/Temperatur“, „Prüfergebnisse je Probe (Boxplot)“, „Chargenvergleich“ zeigen plausible Diagramme und Kennzahlen.
- [ ] I4 Eigene Auswertung speichern; Export Excel/CSV.

## J. Compoundierungsmodul
- [ ] J1 Auf einem Versuch „+ Compoundierlauf“: Extruder, Rezeptur vorbelegt; Zonenvorlage laden (13 Zonen ZSE 27 MAXX); Zonen hinzufügen/entfernen/umbenennen.
- [ ] J2 Dosierstellen, Prozessparameter, Prozessverlauf erfassen; Detailseite zeigt Kennzahlen, Temperaturprofil (Soll/Ist) und Verlaufsdiagramm.
- [ ] J3 „Erzeugte Probe/Charge“ legt eine Probe am Versuch an und verknüpft sie.
- [ ] J4 Vergleich zweier Läufe hebt unterschiedliche Parameter hervor; Diagramme der Temperaturprofile.
- [ ] J5 Compoundierlauf erscheint im Versuchsdossier (PDF) und in der Auswertung „Compoundierläufe“.
- [ ] J6 Modul unter *Administration → Module* deaktivieren → Menüeintrag und Seiten verschwinden; erneut aktivieren → Daten wieder da. Zonenvorlagen in der Modulkonfiguration änderbar.

## K. Import, Export, Berichte
- [ ] K1 Materialimport aus CSV (Semikolon, Dezimalkomma): Prüflauf, Bericht, Bestätigung; fehlerhafte Datei → nichts gespeichert, Fehler mit Zeilennummer.
- [ ] K2 Messdatenimport mit `meta_`-Spalten.
- [ ] K3 Listenexport CSV/Excel/JSON jedes Datensatztyps.
- [ ] K4 Versuchsdossier als PDF enthält Stammdaten, Ziel, Materialien, Rezeptur, Prozessparameter, Proben, Prüfungen, Ergebnisse, Bewertung, Schlussfolgerung, Anhangverzeichnis, Version, Freigabestatus, Freigaben, Audit-Trail-Auszug.
- [ ] K5 Auftragsdossier als ZIP enthält PDF, JSON, Anhänge und `SHA256SUMS.txt`.

## L. Datensicherung und Wiederherstellung
- [ ] L1 Sicherung über Oberfläche und `backup.bat`; Status „vollständig“; Eintrag im Sicherungsprotokoll.
- [ ] L2 ZIP enthält `database/eln.db`, `files/`, `config/`, `manifest.json`.
- [ ] L3 Daten ändern → `stop.bat` → `restore.bat <zip>` → nach Start ist der alte Stand wiederhergestellt; Sicherung „vor-wiederherstellung“ existiert.
- [ ] L4 Wiederherstellung über die Oberfläche nur als Administrator und nur mit Eingabe „WIEDERHERSTELLEN“.
- [ ] L5 Vor einer Datenbankmigration (neue Version) wird automatisch eine Sicherung angelegt.

## M. Automatisierte Tests
- [ ] M1 `.venv\Scripts\python.exe -m pytest -q` → alle Tests bestanden.
