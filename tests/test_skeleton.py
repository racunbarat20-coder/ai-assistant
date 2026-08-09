"""Phase 1 smoke tests: app boots, health endpoint works, config loads."""

from __future__ import annotations


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["name"]


def test_config_loads_yaml_and_expands_env():
    from app.core.config import get_config, load_yaml
    from pathlib import Path

    cfg = get_config()
    assert cfg.app_name == "AI Assistant"
    # env var substitution in yaml
    assert isinstance(cfg.agents, dict)
    agents = cfg.agents.get("agents", {})
    assert "simple_chat" in agents
    # monkeypatch-free: default llm model comes from env default subclass
    assert cfg.env.llm_model


def test_yaml_expand_env(tmp_path):
    import os

    os.environ["MY_VAR"] = "hello"
    from app.core import config as config_mod

    p = tmp_path / "x.yaml"
    p.write_text("value: ${MY_VAR:-fallback}\ndefault_v: ${MISSING:-fallback_v}\n")
    data = config_mod.load_yaml(p)
    assert data["value"] == "hello"
    assert data["default_v"] == "fallback_v"


def test_logging_redacts_sensitive_keys():
    from app.core.logging import redact_payload

    out = redact_payload(
        {"api_key": "sk-secret", "nested": {"token": "abc", "ok": "keep"}, "list": [1, 2]},
    )
    assert out["api_key"] == "<redacted>"
    assert out["nested"]["token"] == "<redacted>"
    assert out["nested"]["ok"] == "keep"


def test_logging_formatter_includes_request_id():
    from app.core.logging import RedactingFormatter, set_request_id

    import logging

    set_request_id("rid-123")
    rec = logging.LogRecord("t", logging.INFO, __file__, 1, "msg %s", ("x",), None)
    fmt = RedactingFormatter()
    out = fmt.format(rec)
    assert '"request_id": "rid-123"' in out