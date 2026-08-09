"""Phase 3 tests: chat streaming via SSE with a fake LLM client (no API key needed)."""

from __future__ import annotations

import json


class FakeLLM:
    """Async streaming fake: yields fixed tokens matching the LLMClient contract."""

    def __init__(self, words=("Halo, ", "saya ", "asisten.")):
        self.words = words

    async def astream(self, messages, **kwargs):
        assert messages[0]["role"] == "system", "expected system prompt first"
        assert any(m["role"] == "user" for m in messages), "expected user turn in history"
        for w in self.words:
            yield {"type": "delta", "delta": w}
        yield {"type": "usage", "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8}}


def _register(client, email="c0@x.com", username="c0") -> tuple[str, dict]:
    tok = client.post(
        "/api/v1/auth/register",
        json={"email": email, "username": username, "password": "password123"},
    ).json()["access_token"]
    return tok, {"Authorization": f"Bearer {tok}"}


def _stream(client, headers, conv_id, content):
    frames = []
    with client.stream(
        "POST",
        f"/api/v1/conversations/{conv_id}/chat",
        json={"content": content},
        headers=headers,
    ) as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        for line in resp.iter_lines():
            if line.startswith("data: "):
                frames.append(json.loads(line[6:]))
    text = "".join(e["delta"] for e in frames if e["type"] == "token")
    return frames, text


def test_chat_streams_tokens_and_saves_messages(client, monkeypatch):
    from app.services import chat as chat_service

    monkeypatch.setattr(chat_service, "build_llm_client", lambda: FakeLLM())

    tok, headers = _register(client, "c1@x.com", "c1")
    conv_id = client.post("/api/v1/conversations", json={}, headers=headers).json()["id"]

    events, text = _stream(client, headers, conv_id, "halo")
    assert text == "Halo, saya asisten."

    done = [e for e in events if e["type"] == "done"][0]
    assert done["route"] == "simple"
    assert done["usage"]["total_tokens"] == 8

    conv = client.get(f"/api/v1/conversations/{conv_id}", headers=headers).json()
    assert [m["role"] for m in conv["messages"]] == ["user", "assistant"]
    assert conv["messages"][1]["route"] == "simple"
    assert conv["active_route"] == "simple"

    from app.db.base import session_scope
    from app.db.models import AuditLog

    with session_scope() as db:
        row = db.query(AuditLog).filter(AuditLog.action == "chat.send").order_by(AuditLog.id.desc()).first()
        assert row is not None
        assert row.route == "simple"
        assert row.status == "ok"
        assert row.token_usage["total_tokens"] == 8


def test_chat_multiturn_uses_history(client, monkeypatch):
    """Second turn should include the first user message in the prompt history."""
    from app.services import chat as chat_service

    captured = []

    class CaptureLLM(FakeLLM):
        async def astream(self, messages, temperature=None):
            captured.append([m["content"] for m in messages if m["role"] == "user"])
            async for ev in super().astream(messages, temperature=temperature):
                yield ev

    monkeypatch.setattr(chat_service, "build_llm_client", lambda: CaptureLLM())

    _, headers = _register(client, "c2@x.com", "c2")
    conv_id = client.post("/api/v1/conversations", json={}, headers=headers).json()["id"]

    for q in ("pertama?", "kedua?"):
        _stream(client, headers, conv_id, q)

    assert captured[-1][-1] == "kedua?"
    assert "pertama?" in captured[-1]


def test_chat_missing_conversation_returns_error_event(client, monkeypatch):
    from app.services import chat as chat_service

    monkeypatch.setattr(chat_service, "build_llm_client", lambda: FakeLLM())

    _, headers = _register(client, "c3@x.com", "c3")
    resp = client.post(
        "/api/v1/conversations/999999/chat", json={"content": "halo"}, headers=headers
    )
    assert resp.status_code == 404


def test_chat_llm_error_emits_error_event_and_audits(client, monkeypatch):
    from app.services import chat as chat_service
    from app.llm.client import LLMError

    class FailingLLM(FakeLLM):
        async def astream(self, messages, **kwargs):
            raise LLMError("upstream gone")
            yield  # pragma: no cover - keeps this an async generator

    monkeypatch.setattr(chat_service, "build_llm_client", lambda: FailingLLM())

    _, headers = _register(client, "c4@x.com", "c4")
    conv_id = client.post("/api/v1/conversations", json={}, headers=headers).json()["id"]

    events, _ = _stream(client, headers, conv_id, "halo")
    assert events[0]["type"] == "error"
    assert "upstream gone" in events[0]["message"]

    from app.db.base import session_scope
    from app.db.models import AuditLog

    with session_scope() as db:
        row = db.query(AuditLog).filter(AuditLog.action == "chat.send").order_by(AuditLog.id.desc()).first()
        assert row.status == "error"
        assert "upstream gone" in row.error


def test_prompt_render_uses_business_context():
    from app.llm.prompts import render_prompt

    out = render_prompt("system", assistant_name="Asisten", business_context="Perusahaan X", today="2026-08-09")
    assert "Perusahaan X" in out
    assert "Asisten" in out