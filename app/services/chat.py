"""Chat service: orchestrates intent routing + streaming, persists messages, audits."""

from __future__ import annotations

import logging
import time
from typing import AsyncGenerator

from sqlalchemy.orm import Session

from app.db import base as db_base
from app.db.models import Conversation, Message
from app.llm.client import build_llm_client  # noqa: F401 (re-export for tests)
from app.llm.prompts import render_prompt
from app.llm.sse import sse_event
from app.orchestrator.orchestrator import Orchestrator
from app.services import audit

logger = logging.getLogger("app.chat")

_HISTORY_LIMIT = 12


def _history(messages: list[Message], limit: int) -> list[dict[str, str]]:
    """Map stored roles -> LLM messages, bounded to the most recent `limit` turns."""
    out: list[dict[str, str]] = []
    for m in messages[-limit:]:
        role = "assistant" if m.role == "assistant" else "user"
        out.append({"role": role, "content": m.content})
    return out


def _system_prompt() -> str:
    from app.core.config import get_config

    cfg = get_config()
    business = cfg.yaml("business", None)
    context = (business or {}).get("context", "") if isinstance(business, dict) else ""
    return render_prompt(
        "system",
        assistant_name=cfg.app_name,
        business_context=context,
        today=time.strftime("%Y-%m-%d"),
    )


async def stream_chat(
    conversation_id: int,
    content: str,
) -> AsyncGenerator[str, None]:
    """Stream SSE events for one user turn.

    Opens its own DB session so the request-scoped session is never touched
    after the stream ends. Event types: intent | token | done | error
    """
    started_at = time.monotonic()
    with db_base.SessionLocal() as db:
        conv = db.get(Conversation, conversation_id)
        if conv is None:
            yield sse_event({"type": "error", "message": "Conversation not found"})
            return

        stored = (
            db.query(Message)
            .filter(Message.conversation_id == conv.id)
            .order_by(Message.id)
            .all()
        )
        history = _history(stored, _HISTORY_LIMIT)

        # ---- intent detection (config-driven) ----
        orchestrator = Orchestrator(build_llm_client())
        intent = orchestrator.detect(content, history)

        conv.active_route = intent.key
        db.add(Message(conversation_id=conv.id, role="user", content=content, route=intent.key))
        db.commit()

        # rebuild prompt history now that the new user turn is persisted
        stored = (
            db.query(Message)
            .filter(Message.conversation_id == conv.id)
            .order_by(Message.id)
            .all()
        )
        messages = [{"role": "system", "content": _system_prompt()}] + _history(stored, _HISTORY_LIMIT)

        usage = None
        pieces: list[str] = []
        errored = False

        try:
            async for event in orchestrator.run(intent, messages, temperature=0.5):
                etype = event.get("type")
                if etype == "intent":
                    yield sse_event(event)
                elif etype == "token":
                    pieces.append(event["delta"])
                    yield sse_event({"type": "token", "delta": event["delta"]})
                elif etype == "usage":
                    usage = event["usage"]
                elif etype == "notice":
                    yield sse_event({"type": "notice", "message": event["message"]})
                elif etype == "error":
                    if not errored:
                        errored = True
                        logger.warning("chat error event: %s", event.get("message"))
                        yield sse_event({"type": "error", "message": event.get("message")})

            if errored:
                _persist_partial(db, conv, intent, "".join(pieces), usage)
                _audit(db, conv.user_id, intent, started_at, usage=usage, status="error")
            else:
                answer = "".join(pieces)
                assistant = Message(
                    conversation_id=conv.id,
                    role="assistant",
                    content=answer,
                    route=intent.key,
                    meta={"usage": usage},
                )
                db.add(assistant)
                db.commit()
                db.refresh(assistant)
                _audit(db, conv.user_id, intent.key, started_at, usage=usage, status="ok")
                yield sse_event(
                    {
                        "type": "done",
                        "message_id": assistant.id,
                        "route": intent.key,
                        "mode": intent.mode,
                        "agent": intent.agent,
                        "usage": usage,
                    }
                )
        except Exception as exc:  # never leak internals to the client
            logger.exception("chat internal error")
            _persist_partial(db, conv, intent.key, "".join(pieces), usage)
            _audit(db, conv.user_id, intent.key, started_at, usage=usage, status="error", error=type(exc).__name__)
            if not errored:
                yield sse_event({"type": "error", "message": "Internal error while generating the answer."})


def _persist_partial(
    db: Session, conv: Conversation, route: str, text: str, usage: dict | None
) -> None:
    if not text:
        return
    db.add(
        Message(
            conversation_id=conv.id,
            role="assistant",
            content=text,
            route=route,
            meta={"partial": True, "usage": usage},
        )
    )
    db.commit()


def _audit(
    db: Session,
    user_id: int,
    route: str,
    started_at: float,
    *,
    usage: dict | None = None,
    status: str = "ok",
    error: str | None = None,
) -> None:
    latency_ms = int((time.monotonic() - started_at) * 1000)
    audit.log_event(
        db,
        action="chat.send",
        user_id=user_id,
        route=route,
        agent=route,
        status=status,
        latency_ms=latency_ms,
        token_usage=usage,
        error=error,
    )