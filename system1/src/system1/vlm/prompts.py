"""Prompt template loading for local VLM semantic requests.

The source of truth for every prompt body is the versioned text file at
``system1/prompts/<prompt_version>.txt``. This module only resolves and
substitutes; it must never embed prompt bodies inline.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

_PROMPT_ROOT = Path(__file__).resolve().parents[3] / "prompts"

_TEMPLATE_CACHE: dict[str, str] = {}


def prompt_root() -> Path:
    return _PROMPT_ROOT


def read_prompt(prompt_version: str) -> str:
    """Load a prompt body from ``system1/prompts/<version>.txt``."""

    template = _TEMPLATE_CACHE.get(prompt_version)
    if template is not None:
        return template
    if Path(prompt_version).name != prompt_version:
        raise ValueError(f"Unsafe prompt version: {prompt_version}")
    path = _PROMPT_ROOT / f"{prompt_version}.txt"
    if not path.is_file():
        raise ValueError(f"Unknown prompt_version: {prompt_version}")
    template = path.read_text(encoding="utf-8").strip()
    if not template:
        raise ValueError(f"Prompt template is empty: {prompt_version}")
    _TEMPLATE_CACHE[prompt_version] = template
    return template


def build_text_prompt(
    prompt_version: str,
    *,
    variables: Mapping[str, Any] | None = None,
) -> str:
    template = read_prompt(prompt_version)

    if not variables:
        return template

    result = template
    for key, value in variables.items():
        result = result.replace(f"{{{{{key}}}}}", str(value))
    return result
