from __future__ import annotations

from pathlib import Path

from system1.batch.writer import write_batches
from system1.config import load_provider_plan
from system1.db.duckdb_builder import write_duckdb
from system1.db.sqlite_builder import write_sqlite
from system1.indexes.builder import write_index_files
from system1.ingest.discovery import discover_paired_inputs
from system1.ingest.pipeline import build_tables
from system1.release.artifacts import write_worker_artifacts
from system1.release.checkpoint import read_checkpoint, write_checkpoint
from system1.release.smoke import write_smoke_report
from system1.release.types import BuildOptions, RELEASE_NAME, config_dir, create_release_directories, default_input_dir, write_json
from system1.release.writer import package_release, write_manifest, write_parquet_tables
from system1.validation.release_validator import validate_release


def build_mini_seed(
    output_dir: Path | str,
    *,
    input_dir: Path | str | None = None,
    validate: bool = True,
    mode: str = "debug_small_sample",
    providers: str = "mock",
) -> Path:
    release_dir = Path(output_dir) / RELEASE_NAME
    create_release_directories(release_dir)

    provider_plan = load_provider_plan(config_dir(), providers)
    options = BuildOptions(mode=mode, providers=providers, provider_plan=provider_plan)
    pairs = discover_paired_inputs(input_dir or default_input_dir())
    previous_checkpoint = read_checkpoint(release_dir)
    tables = build_tables(pairs, release_dir, options, previous_checkpoint)

    write_parquet_tables(release_dir, tables)
    write_batches(release_dir, pairs)
    index_kind = write_index_files(release_dir, tables, previous_checkpoint)
    write_sqlite(release_dir / "db" / "app.sqlite", tables)
    write_duckdb(release_dir / "db" / "staging.duckdb", tables)
    write_manifest(release_dir, tables, index_kind, options)
    write_checkpoint(release_dir, options, tables)

    if validate:
        validate_release(release_dir)
    else:
        write_json(release_dir / "manifests" / "validation_report.json", {"status": "not_run", "errors": []})
        (release_dir / "manifests" / "validation_errors.jsonl").write_text("", encoding="utf-8")

    return release_dir


__all__ = [
    "build_mini_seed",
    "discover_paired_inputs",
    "package_release",
    "write_smoke_report",
    "write_worker_artifacts",
]
