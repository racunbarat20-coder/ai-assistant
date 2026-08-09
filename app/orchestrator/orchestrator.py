"""Orchestrator: detect intent -> emit route context -> dispatch to mode runner.

The chat service drives this as a single async stream so UI/LLM latency are
uniform. All modes share the same event protocol.
"""

from __future__ import annotations

from typing import Any, AsyncGenerator

from app.orchestrator import modes
from app.orchestrator.router import RouteIntent, detect_route

_MODE_RUNNERS = {
    "simple": modes.run_simple,
    "rag": modes.run_rag,
    "sql": modes.run_sql,
    "deep": modes.run_deep,
}


class Orchestrator:
    def __init__(self, llm_client: Any) -> None:
        self.llm = llm_client

    def detect(
        self,
        message: str,
        history: list[str] | None = None,
        use_llm: bool = False,
    ) -> RouteIntent:
        return detect_route(message, history or [], self.llm if use_llm else None)

    async def run(
        self,
        intent: RouteIntent,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Emit intent context then delegate to the mode runner."""
        yield {
            "type": "intent",
            "route": intent.key,
            "mode": intent.mode,
            "agent": intent.agent,
            "confidence": intent.confidence,
            "method": intent.method,
        }

        runner = _MODE_RUNNERS.get(intent.mode, modes.run_simple)
        async for event in runner(messages, self.llm, temperature=temperature, route=intent.mode):
            event.setdefault("route", intent.key)
            event.setdefault("agent", intent.agent)
            yield event


def build_orchestrator() -> Orchestrator:
    from app.llm.client import build_llm_client

    return Orchestrator(build_llm_client())