"""Deklarative Formularfelder und Validierung mit Pydantic.

Eine Liste von ``FieldSpec`` beschreibt ein Formular. Daraus werden
- die Eingabemaske (Template ``partials/form_fields.html``),
- ein Pydantic-Modell zur Validierung (``build_model``) und
- deutsche Fehlermeldungen
erzeugt. Dieselben Definitionen werden auch für CSV/JSON-Importe verwendet.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from functools import lru_cache
from typing import Annotated, Any, Callable, Optional

from pydantic import BeforeValidator, ValidationError, create_model

from .formatting import parse_date, parse_datetime, parse_number


@dataclass(frozen=True)
class FieldSpec:
    name: str
    label: str
    kind: str = "text"  # text, textarea, int, float, date, datetime, select, ref, multi_ref, bool, tags
    required: bool = False
    options: tuple = ()
    ref: str | None = None  # Entitätsschlüssel bei ref/multi_ref
    unit: str | None = None
    help: str | None = None
    group: str | None = None
    width: str = "half"  # full, half, third
    max_length: int | None = None
    placeholder: str | None = None
    allow_custom: bool = False  # select mit freier Eingabe (datalist)

    @property
    def is_multi(self) -> bool:
        return self.kind == "multi_ref"


def _empty_to_none(v):
    if isinstance(v, str) and v.strip() == "":
        return None
    return v


def _num(v):
    v = _empty_to_none(v)
    if v is None:
        return None
    try:
        return parse_number(v)
    except (ValueError, TypeError):
        raise ValueError("Bitte eine gültige Zahl eingeben (z. B. 12,5).") from None


def _int(v):
    v = _num(v)
    if v is None:
        return None
    if int(v) != v:
        raise ValueError("Bitte eine ganze Zahl eingeben.")
    return int(v)


def _date(v):
    v = _empty_to_none(v)
    if v is None:
        return None
    try:
        return parse_date(v)
    except (ValueError, TypeError):
        raise ValueError("Bitte ein gültiges Datum eingeben (TT.MM.JJJJ).") from None


def _datetime(v):
    v = _empty_to_none(v)
    if v is None:
        return None
    try:
        return parse_datetime(v)
    except (ValueError, TypeError):
        raise ValueError("Bitte Datum und Uhrzeit gültig eingeben (TT.MM.JJJJ HH:MM).") from None


def _text(max_len: int | None):
    def conv(v):
        v = _empty_to_none(v)
        if v is None:
            return None
        s = str(v).strip()
        if max_len and len(s) > max_len:
            raise ValueError(f"Der Text ist zu lang (höchstens {max_len} Zeichen).")
        return s

    return conv


def _tags(v):
    v = _empty_to_none(v)
    if v is None:
        return None
    parts = [p.strip() for p in str(v).replace(";", ",").split(",")]
    seen: list[str] = []
    for p in parts:
        if p and p.lower() not in [s.lower() for s in seen]:
            seen.append(p)
    return ", ".join(seen) or None


def _bool(v):
    if isinstance(v, bool):
        return v
    if v is None:
        return False
    return str(v).strip().lower() in ("1", "on", "true", "ja", "yes", "x")


def _ref(v):
    v = _empty_to_none(v)
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        raise ValueError("Bitte einen gültigen Eintrag auswählen.") from None


def _multi_ref(v):
    if v is None:
        return []
    if not isinstance(v, (list, tuple)):
        v = [v]
    out = []
    for item in v:
        item = _empty_to_none(item)
        if item is None:
            continue
        try:
            out.append(int(item))
        except (TypeError, ValueError):
            raise ValueError("Bitte gültige Einträge auswählen.") from None
    return out


def _select(options: tuple, allow_custom: bool, max_len: int | None):
    text_conv = _text(max_len)

    def conv(v):
        v = text_conv(v)
        if v is None:
            return None
        if options and not allow_custom and v not in options:
            raise ValueError("Bitte einen gültigen Eintrag aus der Liste auswählen.")
        return v

    return conv


def _not_none(v):
    if v is None or v == []:
        raise ValueError("Pflichtfeld – bitte ausfüllen.")
    return v


def _field_type(spec: FieldSpec):
    converters: dict[str, tuple[Any, Callable]] = {
        "text": (str, _text(spec.max_length or 250)),
        "textarea": (str, _text(spec.max_length or 100_000)),
        "int": (int, _int),
        "float": (float, _num),
        "date": (date, _date),
        "datetime": (datetime, _datetime),
        "select": (str, _select(spec.options, spec.allow_custom, spec.max_length or 120)),
        "ref": (int, _ref),
        "tags": (str, _tags),
    }
    if spec.kind == "bool":
        return Annotated[bool, BeforeValidator(_bool)], False
    if spec.kind == "multi_ref":
        validators = [BeforeValidator(_multi_ref)]
        return Annotated[list[int], *validators], []
    base, conv = converters[spec.kind]
    if spec.required:
        return Annotated[base, BeforeValidator(_not_none), BeforeValidator(conv)], ...
    return Annotated[Optional[base], BeforeValidator(conv)], None


@lru_cache(maxsize=256)
def build_model(name: str, specs: tuple[FieldSpec, ...]):
    fields = {}
    for spec in specs:
        typ, default = _field_type(spec)
        fields[spec.name] = (typ, default)
    return create_model(name, **fields)


GERMAN_ERRORS = {
    "missing": "Pflichtfeld – bitte ausfüllen.",
    "int_parsing": "Bitte eine ganze Zahl eingeben.",
    "int_type": "Bitte eine ganze Zahl eingeben.",
    "float_parsing": "Bitte eine gültige Zahl eingeben (z. B. 12,5).",
    "float_type": "Bitte eine gültige Zahl eingeben (z. B. 12,5).",
    "date_parsing": "Bitte ein gültiges Datum eingeben (TT.MM.JJJJ).",
    "date_from_datetime_parsing": "Bitte ein gültiges Datum eingeben (TT.MM.JJJJ).",
    "date_type": "Bitte ein gültiges Datum eingeben (TT.MM.JJJJ).",
    "datetime_parsing": "Bitte Datum und Uhrzeit gültig eingeben.",
    "datetime_type": "Bitte Datum und Uhrzeit gültig eingeben.",
    "string_type": "Bitte einen Text eingeben.",
    "list_type": "Bitte gültige Einträge auswählen.",
}


def german_message(err: dict) -> str:
    if err.get("type") == "value_error":
        msg = err.get("msg", "")
        return msg.split(", ", 1)[1] if msg.startswith("Value error, ") else msg
    return GERMAN_ERRORS.get(err.get("type", ""), err.get("msg", "Ungültige Eingabe."))


def validate_values(specs: list[FieldSpec] | tuple[FieldSpec, ...], raw: dict, model_name: str = "Form"):
    """Validiert Rohwerte. Rückgabe: (werte, fehler) – fehler = {feldname: meldung}."""
    specs_t = tuple(specs)
    model = build_model(model_name, specs_t)
    data = {}
    for spec in specs_t:
        if spec.name in raw:
            data[spec.name] = raw[spec.name]
        elif spec.kind == "bool":
            data[spec.name] = False
    try:
        obj = model.model_validate(data)
    except ValidationError as exc:
        errors: dict[str, str] = {}
        for err in exc.errors():
            loc = err.get("loc") or ("__all__",)
            errors.setdefault(str(loc[0]), german_message(err))
        return None, errors
    return obj.model_dump(), {}


def raw_from_form(specs, form) -> dict:
    """Übernimmt die Rohwerte aus einem Starlette-FormData-Objekt."""
    raw: dict[str, Any] = {}
    for spec in specs:
        if spec.kind == "multi_ref":
            raw[spec.name] = form.getlist(spec.name)
        elif spec.kind == "bool":
            raw[spec.name] = form.get(spec.name)
        elif spec.name in form:
            raw[spec.name] = form.get(spec.name)
    return raw


def spec_by_name(specs, name: str) -> FieldSpec | None:
    for s in specs:
        if s.name == name:
            return s
    return None
