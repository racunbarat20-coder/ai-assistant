"""Conversation routes: /api/v1/conversations CRUD."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.schemas import ConversationBrief, ConversationCreate, ConversationOut
from app.db.base import get_db
from app.db.models import User
from app.services import audit, conversation

router = APIRouter(prefix="/api/v1/conversations", tags=["conversations"])


@router.post("", response_model=ConversationOut, status_code=status.HTTP_201_CREATED)
def create_conversation(
    body: ConversationCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conv = conversation.create_conversation(db, user, body.title)
    audit.log_event(db, action="conversation.create", user_id=user.id, status="ok")
    return ConversationOut.model_validate(conv)


@router.get("", response_model=list[ConversationBrief])
def list_conversations(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    convs = conversation.list_conversations(db, user)
    return [ConversationBrief.model_validate(c) for c in convs]


@router.get("/{conversation_id}", response_model=ConversationOut)
def get_conversation(
    conversation_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conv = conversation.get_conversation(db, user, conversation_id)
    return ConversationOut.model_validate(conv)


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(
    conversation_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conversation.delete_conversation(db, user, conversation_id)
    audit.log_event(db, action="conversation.delete", user_id=user.id, status="ok")
    return Response(status_code=status.HTTP_204_NO_CONTENT)