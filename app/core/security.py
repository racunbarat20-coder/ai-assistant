"""Password hashing (PBKDF2-HMAC-SHA256, stdlib) and JWT helpers.

No bcrypt/passlib dependency -> fewer supply-chain surface. Format:
    pbkdf2_sha256$<iterations>$<salt_b64>$<digest_b64>
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt

from app.core.config import get_config

_ITERATIONS = 260_000
_ALGO = "sha256"


def _pepper() -> str:
    return get_config().env.password_pepper or ""


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac(_ALGO, (password + _pepper()).encode("utf-8"), salt, _ITERATIONS)
    return "$".join(
        [
            f"pbkdf2_{_ALGO}",
            str(_ITERATIONS),
            base64.b64encode(salt).decode(),
            base64.b64encode(dk).decode(),
        ]
    )


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iter_s, salt_b64, dk_b64 = stored.split("$")
        iterations = int(iter_s)
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(dk_b64)
    except (ValueError, TypeError):
        return False
    dk = hashlib.pbkdf2_hmac(_ALGO, (password + _pepper()).encode("utf-8"), salt, iterations)
    return hmac.compare_digest(dk, expected)


def create_access_token(
    subject: Any,
    role: str = "user",
    group: str | None = None,
    expires_minutes: int | None = None,
) -> str:
    cfg = get_config().env
    minutes = expires_minutes or cfg.access_token_expire_minutes
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": str(subject),
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=minutes),
    }
    if group:
        payload["group"] = group
    return jwt.encode(payload, cfg.jwt_secret_key, algorithm=cfg.jwt_algorithm)


def decode_token(token: str) -> dict[str, Any]:
    cfg = get_config().env
    return jwt.decode(token, cfg.jwt_secret_key, algorithms=[cfg.jwt_algorithm])