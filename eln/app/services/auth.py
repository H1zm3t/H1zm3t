"""Anmeldung, Sitzungen, Benutzer und Rollen."""
from __future__ import annotations

import json
import secrets
from datetime import timedelta

from sqlalchemy.orm import Session

from ..config import get_settings
from ..core.permissions import DEFAULT_ROLES
from ..core.security import hash_password, new_token, password_problems, token_hash, verify_password
from ..db import utcnow
from ..models import Role, User, UserSession
from . import audit
from .audit import Actor


class AuthError(Exception):
    pass


def ensure_default_roles(db: Session) -> None:
    for key, data in DEFAULT_ROLES.items():
        role = db.query(Role).filter_by(key=key).first()
        if role is None:
            role = Role(key=key, name=data["name"], description=data["description"])
            role.permissions = data["permissions"]
            db.add(role)
    db.flush()


def create_user(db: Session, actor: Actor, *, username: str, full_name: str, password: str,
                role_keys: list[str], email: str | None = None, short_name: str | None = None,
                department: str | None = None, must_change_password: bool = False) -> User:
    username = username.strip().lower()
    if not username or not username.replace(".", "").replace("-", "").replace("_", "").isalnum():
        raise AuthError("Der Benutzername darf nur Buchstaben, Ziffern, Punkt, Binde- und Unterstrich enthalten.")
    if db.query(User).filter_by(username=username).first():
        raise AuthError(f"Der Benutzername »{username}« ist bereits vergeben.")
    problems = password_problems(password)
    if problems:
        raise AuthError(" ".join(problems))
    roles = db.query(Role).filter(Role.key.in_(role_keys)).all()
    if not roles:
        raise AuthError("Bitte mindestens eine Rolle auswählen.")
    user = User(
        username=username, full_name=full_name.strip(), email=email, short_name=short_name,
        department=department, password_hash=hash_password(password), roles=roles,
        must_change_password=must_change_password, password_changed_at=utcnow(),
    )
    db.add(user)
    db.flush()
    audit.log(db, actor, "create", entity_type="user", entity_id=user.id, entity_code=user.username,
              new=f"{user.full_name}; Rollen: {', '.join(r.name for r in roles)}")
    return user


def authenticate(db: Session, username: str, password: str, ip: str | None) -> User:
    settings = get_settings()
    actor = Actor(user=None, ip=ip)
    user = db.query(User).filter_by(username=(username or "").strip().lower()).first()
    now = utcnow()
    if user is None:
        audit.log_security(db, actor, "login_failed", f"Unbekannter Benutzer: {username[:64]}", result="abgelehnt")
        raise AuthError("Benutzername oder Passwort ist falsch.")
    if not user.is_active:
        audit.log_security(db, Actor(user, ip), "login_failed", "Konto deaktiviert", result="abgelehnt")
        raise AuthError("Dieses Konto ist deaktiviert. Bitte wenden Sie sich an die Administration.")
    if user.locked_until and user.locked_until > now:
        audit.log_security(db, Actor(user, ip), "login_failed", "Konto gesperrt", result="abgelehnt")
        minutes = int((user.locked_until - now).total_seconds() // 60) + 1
        raise AuthError(f"Das Konto ist wegen zu vieler Fehlversuche für {minutes} Minute(n) gesperrt.")
    if not verify_password(password or "", user.password_hash):
        user.failed_logins += 1
        audit.log_security(db, Actor(user, ip), "login_failed",
                           f"Falsches Passwort (Versuch {user.failed_logins})", result="abgelehnt")
        if user.failed_logins >= settings.max_failed_logins:
            user.locked_until = now + timedelta(minutes=settings.lockout_minutes)
            user.failed_logins = 0
            audit.log_security(db, Actor(user, ip), "account_locked",
                               f"Gesperrt bis {user.locked_until:%d.%m.%Y %H:%M}", result="gesperrt")
        raise AuthError("Benutzername oder Passwort ist falsch.")
    user.failed_logins = 0
    user.locked_until = None
    user.last_login = now
    audit.log_security(db, Actor(user, ip), "login")
    return user


def start_session(db: Session, user: User, ip: str | None, user_agent: str | None) -> str:
    token = new_token()
    db.add(UserSession(token_hash=token_hash(token), user_id=user.id, csrf_token=secrets.token_urlsafe(32),
                       ip_address=ip, user_agent=(user_agent or "")[:300]))
    db.flush()
    return token


def load_session(db: Session, token: str | None) -> UserSession | None:
    if not token:
        return None
    sess = db.query(UserSession).filter_by(token_hash=token_hash(token)).first()
    if sess is None:
        return None
    timeout = timedelta(minutes=get_settings().session_timeout_min)
    now = utcnow()
    if now - sess.last_seen > timeout or not sess.user.is_active:
        db.delete(sess)
        db.flush()
        return None
    if (now - sess.last_seen).total_seconds() > 30:
        sess.last_seen = now
    return sess


def end_session(db: Session, token: str | None, actor: Actor) -> None:
    if not token:
        return
    sess = db.query(UserSession).filter_by(token_hash=token_hash(token)).first()
    if sess:
        db.delete(sess)
        audit.log_security(db, actor, "logout")


def change_password(db: Session, actor: Actor, user: User, new_password: str, *, old_password: str | None = None,
                    by_admin: bool = False) -> None:
    if not by_admin and not verify_password(old_password or "", user.password_hash):
        raise AuthError("Das bisherige Passwort ist nicht korrekt.")
    problems = password_problems(new_password)
    if problems:
        raise AuthError(" ".join(problems))
    user.password_hash = hash_password(new_password)
    user.password_changed_at = utcnow()
    user.must_change_password = by_admin
    user.version += 1
    db.query(UserSession).filter(UserSession.user_id == user.id).delete() if by_admin else None
    audit.log(db, actor, "password_change", entity_type="user", entity_id=user.id, entity_code=user.username,
              new="durch Administration zurückgesetzt" if by_admin else "durch Benutzer geändert")


def push_flash(sess: UserSession | None, kind: str, message: str) -> None:
    if sess is None:
        return
    items = json.loads(sess.flash_json or "[]")
    items.append({"kind": kind, "message": message})
    sess.flash_json = json.dumps(items[-5:], ensure_ascii=False)


def pop_flashes(sess: UserSession | None) -> list[dict]:
    if sess is None:
        return []
    items = json.loads(sess.flash_json or "[]")
    if items:
        sess.flash_json = "[]"
    return items
