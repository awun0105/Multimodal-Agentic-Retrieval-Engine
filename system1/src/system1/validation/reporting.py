from __future__ import annotations

import json
from pathlib import Path

from system1.validation.types import ValidationResult


def write_validation_outputs(release_path: Path, result: ValidationResult) -> None:
    manifests_dir = release_path / "manifests"
    manifests_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "status": result.status,
        "error_count": len(result.errors),
        "degraded_count": len(result.degraded),
        "errors": list(result.errors),
        "degraded": list(result.degraded),
        "capabilities": result.capabilities or {},
        "release_usable": not result.errors and (result.capabilities or {}).get("core_runtime", "pass") == "pass",
    }
    (manifests_dir / "validation_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    with (manifests_dir / "validation_errors.jsonl").open("w", encoding="utf-8") as error_file:
        for error in result.errors:
            error_file.write(json.dumps({"error": error}, sort_keys=True) + "\n")
