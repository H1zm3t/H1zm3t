"""Prüf- und Freigabeprozess, Sperre, Revisionen, Snapshots."""
import hashlib

import pytest
from conftest import actor

from app.models import ApprovalRecord, Experiment, RecordSnapshot
from app.services import records, workflow
from app.services.records import RecordError
from app.services.system_settings import set_setting


def _ready(db, eid):
    e = db.get(Experiment, eid)
    a = actor(db, "wiss")
    workflow.perform(db, a, e, "status:in Bearbeitung")
    with pytest.raises(RecordError):
        workflow.perform(db, a, e, "complete")  # Ergebnisse fehlen
    e.results, e.conclusion = "Ergebnis", "Schluss"
    workflow.perform(db, a, e, "complete")
    workflow.perform(db, a, e, "submit")
    return e


def test_full_approval_flow(dbs, sample_data):
    e = _ready(dbs, sample_data["experiment"])
    assert e.status == "zur Prüfung" and e.locked
    with pytest.raises(RecordError):
        records.update_record(dbs, actor(dbs, "wiss"), "experiment", e, {"title": "neu"}, "x")
    workflow.perform(dbs, actor(dbs, "pruefer"), e, "review_approve")
    assert e.status == "freigegeben" and e.locked and e.approved_by_id is not None
    snaps = dbs.query(RecordSnapshot).filter_by(entity_id=e.id).all()
    assert len(snaps) == 2
    for s in snaps:
        assert hashlib.sha256(s.data_json.encode()).hexdigest() == s.sha256
    assert dbs.query(ApprovalRecord).filter_by(entity_id=e.id).count() == 2


def test_self_review_blocked(dbs, sample_data):
    from app.models import Role

    e = _ready(dbs, sample_data["experiment"])
    wiss = actor(dbs, "wiss")
    wiss.user.roles.append(dbs.query(Role).filter_by(key="pruefer").one())
    with pytest.raises(RecordError, match="Unabhängige"):
        workflow.perform(dbs, wiss, e, "review_approve")
    set_setting(dbs, "require_independent_review", "0")
    workflow.perform(dbs, wiss, e, "review_approve")
    assert e.status == "freigegeben"


def test_reject_requires_reason(dbs, sample_data):
    e = _ready(dbs, sample_data["experiment"])
    with pytest.raises(RecordError):
        workflow.perform(dbs, actor(dbs, "pruefer"), e, "review_reject")
    workflow.perform(dbs, actor(dbs, "pruefer"), e, "review_reject", "Kalibrierschein fehlt")
    assert e.status == "Korrektur erforderlich" and not e.locked
    workflow.perform(dbs, actor(dbs, "wiss"), e, "status:in Bearbeitung")
    assert e.status == "in Bearbeitung"


def test_manager_approval_and_revision(dbs, sample_data):
    set_setting(dbs, "require_manager_approval", "1")
    e = _ready(dbs, sample_data["experiment"])
    workflow.perform(dbs, actor(dbs, "pruefer"), e, "review_approve")
    assert e.status == "geprüft"
    with pytest.raises(RecordError):
        workflow.perform(dbs, actor(dbs, "pruefer"), e, "approve")  # kein Freigaberecht
    workflow.perform(dbs, actor(dbs, "leitung"), e, "approve")
    assert e.status == "freigegeben"
    with pytest.raises(RecordError):
        workflow.perform(dbs, actor(dbs, "wiss"), e, "new_revision")  # Grund fehlt
    workflow.perform(dbs, actor(dbs, "wiss"), e, "new_revision", "Nachmessung ergänzt")
    assert e.revision == 2 and e.status == "in Bearbeitung" and not e.locked
    # Änderungen ab Revision 2 erfordern einen Grund
    with pytest.raises(RecordError, match="Änderungsgrund"):
        records.update_record(dbs, actor(dbs, "wiss"), "experiment", e, {"title": "neu"}, None)
    records.update_record(dbs, actor(dbs, "wiss"), "experiment", e, {"title": "neu"}, "Titel präzisiert")
    # freigegebener Stand Rev. 1 bleibt als Snapshot erhalten
    rev1 = [s for s in dbs.query(RecordSnapshot).filter_by(entity_id=e.id) if s.revision == 1 and s.kind == "Freigabe"]
    assert rev1 and rev1[0].data["title"] == "Compoundierung Referenz"


def test_workflow_via_http(client_factory, dbs, sample_data):
    eid = sample_data["experiment"]
    c = client_factory("wiss")
    assert c.post(f"/versuche/{eid}/workflow", {"action": "status:in Bearbeitung"}).status_code == 303
    e = dbs.get(Experiment, eid)
    e.results, e.conclusion = "R", "S"
    dbs.commit()
    for action in ("complete", "submit"):
        assert c.post(f"/versuche/{eid}/workflow", {"action": action}).status_code == 303
    assert client_factory("leser").post(f"/versuche/{eid}/workflow", {"action": "review_approve"}).status_code == 403
    assert client_factory("pruefer").post(f"/versuche/{eid}/workflow", {"action": "review_approve"}).status_code == 303
    dbs.expire_all()
    assert dbs.get(Experiment, eid).status == "freigegeben"
    assert c.get(f"/versuche/{eid}/bearbeiten").status_code == 400
