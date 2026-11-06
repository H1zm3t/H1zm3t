"""Anmeldung, Abmeldung, eigenes Konto."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from ..config import get_settings
from ..services import auth as auth_service
from ..services.audit import Actor
from .deps import SESSION_COOKIE, Ctx, client_ip, get_ctx, get_db, templates

router = APIRouter()


def _safe_next(target: str | None) -> str:
    if not target or not target.startswith("/") or target.startswith("//") or "\\" in target:
        return "/"
    return target


@router.get("/login")
def login_form(request: Request, db: Session = Depends(get_db)):
    sess = auth_service.load_session(db, request.cookies.get(SESSION_COOKIE))
    db.commit()
    if sess is not None:
        return RedirectResponse(_safe_next(request.query_params.get("next")), status_code=303)
    return templates().TemplateResponse(request, "auth/login.html",
                                        {"next": _safe_next(request.query_params.get("next")), "error": None,
                                         "username": ""})


@router.post("/login")
async def login(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    username = (form.get("username") or "").strip()
    password = form.get("password") or ""
    target = _safe_next(form.get("next"))
    try:
        user = auth_service.authenticate(db, username, password, client_ip(request))
    except auth_service.AuthError as exc:
        db.commit()
        return templates().TemplateResponse(request, "auth/login.html",
                                            {"next": target, "error": str(exc), "username": username[:64]},
                                            status_code=401)
    token = auth_service.start_session(db, user, client_ip(request), request.headers.get("user-agent"))
    db.commit()
    resp = RedirectResponse(target if not user.must_change_password else "/konto?pflicht=1", status_code=303)
    resp.set_cookie(SESSION_COOKIE, token, httponly=True, samesite="lax", secure=get_settings().cookie_secure,
                    path="/")
    return resp


@router.post("/logout")
async def logout(request: Request, ctx: Ctx = Depends(get_ctx)):
    auth_service.end_session(ctx.db, request.cookies.get(SESSION_COOKIE), ctx.actor)
    ctx.db.commit()
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie(SESSION_COOKIE, path="/")
    return resp


@router.get("/konto")
def account(request: Request, ctx: Ctx = Depends(get_ctx)):
    return ctx.render("auth/account.html", forced=request.query_params.get("pflicht") == "1", error=None)


@router.post("/konto")
async def change_password(request: Request, ctx: Ctx = Depends(get_ctx)):
    form = await request.form()
    new = form.get("new_password") or ""
    if new != (form.get("new_password2") or ""):
        return ctx.render("auth/account.html", forced=ctx.user.must_change_password,
                          error="Die neuen Passwörter stimmen nicht überein.")
    try:
        auth_service.change_password(ctx.db, Actor(ctx.user, client_ip(request)), ctx.user, new,
                                     old_password=form.get("old_password") or "")
    except auth_service.AuthError as exc:
        return ctx.render("auth/account.html", forced=ctx.user.must_change_password, error=str(exc))
    return ctx.redirect("/", "success", "Ihr Passwort wurde geändert.")
