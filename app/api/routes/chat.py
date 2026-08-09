"""Chat route: POST /api/v1/conversations/{id}/chat -> SSE stream."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.base import get_db
from app.db.models import User
from app.services import chat, conversation

router = APIRouter(prefix="/api/v1/conversations", tags=["chat"])


class ChatRequest(BaseModel):
    content: str = Field(min_length=1, max_length=4000)


@router.post("/{conversation_id}/chat")
async def chat_stream(
    conversation_id: int,
    body: ChatRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # ownership check (request scope); stream re-validates with its own session
    conversation.get_conversation(db, user, conversation_id)

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(
        chat.stream_chat(conversation_id, body.content),
        media_type="text/event-stream",
        headers=headers,
    )