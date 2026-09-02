from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class AsrResult:
    """Provider-neutral Phase01 ASR result."""

    status: str
    segment_rows: list[dict[str, Any]]
    word_rows: list[dict[str, Any]]
    compute_type: str | None
    attempts: int
    detected_language: str | None
    diagnostics: list[dict[str, Any]] = field(default_factory=list)
    status_details: dict[str, Any] = field(default_factory=dict)

    @property
    def rows(self) -> list[dict[str, Any]]:
        """Temporary compatibility alias for pre-word-alignment callers."""

        return self.segment_rows
