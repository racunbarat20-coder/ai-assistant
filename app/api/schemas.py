"""Pydantic schemas (request/response) for auth & conversations."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator


# ---------------- Auth ----------------
class RegisterRequest(BaseModel):
    email: EmailStr
    username: str = Field(min_length=2, max_length=80)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("password")
    @classmethod
    def password_has_letter_and_digit(cls, v: str) -> str:
        if not any(c.isalpha() for c in v) or not any(c.isdigit() for c in v):
            raise ValueError("password must contain at least one letter and one digit")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: int
    email: EmailStr
    username: str
    role: str
    group: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_minutes: int
    user: UserOut


# ---------------- Conversations ----------------
class ConversationCreate(BaseModel):
    title: str = "New conversation"


class MessageOut(BaseModel):
    id: int
    role: str
    content: str
    route: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ConversationOut(BaseModel):
    id: int
    title: str
    active_route: str | None = None
    created_at: datetime
    updated_at: datetime
    messages: list[MessageOut] = []

    model_config = {"from_attributes": True}


class ConversationBrief(BaseModel):
    id: int
    title: str
    active_route: str | None = None
    updated_at: datetime

    model_config = {"from_attributes": True}