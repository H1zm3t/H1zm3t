"""Gemeinsame Abhängigkeiten der Weboberfläche: Sitzung, Rechte, CSRF, Rendering."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Any
from urllib.parse import quote

from fastapi import Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from jinja2 import ChoiceLoader, Environment, FileSystemLoader, select_autoescape
from sqlalchemy.orm import Session

from ..config import APP_DIR, APP_NAME, APP_VERSION
from ..core import formatting
from ..core.modules import get_registry
from ..core.permissions import PERMISSIONS
from ..core.security import constant_time_equals
from ..db import SessionLocal
from ..models import User, UserSession
from ..services import auth as auth_service
from ..services.audit import ACTION_LABELS, Actor
from ..services.entities import ENTITY_DEFS, entity_type_label, entity_url
from ..services.system_settings import get_setting

SESSION_COOKIE = "eln_session"


class NotAuthenticated(Exception):
    pass


class PermissionDenied(Exception):
    def __init__(self, message: str = "Sie haben keine Berechtigung für diese Aktion."):
        super().__init__(message)
        self.message = message


def _status_class(status: str | None) -> str:
    mapping = {
        "Entwurf": "neutral", "geplant": "info", "in Bearbeitung": "info", "pausiert": "warning",
        "abgeschlossen": "primary", "zur Prüfung": "warning", "Korrektur erforderlich": "danger",
        "geprüft": "primary", "freigegeben": "success", "archiviert": "neutral", "abgebrochen": "danger",
        "offen": "info", "storniert": "danger", "aktiv": "success", "gültig": "success", "ersetzt": "neutral",
        "betriebsbereit": "success", "in Wartung": "warning", "gesperrt": "danger", "außer Betrieb": "neutral",
        "Quarantäne": "warning", "verbraucht": "neutral", "abgelaufen": "danger", "vorhanden": "success",
        "in Prüfung": "warning", "erledigt": "success", "ungültig": "danger", "vollständig": "success",
        "fehlerhaft": "danger", "fehlgeschlagen": "danger", "erfolgreich": "success", "abgelehnt": "danger",
        "ruhend": "neutral", "ausgelaufen": "neutral", "zurückgezogen": "neutral", "erfasst": "info",
        "dringend": "danger", "hoch": "warning", "normal": "neutral", "niedrig": "neutral",
        "streng vertraulich": "danger", "vertraulich": "warning", "intern": "neutral", "öffentlich": "info",
    }
    return mapping.get(status or "", "neutral")


def _build_env() -> Environment:
    loaders = [FileSystemLoader(str(APP_DIR / "templates"))]
    for m in get_registry().all():
        tdir = m.templates_dir()
        if tdir and tdir.exists():
            loaders.append(FileSystemLoader(str(tdir)))
    env = Environment(loader=ChoiceLoader(loaders), autoescape=select_autoescape(["html", "xml"]),
                      trim_blocks=True, lstrip_blocks=True)
    env.filters.update({
        "de_date": formatting.de_date, "de_datetime": formatting.de_datetime, "de_num": formatting.de_number,
        "de_input": formatting.de_input_number, "filesize": formatting.file_size, "status_class": _status_class,
        "action_label": lambda a: ACTION_LABELS.get(a, a), "type_label": entity_type_label,
    })
    env.globals.update({
        "APP_NAME": APP_NAME, "APP_VERSION": APP_VERSION, "PERMISSIONS": PERMISSIONS, "ENTITY_DEFS": ENTITY_DEFS,
        "entity_url": entity_url, "today": date.today,
    })
    return env


_templates: Jinja2Templates | None = None


def templates() -> Jinja2Templates:
    global _templates
    if _templates is None:
        _templates = Jinja2Templates(env=_build_env())
    return _templates


def get_db():
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@dataclass
class Ctx:
    request: Request
    db: Session
    user: User
    session: UserSession

    @property
    def actor(self) -> Actor:
        return Actor(self.user, client_ip(self.request))

    def flash(self, kind: str, message: str) -> None:
        auth_service.push_flash(self.session, kind, message)

    def require(self, permission: str) -> None:
        if not self.user.has(permission):
            raise PermissionDenied(f"Für diese Aktion fehlt das Recht »{PERMISSIONS.get(permission, permission)}«.")

    def render(self, template: str, status_code: int = 200, **context: Any) -> HTMLResponse:
        registry = get_registry()
        module_nav = []
        for m in registry.enabled(self.db):
            for entry in m.nav_entries():
                if self.user.has(entry.permission):
                    module_nav.append(entry)
        context.update({
            "request": self.request, "user": self.user, "csrf_token": self.session.csrf_token,
            "flashes": auth_service.pop_flashes(self.session), "module_nav": module_nav,
            "company_name": get_setting(self.db, "company_name"),
            "current_path": self.request.url.path,
        })
        self.db.commit()
        return templates().TemplateResponse(self.request, template, context, status_code=status_code)

    def redirect(self, url: str, kind: str | None = None, message: str | None = None) -> RedirectResponse:
        if kind and message:
            self.flash(kind, message)
        self.db.commit()
        return RedirectResponse(url, status_code=303)


async def get_ctx(request: Request, db: Session = Depends(get_db)) -> Ctx:
    token = request.cookies.get(SESSION_COOKIE)
    sess = auth_service.load_session(db, token)
    if sess is None:
        db.commit()
        raise NotAuthenticated()
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        sent = request.headers.get("x-csrf-token")
        if not sent:
            ctype = request.headers.get("content-type", "")
            if "form" in ctype:
                form = await request.form()
                sent = form.get("csrf_token")
        if not sent or not constant_time_equals(str(sent), sess.csrf_token):
            from ..services import audit

            audit.log_security(db, Actor(sess.user, client_ip(request)), "csrf_failed", request.url.path,
                               result="abgelehnt")
            db.commit()
            raise HTTPException(status_code=403, detail="Sicherheitsprüfung (CSRF) fehlgeschlagen. "
                                                        "Bitte laden Sie die Seite neu und versuchen Sie es erneut.")
    ctx = Ctx(request=request, db=db, user=sess.user, session=sess)
    if sess.user.must_change_password and request.url.path not in ("/konto", "/logout"):
        raise MustChangePassword()
    return ctx


class MustChangePassword(Exception):
    pass


def login_redirect(request: Request) -> RedirectResponse:
    target = request.url.path
    if request.url.query:
        target += "?" + request.url.query
    return RedirectResponse(f"/login?next={quote(target)}", status_code=303)


def json_dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)
