"""Zentrale Suche über alle Datensatztypen, Anhänge und Fachmodule.

Die Suche verwendet parametrisierte LIKE-Abfragen (SQL-Injection-sicher).
Für große Datenmengen kann ``search`` später durch eine Volltextsuche
(SQLite FTS5 / PostgreSQL tsvector) ersetzt werden, ohne die Oberfläche zu ändern.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..core.formatting import parse_date
from ..core.modules import SearchHit, get_registry
from ..models import Attachment, Batch, Experiment, Material, Order, User
from .entities import ENTITY_DEFS, can_see, entity_url, get_entity, restricted_order_ids
from .files import can_view_attachment

SEARCHABLE_TYPES = ["order", "project", "experiment", "series", "recipe", "material", "batch", "sample", "device",
                    "method", "measurement", "task"]
PAGE_SIZE = 25
SORTS = {"relevance": "Relevanz", "date_desc": "Neueste zuerst", "date_asc": "Älteste zuerst", "code": "Kennung"}


@dataclass
class SearchParams:
    q: str = ""
    types: list[str] = field(default_factory=list)
    status: str = ""
    responsible_id: int | None = None
    date_from: date | None = None
    date_to: date | None = None
    experiment_type: str = ""
    department: str = ""
    device_id: int | None = None
    material_id: int | None = None
    batch_id: int | None = None
    client: str = ""
    tags: str = ""
    include_files: bool = True
    sort: str = "relevance"
    page: int = 1

    @classmethod
    def from_mapping(cls, m) -> "SearchParams":
        def get(k, default=""):
            v = m.get(k) if hasattr(m, "get") else None
            return v if v not in (None, "") else default

        def int_or_none(k):
            try:
                return int(get(k)) if get(k) else None
            except ValueError:
                return None

        def date_or_none(k):
            try:
                return parse_date(get(k)) if get(k) else None
            except (ValueError, TypeError):
                return None

        types = m.getlist("types") if hasattr(m, "getlist") else list(m.get("types") or [])
        try:
            page = max(1, int(get("page", 1)))
        except ValueError:
            page = 1
        return cls(
            q=str(get("q")).strip()[:200], types=[t for t in types if t in SEARCHABLE_TYPES],
            status=str(get("status")), responsible_id=int_or_none("responsible_id"),
            date_from=date_or_none("date_from"), date_to=date_or_none("date_to"),
            experiment_type=str(get("experiment_type")), department=str(get("department")),
            device_id=int_or_none("device_id"), material_id=int_or_none("material_id"),
            batch_id=int_or_none("batch_id"), client=str(get("client")).strip(), tags=str(get("tags")).strip(),
            include_files=str(get("include_files", "1")) in ("1", "on", "true"),
            sort=get("sort", "relevance") if get("sort", "relevance") in SORTS else "relevance", page=page,
        )

    def to_dict(self) -> dict:
        return {
            "q": self.q, "types": self.types, "status": self.status, "responsible_id": self.responsible_id,
            "date_from": self.date_from.isoformat() if self.date_from else "",
            "date_to": self.date_to.isoformat() if self.date_to else "",
            "experiment_type": self.experiment_type, "department": self.department, "device_id": self.device_id,
            "material_id": self.material_id, "batch_id": self.batch_id, "client": self.client, "tags": self.tags,
            "include_files": self.include_files, "sort": self.sort,
        }

    @property
    def has_filters(self) -> bool:
        return any([self.status, self.responsible_id, self.date_from, self.date_to, self.experiment_type,
                    self.department, self.device_id, self.material_id, self.batch_id, self.client, self.tags])


def _like(term: str) -> str:
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _snippet(obj, attrs, words: list[str]) -> str:
    for a in attrs:
        val = getattr(obj, a, None)
        if not val or not isinstance(val, str):
            continue
        low = val.lower()
        for w in words:
            pos = low.find(w.lower())
            if pos >= 0:
                start = max(0, pos - 60)
                end = min(len(val), pos + len(w) + 80)
                return ("…" if start else "") + val[start:end].replace("\n", " ") + ("…" if end < len(val) else "")
    return ""


def _score(obj, attrs, words) -> int:
    score = 0
    for w in words:
        wl = w.lower()
        if (getattr(obj, "code", "") or "").lower() == wl:
            score += 100
        for i, a in enumerate(attrs):
            v = getattr(obj, a, None)
            if isinstance(v, str) and wl in v.lower():
                score += max(1, 10 - i)
    return score


def _apply_filters(p: SearchParams, key: str, model, q):
    if p.status and hasattr(model, "status"):
        q = q.filter(model.status == p.status)
    if p.responsible_id:
        for attr in ("responsible_id", "assignee_id"):
            if hasattr(model, attr):
                q = q.filter(getattr(model, attr) == p.responsible_id)
                break
        else:
            return None
    date_col = model.created_at
    if p.date_from:
        q = q.filter(date_col >= datetime.combine(p.date_from, datetime.min.time()))
    if p.date_to:
        q = q.filter(date_col < datetime.combine(p.date_to + timedelta(days=1), datetime.min.time()))
    if p.experiment_type:
        if key != "experiment":
            return None
        q = q.filter(Experiment.experiment_type == p.experiment_type)
    if p.department:
        if key != "experiment":
            return None
        q = q.filter(Experiment.department == p.department)
    if p.device_id:
        if key == "experiment":
            q = q.filter(Experiment.devices.any(id=p.device_id))
        elif key == "measurement":
            q = q.filter(model.device_id == p.device_id)
        elif key == "device":
            q = q.filter(model.id == p.device_id)
        else:
            return None
    if p.material_id:
        if key == "experiment":
            q = q.filter(or_(Experiment.materials.any(id=p.material_id),
                             Experiment.recipe_id.in_(_recipe_ids_with_material(q.session, p.material_id))))
        elif key in ("sample", "batch"):
            q = q.filter(model.material_id == p.material_id)
        elif key == "material":
            q = q.filter(model.id == p.material_id)
        elif key == "recipe":
            q = q.filter(model.id.in_(_recipe_ids_with_material(q.session, p.material_id)))
        else:
            return None
    if p.batch_id:
        if key == "experiment":
            q = q.filter(Experiment.batches.any(id=p.batch_id))
        elif key == "sample":
            q = q.filter(model.batch_id == p.batch_id)
        elif key == "batch":
            q = q.filter(model.id == p.batch_id)
        else:
            return None
    if p.client:
        if key == "order":
            q = q.filter(or_(Order.client.ilike(_like(p.client), escape="\\"),
                             Order.customer.ilike(_like(p.client), escape="\\")))
        elif key == "experiment":
            q = q.join(Order, Experiment.order_id == Order.id).filter(
                or_(Order.client.ilike(_like(p.client), escape="\\"), Order.customer.ilike(_like(p.client), escape="\\")))
        else:
            return None
    if p.tags:
        if not hasattr(model, "tags"):
            return None
        for t in [t.strip() for t in p.tags.split(",") if t.strip()]:
            q = q.filter(model.tags.ilike(_like(t), escape="\\"))
    return q


def _recipe_ids_with_material(db: Session, material_id: int) -> list[int]:
    from ..models import RecipeItem

    return [r[0] for r in db.query(RecipeItem.recipe_id).filter(RecipeItem.material_id == material_id).distinct()]


def search(db: Session, user: User, p: SearchParams) -> dict:
    words = [w for w in p.q.split() if w][:8]
    types = p.types or SEARCHABLE_TYPES
    hidden_orders = restricted_order_ids(db, user)
    hits: list[tuple[int, SearchHit]] = []
    counts: dict[str, int] = {}

    for key in types:
        d = ENTITY_DEFS[key]
        model = d.model
        q = db.query(model)
        for w in words:
            conds = [getattr(model, a).ilike(_like(w), escape="\\") for a in d.search_attrs]
            if key == "batch":
                q = q.join(Material, Batch.material_id == Material.id) if w == words[0] else q
                conds += [Material.name.ilike(_like(w), escape="\\"),
                          Material.material_number.ilike(_like(w), escape="\\")]
            q = q.filter(or_(*conds))
        q = _apply_filters(p, key, model, q)
        if q is None:
            continue
        if hidden_orders:
            if key == "order":
                q = q.filter(~model.id.in_(hidden_orders))
            elif hasattr(model, "order_id"):
                q = q.filter(or_(model.order_id.is_(None), ~model.order_id.in_(hidden_orders)))
        rows = q.limit(500).all()
        for obj in rows:
            if key in ("measurement",) and not can_see(db, user, key, obj):
                continue
            title = getattr(obj, d.title_attr, None) or obj.code
            dt = getattr(obj, "created_at", None)
            hits.append((
                _score(obj, d.search_attrs, words) if words else 0,
                SearchHit(entity_type=key, entity_id=obj.id, code=obj.code, title=str(title), url=d.url_for(obj),
                          snippet=_snippet(obj, d.search_attrs[1:], words) if words else "",
                          status=getattr(obj, d.status_field, None) if d.status_field else None, date=dt,
                          type_label=d.label),
            ))
            counts[key] = counts.get(key, 0) + 1

    if p.include_files and words and not p.has_filters:
        q = db.query(Attachment).filter(Attachment.status != "ungültig")
        for w in words:
            q = q.filter(or_(Attachment.original_filename.ilike(_like(w), escape="\\"),
                             Attachment.description.ilike(_like(w), escape="\\"),
                             Attachment.caption.ilike(_like(w), escape="\\"),
                             Attachment.extracted_text.ilike(_like(w), escape="\\")))
        for att in q.limit(300).all():
            if not can_view_attachment(user, att):
                continue
            parent = get_entity(db, att.entity_type, att.entity_id)
            if parent is None or (att.entity_type in ENTITY_DEFS and not can_see(db, user, att.entity_type, parent)):
                continue
            snippet = _snippet(att, ("description", "caption", "extracted_text"), words)
            hits.append((
                _score(att, ("original_filename", "description", "caption", "extracted_text"), words),
                SearchHit(entity_type="attachment", entity_id=att.id, code=getattr(parent, "code", ""),
                          title=att.original_filename, url=entity_url(att.entity_type, att.entity_id) + "#anhaenge",
                          snippet=snippet, status=att.status, date=att.created_at, type_label="Anhang"),
            ))
            counts["attachment"] = counts.get("attachment", 0) + 1

    if words and not p.has_filters and not p.types:
        for module in get_registry().enabled(db):
            for hit in module.search(db, p.q, user):
                hits.append((5, hit))
                counts[hit.entity_type] = counts.get(hit.entity_type, 0) + 1

    if p.sort == "date_desc":
        hits.sort(key=lambda h: h[1].date or datetime.min, reverse=True)
    elif p.sort == "date_asc":
        hits.sort(key=lambda h: h[1].date or datetime.min)
    elif p.sort == "code":
        hits.sort(key=lambda h: h[1].code)
    else:
        hits.sort(key=lambda h: (h[0], h[1].date or datetime.min), reverse=True)

    total = len(hits)
    pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page = min(p.page, pages)
    start = (page - 1) * PAGE_SIZE
    return {"hits": [h[1] for h in hits[start:start + PAGE_SIZE]], "total": total, "page": page, "pages": pages,
            "counts": counts}
