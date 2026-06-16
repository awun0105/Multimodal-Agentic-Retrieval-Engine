from __future__ import annotations

from pathlib import Path

from system1.validation.filesystem import check_manifest, check_required_files
from system1.validation.reporting import write_validation_outputs
from system1.validation.sqlite_checks import check_sqlite
from system1.validation.types import ValidationResult


def validate_release(release_dir: Path | str) -> ValidationResult:
    release_path = Path(release_dir)
    errors: list[str] = []
    degraded: list[str] = []
    capabilities: dict[str, str] = {}

    check_required_files(release_path, errors)
    check_manifest(release_path, errors)

    sqlite_path = release_path / "db" / "app.sqlite"
    if sqlite_path.exists():
        capabilities = check_sqlite(sqlite_path, errors, degraded)

    result = ValidationResult(
        release_dir=release_path,
        status="pass" if not errors else "fail",
        errors=tuple(errors),
        degraded=tuple(degraded),
        capabilities=capabilities,
    )
    write_validation_outputs(release_path, result)
    return result
