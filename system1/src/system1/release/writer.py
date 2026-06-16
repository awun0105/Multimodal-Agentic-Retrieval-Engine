from __future__ import annotations

import shutil
from pathlib import Path

import pandas as pd

from system1.release.types import BuildOptions, RELEASE_NAME, write_json


def write_parquet_tables(release_dir: Path, tables: dict[str, pd.DataFrame]) -> None:
    """Legacy dev helper for `build-mini-seed` only.

    Do not use this helper for the phase-based worker pipeline. Real phase
    commands write ingestion, structure, feature, and merged outputs
    incrementally instead of dumping all tables at once.
    """
    table_dir = release_dir / "tables"
    raw_mapping_dir = release_dir / "raw_mapping"
    for name, frame in tables.items():
        if name in {"release_capabilities", "_embeddings", "_reuse"}:
            continue
        target = raw_mapping_dir / f"{name}.parquet" if name == "media_store_manifest" else table_dir / f"{name}.parquet"
        frame.to_parquet(target, index=False)


def write_manifest(release_dir: Path, tables: dict[str, pd.DataFrame], index_kind: str, options: BuildOptions) -> None:
    """Legacy dev helper for `build-mini-seed` only.

    Do not use this helper for the phase-based worker pipeline. The phase-based
    flow writes runtime manifests during merge, validation, and smoke-test.
    """
    capabilities = {row["capability"]: row["status"] for row in tables["release_capabilities"].to_dict("records")}
    manifest = {
        "release_id": RELEASE_NAME,
        "mode": options.mode,
        "providers": options.providers,
        "provider_plan": (options.provider_plan.__dict__ if options.provider_plan else {}),
        "counts": {name: int(len(frame)) for name, frame in tables.items() if name != "_embeddings"},
        "app_sqlite": "db/app.sqlite",
        "fts5": "app.sqlite:text_documents_fts",
        "visual_index": "indexes/visual.faiss",
        "vector_map": "indexes/vector_map.parquet",
        "capabilities": capabilities,
        "release_usable": capabilities.get("core_runtime") == "pass" and capabilities.get("text_search") == "pass",
        "index_backend": index_kind,
    }
    write_json(release_dir / "manifests" / "dataset_manifest.json", manifest)
    pd.DataFrame([{"artifact_path": str(path.relative_to(release_dir)), "artifact_type": path.suffix.lstrip(".") or "file"} for path in sorted(release_dir.rglob("*")) if path.is_file()]).to_parquet(release_dir / "manifests" / "artifact_manifest.parquet", index=False)
    pd.DataFrame([{"video_id": row["video_id"], "status": "complete" if options.mode == "bronze_fast" else "debug_mock_complete"} for row in tables["videos"].to_dict("records")]).to_parquet(release_dir / "manifests" / "video_processing_status.parquet", index=False)
    pd.DataFrame([{"check": options.mode, "status": "pass"}]).to_parquet(release_dir / "manifests" / "quality_report.parquet", index=False)
    tables["_reuse"].to_parquet(release_dir / "manifests" / "reuse_manifest.parquet", index=False)


def copy_if_exists(source: Path, target: Path) -> None:
    if not source.exists():
        return
    if source.is_dir():
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(source, target)
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def package_release(release_dir: Path | str) -> Path:
    release_path = Path(release_dir)
    archive_base = release_path.parent / release_path.name
    archive_path = shutil.make_archive(str(archive_base), "zip", release_path.parent, release_path.name)
    return Path(archive_path)
