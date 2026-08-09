"""Conversation service: create/list/get/delete incl. ownership checks."""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models import Conversation, User


def _conversation(db: Session, conversation_id: int, user_id: int) -> Conversation:
    conv = db.scalar(
        select(Conversation)
        .options(selectinload(Conversation.messages))
        .where(Conversation.id == conversation_id, Conversation.user_id == user_id)
    )
    if conv is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    return conv


def create_conversation(db: Session, user: User, title: str = "New conversation") -> Conversation:
    conv = Conversation(user_id=user.id, title=title)
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv


def list_conversations(db: Session, user: User) -> list[Conversation]:
    return list(
        db.scalars(
            select(Conversation)
            .where(Conversation.user_id == user.id)
            .order_by(Conversation.updated_at.desc())
        )
    )


def get_conversation(db: Session, user: User, conversation_id: int) -> Conversation:
    return _conversation(db, conversation_id, user.id)


def delete_conversation(db: Session, user: User, conversation_id: int) -> None:
    conv = _conversation(db, conversation_id, user.id)
    db.delete(conv)
    db.commit()