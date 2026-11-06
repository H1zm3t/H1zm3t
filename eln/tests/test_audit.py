"""Audit Trail: Vollständigkeit, Unveränderlichkeit, Hash-Kette, Ansicht."""
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DatabaseError

from app.models import AuditLog
from app.services import audit


def test_entries_written_with_user_ip_version(dbs, sample_data):
    e = dbs.query(AuditLog).filter_by(entity_type="experiment", action="create").one()
    assert e.username == "wiss" and e.ip_address == "127.0.0.1" and e.record_version == 1
    assert e.entry_hash and e.entity_code.startswith("V-")


def test_chain_valid(dbs, sample_data):
    assert audit.verify_chain(dbs)["ok"]


def test_update_and_delete_blocked_by_database(dbs, sample_data):
    with pytest.raises(DatabaseError):
        dbs.execute(text("UPDATE audit_log SET new_value='manipuliert' WHERE id=1"))
    dbs.rollback()
    with pytest.raises(DatabaseError):
        dbs.execute(text("DELETE FROM audit_log WHERE id=1"))
    dbs.rollback()


def test_tampering_detected(dbs, sample_data):
    dbs.execute(text("DROP TRIGGER audit_log_no_update"))
    dbs.execute(text("UPDATE audit_log SET new_value='manipuliert' WHERE id=3"))
    dbs.commit()
    result = audit.verify_chain(dbs)
    assert not result["ok"] and result["broken_id"] == 3


def test_audit_view_filters_and_readonly(client_factory, sample_data):
    c = client_factory("admin")
    r = c.get("/audit?typ=experiment&aktion=create")
    assert r.status_code == 200 and "V-" in r.text
    r = c.get("/audit?benutzer=wiss&von=01.01.2020&bis=31.12.2099")
    assert r.status_code == 200
    assert c.post("/audit", {}).status_code == 405  # keine schreibende Route
    assert "Kette intakt" in c.get("/audit/pruefen", follow_redirects=True).text
