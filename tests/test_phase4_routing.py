"""Phase 4 tests: intent routing + orchestrator dispatch in the chat stream."""

from __future__ import annotations

import json


from app.db.models import AuditLog
from app.orchestrator.router import RouteIntent, detect_route, heuristic_route

import pytest


class FakeLLM:
    def __init__(self, words=("jawaban ", "mode ", "sesuai.")):
        self.words = words

    async def astream(self, messages, temperature=None):
        for w in self.words:
            yield {"type": "delta", "delta": w}
        yield {"type": "usage", "usage": {"total_tokens": 5}}


def _register(client, email="r0@x.com", username="r0"):
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
        for line in resp.iter_lines():
            if line.startswith("data: "):
                frames.append(json.loads(line[6:]))
    return frames


def test_heuristic_routes_data_sql():
    intent = heuristic_route("Berapa total penjualan di database kita bulan lalu?")
    assert intent.key == "data_sql"
    assert intent.mode == "sql"


def test_heuristic_routes_deep_analysis():
    intent = heuristic_route("Tolong berikan analisis mendalam dan rekomendasi strategi pemasaran.")
    assert intent.key == "analysis"
    assert intent.mode == "deep"


def test_heuristic_routes_knowledge():
    intent = heuristic_route("Tolong cari di basis pengetahuan tentang standar kami.")
    assert intent.key == "knowledge"
    assert intent.mode == "rag"


def test_heuristic_falls_back_to_simple():
    intent = heuristic_route("Halo, apa kabar?")
    assert intent.key == "simple"
    assert intent.mode == "simple"


def test_detect_route_respects_config_and_fallback(monkeypatch):
    # LLM router disabled by default settings -> heuristic result even with fake llm
    fake = object()
    intent = detect_route("Beri saya laporan statistik data mingguan.", llm_client=fake)
    assert intent.key == "data_sql"


def test_chat_emits_intent_event_with_route(client, monkeypatch):
    from app.services import chat as chat_service

    captured_routes = []

    class TracingLLM(FakeLLM):
        async def astream(self, messages, temperature=None):
            captured_routes.append(messages[1]["content"] if len(messages) > 1 else "")
            async for ev in super().astream(messages, temperature=temperature):
                yield ev

    monkeypatch.setattr(chat_service, "build_llm_client", lambda: TracingLLM())

    _, headers = _register(client)
    conv_id = client.post("/api/v1/conversations", json={}, headers=headers).json()["id"]

    frames = _stream(client, headers, conv_id, "Hitung total jumlah transaksi di data kami")
    kinds = [f["type"] for f in frames]
    assert "intent" in kinds
    intent = [f for f in frames if f["type"] == "intent"][0]
    assert intent["route"] == "data_sql"
    assert intent["mode"] == "sql"
    assert intent["agent"] == "data_analyst"
    assert "done" in kinds

    conv = client.get(f"/api/v1/conversations/{conv_id}", headers=headers).json()
    assert conv["active_route"] == "data_sql"
    assert conv["messages"][0]["role"] == "user" and conv["messages"][0]["route"] == "data_sql"
    assert conv["messages"][1]["role"] == "assistant" and conv["messages"][1]["route"] == "data_sql"


def test_simple_route_still_streams(client, monkeypatch):
    from app.services import chat as chat_service

    monkeypatch.setattr(chat_service, "build_llm_client", lambda: FakeLLM())

    _, headers = _register(client, "r1@x.com", "r1")
    conv_id = client.post("/api/v1/conversations", json={}, headers=headers).json()["id"]

    frames = _stream(client, headers, conv_id, "apa itu ai?")
    intent = [f for f in frames if f["type"] == "intent"][0]
    assert intent["route"] == "simple"
    done = [f for f in frames if f["type"] == "done"][0]
    assert done["agent"] == "simple_chat"