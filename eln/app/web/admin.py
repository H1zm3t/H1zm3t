"""Administration: Benutzer, Rollen, Einstellungen, Module, Datensicherung, Systeminformation."""
from __future__ import annotations

import platform
import sys

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy import func

from ..config import APP_VERSION, get_settings
from ..core.modules import get_registry
from ..core.permissions import PERMISSIONS
from ..models import AuditLog, BackupRecord, ModuleState, Role, User, UserSession
from ..services import audit, auth as auth_service, backup as backup_service
from ..services.entities import ENTITY_DEFS
from ..services.records import RecordError
from ..services.system_settings import SETTING_DEFS, all_settings, set_setting
from .deps import SESSION_COOKIE, Ctx, get_ctx

router = APIRouter(prefix="/admin")


# --- Benutzer -------------------------------------------------------------------

@router.get("/benutzer")
def users(ctx: Ctx = Depends(get_ctx)):
    ctx.require("manage_users")
    from datetime import datetime

    return ctx.render("admin/users.html", users=ctx.db.query(User).order_by(User.full_name).all(), now=datetime.now())


@router.get("/benutzer/neu")
def new_user(ctx: Ctx = Depends(get_ctx)):
    ctx.require("manage_users")
    return ctx.render("admin/user_form.html", u=None, roles=ctx.db.query(Role).all(), error=None, form={})


@router.post("/benutzer/neu")
async def create_user(request: Request, ctx: Ctx = Depends(get_ctx)):
    ctx.require("manage_users")
    form = await request.form()
    try:
        u = auth_service.create_user(
            ctx.db, ctx.actor, username=form.get("username", ""), full_name=form.get("full_name", ""),
            password=form.get("password", ""), role_keys=form.getlist("roles"),
            email=form.get("email") or None, short_name=form.get("short_name") or None,
            department=form.get("department") or None, must_change_password=True)
    except auth_service.AuthError as exc:
        ctx.db.rollback()
        return ctx.render("admin/user_form.html", u=None, roles=ctx.db.query(Role).all(), error=str(exc),
                          form=dict(form), selected=form.getlist("roles"))
    return ctx.redirect("/admin/benutzer", "success",
                        f"Benutzer {u.username} angelegt. Das Passwort muss bei der ersten Anmeldung geändert werden.")


@router.get("/benutzer/{uid:int}")
def edit_user(uid: int, ctx: Ctx = Depends(get_ctx)):
    ctx.require("manage_users")
    u = ctx.db.get(User, uid)
    if u is None:
        raise HTTPException(404)
    logins = (ctx.db.query(AuditLog).filter(AuditLog.user_id == uid, AuditLog.entity_type == "security")
              .order_by(AuditLog.id.desc()).limit(20).all())
    return ctx.render("admin/user_form.html", u=u, roles=ctx.db.query(Role).all(), error=None,
                      form={}, selected=[r.key for r in u.roles], logins=logins)


@router.post("/benutzer/{uid:int}")
async def update_user(uid: int, request: Request, ctx: Ctx = Depends(get_ctx)):
    ctx.require("manage_users")
    u = ctx.db.get(User, uid)
    if u is None:
        raise HTTPException(404)
    form = await request.form()
    role_keys = form.getlist("roles")
    roles = ctx.db.query(Role).filter(Role.key.in_(role_keys)).all()
    if not roles:
        raise RecordError("Bitte mindestens eine Rolle auswählen.")
    active = form.get("is_active") == "1"
    if u.id == ctx.user.id and (not active or "admin" not in role_keys):
        raise RecordError("Sie können sich nicht selbst deaktivieren oder die eigene Administratorrolle entziehen.")
    changes = {}
    for attr in ("full_name", "email", "short_name", "department"):
        new = (form.get(attr) or "").strip() or None
        if attr == "full_name" and not new:
            raise RecordError("Der Name darf nicht leer sein.")
        if getattr(u, attr) != new:
            changes[attr] = (getattr(u, attr), new)
            setattr(u, attr, new)
    if u.is_active != active:
        changes["aktiv"] = (u.is_active, active)
        u.is_active = active
        if not active:
            ctx.db.query(UserSession).filter(UserSession.user_id == u.id).delete()
    old_roles = sorted(r.key for r in u.roles)
    if old_roles != sorted(role_keys):
        changes["Rollen"] = (", ".join(old_roles), ", ".join(sorted(role_keys)))
        u.roles = roles
    if form.get("unlock") == "1":
        u.locked_until = None
        u.failed_logins = 0
        changes["Sperre"] = ("gesperrt", "entsperrt")
    if changes:
        u.version += 1
        for field, (old, new) in changes.items():
            audit.log(ctx.db, ctx.actor, "update", entity_type="user", entity_id=u.id, entity_code=u.username,
                      field=field, old=old, new=new, version=u.version, reason=form.get("reason") or None)
    return ctx.redirect(f"/admin/benutzer/{u.id}", "success", "Benutzer gespeichert.")


@router.post("/benutzer/{uid:int}/passwort")
async def reset_password(uid: int, request: Request, ctx: Ctx = Depends(get_ctx)):
    ctx.require("manage_users")
    u = ctx.db.get(User, uid)
    if u is None:
        raise HTTPException(404)
    form = await request.form()
    try:
        auth_service.change_password(ctx.db, ctx.actor, u, form.get("password", ""), by_admin=True)
    except auth_service.AuthError as exc:
        raise RecordError(str(exc)) from None
    return ctx.redirect(f"/admin/benutzer/{u.id}", "success",
                        "Passwort zurückgesetzt. Der Benutzer muss es bei der nächsten Anmeldung ändern.")


# --- Rollen -----------------------------------------------------------------------

@router.get("/rollen")
def roles(ctx: Ctx = Depends(get_ctx)):
    ctx.require("manage_users")
    return ctx.render("admin/roles.html", roles=ctx.db.query(Role).order_by(Role.id).all(), permissions=PERMISSIONS)


@router.post("/rollen")
async def save_roles(request: Request, ctx: Ctx = Depends(get_ctx)):
    ctx.require("manage_users")
    form = await request.form()
    for role in ctx.db.query(Role).all():
        if role.key == "admin":
            continue  # Administrator behält immer alle Rechte
        new = {p for p in PERMISSIONS if form.get(f"{role.key}:{p}") == "1"}
        if new != role.permissions:
            audit.log(ctx.db, ctx.actor, "update", entity_type="role", entity_id=role.id, entity_code=role.key,
                      field="Rechte", old=", ".join(sorted(role.permissions)), new=", ".join(sorted(new)),
                      reason=form.get("reason") or None)
            role.permissions = new
    return ctx.redirect("/admin/rollen", "success", "Rollenrechte gespeichert.")


# --- Einstellungen ------------------------------------------------------------------

@router.get("/einstellungen")
def settings_page(ctx: Ctx = Depends(get_ctx)):
    ctx.require("manage_settings")
    return ctx.render("admin/settings.html", items=all_settings(ctx.db), env=get_settings())


@router.post("/einstellungen")
async def save_settings(request: Request, ctx: Ctx = Depends(get_ctx)):
    ctx.require("manage_settings")
    form = await request.form()
    changed = 0
    for d in SETTING_DEFS:
        value = form.get(d.key) if d.kind != "bool" else ("1" if form.get(d.key) == "1" else "0")
        if value is None:
            continue
        try:
            old, new = set_setting(ctx.db, d.key, value)
        except ValueError:
            raise RecordError(f"Ungültiger Wert für »{d.label}«.") from None
        if old != new:
            changed += 1
            audit.log(ctx.db, ctx.actor, "settings", entity_type="settings", entity_code=d.key, field=d.label,
                      old=old, new=new, reason=form.get("reason") or None)
    return ctx.redirect("/admin/einstellungen", "success", f"{changed} Einstellung(en) geändert.")


# --- Module -------------------------------------------------------------------------

@router.get("/module")
def modules_page(ctx: Ctx = Depends(get_ctx)):
    ctx.require("manage_settings")
    reg = get_registry()
    states = {s.key: s for s in ctx.db.query(ModuleState).all()}
    return ctx.render("admin/modules.html", modules=reg.all(), states=states, enabled=reg.enabled_keys(ctx.db))


@router.post("/module/{key}")
async def toggle_module(key: str, request: Request, ctx: Ctx = Depends(get_ctx)):
    ctx.require("manage_settings")
    reg = get_registry()
    module = reg.get(key)
    if module is None:
        raise HTTPException(404)
    form = await request.form()
    enable = form.get("enabled") == "1"
    state = ctx.db.get(ModuleState, key)
    if state is None:
        state = ModuleState(key=key, enabled=enable, installed_version=module.version)
        ctx.db.add(state)
    state.enabled = enable
    (module.on_enable if enable else module.on_disable)(ctx.db)
    audit.log(ctx.db, ctx.actor, "module_enable" if enable else "module_disable", entity_type="module",
              entity_code=key, new=module.name)
    ctx.db.commit()
    reg.invalidate()
    return ctx.redirect("/admin/module", "success", f"Modul »{module.name}« {'aktiviert' if enable else 'deaktiviert'}.")


@router.post("/module/{key}/konfiguration")
async def module_config(key: str, request: Request, ctx: Ctx = Depends(get_ctx)):
    import json

    ctx.require("manage_settings")
    module = get_registry().get(key)
    state = ctx.db.get(ModuleState, key)
    if module is None or state is None:
        raise HTTPException(404)
    form = await request.form()
    try:
        new = json.loads(form.get("config") or "{}")
        if not isinstance(new, dict):
            raise ValueError
    except ValueError:
        return ctx.redirect("/admin/module", "error", "Ungültiges JSON – die Konfiguration muss ein Objekt {…} sein.")
    old = state.config_json
    state.config_json = json.dumps(new, ensure_ascii=False)
    audit.log(ctx.db, ctx.actor, "settings", entity_type="module", entity_code=key, field="Modulkonfiguration",
              old=old, new=state.config_json, reason=form.get("reason") or None)
    return ctx.redirect("/admin/module", "success", f"Konfiguration von »{module.name}« gespeichert.")


# --- Datensicherung -------------------------------------------------------------------

@router.get("/sicherung")
def backup_page(ctx: Ctx = Depends(get_ctx)):
    ctx.require("backup")
    records = ctx.db.query(BackupRecord).order_by(BackupRecord.id.desc()).limit(50).all()
    return ctx.render("admin/backup.html", files=backup_service.list_backups(), records=records,
                      log=backup_service.read_log(30), settings=get_settings(),
                      is_admin="admin" in ctx.user.role_keys)


@router.post("/sicherung/erstellen")
def make_backup(ctx: Ctx = Depends(get_ctx)):
    ctx.require("backup")
    ctx.db.commit()
    result = backup_service.create_backup("manuell", ctx.user.username)
    audit.log(ctx.db, ctx.actor, "backup", entity_type="backup", new=result["filename"],
              result="erfolgreich" if result["ok"] else "fehlgeschlagen")
    return ctx.redirect("/admin/sicherung", "success" if result["ok"] else "error",
                        f"Sicherung {result['filename']}: {result['message']}")


@router.post("/sicherung/pruefen")
async def check_backup(request: Request, ctx: Ctx = Depends(get_ctx)):
    ctx.require("backup")
    form = await request.form()
    try:
        path = backup_service.resolve_backup(form.get("filename", ""))
    except backup_service.BackupError as exc:
        raise RecordError(str(exc)) from None
    result = backup_service.verify_backup(path)
    return ctx.redirect("/admin/sicherung", "success" if result["ok"] else "error",
                        f"{path.name}: {result['message']}")


@router.get("/sicherung/download/{filename}")
def download_backup(filename: str, ctx: Ctx = Depends(get_ctx)):
    ctx.require("backup")
    if "admin" not in ctx.user.role_keys:
        raise HTTPException(403, "Nur Administratoren dürfen Sicherungen herunterladen.")
    try:
        path = backup_service.resolve_backup(filename)
    except backup_service.BackupError as exc:
        raise HTTPException(404, str(exc)) from None
    return FileResponse(path, media_type="application/zip", filename=path.name)


@router.post("/sicherung/wiederherstellen")
async def restore(request: Request, ctx: Ctx = Depends(get_ctx)):
    if "admin" not in ctx.user.role_keys:
        raise HTTPException(403, "Wiederherstellung ist nur mit Administratorrecht zulässig.")
    form = await request.form()
    if form.get("confirm") != "WIEDERHERSTELLEN":
        return ctx.redirect("/admin/sicherung", "error",
                            "Bitte zur Bestätigung WIEDERHERSTELLEN in das Feld eingeben.")
    try:
        path = backup_service.resolve_backup(form.get("filename", ""))
    except backup_service.BackupError as exc:
        raise RecordError(str(exc)) from None
    username = ctx.user.username
    ctx.db.commit()
    ctx.db.close()
    try:
        result = backup_service.restore_backup(path, username)
    except backup_service.BackupError as exc:
        raise RecordError(str(exc)) from None
    resp = RedirectResponse("/login?wiederhergestellt=1", status_code=303)
    resp.delete_cookie(SESSION_COOKIE, path="/")
    return resp


# --- Systeminformation ------------------------------------------------------------------

@router.get("/system")
def system_info(ctx: Ctx = Depends(get_ctx)):
    ctx.require("manage_settings")
    from ..bootstrap import migration_status

    current, head = migration_status()
    counts = {d.plural: ctx.db.query(func.count(d.model.id)).scalar() for d in ENTITY_DEFS.values()}
    chain = audit.verify_chain(ctx.db)
    s = get_settings()
    return ctx.render("admin/system.html", version=APP_VERSION, python=sys.version.split()[0],
                      platform=platform.platform(), settings=s, migration_current=current, migration_head=head,
                      counts=counts, chain=chain,
                      sessions=ctx.db.query(UserSession).count())
