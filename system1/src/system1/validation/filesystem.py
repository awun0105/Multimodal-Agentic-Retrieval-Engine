from __future__ import annotations

import json
from pathlib import Path

from system1.validation.constants import REQUIRED_FILES


def check_required_files(release_path: Path, errors: list[str]) -> None:
    for relative_path in sorted(REQUIRED_FILES):
        if not (release_path / relative_path).exists():
            errors.append(f"missing required file: {relative_path}")


def check_manifest(release_path: Path, errors: list[str]) -> None:
    manifest_path = release_path / "manifests" / "dataset_manifest.json"
    if not manifest_path.exists():
        return
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not manifest.get("counts"):
        errors.append("dataset_manifest.json missing counts")
