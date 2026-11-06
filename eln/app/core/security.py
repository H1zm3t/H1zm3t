"""Passwort-Hashing (PBKDF2-HMAC-SHA256, Python-Standardbibliothek) und Tokens."""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

ALGORITHM = "pbkdf2_sha256"
PBKDF2_ITERATIONS = 600_000  # Empfehlung OWASP 2023 für PBKDF2-SHA256
MIN_PASSWORD_LENGTH = 10


def hash_password(password: str, iterations: int | None = None) -> str:
    iterations = iterations or PBKDF2_ITERATIONS
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return "$".join(
        [ALGORITHM, str(iterations), base64.b64encode(salt).decode(), base64.b64encode(digest).decode()]
    )


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, iterations, salt_b64, digest_b64 = stored.split("$")
        if algorithm != ALGORITHM:
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(digest_b64)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iterations))
        return hmac.compare_digest(digest, expected)
    except (ValueError, TypeError):
        return False


def password_problems(password: str) -> list[str]:
    """Einfache Passwortrichtlinie – liefert verständliche Hinweise."""
    problems = []
    if len(password) < MIN_PASSWORD_LENGTH:
        problems.append(f"Das Passwort muss mindestens {MIN_PASSWORD_LENGTH} Zeichen lang sein.")
    if password.isalpha() or password.isdigit():
        problems.append("Das Passwort muss Buchstaben und Ziffern oder Sonderzeichen enthalten.")
    return problems


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))
