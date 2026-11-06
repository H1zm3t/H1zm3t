"""Zentrale Suche."""
import io

from conftest import user

from app.models import Experiment
from app.services.search import SearchParams, search


def test_free_text_and_filters(dbs, sample_data):
    e = dbs.get(Experiment, sample_data["experiment"])
    e.observations = "Strangabriss nach 12 Minuten"
    dbs.commit()
    u = user(dbs, "wiss")
    res = search(dbs, u, SearchParams(q="strangabriss"))
    assert any(h.code == e.code for h in res["hits"])
    res = search(dbs, u, SearchParams(q="100230"))
    assert any(h.entity_type == "material" for h in res["hits"])
    res = search(dbs, u, SearchParams(q="CH4711"))
    assert any(h.entity_type == "batch" for h in res["hits"])
    res = search(dbs, u, SearchParams(device_id=sample_data["device"], types=["experiment"]))
    assert [h.code for h in res["hits"]] == [e.code]
    res = search(dbs, u, SearchParams(q="Referenz", status="freigegeben"))
    assert not any(h.code == e.code for h in res["hits"])
    res = search(dbs, u, SearchParams(client="Produktmanagement", types=["order", "experiment"]))
    assert {h.entity_type for h in res["hits"]} == {"order", "experiment"}


def test_attachment_content_search_and_pagination(client_factory, dbs, sample_data):
    c = client_factory("wiss")
    c.post("/anhaenge/upload", {"entity_type": "experiment", "entity_id": str(sample_data["experiment"])},
           files=[("files", ("notiz.txt", io.BytesIO("Viskositätssprung bei 230 °C".encode()), "text/plain"))])
    r = c.get("/suche?q=Viskositätssprung")
    assert "notiz.txt" in r.text
    r = c.get("/suche?q=%25")  # Platzhalterzeichen werden nicht als Wildcard interpretiert
    assert r.status_code == 200


def test_saved_search(client_factory, dbs, sample_data):
    from app.models import SavedQuery

    c = client_factory("wiss")
    assert c.post("/suche/speichern", {"name": "Meine PP-Suche", "query": "q=PP"}).status_code == 303
    sq = dbs.query(SavedQuery).one()
    r = c.get(f"/suche/gespeichert/{sq.id}", follow_redirects=False)
    assert r.headers["location"] == "/suche?q=PP"
