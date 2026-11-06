# Datenintegrität (ALCOA+) – Umsetzung und Grenzen

## Wichtiger Hinweis

Dieses ELN wurde an den ALCOA+-Grundsätzen ausgerichtet. Technische Funktionen allein machen ein System **nicht**
GxP-validiert, **nicht** konform zu FDA 21 CFR Part 11 und **nicht** konform zu EU-GMP Annex 11. Soll das System in
einem regulierten Umfeld eingesetzt werden, sind zusätzlich erforderlich:

- formelle Computersystemvalidierung (z. B. nach GAMP 5) mit Anforderungs-, Risiko- und Testdokumentation (IQ/OQ/PQ),
- Risikobewertung (Datenfluss, kritische Daten, Schnittstellen),
- Verfahrensanweisungen (Benutzerverwaltung, Rechtevergabe, Freigabe, Sicherung/Wiederherstellung, Archivierung,
  Änderungsmanagement, Störungsbehandlung, periodische Überprüfung des Audit Trails),
- Schulung und Qualifikation der Anwender,
- organisatorische und IT-Kontrollen (Zugriffsschutz auf Server, Datenbankdatei und Dateiablage, Zeitsynchronisation,
  Betriebssystem-Härtung, Virenschutz, Notfallplanung),
- ggf. rechtsverbindliche elektronische Signaturen (Part 11 Subpart C) – die Prüf- und Freigabevermerke dieses
  Systems sind elektronische Vermerke mit Personenbezug, aber keine qualifizierten Signaturen.

## Abbildung der Grundsätze

| Grundsatz | Umsetzung im ELN |
|---|---|
| **Attributable** (zuordenbar) | Persönliche Konten, keine Sammelkonten vorgesehen; jede Änderung mit Benutzer, Zeit, IP im Audit Trail; Ersteller/Bearbeiter an jedem Datensatz; Prüf-/Freigabevermerke mit Person |
| **Legible** (lesbar) | Klartext-Oberfläche, lesbare Audit-Trail-Ansicht mit Filtern, PDF-Dossiers, Exporte |
| **Contemporaneous** (zeitnah) | Zeitstempel werden serverseitig gesetzt (nicht vom Benutzer); Dokumentation direkt im System; Snapshot bei Einreichung |
| **Original** | Originaldateien unverändert in der Dateiablage mit SHA-256; neue Versionen statt Überschreiben; Messwerte als Rohwerte gespeichert |
| **Accurate** (richtig) | Validierung von Eingaben (Pflichtfelder, Zahlen, Datumsangaben), Rezeptursummenprüfung, Gerätewarnungen bei Sperre/überfälliger Kalibrierung, Vier-Augen-Prüfung |
| **Complete** (vollständig) | Kein physisches Löschen von Kern-Datensätzen; Archivieren/Ungültig-Setzen mit Begründung; vollständige Änderungshistorie inkl. alter Werte; Dossier mit Audit-Trail-Auszug |
| **Consistent** (konsistent) | Transaktionen (alles oder nichts), Statusmodell mit erlaubten Übergängen, eindeutige Kennungen, einheitliche Formate |
| **Enduring** (dauerhaft) | Datenbank + Dateiablage, geprüfte ZIP-Sicherungen mit Manifest/Prüfsummen, Sicherung vor Migrationen; offene Exportformate (PDF, JSON, CSV, XLSX) |
| **Available** (verfügbar) | Suche über alle Inhalte, Exporte, Wiederherstellung, dokumentierte Datenstruktur |

## Technische Schutzmaßnahmen des Audit Trails

1. **Nur Einfügen:** Die Oberfläche bietet keine Funktion zum Ändern oder Löschen von Audit-Einträgen.
2. **Datenbank-Trigger** (`audit_log_no_update`, `audit_log_no_delete`) brechen UPDATE/DELETE ab.
3. **Hash-Kette:** Jeder Eintrag enthält den SHA-256 seines Vorgängers und seinen eigenen Hash über alle Felder.
   Veränderte, gelöschte oder eingefügte Einträge werden bei der Prüfung erkannt
   (*Audit Trail → Integrität prüfen*, *Administration → System*, `manage.py verify-audit`).
4. **Snapshots:** Bei Einreichung, Prüfung und Freigabe wird der vollständige Versuchsstand (inkl. Rezeptur,
   Messwerte, Anhangsprüfsummen) als JSON mit SHA-256 eingefroren; die Freigabevermerke verweisen darauf.

Grenze: Wer Schreibzugriff auf die Datenbankdatei und Kenntnisse hat, kann Trigger entfernen und die gesamte Kette
neu berechnen. Deshalb sind Dateisystemrechte, Sicherungen an getrenntem Ort (deren Hash-Kette verglichen werden
kann) und für höhere Anforderungen ein Datenbankserver mit getrennten Rechten (siehe MEHRBENUTZERBETRIEB.md) nötig.

## Protokollierte Ereignisse

Anlegen, Ändern (feldweise mit Alt/Neu), Statuswechsel, Einreichen, Prüfen, Zurückweisen, Freigeben, neue Revision,
Archivieren, Datei-Upload/-Version/-Download/-Statusänderung/-Löschung, Kommentare, Verknüpfungen, Exporte, Importe,
Anmeldung, fehlgeschlagene Anmeldung, Kontosperre, Abmeldung, Passwortänderung, verweigerte CSRF-Prüfungen,
Änderungen an Benutzern, Rollen, Einstellungen und Modulen, Sicherungen, Wiederherstellungen, Migrationen.
