from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ValidationResult:
    release_dir: Path
    status: str
    errors: tuple[str, ...]
    degraded: tuple[str, ...] = ()
    capabilities: dict[str, str] | None = None
    schema_validation: dict[str, object] | None = None

    @property
    def passed(self) -> bool:
        return self.status == "pass"
