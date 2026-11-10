"""Verwaltungsbefehle für das ELN.

Aufruf:  python manage.py <befehl> [optionen]

Befehle:
  init               Datenbank anlegen/migrieren und ersten Administrator erstellen
  needs-setup        Prüft, ob die Ersteinrichtung noch aussteht (Rückgabecode 1 = ja)
  migrate            Datenbankmigrationen ausführen (mit Sicherung vorher)
  create-admin       Weiteren Administrator anlegen
  seed-demo          Beispieldaten anlegen (nur in leerer Datenbank sinnvoll)
  run                Anwendung starten (öffnet Microsoft Edge)
  stop               Laufende Anwendung beenden
  backup             Sicherung erstellen
  verify-backup ZIP  Sicherung prüfen
  restore ZIP        Sicherung wiederherstellen (Warnung!)
  verify-audit       Hash-Kette des Audit Trails prüfen
  new-module KEY     Neues Fachmodul aus der Vorlage erzeugen
"""
from __future__ import annotations

import argparse
import getpass
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

from app.config import get_settings  # noqa: E402


def _pid_file() -> Path:
    return get_settings().data_dir / "eln.pid"


def ask_password(prompt: str = "Passwort") -> str:
    from app.core.security import password_problems

    while True:
        pw = os.environ.get("ELN_ADMIN_PASSWORD") or getpass.getpass(f"{prompt} (min. 10 Zeichen): ")
        problems = password_problems(pw)
        if problems:
            print("  " + " ".join(problems))
            if os.environ.get("ELN_ADMIN_PASSWORD"):
                sys.exit(1)
            continue
        if os.environ.get("ELN_ADMIN_PASSWORD") or pw == getpass.getpass("Passwort wiederholen: "):
            return pw
        print("  Die Passwörter stimmen nicht überein.")


def cmd_migrate(_args) -> None:
    from app.bootstrap import init_database

    print(init_database())


def _create_admin(username: str, full_name: str, password: str) -> None:
    from app.db import session_scope
    from app.services import auth
    from app.services.audit import SYSTEM

    with session_scope() as db:
        auth.create_user(db, SYSTEM, username=username, full_name=full_name, password=password, role_keys=["admin"])
    print(f"Administrator »{username}« angelegt.")


def cmd_init(args) -> None:
    from app.bootstrap import init_database
    from app.db import session_scope
    from app.models import User

    settings = get_settings()
    settings.ensure_dirs()
    print(f"Datenverzeichnis: {settings.data_dir}")
    print(f"Sicherungsziel:   {settings.backup_dir}")
    print(init_database())
    with session_scope() as db:
        has_users = db.query(User).count() > 0
    if has_users:
        print("Es existieren bereits Benutzer – kein neuer Administrator angelegt.")
        return
    print("\nErsten Administrator anlegen:")
    username = args.username or os.environ.get("ELN_ADMIN_USER") or input("Benutzername [admin]: ").strip() or "admin"
    full_name = args.full_name or os.environ.get("ELN_ADMIN_NAME") or input("Vollständiger Name [Administrator]: ").strip() or "Administrator"
    _create_admin(username, full_name, ask_password())


def cmd_needs_setup(_args) -> None:
    """Rückgabecode 1, wenn noch kein Benutzer existiert (Ersteinrichtung nötig), sonst 0."""
    from app.config import get_settings as _gs
    from app.db import session_scope
    from app.models import User

    db_path = _gs().sqlite_path
    if db_path is not None and not db_path.exists():
        sys.exit(1)
    try:
        with session_scope() as db:
            sys.exit(0 if db.query(User).count() > 0 else 1)
    except SystemExit:
        raise
    except Exception:
        sys.exit(1)


def cmd_create_admin(args) -> None:
    from app.bootstrap import init_database

    init_database()
    username = args.username or input("Benutzername: ").strip()
    full_name = args.full_name or input("Vollständiger Name: ").strip()
    _create_admin(username, full_name, ask_password())


def cmd_seed_demo(args) -> None:
    from app.bootstrap import init_database
    from scripts.seed_demo import seed

    init_database()
    password = args.password or os.environ.get("ELN_DEMO_PASSWORD")
    if not password:
        password = ask_password("Gemeinsames Passwort für die Demo-Benutzer")
    print(seed(password))


def _open_browser(url: str) -> None:
    for _ in range(60):
        try:
            urllib.request.urlopen(url + "/login", timeout=1)
            break
        except Exception:
            time.sleep(0.5)
    if sys.platform.startswith("win"):
        try:
            subprocess.Popen(["cmd", "/c", "start", "", "msedge", url], creationflags=0x08000000)
            return
        except OSError:
            pass
    import webbrowser

    webbrowser.open(url)


def cmd_run(args) -> None:
    import uvicorn

    settings = get_settings()
    settings.ensure_dirs()
    from app.main import create_app

    app = create_app()
    url = f"http://{settings.host}:{settings.port}"
    pid_file = _pid_file()
    pid_file.write_text(str(os.getpid()))
    print(f"\n  ELN läuft unter {url}\n  Beenden: Fenster schließen, Strg+C oder stop.bat\n")
    if settings.open_browser and not args.no_browser:
        threading.Thread(target=_open_browser, args=(url,), daemon=True).start()
    try:
        uvicorn.run(app, host=settings.host, port=settings.port, log_level="warning", proxy_headers=False)
    finally:
        pid_file.unlink(missing_ok=True)


def cmd_stop(_args) -> None:
    pid_file = _pid_file()
    if not pid_file.exists():
        print("Keine laufende Instanz gefunden.")
        return
    pid = int(pid_file.read_text().strip())
    try:
        if sys.platform.startswith("win"):
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], check=False)
        else:
            os.kill(pid, signal.SIGTERM)
        print(f"ELN (Prozess {pid}) beendet.")
    except ProcessLookupError:
        print("Prozess lief nicht mehr.")
    pid_file.unlink(missing_ok=True)


def cmd_backup(_args) -> None:
    from app.services.backup import create_backup

    r = create_backup("manuell", getpass.getuser())
    print(("OK: " if r["ok"] else "FEHLER: ") + f"{r['path']} – {r['message']}")
    sys.exit(0 if r["ok"] else 1)


def cmd_verify_backup(args) -> None:
    from app.services.backup import verify_backup

    r = verify_backup(Path(args.zip))
    print(("OK: " if r["ok"] else "FEHLER: ") + r["message"])
    sys.exit(0 if r["ok"] else 1)


def cmd_restore(args) -> None:
    from app.services.backup import restore_backup

    if _pid_file().exists():
        print("WARNUNG: Die Anwendung scheint zu laufen. Bitte zuerst mit stop.bat beenden.")
        if not args.yes:
            return
    print(f"ACHTUNG: Datenbank und Dateiablage werden durch den Stand aus {args.zip} ersetzt.")
    print("Der aktuelle Stand wird vorher automatisch gesichert.")
    if not args.yes and input("Zum Fortfahren WIEDERHERSTELLEN eingeben: ").strip() != "WIEDERHERSTELLEN":
        print("Abgebrochen.")
        return
    r = restore_backup(Path(args.zip), getpass.getuser())
    print(r["message"])


def cmd_verify_audit(_args) -> None:
    from app.db import session_scope
    from app.services.audit import verify_chain

    with session_scope() as db:
        r = verify_chain(db)
    print(("OK: " if r["ok"] else "FEHLER: ") + r["message"])
    sys.exit(0 if r["ok"] else 1)


def cmd_new_module(args) -> None:
    key = args.key.strip().lower()
    if not key.isidentifier() or key.startswith("_"):
        print("Der Schlüssel muss ein gültiger Python-Bezeichner sein (z. B. schmelzindex).")
        sys.exit(1)
    src = BASE / "app" / "modules" / "_template"
    dst = BASE / "app" / "modules" / key
    if dst.exists():
        print(f"Modul {key} existiert bereits.")
        sys.exit(1)
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__"))
    for p in dst.rglob("*"):
        if p.is_file() and p.suffix in (".py", ".html"):
            p.write_text(p.read_text(encoding="utf-8").replace("beispielmodul", key).replace("Beispielmodul", key.capitalize()),
                         encoding="utf-8")
    tpl_dir = dst / "templates" / "beispielmodul"
    if tpl_dir.exists():
        tpl_dir.rename(dst / "templates" / key)
    print(f"Modul angelegt: {dst}\nNächste Schritte: module.py anpassen, ggf. Migration erzeugen "
          f"(siehe docs/PLUGIN_ENTWICKLUNG.md), Anwendung neu starten, Modul unter Administration → Module aktivieren.")


def main() -> None:
    parser = argparse.ArgumentParser(description="ELN Verwaltung")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init")
    p.add_argument("--username")
    p.add_argument("--full-name")
    p.set_defaults(func=cmd_init)
    sub.add_parser("migrate").set_defaults(func=cmd_migrate)
    sub.add_parser("needs-setup").set_defaults(func=cmd_needs_setup)
    p = sub.add_parser("create-admin")
    p.add_argument("--username")
    p.add_argument("--full-name")
    p.set_defaults(func=cmd_create_admin)
    p = sub.add_parser("seed-demo")
    p.add_argument("--password")
    p.set_defaults(func=cmd_seed_demo)
    p = sub.add_parser("run")
    p.add_argument("--no-browser", action="store_true")
    p.set_defaults(func=cmd_run)
    sub.add_parser("stop").set_defaults(func=cmd_stop)
    sub.add_parser("backup").set_defaults(func=cmd_backup)
    p = sub.add_parser("verify-backup")
    p.add_argument("zip")
    p.set_defaults(func=cmd_verify_backup)
    p = sub.add_parser("restore")
    p.add_argument("zip")
    p.add_argument("--yes", action="store_true", help="ohne Rückfrage (nur für Skripte)")
    p.set_defaults(func=cmd_restore)
    sub.add_parser("verify-audit").set_defaults(func=cmd_verify_audit)
    p = sub.add_parser("new-module")
    p.add_argument("key")
    p.set_defaults(func=cmd_new_module)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
