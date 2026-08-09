"""Mode runners (one per route mode). Each is an async generator yielding SSE
event dicts: {"type":"token"|"usage"|"done"|"notice"|"error", ...}.

Phase 4 wires the routing + dispatch layer; rag/sql/deep are placeholders that
will be fully implemented in Phase 5-7.
"""

from __future__ import annotations

from typing import Any, AsyncGenerator

from app.llm.client import LLMError


async def run_simple(
    messages: list[dict[str, str]],
    llm: Any,
    *,
    temperature: float = 0.2,
    route: str = "simple",
) -> AsyncGenerator[dict[str, Any], None]:
    """Plain single-shot answer, streaming."""
    try:
        async for event in llm.astream(messages, temperature=temperature):
            yield event
    except LLMError as exc:
        yield {"type": "error", "message": str(exc)[:300]}


async def _pending(notice: str, answer: str) -> AsyncGenerator[dict[str, Any], None]:
    yield {"type": "notice", "message": notice}
    yield {"type": "delta", "delta": answer}
    yield {"type": "done", "mode": "pending"}


async def run_rag(messages, llm, **kwargs) -> AsyncGenerator[dict[str, Any], None]:
    """Stub until Phase 5 (RAG)."""
    async for ev in _pending(
        "Mode knowledge (RAG) belum tersedia pada fase ini.",
        "Saya belum dapat mencari knowledge base. Gunakan pertanyaan biasa dulu.",
    ):
        yield ev


async def run_sql(messages, llm, **kwargs) -> AsyncGenerator[dict[str, Any], None]:
    """Stub until Phase 6 (SQL tool)."""
    async for ev in _pending(
        "Mode data/SQL belum tersedia pada fase ini.",
        "Analisis data belum aktif. Untuk saat ini saya jawab dari pengetahuan umum.",
    ):
        yield ev


async def run_deep(messages, llm, **kwargs) -> AsyncGenerator[dict[str, Any], None]:
    """Stub until Phase 7 (deep analysis pipeline)."""
    async for ev in _pending(
        "Mode analisis mendalam belum tersedia pada fase ini.",
        "Analisis mendalam belum tersedia. Coba pertanyaan yang lebih sederhana.",
    ):
        yield ev