"""Rollen und Rechte, Vertraulichkeit."""
from conftest import user


def test_reader_cannot_create(client_factory):
    c = client_factory("leser")
    assert c.get("/auftraege").status_code == 200
    assert c.get("/auftraege/neu").status_code == 403
    r = c.post("/auftraege/neu", {"title": "x"})
    assert r.status_code == 403


def test_lab_cannot_manage_master_data_or_users(client_factory):
    c = client_factory("labor")
    assert c.get("/materialien/neu").status_code == 403
    assert c.get("/admin/benutzer").status_code == 403
    assert c.get("/audit").status_code == 403
    assert c.get("/admin/sicherung").status_code == 403


def test_reviewer_can_view_audit_but_not_edit(client_factory, sample_data):
    c = client_factory("pruefer")
    assert c.get("/audit").status_code == 200
    assert c.get(f"/versuche/{sample_data['experiment']}/bearbeiten").status_code == 403


def test_user_with_multiple_roles(dbs):
    from app.models import Role

    u = user(dbs, "labor")
    u.roles.append(dbs.query(Role).filter_by(key="pruefer").one())
    dbs.commit()
    assert u.has("review") and u.has("create") and not u.has("manage_users")


def test_role_permissions_editable(client_factory, dbs):
    c = client_factory("admin")
    form = {f"leser:{p}": "1" for p in ("view", "export")}
    for r in ("leitung", "wissenschaftler", "labor", "pruefer"):
        form[f"{r}:view"] = "1"
    assert c.post("/admin/rollen", form).status_code == 303
    from app.models import Role

    dbs.expire_all()
    assert dbs.query(Role).filter_by(key="leser").one().permissions == {"view", "export"}


def test_strictly_confidential_order_hidden(client_factory, sample_data, dbs):
    from app.models import Order

    o = dbs.get(Order, sample_data["order"])
    o.confidentiality = "streng vertraulich"
    dbs.commit()
    assert client_factory("labor").get(f"/auftraege/{o.id}").status_code == 403
    assert client_factory("leitung").get(f"/auftraege/{o.id}").status_code == 200
    assert client_factory("wiss").get(f"/auftraege/{o.id}").status_code == 200  # verantwortlich
    assert "Stabilisierung PP" not in client_factory("labor").get("/suche?q=Stabilisierung").text
