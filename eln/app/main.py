"""FastAPI-Anwendung (App-Fabrik)."""
from __future__ import annotations

import logging
import traceback

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from .config import APP_DIR, APP_NAME, APP_VERSION
from .core.modules import get_registry
from .logging_setup import setup_logging
from .services.records import RecordError
from .web.deps import MustChangePassword, NotAuthenticated, PermissionDenied, login_redirect, templates

log = logging.getLogger("eln.web")

CSP = ("default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; script-src 'self'; "
       "frame-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'self'")


def _error_page(request: Request, status: int, title: str, message: str) -> HTMLResponse:
    wants_json = request.headers.get("accept", "").startswith("application/json") or request.url.path.startswith("/api/")
    if wants_json:
        return JSONResponse({"detail": message}, status_code=status)
    return templates().TemplateResponse(request, "error.html", {"status": status, "title": title, "message": message},
                                        status_code=status)


def create_app(run_init: bool = True) -> FastAPI:
    setup_logging()
    if run_init:
        from .bootstrap import init_database

        log.info(init_database())
    registry = get_registry()

    app = FastAPI(title=APP_NAME, version=APP_VERSION, docs_url=None, redoc_url=None, openapi_url=None)
    app.mount("/static", StaticFiles(directory=str(APP_DIR / "static")), name="static")

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault("Content-Security-Policy", CSP)
        if not request.url.path.startswith("/static"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    @app.exception_handler(NotAuthenticated)
    async def _not_auth(request: Request, exc: NotAuthenticated):
        if request.url.path.startswith("/api/") or request.headers.get("x-requested-with") == "fetch":
            return JSONResponse({"detail": "Nicht angemeldet oder Sitzung abgelaufen."}, status_code=401)
        return login_redirect(request)

    @app.exception_handler(MustChangePassword)
    async def _must_change(request: Request, exc: MustChangePassword):
        return RedirectResponse("/konto?pflicht=1", status_code=303)

    @app.exception_handler(PermissionDenied)
    async def _denied(request: Request, exc: PermissionDenied):
        return _error_page(request, 403, "Keine Berechtigung", exc.message)

    @app.exception_handler(RecordError)
    async def _record_error(request: Request, exc: RecordError):
        return _error_page(request, 400, "Aktion nicht möglich", str(exc))

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException):
        titles = {404: "Nicht gefunden", 403: "Zugriff verweigert", 405: "Methode nicht erlaubt",
                  413: "Datei zu groß", 400: "Ungültige Anfrage"}
        message = exc.detail if isinstance(exc.detail, str) and exc.detail not in ("Not Found",) else \
            "Die angeforderte Seite oder der Datensatz wurde nicht gefunden."
        return _error_page(request, exc.status_code, titles.get(exc.status_code, "Fehler"), message)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        return _error_page(request, 400, "Ungültige Eingabe",
                           "Die Anfrage enthält ungültige oder fehlende Werte. Bitte prüfen Sie Ihre Eingaben.")

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        log.error("Unerwarteter Fehler bei %s %s\n%s", request.method, request.url.path, traceback.format_exc())
        return _error_page(request, 500, "Interner Fehler",
                           "Es ist ein unerwarteter Fehler aufgetreten. Er wurde im Fehlerprotokoll "
                           "(data/logs/fehler.log) festgehalten. Bitte informieren Sie die Administration.")

    from .web import (admin, analytics, attachments, audit_views, auth_views, dashboard, experiments, io_views,
                      records, recipes, search_views, api)

    for module in (auth_views, dashboard, experiments, recipes, records, attachments, search_views, analytics,
                   audit_views, io_views, admin, api):
        app.include_router(module.router)

    from .web.modules_web import module_router_guard

    for m in registry.all():
        r = m.router()
        if r is not None:
            app.include_router(r, dependencies=[module_router_guard(m.key)])

    return app
