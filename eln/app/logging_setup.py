"""Technische Protokollierung (getrennt vom fachlichen Audit Trail)."""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from .config import get_settings

_configured = False


def setup_logging() -> None:
    global _configured
    if _configured:
        return
    settings = get_settings()
    settings.log_dir.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)-8s %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S")
    root = logging.getLogger("eln")
    root.setLevel(settings.log_level)
    app_handler = RotatingFileHandler(settings.log_dir / "eln.log", maxBytes=5_000_000, backupCount=5, encoding="utf-8")
    app_handler.setFormatter(fmt)
    err_handler = RotatingFileHandler(settings.log_dir / "fehler.log", maxBytes=5_000_000, backupCount=5,
                                      encoding="utf-8")
    err_handler.setLevel(logging.ERROR)
    err_handler.setFormatter(fmt)
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    root.addHandler(app_handler)
    root.addHandler(err_handler)
    root.addHandler(console)
    _configured = True
