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
