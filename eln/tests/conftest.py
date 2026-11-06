"""Testumgebung: jede Testfunktion erhält ein eigenes, leeres Datenverzeichnis."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config, db as db_module  # noqa: E402
from app.core import security  # noqa: E402

security.PBKDF2_ITERATIONS = 1000  # nur für schnelle Tests
PASSWORD = "Testpasswort1!"
ROLES = {"admin": ["admin"], "leitung": ["leitung"], "wiss": ["wissenschaftler"], "labor": ["labor"],
         "pruefer": ["pruefer"], "pruefer2": ["pruefer"], "leser": ["leser"]}


@pytest.fixture()
def env(tmp_path, monkeypatch):
    for key in list(__import__("os").environ):
        if key.startswith("ELN_"):
            monkeypatch.delenv(key, raising=False)
    settings = config.load_settings({"ELN_DATA_DIR": str(tmp_path / "data"),
                                     "ELN_BACKUP_DIR": str(tmp_path / "backups"),
                                     "ELN_OPEN_BROWSER": "0"})
    settings.env_file = tmp_path / "nicht-vorhanden.env"
    config.set_settings(settings)
    db_module.reset_engine()
    from app.bootstrap import init_database
    from app.core.modules import get_registry
    from app.services import auth
    from app.services.audit import SYSTEM

    get_registry().invalidate()
    init_database()
    with db_module.session_scope() as db:
        for name, roles in ROLES.items():
            auth.create_user(db, SYSTEM, username=name, full_name=f"Test {name}", password=PASSWORD, role_keys=roles)
    yield settings
    db_module.reset_engine()


@pytest.fixture()
def app(env):
    from app.main import create_app

    return create_app(run_init=False)


class Client:
    """TestClient mit Anmeldung und automatischem CSRF-Token."""

    def __init__(self, app, username: str | None = None):
        from fastapi.testclient import TestClient

        self.c = TestClient(app, raise_server_exceptions=True)
        self.csrf = ""
        if username:
            self.login(username)

    def login(self, username: str, password: str = PASSWORD):
        r = self.c.post("/login", data={"username": username, "password": password, "next": "/"},
                        follow_redirects=False)
        assert r.status_code == 303, r.text
        self.refresh_csrf()
        return r

    def refresh_csrf(self):
        page = self.c.get("/konto").text
        m = re.search(r'name="csrf-token" content="([^"]+)"', page)
        self.csrf = m.group(1) if m else ""

    def get(self, url, **kw):
        return self.c.get(url, **kw)

    def post(self, url, data=None, files=None, follow=False, **kw):
        data = dict(data or {})
        data.setdefault("csrf_token", self.csrf)
        return self.c.post(url, data=data, files=files, follow_redirects=follow, **kw)


@pytest.fixture()
def client_factory(app):
    return lambda username=None: Client(app, username)


@pytest.fixture()
def dbs(env):
    s = db_module.SessionLocal()
    yield s
    s.close()


def user(db, username):
    from app.models import User

    return db.query(User).filter_by(username=username).one()


def actor(db, username):
    from app.services.audit import Actor

    return Actor(user(db, username), "127.0.0.1")


@pytest.fixture()
def sample_data(env):
    """Auftrag, Material, Charge, Gerät und Versuch für mehrere Tests."""
    from app.services import records

    with db_module.session_scope() as db:
        a = actor(db, "wiss")
        adm = actor(db, "admin")
        mat = records.create_record(db, adm, "material", {"name": "Polypropylen", "material_number": "100230",
                                                          "material_type": "Polymer", "status": "aktiv"})
        mat2 = records.create_record(db, adm, "material", {"name": "Antioxidans", "material_number": "200110",
                                                           "material_type": "Antioxidans", "status": "aktiv"})
        batch = records.create_record(db, adm, "batch", {"material_id": mat.id, "batch_number": "CH4711",
                                                         "status": "freigegeben"})
        dev = records.create_record(db, adm, "device", {"name": "Leistritz ZSE 27 MAXX", "device_type": "Extruder",
                                                        "status": "betriebsbereit"})
        order = records.create_record(db, a, "order", {
            "title": "Stabilisierung PP", "client": "Produktmanagement", "priority": "normal",
            "responsible_id": a.user_id, "status": "offen", "confidentiality": "intern",
            "task_description": "Vergleich zweier AO-Pakete"})
        exp = records.create_record(db, a, "experiment", {
            "title": "Compoundierung Referenz", "order_id": order.id, "experiment_type": "Rezepturentwicklung",
            "department": "Compoundierung", "responsible_id": a.user_id, "objective": "Referenz herstellen",
            "devices": [dev.id], "materials": [mat.id], "batches": [batch.id]})
        ids = {"material": mat.id, "material2": mat2.id, "batch": batch.id, "device": dev.id, "order": order.id,
               "experiment": exp.id}
    return ids
