"""Datensicherung und Wiederherstellung."""
import io
import json
import zipfile
from pathlib import Path

from app.db import session_scope
from app.models import Material
from app.services import backup


def test_backup_complete_and_verified(client_factory, env, sample_data):
    c = client_factory("wiss")
    c.post("/anhaenge/upload", {"entity_type": "experiment", "entity_id": str(sample_data["experiment"])},
           files=[("files", ("a.txt", io.BytesIO(b"Inhalt"), "text/plain"))])
    result = backup.create_backup("manuell", "test")
    assert result["ok"], result["message"]
    path = Path(result["path"])
    assert path.parent == env.backup_dir and path.name.startswith("eln_sicherung_")
    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        manifest = json.loads(zf.read("manifest.json"))
    assert "database/eln.db" in names and "config/modules.json" in names
    assert any(n.startswith("files/") for n in names)
    assert len(manifest["files"]) == result["file_count"]
    assert backup.verify_backup(path)["ok"]
    assert backup.read_log()[0]["status"] == "vollständig"


def test_corrupted_backup_detected(env, sample_data, tmp_path):
    result = backup.create_backup("manuell", "test")
    src = Path(result["path"])
    bad = env.backup_dir / "eln_sicherung_kaputt.zip"
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(bad, "w") as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "config/modules.json":
                data = b"{}"
            zout.writestr(item, data)
    assert not backup.verify_backup(bad)["ok"]


def test_restore(env, sample_data):
    result = backup.create_backup("manuell", "test")
    with session_scope() as db:
        db.query(Material).filter_by(material_number="200110").one().name = "nach Sicherung geändert"
    restored = backup.restore_backup(Path(result["path"]), "admin")
    assert restored["ok"]
    with session_scope() as db:
        assert db.query(Material).filter_by(material_number="200110").one().name == "Antioxidans"
    assert any("vor-wiederherstellung" in b["filename"] for b in backup.list_backups())


def test_restore_requires_admin(client_factory, env, sample_data):
    name = backup.create_backup("manuell", "test")["filename"]
    c = client_factory("leitung")
    assert c.get("/admin/sicherung").status_code == 200
    r = c.post("/admin/sicherung/wiederherstellen", {"filename": name, "confirm": "WIEDERHERSTELLEN"})
    assert r.status_code == 403
    r = client_factory("admin").post("/admin/sicherung/wiederherstellen", {"filename": name, "confirm": "nein"})
    assert r.status_code == 303 and "/admin/sicherung" in r.headers["location"]
    r = client_factory("admin").post("/admin/sicherung/wiederherstellen", {"filename": "../x.zip",
                                                                           "confirm": "WIEDERHERSTELLEN"})
    assert r.status_code == 400
