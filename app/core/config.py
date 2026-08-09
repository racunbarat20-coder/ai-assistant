"""Central configuration: merges .env (secrets) + config/*.yaml (non-secret) into AppConfig."""

from __future__ import annotations

import functools
import os
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = PROJECT_ROOT / "config"


def _expand_env(value: Any) -> Any:
    """Expand ${VAR:-default} placeholders in YAML values (e.g. ${LLM_MODEL:-gpt-4o-mini})."""
    if isinstance(value, str):
        pattern = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")

        def repl(match: re.Match) -> str:
            env_var, default = match.group(1), match.group(2)
            return os.getenv(env_var, default or "")

        return pattern.sub(repl, value)
    if isinstance(value, dict):
        return {k: _expand_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env(v) for v in value]
    return value


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return _expand_env(data)


class EnvSettings(BaseSettings):
    """Secrets and runtime settings loaded from environment / .env."""

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    llm_api_key: str = ""
    llm_base_url: str | None = None
    llm_model: str = "gpt-4o-mini"
    llm_embedding_model: str = "text-embedding-3-small"

    database_url: str = "sqlite:///./data/assistant.db"
    vector_database_url: str = "qdrant://:memory:"
    qdrant_path: str = "./data/vector"
    qdrant_collection: str = "documents"

    jwt_secret_key: str = "dev-only-change-me-7f4a9c2e1b85d6023a9f8c47e1b2d3e4f5a6b7c8d9e0f"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440
    password_pepper: str = ""

    environment: str = "dev"
    log_level: str = "INFO"


class AppConfig:
    """Combined config object exposing env + yaml deterministically."""

    def __init__(self) -> None:
        self.env = EnvSettings()
        self._yaml: dict[str, Any] = {}
        self._load_yaml_files()

    def _load_yaml_files(self) -> None:
        for path in sorted(CONFIG_DIR.glob("*.yaml")):
            self._yaml[path.stem] = load_yaml(path)

    def yaml(self, key: str, default: Any = None) -> Any:
        return self._yaml.get(key, default)

    # -- helpers for common sections -----------------------------------
    @property
    def settings(self) -> dict[str, Any]:
        return self._yaml.get("settings", {})

    @property
    def agents(self) -> dict[str, Any]:
        return self._yaml.get("agents", {})

    @property
    def llm(self) -> dict[str, Any]:
        return self.settings.get("llm", {})

    @property
    def features(self) -> dict[str, bool]:
        return self.settings.get("features", {})

    @property
    def guardrails_cfg(self) -> dict[str, Any]:
        return self.settings.get("guardrails", {})

    @property
    def rag_cfg(self) -> dict[str, Any]:
        return self.settings.get("rag", {})

    @property
    def app_name(self) -> str:
        return self.settings.get("app", {}).get("name", "AI Assistant")

    @property
    def is_debug(self) -> bool:
        return self.settings.get("app", {}).get("debug", False)

    @property
    def database_url(self) -> str:
        return self.env.database_url or self.settings.get("database", {}).get("url", "")

    @property
    def redact_fields(self) -> list[str]:
        return self.settings.get("logging", {}).get("redact_fields", [])


@functools.lru_cache
def get_config() -> AppConfig:
    return AppConfig()