"""Anhänge (Upload, Vorschau, Download, Versionen, Status) und Kommentare."""
from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

from ..core.vocab import CONFIDENTIALITY
from ..models import Attachment, Comment, RecordSnapshot
from ..services import audit, files as file_service
from ..services.entities import ENTITY_DEFS, can_see, entity_url, get_entity
from ..services.records import RecordError
from .deps import Ctx, get_ctx

router = APIRouter()


def _parent_check(ctx: Ctx, entity_type: str, entity_id: int):
    obj = get_entity(ctx.db, entity_type, entity_id)
    if obj is None:
        raise HTTPException(404, "Der zugehörige Datensatz existiert nicht.")
    if entity_type in ENTITY_DEFS and not can_see(ctx.db, ctx.user, entity_type, obj):
        raise HTTPException(403, "Dieser Datensatz ist vertraulich.")
    return obj


def _get_att(ctx: Ctx, att_id: int) -> Attachment:
    att = ctx.db.get(Attachment, att_id)
    if att is None:
        raise HTTPException(404, "Anhang nicht gefunden.")
    _parent_check(ctx, att.entity_type, att.entity_id)
    if not file_service.can_view_attachment(ctx.user, att):
        raise HTTPException(403, "Dieser Anhang ist streng vertraulich.")
    return att


@router.post("/anhaenge/upload")
async def upload(request: Request, ctx: Ctx = Depends(get_ctx)):
    ctx.require("create")
    form = await request.form()
    entity_type = form.get("entity_type", "")
    try:
        entity_id = int(form.get("entity_id", ""))
    except ValueError:
        raise HTTPException(400, "Ungültiger Datensatz.") from None
    _parent_check(ctx, entity_type, entity_id)
    confidentiality = form.get("confidentiality") or "intern"
    if confidentiality not in CONFIDENTIALITY:
        confidentiality = "intern"
    uploads = [f for f in form.getlist("files") if hasattr(f, "filename") and f.filename]
    is_fetch = request.headers.get("x-requested-with") == "fetch"
    if not uploads:
        if is_fetch:
            return JSONResponse({"ok": False, "messages": ["Keine Datei ausgewählt."]}, status_code=400)
        return ctx.redirect(entity_url(entity_type, entity_id) + "#anhaenge", "error", "Keine Datei ausgewählt.")
    messages, ok_count = [], 0
    for up in uploads:
        try:
            result = file_service.save_upload(
                ctx.db, ctx.actor, stream=up.file, filename=up.filename, entity_type=entity_type,
                entity_id=entity_id, description=(form.get("description") or "").strip() or None,
                caption=(form.get("caption") or "").strip() or None, category=form.get("category") or None,
                confidentiality=confidentiality)
            ctx.db.commit()
            ok_count += 1
            if result.duplicates:
                where = ", ".join(sorted({f"{d.original_filename} ({d.entity_type} {d.entity_id})"
                                          for d in result.duplicates})[:3])
                messages.append(f"Hinweis: »{result.attachment.original_filename}« ist inhaltsgleich "
                                f"(SHA-256) mit bereits vorhandenen Dateien: {where}")
        except RecordError as exc:
            ctx.db.rollback()
            messages.append(f"{up.filename}: {exc}")
    summary = f"{ok_count} von {len(uploads)} Datei(en) hochgeladen."
    if is_fetch:
        ctx.db.commit()
        return JSONResponse({"ok": ok_count > 0, "summary": summary, "messages": messages})
    for m in messages:
        ctx.flash("warning", m)
    return ctx.redirect(entity_url(entity_type, entity_id) + "#anhaenge", "success" if ok_count else "error", summary)


def _file_response(ctx: Ctx, att: Attachment, inline: bool):
    path = file_service.absolute_path(att)
    if not path.exists():
        raise HTTPException(404, "Die Datei fehlt in der Dateiablage. Bitte Administration informieren.")
    if not inline:
        audit.log(ctx.db, ctx.actor, "file_download", entity_type=att.entity_type, entity_id=att.entity_id,
                  field=att.original_filename, version=att.version)
    ctx.db.commit()
    disp = "inline" if inline else "attachment"
    ascii_name = att.original_filename.encode("ascii", "replace").decode().replace("?", "_").replace('"', "")
    headers = {"Content-Disposition": f"{disp}; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(att.original_filename)}"}
    media = att.mime_type if inline else "application/octet-stream"
    return FileResponse(path, media_type=media, headers=headers)


@router.get("/anhaenge/{att_id:int}/download")
def download(att_id: int, ctx: Ctx = Depends(get_ctx)):
    ctx.require("view")
    return _file_response(ctx, _get_att(ctx, att_id), inline=False)


@router.get("/anhaenge/{att_id:int}/vorschau")
def preview(att_id: int, ctx: Ctx = Depends(get_ctx)):
    ctx.require("view")
    att = _get_att(ctx, att_id)
    if not (att.extension in file_service.PREVIEW_IMAGE_EXT or att.extension == "pdf"):
        raise HTTPException(400, "Für diesen Dateityp ist keine Vorschau verfügbar.")
    return _file_response(ctx, att, inline=True)


@router.get("/anhaenge/{att_id:int}")
def detail(att_id: int, ctx: Ctx = Depends(get_ctx)):
    ctx.require("view")
    att = _get_att(ctx, att_id)
    chain = []
    cur = att
    while cur is not None:
        chain.append(cur)
        cur = ctx.db.get(Attachment, cur.previous_id) if cur.previous_id else None
    newer = ctx.db.query(Attachment).filter(Attachment.previous_id == att.id).first()
    duplicates = file_service.find_duplicates(ctx.db, att.sha256, exclude_id=att.id)
    from ..models import AuditLog

    history = (ctx.db.query(AuditLog).filter(AuditLog.entity_type == att.entity_type,
                                             AuditLog.entity_id == att.entity_id,
                                             AuditLog.field.like(f"{att.original_filename}%"))
               .order_by(AuditLog.id.desc()).all())
    from ..core.vocab import ATTACHMENT_CATEGORIES

    return ctx.render("attachments/detail.html", att=att, chain=chain, newer=newer, duplicates=duplicates,
                      history=history, parent_url=entity_url(att.entity_type, att.entity_id),
                      parent=get_entity(ctx.db, att.entity_type, att.entity_id),
                      categories=ATTACHMENT_CATEGORIES, levels=CONFIDENTIALITY,
                      locked=file_service.entity_locked(ctx.db, att.entity_type, att.entity_id),
                      can_delete=_physical_delete_allowed(ctx, att)[0])


@router.get("/anhaenge/{att_id:int}/pruefen")
def verify(att_id: int, ctx: Ctx = Depends(get_ctx)):
    ctx.require("view")
    att = _get_att(ctx, att_id)
    ok = file_service.verify_attachment(att)
    return ctx.redirect(f"/anhaenge/{att.id}", "success" if ok else "error",
                        "Prüfsumme stimmt überein – die Datei ist unverändert." if ok else
                        "ACHTUNG: Datei fehlt oder Prüfsumme weicht ab! Bitte Administration informieren.")


@router.post("/anhaenge/{att_id:int}/meta")
async def update_meta(att_id: int, request: Request, ctx: Ctx = Depends(get_ctx)):
    ctx.require("edit")
    att = _get_att(ctx, att_id)
    locked = file_service.entity_locked(ctx.db, att.entity_type, att.entity_id)
    if locked:
        raise RecordError(locked)
    form = await request.form()
    conf = form.get("confidentiality") or att.confidentiality
    file_service.update_meta(ctx.db, ctx.actor, att, description=(form.get("description") or "").strip() or None,
                             caption=(form.get("caption") or "").strip() or None,
                             category=form.get("category") or None,
                             confidentiality=conf if conf in CONFIDENTIALITY else att.confidentiality,
                             reason=(form.get("reason") or "").strip() or None)
    return ctx.redirect(f"/anhaenge/{att.id}", "success", "Angaben gespeichert.")


@router.post("/anhaenge/{att_id:int}/neue-version")
async def new_version(att_id: int, request: Request, ctx: Ctx = Depends(get_ctx)):
    ctx.require("edit")
    att = _get_att(ctx, att_id)
    if att.status != "aktiv":
        raise RecordError("Nur aktive Dateien können durch eine neue Version ersetzt werden.")
    form = await request.form()
    up = form.get("file")
    reason = (form.get("reason") or "").strip()
    if not reason:
        raise RecordError("Bitte einen Grund für die neue Version angeben.")
    if not hasattr(up, "filename") or not up.filename:
        raise RecordError("Bitte eine Datei auswählen.")
    result = file_service.save_upload(ctx.db, ctx.actor, stream=up.file, filename=up.filename,
                                      entity_type=att.entity_type, entity_id=att.entity_id,
                                      description=att.description, caption=att.caption, category=att.category,
                                      confidentiality=att.confidentiality, previous=att, reason=reason)
    return ctx.redirect(f"/anhaenge/{result.attachment.id}", "success",
                        f"Version {result.attachment.version} gespeichert. Die bisherige Version bleibt erhalten.")


@router.post("/anhaenge/{att_id:int}/status")
async def set_status(att_id: int, request: Request, ctx: Ctx = Depends(get_ctx)):
    att = _get_att(ctx, att_id)
    form = await request.form()
    new_status = form.get("status", "")
    ctx.require("archive" if new_status == "archiviert" else "delete_files")
    file_service.set_status(ctx.db, ctx.actor, att, new_status, (form.get("reason") or "").strip() or None)
    return ctx.redirect(f"/anhaenge/{att.id}", "success", f"Datei als »{new_status}« gekennzeichnet.")


def _physical_delete_allowed(ctx: Ctx, att: Attachment) -> tuple[bool, str]:
    if not ctx.user.has("delete_files"):
        return False, "Keine Berechtigung."
    if file_service.entity_locked(ctx.db, att.entity_type, att.entity_id):
        return False, "Datensatz ist gesperrt."
    in_snapshot = ctx.db.query(RecordSnapshot).filter(RecordSnapshot.data_json.contains(att.file_uid)).first()
    if in_snapshot:
        return False, "Datei ist Teil eines eingereichten oder freigegebenen Stands und darf nicht gelöscht werden."
    if ctx.db.query(Attachment).filter(Attachment.previous_id == att.id).first():
        return False, "Es existieren neuere Versionen dieser Datei."
    return True, ""


@router.post("/anhaenge/{att_id:int}/loeschen")
async def delete(att_id: int, request: Request, ctx: Ctx = Depends(get_ctx)):
    """Kontrollierte physische Löschung (nur nie eingereichte Dateien, mit Begründung)."""
    att = _get_att(ctx, att_id)
    allowed, why = _physical_delete_allowed(ctx, att)
    if not allowed:
        raise RecordError(f"Löschen nicht möglich: {why} Verwenden Sie »ungültig setzen«.")
    form = await request.form()
    reason = (form.get("reason") or "").strip()
    if not reason:
        raise RecordError("Bitte eine Begründung angeben.")
    path = file_service.absolute_path(att)
    url = entity_url(att.entity_type, att.entity_id)
    audit.log(ctx.db, ctx.actor, "delete", entity_type=att.entity_type, entity_id=att.entity_id,
              field=att.original_filename, old=f"SHA-256 {att.sha256}; {att.size_bytes} Bytes", new=None,
              reason=reason, version=att.version)
    if att.previous_id:
        prev = ctx.db.get(Attachment, att.previous_id)
        if prev and prev.status == "ersetzt":
            prev.status = "aktiv"
    ctx.db.delete(att)
    ctx.db.commit()
    path.unlink(missing_ok=True)
    return ctx.redirect(url + "#anhaenge", "success", "Datei gelöscht (im Audit Trail protokolliert).")


@router.post("/kommentare")
async def add_comment(request: Request, ctx: Ctx = Depends(get_ctx)):
    ctx.require("view")
    form = await request.form()
    entity_type = form.get("entity_type", "")
    try:
        entity_id = int(form.get("entity_id", ""))
    except ValueError:
        raise HTTPException(400) from None
    _parent_check(ctx, entity_type, entity_id)
    text = (form.get("text") or "").strip()
    if not text:
        return ctx.redirect(entity_url(entity_type, entity_id) + "#kommentare", "error", "Kommentar ist leer.")
    c = Comment(entity_type=entity_type, entity_id=entity_id, text=text[:10000], created_by_id=ctx.user.id)
    ctx.db.add(c)
    audit.log(ctx.db, ctx.actor, "comment", entity_type=entity_type, entity_id=entity_id, new=text[:500])
    return ctx.redirect(entity_url(entity_type, entity_id) + "#kommentare", "success", "Kommentar gespeichert.")
