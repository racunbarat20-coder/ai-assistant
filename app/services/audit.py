"""Audit logging service: persists non-sensitive event metadata to audit_logs."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.core.logging import get_request_id
from app.db.models import AuditLog

logger = logging.getLogger("app.audit")

# Only these fields are ever stored (never secrets/credentials).
_AUDIT_WHITELIST = {
    "request_id",
    "user_id",
    "action",
    "route",
    "agent",
    "tool",
    "status",
    "latency_ms",
    "token_usage",
    "error",
    "meta",
}


def log_event(
    db: Session,
    *,
    action: str,
    user_id: int | None = None,
    request_id: str | None = None,
    route: str | None = None,
    agent: str | None = None,
    tool: str | None = None,
    status: str = "ok",
    latency_ms: int | None = None,
    token_usage: dict[str, Any] | None = None,
    error: str | None = None,
    meta: dict[str, Any] | None = None,
) -> AuditLog:
    entry = AuditLog(
        request_id=request_id or get_request_id(),
        user_id=user_id,
        action=action,
        route=route,
        agent=agent,
        tool=tool,
        status=status,
        latency_ms=latency_ms,
        token_usage=token_usage,
        error=error,
        meta=meta,
    )
    db.add(entry)
    try:
        db.commit()
    except Exception:  # audit must never break the request
        db.rollback()
        logger.exception("audit persist failed")
    logger.info(
        "audit %s route=%s agent=%s tool=%s status=%s latency_ms=%s",
        action, route, agent, tool, status, latency_ms,
        extra={"data": {k: str(getattr(entry, k)) if getattr(entry, k) is not None else None
                        for k in _AUDIT_WHITELIST}},
    )
    return entry