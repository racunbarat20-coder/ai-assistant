"""Provider-agnostic LLM client (OpenAI-compatible).

Supports sync `complete()` (used by orchestrator/planner/evaluator) and
async `astream()` (used by chat / SSE). Swap the vendor by pointing
`LLM_BASE_URL` to any OpenAI-compatible endpoint, or replace this module's
two methods with a different provider while keeping the same contract.
"""

from __future__ import annotations

import logging
from typing import Any, AsyncGenerator

import openai

logger = logging.getLogger("app.llm")


class LLMError(RuntimeError):
    """Raised when the model call fails or is misconfigured."""


class LLMConfigurationError(LLMError):
    pass


def _usage_of(resp: Any) -> dict[str, int] | None:
    usage = getattr(resp, "usage", None)
    if usage is None:
        return None
    return {
        "prompt_tokens": getattr(usage, "prompt_tokens", 0),
        "completion_tokens": getattr(usage, "completion_tokens", 0),
        "total_tokens": getattr(usage, "total_tokens", 0),
    }


class LLMClient:
    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 1024,
        timeout: float = 60.0,
    ) -> None:
        if not api_key:
            raise LLMConfigurationError(
                "LLM_API_KEY is not set. Add it to your .env (see .env.example)."
            )
        self.sync = openai.OpenAI(api_key=api_key, base_url=base_url or None, timeout=timeout)
        self.async_client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url or None, timeout=timeout)
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

    # ---- non-streaming -------------------------------------------------
    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        try:
            resp = self.sync.chat.completions.create(
                model=model or self.model,
                messages=messages,
                temperature=self.temperature if temperature is None else temperature,
                max_tokens=max_tokens or self.max_tokens,
            )
        except Exception as exc:  # pragma: no cover - network/provider behaviour
            logger.warning("LLM complete failed: %s", exc)
            raise LLMError(f"LLM request failed: {exc}") from exc

        choice = resp.choices[0]
        return {
            "content": (choice.message.content or "").strip(),
            "usage": _usage_of(resp),
            "model": resp.model,
            "finish_reason": choice.finish_reason,
        }

    # ---- streaming -----------------------------------------------------
    async def astream(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Yield event dicts: {"type": "delta", "delta": str} then {"type": "usage", "usage": {...}}."""
        try:
            stream = await self.async_client.chat.completions.create(
                model=model or self.model,
                messages=messages,
                temperature=self.temperature if temperature is None else temperature,
                max_tokens=max_tokens or self.max_tokens,
                stream=True,
                stream_options={"include_usage": True},
            )
        except Exception as exc:
            logger.exception("LLM stream start failed: %s", exc)
            raise LLMError(f"LLM streaming failed: {exc}")

        async for chunk in stream:
            if not chunk.choices:
                if chunk.usage is not None:
                    yield {"type": "usage", "usage": _usage_of(chunk)}
                continue
            delta = chunk.choices[0].delta.content
            if delta:
                yield {"type": "delta", "delta": delta}


def build_llm_client() -> LLMClient:
    """Factory hooked to settings; overridable in tests via monkeypatch."""
    from app.core.config import get_config

    cfg = get_config()
    llm_cfg = cfg.llm
    return LLMClient(
        api_key=cfg.env.llm_api_key,
        model=cfg.env.llm_model,
        base_url=cfg.env.llm_base_url,
        temperature=llm_cfg.get("temperature", 0.2),
        max_tokens=llm_cfg.get("max_tokens", 1024),
        timeout=llm_cfg.get("timeout_seconds", 60),
    )