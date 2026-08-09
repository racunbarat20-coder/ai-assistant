"""Intent router: decides which route/mode handles a user message.

Config-driven keywords (settings.yaml -> orchestrator.keywords). Optionally an
LLM-based router can be enabled (use_llm_router), with heuristic as fallback so
the assistant stays usable without an API key.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from app.core.config import get_config
from app.llm.prompts import render_prompt

DEFAULT_MODE = "simple"
DEFAULT_AGENT = "simple_chat"

_ROUTE_AGENTS = {
    "simple": "simple_chat",
    "knowledge": "knowledge_assistant",
    "data_sql": "data_analyst",
    "analysis": "deep_analyst",
}


@dataclass
class RouteIntent:
    key: str = DEFAULT_MODE          # simple | knowledge | data_sql | analysis
    mode: str = DEFAULT_MODE
    agent: str = DEFAULT_AGENT
    confidence: float = 1.0
    method: str = "heuristic"        # heuristic | llm
    detail: str = field(default="")


def _parse_json(text: str) -> dict[str, Any] | None:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        import re

        m = re.search(r"\{[^{}]+\}", text, re.DOTALL)
        if not m:
            return None
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    return data if isinstance(data, dict) else None


def _mode_for(key: str) -> str:
    cfg = get_config()
    for r in cfg.settings.get("orchestrator", {}).get("routes", []):
        if r.get("key") == key:
            return r.get("mode", key)
    return key


def heuristic_route(message: str, history: list[str] | None = None) -> RouteIntent:
    cfg = get_config()
    keywords = cfg.settings.get("orchestrator", {}).get("keywords", {})
    text = f"{message}\n{' '.join(history or [])[-1200:]}".lower()
    best_key, best_score = DEFAULT_MODE, 0.0

    for key, words in keywords.items():
        if not isinstance(words, list):
            continue
        for w in words:
            if w in text:
                if best_key == DEFAULT_MODE:
                    best_key = key
                best_score += len(w)

    if best_key == DEFAULT_MODE or best_score < 4:
        return RouteIntent()

    return RouteIntent(
        key=best_key,
        mode=_mode_for(best_key),
        agent=_ROUTE_AGENTS.get(best_key, DEFAULT_AGENT),
        confidence=0.8,
        method="heuristic",
        detail=f"keyword-score={best_score}",
    )


def llm_route(message: str, llm_client: Any, history: list[str] | None = None) -> RouteIntent:
    """Ask the LLM to classify the message into the configured route keys."""
    cfg = get_config()
    keys = [r["key"] for r in cfg.settings.get("orchestrator", {}).get("routes", [])]
    prompt = render_prompt(
        "router",
        message=message,
        keys=keys,
        history="\n".join(history[-4:]) if history else "",
    )
    result = llm_client.complete([{"role": "user", "content": prompt}], temperature=0)
    parsed = _parse_json(result.get("content", ""))
    if not parsed:
        return RouteIntent(method="llm", detail="unparsable-response")
    key = str(parsed.get("route", "")).strip()
    if key not in keys:
        return RouteIntent(method="llm", detail=f"unknown-route:{key}")
    conf = float(parsed.get("confidence", 0.6))
    return RouteIntent(
        key=key,
        mode=_mode_for(key),
        agent=_ROUTE_AGENTS.get(key, DEFAULT_AGENT),
        confidence=conf,
        method="llm",
    )


def detect_route(message: str, history: list[str] | None = None,
                 llm_client: Any | None = None) -> RouteIntent:
    """Entry point: LLM router (if enabled) with heuristic fallback."""
    cfg = get_config()
    use_llm = cfg.settings.get("orchestrator", {}).get("use_llm_router", False)
    if use_llm and llm_client is not None:
        intent = llm_route(message, llm_client, history or [])
        if intent.key != DEFAULT_MODE and intent.method == "llm":
            return intent
    return heuristic_route(message, history or [])