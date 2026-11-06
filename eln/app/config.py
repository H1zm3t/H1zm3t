"""Zentrale Konfiguration.

Werte werden in dieser Reihenfolge bestimmt:
1. Umgebungsvariablen (ELN_*)
2. Datei ``.env`` im Programmordner
3. Standardwerte

Zugangsdaten werden niemals im Quellcode abgelegt.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
APP_DIR = BASE_DIR / "app"
APP_VERSION = "1.0.0"
APP_NAME = "ELN Anwendungstechnik"


def _read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip().strip('"').strip("'")
        values[key.strip()] = value
    return values


def _resolve(path_value: str) -> Path:
    p = Path(path_value).expanduser()
    if not p.is_absolute():
        p = BASE_DIR / p
    return p.resolve()


@dataclass
class Settings:
    data_dir: Path
    files_dir: Path
    backup_dir: Path
    log_dir: Path
    database_url: str
    host: str = "127.0.0.1"
    port: int = 8000
    session_timeout_min: int = 60
    max_upload_mb: int = 100
    max_failed_logins: int = 5
    lockout_minutes: int = 15
    cookie_secure: bool = False
    log_level: str = "INFO"
    open_browser: bool = True
    env_file: Path = field(default_factory=lambda: BASE_DIR / ".env")

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def sqlite_path(self) -> Path | None:
        if not self.is_sqlite:
            return None
        raw = self.database_url.split("///", 1)[1]
        return Path(raw)

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.files_dir, self.backup_dir, self.log_dir):
            d.mkdir(parents=True, exist_ok=True)


def load_settings(overrides: dict[str, str] | None = None) -> Settings:
    env_file = BASE_DIR / ".env"
    values = _read_env_file(env_file)
    for key, val in os.environ.items():
        if key.startswith("ELN_"):
            values[key] = val
    if overrides:
        values.update(overrides)

    def get(key: str, default: str) -> str:
        return values.get(key, default) or default

    data_dir = _resolve(get("ELN_DATA_DIR", "data"))
    files_dir = _resolve(values["ELN_FILES_DIR"]) if values.get("ELN_FILES_DIR") else data_dir / "files"
    backup_dir = _resolve(get("ELN_BACKUP_DIR", "backups"))
    db_url = values.get("ELN_DATABASE_URL") or f"sqlite:///{(data_dir / 'eln.db').as_posix()}"
    return Settings(
        data_dir=data_dir,
        files_dir=files_dir,
        backup_dir=backup_dir,
        log_dir=data_dir / "logs",
        database_url=db_url,
        host=get("ELN_HOST", "127.0.0.1"),
        port=int(get("ELN_PORT", "8000")),
        session_timeout_min=int(get("ELN_SESSION_TIMEOUT_MIN", "60")),
        max_upload_mb=int(get("ELN_MAX_UPLOAD_MB", "100")),
        max_failed_logins=int(get("ELN_MAX_FAILED_LOGINS", "5")),
        lockout_minutes=int(get("ELN_LOCKOUT_MINUTES", "15")),
        cookie_secure=get("ELN_COOKIE_SECURE", "0") in ("1", "true", "True", "ja"),
        log_level=get("ELN_LOG_LEVEL", "INFO").upper(),
        open_browser=get("ELN_OPEN_BROWSER", "1") in ("1", "true", "True", "ja"),
        env_file=env_file,
    )


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = load_settings()
    return _settings


def set_settings(settings: Settings) -> None:
    """Wird von Tests und vom Startskript genutzt, um die Konfiguration festzulegen."""
    global _settings
    _settings = settings
