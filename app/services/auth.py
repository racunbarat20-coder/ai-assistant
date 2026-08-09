"""Auth service: register/login, token issuance, audit hooks."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_config
from app.core.security import create_access_token, hash_password, verify_password
from app.db.models import User
from app.services import audit


def _maybe_audit(db: Session | None, **kwargs) -> None:
    if db is not None:
        audit.log_event(db, **kwargs)


def register_user(db: Session, email: str, username: str, password: str) -> tuple[User, str]:
    existing = db.scalar(select(User).where((User.email == email) | (User.username == username)))
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email or username already exists")

    user = User(email=email, username=username, password_hash=hash_password(password))
    db.add(user)
    db.commit()
    db.refresh(user)

    token = _issue_token(user)
    _maybe_audit(db, action="auth.register", user_id=user.id, status="ok")
    return user, token


def login_user(db: Session, email: str, password: str) -> tuple[User, str]:
    user = db.scalar(select(User).where(User.email == email))
    if user is None or not verify_password(password, user.password_hash):
        # audit failed attempt for recognized account
        _maybe_audit(
            db,
            action="auth.login",
            user_id=user.id if user else None,
            status="failed",
            error="invalid credentials",
        )
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is disabled")

    user.last_login_at = datetime.now(timezone.utc)
    db.commit()

    token = _issue_token(user)
    _maybe_audit(db, action="auth.login", user_id=user.id, status="ok")
    return user, token


def _issue_token(user: User) -> str:
    return create_access_token(subject=user.id, role=user.role, group=user.group)


def token_expiry_minutes() -> int:
    return get_config().env.access_token_expire_minutes