"""Auth routes: /api/v1/auth/register|login|me."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.schemas import LoginRequest, RegisterRequest, TokenOut, UserOut
from app.db.base import get_db
from app.db.models import User
from app.services import auth

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/register", response_model=TokenOut, status_code=201)
def register(body: RegisterRequest, db: Session = Depends(get_db)):
    user, token = auth.register_user(db, body.email, body.username, body.password)
    return TokenOut(
        access_token=token,
        expires_in_minutes=auth.token_expiry_minutes(),
        user=UserOut.model_validate(user),
    )


@router.post("/login", response_model=TokenOut)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user, token = auth.login_user(db, body.email, body.password)
    return TokenOut(
        access_token=token,
        expires_in_minutes=auth.token_expiry_minutes(),
        user=UserOut.model_validate(user),
    )


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return UserOut.model_validate(user)