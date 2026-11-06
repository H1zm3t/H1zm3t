"""Rechte und Standardrollen.

Die Rechte einer Rolle sind in der Datenbank gespeichert und können in der
Benutzerverwaltung angepasst werden. Hier stehen nur die Standardwerte.
"""
from __future__ import annotations

PERMISSIONS: dict[str, str] = {
    "view": "Anzeigen",
    "create": "Anlegen",
    "edit": "Bearbeiten",
    "complete": "Abschließen / zur Prüfung einreichen",
    "review": "Prüfen",
    "approve": "Freigeben",
    "archive": "Archivieren",
    "export": "Exportieren",
    "manage_master_data": "Stammdaten verwalten",
    "delete_files": "Dateien löschen / ungültig setzen",
    "manage_users": "Benutzer verwalten",
    "view_audit": "Audit Trail anzeigen",
    "manage_settings": "Systemeinstellungen ändern",
    "backup": "Datensicherung erstellen",
    "import": "Daten importieren",
}

DEFAULT_ROLES: dict[str, dict] = {
    "admin": {
        "name": "Administrator",
        "description": "Vollzugriff inkl. Benutzerverwaltung, Einstellungen und Wiederherstellung.",
        "permissions": list(PERMISSIONS),
    },
    "leitung": {
        "name": "Abteilungsleitung",
        "description": "Zweite Freigabe, Auswertungen, Audit Trail.",
        "permissions": [
            "view", "create", "edit", "complete", "review", "approve", "archive", "export",
            "manage_master_data", "view_audit", "backup", "import",
        ],
    },
    "wissenschaftler": {
        "name": "Wissenschaftler / Ingenieur",
        "description": "Planung, Durchführung und Bewertung von Versuchen.",
        "permissions": ["view", "create", "edit", "complete", "export", "manage_master_data", "import"],
    },
    "labor": {
        "name": "Labormitarbeiter",
        "description": "Durchführung und Dokumentation von Versuchen.",
        "permissions": ["view", "create", "edit", "complete"],
    },
    "pruefer": {
        "name": "Prüfer",
        "description": "Unabhängige Prüfung eingereichter Versuche.",
        "permissions": ["view", "review", "export", "view_audit"],
    },
    "leser": {
        "name": "Leser",
        "description": "Nur Lesezugriff.",
        "permissions": ["view"],
    },
}
