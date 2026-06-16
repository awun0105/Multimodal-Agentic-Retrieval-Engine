from __future__ import annotations

import json
from pathlib import Path

from system1.validation.types import ValidationResult


def write_validation_outputs(release_path: Path, result: ValidationResult) -> None:
    manifests_dir = release_path / "manifests"
    manifests_dir.mkdir(parents=True, exist_ok=True)
    capabilities = result.capabilities or {}
    core_runtime = capabilities.get("core_runtime", "fail" if result.errors else "pass")
    visual_search = capabilities.get("visual_search", "fail")
    text_search = capabilities.get("text_search", "fail")
    inspection_context = capabilities.get("inspection_context", "fail")
    enrichment_overall = capabilities.get("enrichment_overall", "fail")
    release_usable = (
        not result.errors
        and core_runtime == "pass"
        and text_search != "fail"
        and inspection_context != "fail"
        and visual_search != "fail"
    )
    report = {
        "status": result.status,
        "core_runtime": core_runtime,
        "visual_search": visual_search,
        "text_search": text_search,
        "inspection_context": inspection_context,
        "enrichment_overall": enrichment_overall,
        "release_usable": release_usable,
        "error_count": len(result.errors),
        "warning_count": len(result.degraded),
        "errors": list(result.errors),
        "warnings": list(result.degraded),
        "degraded": list(result.degraded),
        "capabilities": capabilities,
    }
    (manifests_dir / "validation_report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    dataset_manifest_path = manifests_dir / "dataset_manifest.json"
    if dataset_manifest_path.exists():
        dataset_manifest = json.loads(dataset_manifest_path.read_text(encoding="utf-8"))
        dataset_manifest["release_usable"] = release_usable
        dataset_manifest["validation_status"] = result.status
        dataset_manifest["validation_error_count"] = len(result.errors)
        dataset_manifest["validation_warning_count"] = len(result.degraded)
        dataset_manifest_path.write_text(json.dumps(dataset_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with (manifests_dir / "validation_errors.jsonl").open("w", encoding="utf-8") as error_file:
        for error in result.errors:
            error_file.write(json.dumps({"error": error}, sort_keys=True) + "\n")
