"""Wertelisten (Status, Kategorien, Einheiten)."""
from __future__ import annotations

EXPERIMENT_STATUS = (
    "Entwurf", "geplant", "in Bearbeitung", "pausiert", "abgeschlossen", "zur Prüfung",
    "Korrektur erforderlich", "geprüft", "freigegeben", "archiviert", "abgebrochen",
)
ORDER_STATUS = ("offen", "in Bearbeitung", "pausiert", "abgeschlossen", "storniert", "archiviert")
PROJECT_STATUS = ("aktiv", "ruhend", "abgeschlossen", "archiviert")
SERIES_STATUS = ("aktiv", "abgeschlossen", "archiviert")
PRIORITIES = ("niedrig", "normal", "hoch", "dringend")
CONFIDENTIALITY = ("öffentlich", "intern", "vertraulich", "streng vertraulich")
DEPARTMENTS = (
    "Compoundierung", "Spritzguss", "Mechanische Prüfung", "Rheologie", "Thermische Analyse",
    "Partikelanalytik", "Alterung / Klima / Autoklav", "Rohstoffprüfung", "Mischen / Mahlen",
    "Musterherstellung", "Sonstiges",
)
EXPERIMENT_TYPES = (
    "Rezepturentwicklung", "Rezepturoptimierung", "Kundenmuster", "Rohstoffprüfung", "Vergleichsversuch",
    "Reklamationsuntersuchung", "Mustermengenherstellung", "Langzeitversuch", "Methodenentwicklung", "Sonstiges",
)
MATERIAL_TYPES = (
    "Polymer", "Additiv", "Stabilisator", "Antioxidans", "Flammschutzmittel", "Füllstoff", "Verstärkungsstoff",
    "Pigment / Farbmittel", "Masterbatch", "Compound", "Gleitmittel", "Nukleierungsmittel", "Sonstiges",
)
MATERIAL_STATUS = ("aktiv", "gesperrt", "ausgelaufen")
BATCH_STATUS = ("Quarantäne", "freigegeben", "gesperrt", "verbraucht", "abgelaufen")
DEVICE_STATUS = ("betriebsbereit", "in Wartung", "gesperrt", "außer Betrieb")
DEVICE_TYPES = (
    "Extruder", "Spritzgussmaschine", "Werkzeug", "Zugprüfmaschine", "Pendelschlagwerk", "Fließprüfgerät",
    "Kapillarrheometer", "DSC", "TGA", "Partikelmessgerät", "Mühle", "Mischer", "Ofen", "Klimaschrank",
    "Autoklav", "Waage", "Dosiergerät", "Sonstiges",
)
METHOD_STATUS = ("gültig", "in Entwicklung", "zurückgezogen")
SAMPLE_TYPES = (
    "Rohstoff", "Additivmischung", "Masterbatch", "Compound / Granulat", "Prüfkörper", "gealterter Prüfkörper",
    "Kundenmuster", "Pulver", "Platte / Folie", "Sonstiges",
)
SAMPLE_STATUS = ("geplant", "vorhanden", "in Prüfung", "verbraucht", "versendet", "entsorgt")
RECIPE_STATUS = ("Entwurf", "gültig", "ersetzt", "archiviert")
UNITS = ("g", "kg", "mg", "t", "ml", "l", "Stk.")
MASS_UNITS = {"mg": 0.001, "g": 1.0, "kg": 1000.0, "t": 1_000_000.0}
TASK_STATUS = ("offen", "in Bearbeitung", "erledigt")
ATTACHMENT_CATEGORIES = (
    "Foto", "Bericht", "Messdatei", "Rohdaten", "Auswertung", "Sicherheitsdatenblatt", "Analysenzertifikat",
    "Prüfvorschrift", "Kalibrierzertifikat", "Wartungsprotokoll", "Kundenunterlage", "Schneckenkonfiguration",
    "Prozessdatei", "Sonstiges",
)

# --- Auftragsplanung (entspricht den Listen im Excel-Formular »Compoundierplan«) ---
ACTIVITY_CATEGORIES: dict[str, tuple[str, ...]] = {
    "Vorbereitung und Rohstoffe": (
        "Auftrag prüfen", "Auftragsdetails klären", "Rohstoffverfügbarkeit prüfen", "Rohstoffe bereitstellen",
        "Rohstoffe konditionieren", "Rohstofffeuchtigkeit bestimmen", "Vormischung herstellen", "Dryblend herstellen",
        "Material mahlen", "Probe ziehen", "Material fotografieren"),
    "Compoundierung und Verarbeitung": (
        "Compoundherstellung Extruder", "Masterbatchherstellung", "Additivmischung herstellen", "Reagenzglasguss",
        "RIM", "Handguss", "Gusspolyamid", "Sonstige Verarbeitung"),
    "Spritzguss und Prüfkörper": (
        "Spritzguss Zugprüfkörper", "Spritzguss Schlagprüfkörper", "Spritzguss Biegeprüfkörper", "Spritzguss Spirale",
        "Spritzguss 3-Stufen/Glatt-Platte", "Spritzguss 3-Stufen/3-Stufen-Platte", "Spritzguss Schrumpfplatte",
        "Spritzguss sonstiger Prüfkörper"),
    "Konditionierung und Alterung": (
        "Normklima", "Feuchte-Konditionierung", "Trocknung", "Klimaofenlagerung", "Ofenalterung Zugprüfkörper",
        "Ofenalterung Schlagprüfkörper", "Ofenalterung Biegeprüfkörper", "Autoklavenlagerung", "Medienlagerung",
        "Dachlagerung", "sonstige Alterung"),
    "Mechanische Prüfungen": (
        "Zugeigenschaften", "Biegeprüfung", "Charpy ungekerbt", "Charpy gekerbt", "Izod ungekerbt", "Izod gekerbt",
        "Härte", "sonstige mechanische Prüfung"),
    "Rheologische Untersuchungen": (
        "MVR / MFI", "HKR", "Fließspirale", "Drehmomentmessung", "Viskositätsverlauf",
        "sonstige rheologische Untersuchung"),
    "Analytik": (
        "DSC", "TGA", "IR", "RFA", "rV", "iV", "AEG-Bestimmung", "UV-VIS", "Partikelgrößenverteilung",
        "Feuchtigkeitsbestimmung", "L*a*b*-Messung", "Glanzmessung", "Mikroskopie/Fotodokumentation",
        "sonstige Analytik"),
    "Optische und visuelle Bewertung": (
        "Granulat fotografieren", "Prüfkörper fotografieren", "Oberfläche fotografieren", "Farbe visuell bewerten",
        "Ablagerungen bewerten", "Verfärbung bewerten", "Schlieren bewerten", "Glanz messen", "L*a*b* messen",
        "Mikroskopische Untersuchung"),
    "Dokumentation und Abschluss": (
        "Rohdaten übertragen", "Rohdaten prüfen", "Bilder ablegen", "Ergebnisse auswerten",
        "Ergebnisübersicht erstellen", "Bericht erstellen", "Auftraggeber informieren", "Dokumentation vollständig",
        "Auftrag abschließen"),
}
ACTIVITY_STATUS = (
    "nicht erforderlich", "geplant", "wartet auf Voraussetzung", "bereit", "in Bearbeitung",
    "praktisch abgeschlossen", "Dokumentation offen", "abgeschlossen", "zurückgestellt", "entfallen",
)
ACTIVITY_DONE = ("abgeschlossen",)
ACTIVITY_NOT_COUNTED = ("nicht erforderlich", "entfallen")
MATERIAL_SECTIONS = ("Rohstoffe für Compound Herstellung", "Rohstoffe für MB Herstellung", "weitere benötigte Rohstoffe")
RECIPE_TYPES = ("Compound", "Masterbatch", "Pulvermischung", "Additivmischung", "Sonstige")
