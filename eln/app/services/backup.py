"""Datensicherung und Wiederherstellung.

Eine Sicherung ist ein ZIP-Archiv mit Zeitstempel und enthält:
- ``database/eln.db``  konsistente Kopie (SQLite-Backup-API, auch bei laufendem Betrieb)
- ``files/...``        alle hochgeladenen Dateien
- ``config/.env``      Konfiguration (falls vorhanden)
- ``config/modules.json`` Modulkonfiguration und Systemeinstellungen
- ``manifest.json``    Inhaltsverzeichnis mit SHA-256 je Datei

Nach dem Schreiben wird das Archiv erneut geöffnet und vollständig geprüft
(Prüfsummen, Dateianzahl, SQLite-Integritätsprüfung). Jede Sicherung wird in
``backup_log.jsonl`` im Sicherungsordner und in der Datenbank protokolliert.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

from ..config import APP_VERSION, get_settings
from ..db import reset_engine, session_scope

MANIFEST = "manifest.json"


class BackupError(Exception):
    pass


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _append_log(entry: dict) -> None:
    settings = get_settings()
    settings.backup_dir.mkdir(parents=True, exist_ok=True)
    with open(settings.backup_dir / "backup_log.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _db_copy(target: Path) -> None:
    settings = get_settings()
    src_path = settings.sqlite_path
    if src_path is None:
        raise BackupError("Die integrierte Sicherung unterstützt nur SQLite. Für PostgreSQL/SQL Server bitte "
                          "die Sicherungswerkzeuge des Datenbankservers verwenden.")
    if not src_path.exists():
        raise BackupError(f"Datenbank nicht gefunden: {src_path}")
    src = sqlite3.connect(str(src_path))
    dst = sqlite3.connect(str(target))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()


def _settings_snapshot() -> dict:
    from ..models import ModuleState, SystemSetting

    with session_scope() as db:
        return {
            "modules": [{"key": m.key, "enabled": m.enabled, "version": m.installed_version, "config": m.config}
                        for m in db.query(ModuleState).all()],
            "settings": {s.key: s.value for s in db.query(SystemSetting).all()},
        }


def verify_backup(zip_path: Path) -> dict:
    """Prüft ein Sicherungsarchiv vollständig."""
    if not zip_path.exists():
        return {"ok": False, "message": "Archiv nicht gefunden."}
    try:
        with zipfile.ZipFile(zip_path) as zf:
            if zf.testzip() is not None:
                return {"ok": False, "message": "Archiv ist beschädigt (CRC-Fehler)."}
            manifest = json.loads(zf.read(MANIFEST))
            names = set(zf.namelist())
            for entry in manifest["files"]:
                if entry["path"] not in names:
                    return {"ok": False, "message": f"Datei fehlt im Archiv: {entry['path']}"}
                h = hashlib.sha256()
                with zf.open(entry["path"]) as fh:
                    for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                        h.update(chunk)
                if h.hexdigest() != entry["sha256"]:
                    return {"ok": False, "message": f"Prüfsumme stimmt nicht: {entry['path']}"}
            with tempfile.TemporaryDirectory() as tmp:
                db_file = Path(zf.extract("database/eln.db", tmp))
                con = sqlite3.connect(str(db_file))
                try:
                    res = con.execute("PRAGMA integrity_check").fetchone()[0]
                finally:
                    con.close()
                if res != "ok":
                    return {"ok": False, "message": f"SQLite-Integritätsprüfung: {res}"}
        return {"ok": True, "message": f"Sicherung vollständig ({len(manifest['files'])} Dateien geprüft).",
                "manifest": manifest}
    except (zipfile.BadZipFile, KeyError, json.JSONDecodeError) as exc:
        return {"ok": False, "message": f"Archiv ungültig: {exc}"}


def create_backup(kind: str = "manuell", username: str = "system", record: bool = True) -> dict:
    settings = get_settings()
    settings.backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = {"manuell": "", "vor Migration": "_vor-migration", "vor Wiederherstellung": "_vor-wiederherstellung"}.get(kind, "")
    zip_path = settings.backup_dir / f"eln_sicherung_{stamp}{suffix}.zip"
    n = 1
    while zip_path.exists():
        zip_path = settings.backup_dir / f"eln_sicherung_{stamp}{suffix}_{n}.zip"
        n += 1
    entries = []
    result: dict
    try:
        with tempfile.TemporaryDirectory() as tmp:
            db_tmp = Path(tmp) / "eln.db"
            _db_copy(db_tmp)
            config_json = None
            try:
                config_json = json.dumps(_settings_snapshot(), ensure_ascii=False, indent=2)
            except Exception:  # z. B. vor der ersten Migration noch keine Tabellen
                config_json = json.dumps({"modules": [], "settings": {}})
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
                zf.write(db_tmp, "database/eln.db")
                entries.append({"path": "database/eln.db", "sha256": _sha256(db_tmp), "size": db_tmp.stat().st_size})
                zf.writestr("config/modules.json", config_json)
                entries.append({"path": "config/modules.json",
                                "sha256": hashlib.sha256(config_json.encode("utf-8")).hexdigest(),
                                "size": len(config_json.encode("utf-8"))})
                if settings.env_file.exists():
                    zf.write(settings.env_file, "config/.env")
                    entries.append({"path": "config/.env", "sha256": _sha256(settings.env_file),
                                    "size": settings.env_file.stat().st_size})
                files_root = settings.files_dir
                if files_root.exists():
                    for root, _dirs, files in os.walk(files_root):
                        for fname in files:
                            p = Path(root) / fname
                            rel = p.relative_to(files_root)
                            if rel.parts and rel.parts[0] == "_tmp":
                                continue
                            arc = "files/" + rel.as_posix()
                            zf.write(p, arc)
                            entries.append({"path": arc, "sha256": _sha256(p), "size": p.stat().st_size})
                manifest = {"app_version": APP_VERSION, "created_at": datetime.now().isoformat(timespec="seconds"),
                            "kind": kind, "created_by": username, "files": entries}
                zf.writestr(MANIFEST, json.dumps(manifest, ensure_ascii=False, indent=2))
        check = verify_backup(zip_path)
        status = "vollständig" if check["ok"] else "fehlerhaft"
        result = {"ok": check["ok"], "path": str(zip_path), "filename": zip_path.name, "status": status,
                  "message": check["message"], "file_count": len(entries), "size": zip_path.stat().st_size,
                  "sha256": _sha256(zip_path)}
    except Exception as exc:
        if zip_path.exists():
            zip_path.unlink()
        result = {"ok": False, "path": str(zip_path), "filename": zip_path.name, "status": "fehlgeschlagen",
                  "message": str(exc), "file_count": len(entries), "size": None, "sha256": None}
    _append_log({"zeit": datetime.now().isoformat(timespec="seconds"), "art": kind, "benutzer": username,
                 **{k: result[k] for k in ("filename", "status", "message", "file_count", "size", "sha256")}})
    if record:
        try:
            from ..models import BackupRecord

            with session_scope() as db:
                db.add(BackupRecord(filename=result["filename"], path=result["path"], kind=kind, created_by=username,
                                    size_bytes=result["size"], sha256=result["sha256"],
                                    file_count=result["file_count"], status=result["status"],
                                    message=result["message"]))
        except Exception:  # Protokolldatei backup_log.jsonl enthält den Eintrag in jedem Fall
            pass
    return result


def list_backups() -> list[dict]:
    settings = get_settings()
    if not settings.backup_dir.exists():
        return []
    items = []
    for p in sorted(settings.backup_dir.glob("eln_sicherung_*.zip"), reverse=True):
        items.append({"filename": p.name, "size": p.stat().st_size,
                      "modified": datetime.fromtimestamp(p.stat().st_mtime)})
    return items


def resolve_backup(filename: str) -> Path:
    """Nur Dateinamen im Sicherungsordner zulassen (keine Pfadangaben)."""
    settings = get_settings()
    if "/" in filename or "\\" in filename or not filename.startswith("eln_sicherung_") or not filename.endswith(".zip"):
        raise BackupError("Ungültiger Sicherungsname.")
    path = (settings.backup_dir / filename).resolve()
    if path.parent != settings.backup_dir.resolve() or not path.exists():
        raise BackupError("Sicherung nicht gefunden.")
    return path


def restore_backup(zip_path: Path, username: str = "system") -> dict:
    """Stellt Datenbank und Dateien aus einer Sicherung wieder her.

    Vorher wird automatisch eine Sicherung des aktuellen Stands erstellt.
    Die Konfigurationsdatei .env wird NICHT überschrieben (liegt als Kopie im Archiv).
    """
    settings = get_settings()
    check = verify_backup(zip_path)
    if not check["ok"]:
        raise BackupError(f"Sicherung ist nicht vollständig: {check['message']}")
    pre = create_backup("vor Wiederherstellung", username)
    if not pre["ok"]:
        raise BackupError(f"Sicherung des aktuellen Stands fehlgeschlagen: {pre['message']}")
    db_path = settings.sqlite_path
    if db_path is None:
        raise BackupError("Wiederherstellung ist nur für SQLite implementiert.")
    reset_engine()
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(tmp)
        tmp_root = Path(tmp)
        for suffix in ("-wal", "-shm"):
            Path(str(db_path) + suffix).unlink(missing_ok=True)
        shutil.copy2(tmp_root / "database" / "eln.db", db_path)
        files_src = tmp_root / "files"
        old_files = settings.files_dir.with_name(settings.files_dir.name + "_alt_" + datetime.now().strftime("%Y%m%d%H%M%S"))
        if settings.files_dir.exists():
            settings.files_dir.rename(old_files)
        if files_src.exists():
            shutil.copytree(files_src, settings.files_dir)
        else:
            settings.files_dir.mkdir(parents=True, exist_ok=True)
        if old_files.exists():
            shutil.rmtree(old_files, ignore_errors=True)
    entry = {"zeit": datetime.now().isoformat(timespec="seconds"), "art": "Wiederherstellung", "benutzer": username,
             "filename": zip_path.name, "status": "wiederhergestellt",
             "message": f"Vorher gesichert als {pre['filename']}"}
    _append_log(entry)
    from ..models import BackupRecord
    from . import audit

    with session_scope() as db:
        audit.log(db, audit.Actor(user=None, ip="lokal"), "restore", entity_type="backup",
                  new=f"{zip_path.name} wiederhergestellt durch {username}",
                  reason=f"Stand vorher gesichert: {pre['filename']}")
        db.add(BackupRecord(filename=zip_path.name, path=str(zip_path), kind="Wiederherstellung",
                            created_by=username, status="wiederhergestellt", message=entry["message"]))
    return {"ok": True, "message": f"Wiederherstellung aus {zip_path.name} abgeschlossen. "
                                   f"Der vorherige Stand wurde als {pre['filename']} gesichert.",
            "pre_backup": pre["filename"]}


def read_log(limit: int = 100) -> list[dict]:
    path = get_settings().backup_dir / "backup_log.jsonl"
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()[-limit:]
    out = []
    for line in reversed(lines):
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out
