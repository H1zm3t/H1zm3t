"""Beschreibung der Kern-Datensatztypen (Felder, Listen, URLs, Rechte).

Die generischen Routen (app/web/records.py) und Importe nutzen diese
Definitionen. Spezielle Logik (Workflow, Rezepturtabelle, Messwerte) liegt in
eigenen Services.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..core import vocab
from ..core.forms import FieldSpec as F
from ..models import (
    Batch, Device, Experiment, ExperimentSeries, Material, Measurement, Method, Order, Project, Recipe,
    Sample, Task, User,
)


@dataclass
class EntityDef:
    key: str
    model: type
    label: str
    plural: str
    url: str
    fields: list[F]
    columns: list[tuple[str, str, str]]  # (pfad, bezeichnung, format)
    create_permission: str = "create"
    edit_permission: str = "edit"
    status_field: str | None = "status"
    archive_status: str | None = "archiviert"
    icon: str = "doc"
    title_attr: str = "name"
    search_attrs: tuple[str, ...] = ()
    default_values: dict = field(default_factory=dict)
    is_master_data: bool = False

    def url_for(self, obj) -> str:
        return f"{self.url}/{obj.id}"


U = "user"


def _o(values) -> tuple:
    return tuple(values)


ENTITY_DEFS: dict[str, EntityDef] = {}


def _register(d: EntityDef) -> EntityDef:
    ENTITY_DEFS[d.key] = d
    return d


_register(EntityDef(
    key="project", model=Project, label="Projekt", plural="Projekte", url="/projekte", icon="folder",
    fields=[
        F("name", "Projektname", required=True, width="full"),
        F("customer", "Kunde / Bezug"),
        F("responsible_id", "Verantwortlich", kind="ref", ref=U),
        F("status", "Status", kind="select", options=vocab.PROJECT_STATUS, required=True),
        F("tags", "Schlagwörter", kind="tags", help="Mehrere Schlagwörter durch Komma trennen."),
        F("start_date", "Beginn", kind="date"),
        F("end_date", "Ende", kind="date"),
        F("description", "Beschreibung", kind="textarea", width="full"),
    ],
    columns=[("code", "ID", "link"), ("name", "Projekt", "text"), ("customer", "Kunde", "text"),
             ("responsible.full_name", "Verantwortlich", "text"), ("status", "Status", "status"),
             ("start_date", "Beginn", "date")],
    search_attrs=("code", "name", "description", "customer", "tags"),
    default_values={"status": "aktiv"},
))

_register(EntityDef(
    key="order", model=Order, label="Auftrag", plural="Aufträge", url="/auftraege", icon="clipboard",
    title_attr="title",
    fields=[
        F("title", "Titel", required=True, width="full"),
        F("external_number", "Externe Auftragsnummer", help="z. B. Nummer aus dem Access-System oder SAP"),
        F("project_id", "Projekt", kind="ref", ref="project"),
        F("client", "Auftraggeber", required=True, help="Person oder Abteilung, die den Auftrag erteilt"),
        F("customer", "Kundenbezug", help="Endkunde, falls zutreffend"),
        F("priority", "Priorität", kind="select", options=vocab.PRIORITIES, required=True),
        F("due_date", "Gewünschter Termin", kind="date"),
        F("responsible_id", "Verantwortlich", kind="ref", ref=U, required=True),
        F("participants", "Beteiligte", kind="multi_ref", ref=U),
        F("status", "Status", kind="select", options=vocab.ORDER_STATUS, required=True),
        F("confidentiality", "Vertraulichkeit", kind="select", options=vocab.CONFIDENTIALITY, required=True,
          help="»streng vertraulich«: nur für Verantwortliche, Beteiligte, Leitung und Administration sichtbar."),
        F("tags", "Schlagwörter", kind="tags", width="full"),
        F("task_description", "Aufgabenstellung", kind="textarea", width="full", required=True),
        F("objective", "Zielsetzung", kind="textarea", width="full"),
    ],
    columns=[("code", "ID", "link"), ("external_number", "Ext. Nr.", "text"), ("title", "Titel", "text"),
             ("client", "Auftraggeber", "text"), ("responsible.full_name", "Verantwortlich", "text"),
             ("priority", "Priorität", "priority"), ("due_date", "Termin", "date"), ("status", "Status", "status")],
    search_attrs=("code", "external_number", "title", "client", "customer", "task_description", "objective", "tags"),
    default_values={"status": "offen", "priority": "normal", "confidentiality": "intern"},
))

_register(EntityDef(
    key="series", model=ExperimentSeries, label="Versuchsreihe", plural="Versuchsreihen", url="/versuchsreihen",
    icon="layers",
    fields=[
        F("name", "Bezeichnung", required=True, width="full"),
        F("order_id", "Auftrag", kind="ref", ref="order"),
        F("status", "Status", kind="select", options=vocab.SERIES_STATUS, required=True),
        F("description", "Beschreibung", kind="textarea", width="full"),
    ],
    columns=[("code", "ID", "link"), ("name", "Bezeichnung", "text"), ("order.code", "Auftrag", "text"),
             ("status", "Status", "status")],
    search_attrs=("code", "name", "description"),
    default_values={"status": "aktiv"},
))

EXPERIMENT_FIELDS = [
    F("title", "Bezeichnung", required=True, width="full", group="Stammdaten"),
    F("order_id", "Auftrag", kind="ref", ref="order", group="Stammdaten"),
    F("series_id", "Versuchsreihe", kind="ref", ref="series", group="Stammdaten"),
    F("experiment_type", "Versuchsart", kind="select", options=vocab.EXPERIMENT_TYPES, required=True,
      group="Stammdaten"),
    F("department", "Fachbereich", kind="select", options=vocab.DEPARTMENTS, required=True, group="Stammdaten"),
    F("responsible_id", "Verantwortlich", kind="ref", ref=U, required=True, group="Stammdaten"),
    F("participants", "Beteiligte", kind="multi_ref", ref=U, group="Stammdaten"),
    F("planned_date", "Geplantes Datum", kind="date", group="Stammdaten"),
    F("actual_date", "Tatsächliches Datum", kind="date", group="Stammdaten"),
    F("tags", "Schlagwörter", kind="tags", group="Stammdaten"),
    F("objective", "Ziel", kind="textarea", width="full", group="Ziel und Hypothese", required=True),
    F("hypothesis", "Hypothese", kind="textarea", width="full", group="Ziel und Hypothese"),
    F("method_id", "Methode", kind="ref", ref="method", group="Methode, Geräte und Materialien"),
    F("recipe_id", "Rezeptur", kind="ref", ref="recipe", group="Methode, Geräte und Materialien"),
    F("devices", "Geräte", kind="multi_ref", ref="device", group="Methode, Geräte und Materialien",
      help="Gesperrte oder überfällig kalibrierte Geräte werden beim Speichern gemeldet."),
    F("materials", "Materialien", kind="multi_ref", ref="material", group="Methode, Geräte und Materialien"),
    F("batches", "Chargen", kind="multi_ref", ref="batch", group="Methode, Geräte und Materialien"),
    F("used_samples", "Verwendete Proben", kind="multi_ref", ref="sample", group="Methode, Geräte und Materialien"),
    F("process_steps", "Prozessschritte", kind="textarea", width="full", group="Durchführung"),
    F("observations", "Beobachtungen", kind="textarea", width="full", group="Durchführung"),
    F("deviations", "Abweichungen", kind="textarea", width="full", group="Durchführung"),
    F("raw_data", "Rohdaten / Verweise", kind="textarea", width="full", group="Durchführung",
      help="Verweise auf Messdateien oder kurze Rohdaten. Dateien bitte als Anhang hochladen."),
    F("results", "Ergebnisse", kind="textarea", width="full", group="Ergebnis und Bewertung"),
    F("evaluation", "Bewertung", kind="textarea", width="full", group="Ergebnis und Bewertung"),
    F("conclusion", "Schlussfolgerung", kind="textarea", width="full", group="Ergebnis und Bewertung"),
    F("follow_up", "Folgeaktivitäten", kind="textarea", width="full", group="Ergebnis und Bewertung"),
]

_register(EntityDef(
    key="experiment", model=Experiment, label="Versuch", plural="Versuche", url="/versuche", icon="flask",
    title_attr="title", fields=EXPERIMENT_FIELDS,
    columns=[("code", "ID", "link"), ("revision", "Rev.", "int"), ("title", "Bezeichnung", "text"),
             ("order.code", "Auftrag", "text"), ("department", "Fachbereich", "text"),
             ("responsible.full_name", "Verantwortlich", "text"), ("planned_date", "Geplant", "date"),
             ("status", "Status", "status")],
    search_attrs=("code", "title", "objective", "hypothesis", "observations", "results", "evaluation",
                  "conclusion", "deviations", "tags", "experiment_type", "follow_up", "process_steps"),
    default_values={"status": "Entwurf"},
))

_register(EntityDef(
    key="recipe", model=Recipe, label="Rezeptur", plural="Rezepturen", url="/rezepturen", icon="list",
    fields=[
        F("name", "Bezeichnung", required=True, width="full"),
        F("order_id", "Auftrag", kind="ref", ref="order"),
        F("status", "Status", kind="select", options=vocab.RECIPE_STATUS, required=True),
        F("target_total", "Ansatzgröße (Gesamtmenge)", kind="float"),
        F("total_unit", "Einheit der Ansatzgröße", kind="select", options=("g", "kg", "t"), required=True),
        F("description", "Beschreibung", kind="textarea", width="full"),
    ],
    columns=[("code", "ID", "link"), ("revision", "Rev.", "int"), ("name", "Bezeichnung", "text"),
             ("order.code", "Auftrag", "text"), ("percent_sum", "Summe Gew.-%", "number"),
             ("status", "Status", "status")],
    search_attrs=("code", "name", "description"),
    default_values={"status": "Entwurf", "total_unit": "kg"},
))

_register(EntityDef(
    key="material", model=Material, label="Material", plural="Materialien", url="/materialien", icon="box",
    create_permission="manage_master_data", edit_permission="manage_master_data", is_master_data=True,
    archive_status="ausgelaufen",
    fields=[
        F("name", "Name", required=True),
        F("material_number", "Materialnummer", help="Interne Materialnummer (z. B. SAP). Muss eindeutig sein."),
        F("trade_name", "Handelsname"),
        F("cas_number", "CAS-Nummer"),
        F("manufacturer", "Hersteller"),
        F("supplier", "Lieferant"),
        F("material_type", "Materialtyp", kind="select", options=vocab.MATERIAL_TYPES, required=True),
        F("function", "Funktion", help="z. B. Basispolymer, Antioxidans, Gleitmittel"),
        F("status", "Status", kind="select", options=vocab.MATERIAL_STATUS, required=True),
        F("description", "Beschreibung", kind="textarea", width="full"),
        F("remarks", "Bemerkungen", kind="textarea", width="full"),
    ],
    columns=[("code", "Interne ID", "link"), ("material_number", "Mat.-Nr.", "text"), ("name", "Name", "text"),
             ("trade_name", "Handelsname", "text"), ("supplier", "Lieferant", "text"),
             ("material_type", "Typ", "text"), ("status", "Status", "status")],
    search_attrs=("code", "material_number", "name", "trade_name", "manufacturer", "supplier", "function",
                  "description", "cas_number"),
    default_values={"status": "aktiv"},
))

_register(EntityDef(
    key="batch", model=Batch, label="Charge", plural="Chargen", url="/chargen", icon="tag",
    create_permission="manage_master_data", edit_permission="manage_master_data", is_master_data=True,
    archive_status="verbraucht", title_attr="batch_number",
    fields=[
        F("material_id", "Material", kind="ref", ref="material", required=True),
        F("batch_number", "Chargennummer", required=True),
        F("received_date", "Eingangsdatum", kind="date"),
        F("expiry_date", "Mindesthaltbarkeit", kind="date"),
        F("storage_location", "Lagerort"),
        F("quantity", "Menge", kind="float"),
        F("unit", "Einheit", kind="select", options=vocab.UNITS),
        F("status", "Status", kind="select", options=vocab.BATCH_STATUS, required=True),
        F("remarks", "Bemerkungen", kind="textarea", width="full",
          help="Sicherheitsdatenblatt und Analysenzertifikat bitte als Anhang mit passender Kategorie hochladen."),
    ],
    columns=[("code", "ID", "link"), ("batch_number", "Charge", "text"), ("material.name", "Material", "text"),
             ("material.material_number", "Mat.-Nr.", "text"), ("received_date", "Eingang", "date"),
             ("expiry_date", "MHD", "date"), ("storage_location", "Lagerort", "text"), ("status", "Status", "status")],
    search_attrs=("code", "batch_number", "storage_location", "remarks"),
    default_values={"status": "freigegeben"},
))

_register(EntityDef(
    key="device", model=Device, label="Gerät", plural="Geräte", url="/geraete", icon="tool",
    create_permission="manage_master_data", edit_permission="manage_master_data", is_master_data=True,
    archive_status="außer Betrieb",
    fields=[
        F("name", "Bezeichnung", required=True),
        F("device_type", "Geräteart", kind="select", options=vocab.DEVICE_TYPES, allow_custom=True),
        F("manufacturer", "Hersteller"),
        F("model", "Modell"),
        F("serial_number", "Seriennummer"),
        F("location", "Standort"),
        F("responsible_id", "Verantwortliche Person", kind="ref", ref=U),
        F("status", "Status", kind="select", options=vocab.DEVICE_STATUS, required=True),
        F("last_maintenance", "Letzte Wartung", kind="date", group="Wartung und Kalibrierung"),
        F("next_maintenance", "Nächste Wartung", kind="date", group="Wartung und Kalibrierung"),
        F("last_calibration", "Letzte Kalibrierung", kind="date", group="Wartung und Kalibrierung"),
        F("next_calibration", "Nächste Kalibrierung", kind="date", group="Wartung und Kalibrierung"),
        F("methods", "Verknüpfte Methoden", kind="multi_ref", ref="method", width="full", group="Weitere Angaben"),
        F("notes", "Bemerkungen", kind="textarea", width="full", group="Weitere Angaben"),
    ],
    columns=[("code", "ID", "link"), ("name", "Bezeichnung", "text"), ("manufacturer", "Hersteller", "text"),
             ("location", "Standort", "text"), ("next_calibration", "Nächste Kalibr.", "date"),
             ("next_maintenance", "Nächste Wartung", "date"), ("status", "Status", "status")],
    search_attrs=("code", "name", "manufacturer", "model", "serial_number", "location", "notes"),
    default_values={"status": "betriebsbereit"},
))

_register(EntityDef(
    key="method", model=Method, label="Methode", plural="Methoden", url="/methoden", icon="book",
    create_permission="manage_master_data", edit_permission="manage_master_data", is_master_data=True,
    archive_status="zurückgezogen",
    fields=[
        F("name", "Bezeichnung", required=True),
        F("standard", "Norm / Vorschrift", help="z. B. DIN EN ISO 527-2"),
        F("category", "Kategorie", kind="select", options=vocab.DEPARTMENTS),
        F("status", "Status", kind="select", options=vocab.METHOD_STATUS, required=True),
        F("description", "Beschreibung / Durchführung", kind="textarea", width="full"),
    ],
    columns=[("code", "ID", "link"), ("name", "Bezeichnung", "text"), ("standard", "Norm", "text"),
             ("category", "Kategorie", "text"), ("status", "Status", "status")],
    search_attrs=("code", "name", "standard", "description"),
    default_values={"status": "gültig"},
))

_register(EntityDef(
    key="sample", model=Sample, label="Probe", plural="Proben", url="/proben", icon="vial",
    fields=[
        F("name", "Probenbezeichnung", required=True, width="full"),
        F("sample_type", "Probenart", kind="select", options=vocab.SAMPLE_TYPES, required=True),
        F("origin", "Herkunft", help="z. B. Eigenherstellung, Kunde, Lieferant"),
        F("order_id", "Auftrag", kind="ref", ref="order"),
        F("experiment_id", "Versuch", kind="ref", ref="experiment"),
        F("parent_id", "Übergeordnete Probe", kind="ref", ref="sample",
          help="Hierarchie, z. B. Compound → Prüfkörper → gealterter Prüfkörper"),
        F("material_id", "Material", kind="ref", ref="material"),
        F("recipe_id", "Rezeptur", kind="ref", ref="recipe"),
        F("batch_id", "Charge", kind="ref", ref="batch"),
        F("production_date", "Herstellungsdatum", kind="date"),
        F("sampling_date", "Entnahmedatum", kind="date"),
        F("quantity", "Menge", kind="float"),
        F("unit", "Einheit", kind="select", options=vocab.UNITS),
        F("storage_location", "Lagerort"),
        F("status", "Status", kind="select", options=vocab.SAMPLE_STATUS, required=True),
        F("description", "Beschreibung", kind="textarea", width="full"),
    ],
    columns=[("code", "ID", "link"), ("name", "Bezeichnung", "text"), ("sample_type", "Art", "text"),
             ("experiment.code", "Versuch", "text"), ("parent.code", "Übergeordnet", "text"),
             ("production_date", "Hergestellt", "date"), ("storage_location", "Lagerort", "text"),
             ("status", "Status", "status")],
    search_attrs=("code", "name", "origin", "description", "storage_location"),
    default_values={"status": "vorhanden"},
))

_register(EntityDef(
    key="measurement", model=Measurement, label="Messdatensatz", plural="Messdaten", url="/messdaten", icon="chart",
    status_field=None, archive_status=None,
    fields=[
        F("name", "Bezeichnung", required=True, width="full"),
        F("property_name", "Messgröße", required=True, help="z. B. Zugfestigkeit, Bruchdehnung, MVR"),
        F("unit", "Einheit", help="z. B. MPa, %, cm³/10 min"),
        F("x_name", "Bezugsgröße (x)", help="Optional, z. B. Alterungszeit oder Temperatur"),
        F("x_unit", "Einheit Bezugsgröße", help="z. B. h, °C"),
        F("experiment_id", "Versuch", kind="ref", ref="experiment"),
        F("sample_id", "Probe", kind="ref", ref="sample"),
        F("device_id", "Gerät", kind="ref", ref="device"),
        F("method_id", "Methode", kind="ref", ref="method"),
        F("measured_on", "Messdatum", kind="date"),
        F("conditions", "Prüfbedingungen / Metadaten", kind="textarea", width="full"),
    ],
    columns=[("code", "ID", "link"), ("name", "Bezeichnung", "text"), ("property_name", "Messgröße", "text"),
             ("unit", "Einheit", "text"), ("sample.code", "Probe", "text"), ("experiment.code", "Versuch", "text"),
             ("measured_on", "Datum", "date")],
    search_attrs=("code", "name", "property_name", "conditions"),
))

_register(EntityDef(
    key="task", model=Task, label="Aufgabe", plural="Aufgaben", url="/aufgaben", icon="check",
    title_attr="title", archive_status=None,
    fields=[
        F("title", "Aufgabe", required=True, width="full"),
        F("assignee_id", "Zuständig", kind="ref", ref=U, required=True),
        F("priority", "Priorität", kind="select", options=vocab.PRIORITIES, required=True),
        F("due_date", "Fällig am", kind="date"),
        F("status", "Status", kind="select", options=vocab.TASK_STATUS, required=True),
        F("description", "Beschreibung", kind="textarea", width="full"),
    ],
    columns=[("code", "ID", "link"), ("title", "Aufgabe", "text"), ("assignee.full_name", "Zuständig", "text"),
             ("priority", "Priorität", "priority"), ("due_date", "Fällig", "date"), ("status", "Status", "status")],
    search_attrs=("code", "title", "description"),
    default_values={"status": "offen", "priority": "normal"},
))


# --- Hilfsfunktionen ---------------------------------------------------------

def get_def(key: str) -> EntityDef:
    return ENTITY_DEFS[key]


def entity_url(entity_type: str, entity_id: int) -> str:
    from ..core.modules import get_registry

    if entity_type in ENTITY_DEFS:
        return f"{ENTITY_DEFS[entity_type].url}/{entity_id}"
    if entity_type == "user":
        return f"/admin/benutzer/{entity_id}"
    if entity_type == "module_record":
        return f"/moduldatensatz/{entity_id}"
    reg = get_registry()
    for m in reg.all():
        resolver = getattr(m, "entity_url", None)
        if resolver:
            url = resolver(entity_type, entity_id)
            if url:
                return url
    return "#"


def get_entity(db: Session, entity_type: str, entity_id: int):
    if entity_type in ENTITY_DEFS:
        return db.get(ENTITY_DEFS[entity_type].model, entity_id)
    if entity_type == "user":
        return db.get(User, entity_id)
    from ..core.modules import get_registry

    for m in get_registry().all():
        resolver = getattr(m, "get_entity", None)
        if resolver:
            obj = resolver(db, entity_type, entity_id)
            if obj is not None:
                return obj
    return None


def entity_type_label(entity_type: str) -> str:
    if entity_type in ENTITY_DEFS:
        return ENTITY_DEFS[entity_type].label
    return {"user": "Benutzer", "attachment": "Anhang", "security": "Sicherheit", "system": "System",
            "settings": "Einstellung", "module": "Modul", "backup": "Sicherung", "role": "Rolle",
            "compounding_run": "Compoundierlauf", "module_record": "Moduldatensatz"}.get(entity_type, entity_type)


def resolve_path(obj: Any, path: str) -> Any:
    cur = obj
    for part in path.split("."):
        if cur is None:
            return None
        cur = getattr(cur, part, None)
    return cur


def ref_options(db: Session, ref: str, current_ids: list[int] | None = None) -> list[tuple[int, str]]:
    """Auswahlwerte für Referenzfelder."""
    current_ids = [i for i in (current_ids or []) if i]
    if ref == "user":
        q = db.query(User).filter(or_(User.is_active.is_(True), User.id.in_(current_ids))).order_by(User.full_name)
        return [(u.id, u.full_name) for u in q]
    d = ENTITY_DEFS[ref]
    model = d.model
    q = db.query(model)
    if d.archive_status and d.status_field:
        q = q.filter(or_(getattr(model, d.status_field) != d.archive_status, model.id.in_(current_ids)))
    order_col = getattr(model, "code", model.id)
    rows = q.order_by(order_col.desc() if d.key in ("order", "experiment", "sample") else order_col).limit(2000).all()
    return [(r.id, r.label) for r in rows]


# --- Sichtbarkeit (Vertraulichkeit) -----------------------------------------

PRIVILEGED_ROLES = {"admin", "leitung"}


def can_see_order(user: User, order: Order | None) -> bool:
    if order is None or order.confidentiality != "streng vertraulich":
        return True
    if user.role_keys & PRIVILEGED_ROLES:
        return True
    return user.id in {order.responsible_id, order.created_by_id} or user in order.participants


def restricted_order_ids(db: Session, user: User) -> set[int]:
    """IDs streng vertraulicher Aufträge, die der Benutzer NICHT sehen darf."""
    if user.role_keys & PRIVILEGED_ROLES:
        return set()
    rows = db.query(Order).filter(Order.confidentiality == "streng vertraulich").all()
    return {o.id for o in rows if not can_see_order(user, o)}


def can_see(db: Session, user: User, entity_type: str, obj) -> bool:
    if obj is None:
        return False
    if entity_type == "order":
        return can_see_order(user, obj)
    order = getattr(obj, "order", None)
    if entity_type == "experiment" or (order is not None and entity_type in ("sample", "series", "recipe")):
        return can_see_order(user, order)
    if entity_type == "measurement" and obj.experiment is not None:
        return can_see_order(user, obj.experiment.order)
    return True


def apply_visibility(db: Session, user: User, entity_type: str, query):
    hidden = restricted_order_ids(db, user)
    if not hidden:
        return query
    model = ENTITY_DEFS[entity_type].model
    if entity_type == "order":
        return query.filter(~model.id.in_(hidden))
    if hasattr(model, "order_id"):
        return query.filter(or_(model.order_id.is_(None), ~model.order_id.in_(hidden)))
    return query
