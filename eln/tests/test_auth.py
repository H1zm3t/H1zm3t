"""Anmeldung, Passwörter, Sitzungen, Sperre, CSRF."""
from conftest import PASSWORD, user

from app.core.security import hash_password, verify_password
from app.models import AuditLog, User


def test_password_hash_not_plaintext(dbs):
    u = user(dbs, "admin")
    assert PASSWORD not in u.password_hash
    assert u.password_hash.startswith("pbkdf2_sha256$")
    assert verify_password(PASSWORD, u.password_hash)
    assert not verify_password("falsch", u.password_hash)
    assert hash_password("abc") != hash_password("abc")  # Salt


def test_login_and_logout(client_factory):
    c = client_factory()
    assert c.get("/", follow_redirects=False).status_code == 303
    c.login("wiss")
    r = c.get("/")
    assert r.status_code == 200 and "Dashboard" in r.text
    c.post("/logout")
    assert c.get("/", follow_redirects=False).status_code == 303


def test_wrong_password_and_lockout(client_factory, dbs):
    c = client_factory()
    for _ in range(5):
        r = c.c.post("/login", data={"username": "labor", "password": "falsch"})
        assert r.status_code == 401
    r = c.c.post("/login", data={"username": "labor", "password": PASSWORD})
    assert r.status_code == 401 and "gesperrt" in r.text
    dbs.expire_all()
    assert user(dbs, "labor").locked_until is not None
    actions = [a.action for a in dbs.query(AuditLog).filter(AuditLog.entity_type == "security")]
    assert "login_failed" in actions and "account_locked" in actions


def test_csrf_required(client_factory):
    c = client_factory("wiss")
    r = c.c.post("/kommentare", data={"entity_type": "order", "entity_id": "1", "text": "x"}, follow_redirects=False)
    assert r.status_code == 403


def test_session_timeout(client_factory, dbs):
    from datetime import timedelta

    from app.models import UserSession

    c = client_factory("wiss")
    s = dbs.query(UserSession).first()
    s.last_seen = s.last_seen - timedelta(hours=5)
    dbs.commit()
    assert c.get("/", follow_redirects=False).status_code == 303


def test_new_user_must_change_password(client_factory, dbs):
    c = client_factory("admin")
    r = c.post("/admin/benutzer/neu", {"username": "neu.user", "full_name": "Neu", "password": "Startpasswort9",
                                       "roles": "labor"})
    assert r.status_code == 303
    c2 = client_factory()
    c2.login("neu.user", "Startpasswort9")
    r = c2.get("/", follow_redirects=False)
    assert r.headers["location"].startswith("/konto")
    r = c2.post("/konto", {"old_password": "Startpasswort9", "new_password": "NeuesPasswort1",
                           "new_password2": "NeuesPasswort1"})
    assert r.status_code == 303
    assert c2.get("/").status_code == 200
    dbs.expire_all()
    assert dbs.query(User).filter_by(username="neu.user").one().must_change_password is False


def test_weak_password_rejected(dbs):
    import pytest

    from app.services import auth
    from app.services.audit import SYSTEM

    with pytest.raises(auth.AuthError):
        auth.create_user(dbs, SYSTEM, username="x", full_name="X", password="kurz", role_keys=["leser"])


def test_rendered_forms_contain_valid_csrf_token(client_factory, sample_data, dbs):
    """Regression: Formulare in Makros müssen das echte Sitzungstoken enthalten (Browser sendet nur dieses)."""
    import re

    from app.models import Experiment

    c = client_factory("wiss")
    page = c.get(f"/versuche/{sample_data['experiment']}").text
    tokens = set(re.findall(r'name="csrf_token" value="([^"]*)"', page))
    assert tokens == {c.csrf} and c.csrf
    r = c.c.post(f"/versuche/{sample_data['experiment']}/workflow",
                 data={"csrf_token": tokens.pop(), "action": "status:in Bearbeitung"}, follow_redirects=False)
    assert r.status_code == 303
    dbs.expire_all()
    assert dbs.get(Experiment, sample_data["experiment"]).status == "in Bearbeitung"
    for url in ("/versuche/neu", "/rezepturen", "/admin/benutzer", "/suche?q=x", "/auswertungen?dataset=tasks"):
        html = client_factory("admin").get(url).text
        assert 'name="csrf_token" value=""' not in html, url
