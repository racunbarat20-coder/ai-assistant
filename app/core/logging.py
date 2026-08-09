"""Structured logging with request_id tracing and sensitive-field redaction."""

from __future__ import annotations

import contextvars
import json
import logging
import re
import uuid
from typing import Any

_REQUEST_ID: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")


def get_request_id() -> str:
    return _REQUEST_ID.get()


def set_request_id(value: str) -> None:
    _REQUEST_ID.set(value)


def new_request_id() -> str:
    return uuid.uuid4().hex[:12]


_SENSITIVE_KEY = re.compile(
    r"(api[_-]?key|authorization|bearer|token|secret|password|jwt|credit.?card)", re.IGNORECASE
)


def redact_payload(data: Any, redact_fields: list[str] | None = None, _depth: int = 0) -> Any:
    """Recursively redact sensitive keys and long opaque blobs before logging.

    Never writes API keys / tokens / secrets to logs.
    """
    if _depth > 6:
        return "<max-depth>"
    if isinstance(data, str):
        return data[:2000] + ("..." if len(data) > 2000 else "")
    if isinstance(data, dict):
        out: dict[str, Any] = {}
        for k, v in data.items():
            key_str = str(k).lower()
            matched = _SENSITIVE_KEY.search(key_str) or (
                redact_fields and any(f in key_str for f in redact_fields)
            )
            if matched:
                out[str(k)] = "<redacted>"
            else:
                out[str(k)] = redact_payload(v, redact_fields, _depth + 1)
        return out
    if isinstance(data, (list, tuple)):
        return [redact_payload(x, redact_fields, _depth + 1) for x in data]
    return data


class RedactingFormatter(logging.Formatter):
    """JSON formatter that injects request_id and redacts sensitive fields.

    Structured fields can be passed via `logger.info("...", data={"k": v})`
    (the `extra=` argument) - i.e. the normal `logging` extra mechanism.
    """

    def __init__(self, redact_fields: list[str] | None = None) -> None:
        super().__init__()
        self.redact_fields = redact_fields or []

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "request_id": get_request_id(),
        }
        message = record.getMessage()
        if message and message.strip() and message != "%s":
            entry["message"] = message[:2000]
        data = getattr(record, "data", None)
        if data:
            try:
                redacted = redact_payload(dict(data), self.redact_fields)
                entry["data"] = redacted
            except Exception:
                pass
        if record.exc_info:
            entry["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False, default=str)


class TextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        prefix = f"[{get_request_id()}] {record.levelname:<7} {record.name}: "
        body = record.getMessage()[:2000]
        extra = json.dumps(redact_payload(getattr(record, "data", None), []), ensure_ascii=False) if getattr(
            record, "data", None
        ) else ""
        return prefix + body + (f" {extra}" if extra else "")


def setup_logging(level: str = "INFO", fmt: str = "json", redact_fields: list[str] | None = None) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(
        RedactingFormatter(redact_fields) if fmt == "json" else TextFormatter()
    )
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    # only surface uvicorn errors, keep access logs inside our own middleware
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)