"""Datei-Upload, Prüfsummen, Duplikate, Sperren, Versionen."""
import hashlib
import io

from app.models import Attachment, AuditLog
from app.services import files


def _upload(c, eid, name, content, et="experiment"):
    return c.post("/anhaenge/upload", {"entity_type": et, "entity_id": str(eid), "category": ""},
                  files=[("files", (name, io.BytesIO(content), "application/octet-stream"))],
                  headers={"X-Requested-With": "fetch", "X-CSRF-Token": c.csrf})


def test_upload_checksum_and_storage(client_factory, dbs, sample_data, env):
    c = client_factory("wiss")
    content = b"Messwerte;1;2;3\n" * 100
    r = _upload(c, sample_data["experiment"], "messung.csv", content)
    assert r.status_code == 200 and r.json()["ok"]
    att = dbs.query(Attachment).one()
    assert att.sha256 == hashlib.sha256(content).hexdigest()
    assert att.size_bytes == len(content)
    assert att.stored_filename != "messung.csv" and att.stored_filename.endswith(".csv")
    path = files.absolute_path(att)
    assert path.exists() and env.files_dir in path.parents
    assert files.verify_attachment(att)
    assert "Messwerte" in (att.extracted_text or "")
    assert dbs.query(AuditLog).filter_by(action="file_upload").count() == 1
    dl = c.get(f"/anhaenge/{att.id}/download")
    assert dl.content == content


def test_duplicate_detection(client_factory, dbs, sample_data):
    c = client_factory("wiss")
    _upload(c, sample_data["experiment"], "a.txt", b"gleich")
    r = _upload(c, sample_data["order"], "b.txt", b"gleich", et="order")
    assert any("inhaltsgleich" in m for m in r.json()["messages"])
    assert dbs.query(Attachment).count() == 2


def test_blocked_files(client_factory, dbs, sample_data):
    c = client_factory("wiss")
    for name, content in (("tool.exe", b"MZ..."), ("skript.ps1", b"Write-Host"), ("start.bat", b"echo"),
                          ("rechnung.pdf.exe", b"x"), ("getarnt.txt", b"MZ\x90\x00programm")):
        r = _upload(c, sample_data["experiment"], name, content)
        assert not r.json()["ok"], name
    assert dbs.query(Attachment).count() == 0


def test_path_traversal_name_is_neutralised(client_factory, dbs, sample_data, env):
    c = client_factory("wiss")
    r = _upload(c, sample_data["experiment"], "../../../evil.txt", b"x")
    assert r.json()["ok"]
    att = dbs.query(Attachment).one()
    assert att.original_filename == "evil.txt"
    assert env.files_dir.resolve() in files.absolute_path(att).parents


def test_new_version_keeps_old(client_factory, dbs, sample_data):
    c = client_factory("wiss")
    _upload(c, sample_data["experiment"], "bericht.txt", b"v1")
    old = dbs.query(Attachment).one()
    r = c.post(f"/anhaenge/{old.id}/neue-version", {"reason": "Korrektur"},
               files=[("file", ("bericht.txt", io.BytesIO(b"v2"), "text/plain"))])
    assert r.status_code == 303
    dbs.expire_all()
    versions = dbs.query(Attachment).order_by(Attachment.id).all()
    assert [v.version for v in versions] == [1, 2] and versions[0].status == "ersetzt"
    assert files.absolute_path(versions[0]).read_bytes() == b"v1"


def test_upload_blocked_when_experiment_locked(client_factory, dbs, sample_data):
    from app.models import Experiment

    e = dbs.get(Experiment, sample_data["experiment"])
    e.locked = True
    e.status = "zur Prüfung"
    dbs.commit()
    r = _upload(client_factory("wiss"), e.id, "spaet.txt", b"x")
    assert not r.json()["ok"] and "gesperrt" in r.json()["messages"][0]


def test_invalidate_requires_permission_and_reason(client_factory, dbs, sample_data):
    _upload(client_factory("wiss"), sample_data["experiment"], "x.txt", b"x")
    att = dbs.query(Attachment).one()
    assert client_factory("wiss").post(f"/anhaenge/{att.id}/status", {"status": "ungültig", "reason": "x"}).status_code == 403
    c = client_factory("admin")
    assert c.post(f"/anhaenge/{att.id}/status", {"status": "ungültig"}).status_code == 400
    assert c.post(f"/anhaenge/{att.id}/status", {"status": "ungültig", "reason": "falsche Datei"}).status_code == 303
    dbs.expire_all()
    assert dbs.get(Attachment, att.id).status == "ungültig"


def test_size_limit(client_factory, dbs, sample_data, env):
    env.max_upload_mb = 1
    r = _upload(client_factory("wiss"), sample_data["experiment"], "gross.txt", b"x" * (1024 * 1024 + 10))
    assert not r.json()["ok"] and "maximale Größe" in r.json()["messages"][0]
