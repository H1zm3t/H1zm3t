# ELN – Elektronisches Laborbuch

Ein modernes Laborbuch für F&E in **einer einzigen HTML-Datei**. Keine Installation, kein Python, kein Server, keine Internetverbindung nötig.

## Start

1. `ELN.html` auf ein Netzlaufwerk (oder lokal) kopieren.
2. Per Doppelklick in **Microsoft Edge** oder **Google Chrome** öffnen.
3. Beim ersten Start Namen und Kürzel eingeben.

## Zusammenarbeit im Team

Oben rechts auf **💾 Lokal** klicken → **Gemeinsamen Ordner verbinden** und einen Ordner auf dem Netzlaufwerk wählen
(am besten einen eigenen, leeren Ordner, z. B. `ELN-Daten`). Alle Kolleginnen und Kollegen verbinden denselben Ordner.

- Jeder Versuch liegt dort als eigene Datei `<ID>.json`, eigene Vorlagen in `_vorlagen.json`.
- Der Ordner wird über das normale Backup des Netzlaufwerks mitgesichert.
- Ändern zwei Personen gleichzeitig denselben Versuch, warnt das ELN vor dem Überschreiben.
- Nach einem Neustart des Browsers muss der Ordnerzugriff mit einem Klick erneut bestätigt werden (Vorgabe des Browsers).

Ohne verbundenen Ordner liegen die Daten nur im Browser dieses PCs – dann regelmäßig **Backup exportieren**.
Firefox kann keine Ordner verbinden; dort funktioniert nur der lokale Modus mit Backup-Export/-Import.

## Funktionen

- Versuche mit automatischer ID (`Jahr-Kürzel-Nr.`), Projekt, Datum, Status, Tags
- Abschnitte: Ziel & Hypothese, Versuchsaufbau, Durchführung, Ergebnisse, Fazit (formatierter Text, Bilder per Strg+V)
- Materialien & Geräte (Charge / Serien-Nr.), Messdaten-Tabelle mit Einfügen aus Excel, CSV-Export und Diagramm
- Anhänge (Fotos, PDFs, Messdateien bis 8 MB je Datei)
- Vorlagen (mitgeliefert und eigene), Folgeversuch / Kopie
- Signieren & Sperren mit SHA-256-Prüfsumme, Gegenzeichnung, Nachträge, Änderungsverlauf
- Volltextsuche, Filter nach Status und Projekt, Drucken / PDF, Hell-/Dunkelmodus

## Hinweis

Die Signatur ist ein organisatorischer Schreibschutz mit Integritätsprüfung, keine qualifizierte elektronische Signatur.
Benutzer werden nicht per Passwort geprüft; die Zugriffskontrolle erfolgt über die Rechte des Netzlaufwerks.
