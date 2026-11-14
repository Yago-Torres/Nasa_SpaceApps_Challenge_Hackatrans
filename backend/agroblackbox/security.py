"""Password hashing and opaque session tokens (ABB-05, ADR-0004).

Standard library only. Nothing in this module logs or returns a password or a raw token
except ``new_session_token``, whose raw value is handed to the client exactly once.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import timedelta

# scrypt cost parameters (ADR-0004). Memory use is 128 * r * n bytes = 16 MiB per hash.
SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_DKLEN = 64
SALT_BYTES = 16
_SCRYPT_MAXMEM = 64 * 1024 * 1024

PASSWORD_MIN_LENGTH = 12
PASSWORD_MAX_LENGTH = 256

SESSION_TTL = timedelta(hours=12)
TOKEN_BYTES = 32

MAX_FAILED_LOGINS = 5
LOCKOUT_DURATION = timedelta(minutes=15)


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _scrypt(password: str, salt: bytes, n: int, r: int, p: int, dklen: int) -> bytes:
    return hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=dklen, maxmem=_SCRYPT_MAXMEM
    )


def password_policy_error(password: str) -> str | None:
    """Return a fixed, value-free message when the password violates the policy."""
    if not PASSWORD_MIN_LENGTH <= len(password) <= PASSWORD_MAX_LENGTH:
        return (
            f"Password must contain between {PASSWORD_MIN_LENGTH} and "
            f"{PASSWORD_MAX_LENGTH} characters."
        )
    return None


def hash_password(password: str) -> str:
    """Encode as ``scrypt$n$r$p$salt_b64$hash_b64`` with a fresh random salt."""
    salt = secrets.token_bytes(SALT_BYTES)
    digest = _scrypt(password, salt, SCRYPT_N, SCRYPT_R, SCRYPT_P, SCRYPT_DKLEN)
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, encoded: str | None) -> bool:
    """Constant-time verification. Malformed or missing hashes never verify."""
    if not encoded:
        return False
    try:
        scheme, n, r, p, salt_b64, digest_b64 = encoded.split("$")
        if scheme != "scrypt":
            return False
        salt = base64.b64decode(salt_b64, validate=True)
        expected = base64.b64decode(digest_b64, validate=True)
        candidate = _scrypt(password, salt, int(n), int(r), int(p), len(expected))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(candidate, expected)


# Verified against when the e-mail is unknown, so response time does not reveal accounts.
_DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


def burn_password_check(password: str) -> None:
    verify_password(password, _DUMMY_HASH)


def new_session_token() -> str:
    return secrets.token_urlsafe(TOKEN_BYTES)


def token_digest(token: str) -> str:
    """Only this SHA-256 hex digest is persisted; the raw bearer token is never stored."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
