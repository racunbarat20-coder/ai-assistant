"""Prompt manager: renders Jinja2 templates from the prompts/ directory.

Prompts live outside source code (prompts/*.j2) so they can be tuned by
non-engineers without touching Python.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, TemplateError

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"


@lru_cache
def _environment() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(PROMPTS_DIR)),
        autoescape=False,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=False,
    )


def render_prompt(name: str, **context: Any) -> str:
    """Render prompts/<name>.j2 with the given context.

    Missing or malformed template -> PromptError (so issues surface loudly).
    """
    try:
        return _environment().get_template(f"{name}.j2").render(**context)
    except TemplateError as exc:
        raise RuntimeError(f"Failed to render prompt '{name}.j2': {exc}") from exc


def get_environment() -> Environment:
    return _environment()