from __future__ import annotations

import shutil
import importlib
from pathlib import Path

from typer.testing import CliRunner

from system1.artifacts import checkpoint_relative_path
from system1.cli import app
from system1.release.types import DEFAULT_RELEASE_ID


runner = CliRunner()


def test_assign_batches_sync_saves_phase00_checkpoint(tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    artifact_root = tmp_path / "artifact-store"

    ingest = runner.invoke(
        app,
        [
            "ingest",
            "--mode",
            "debug_small_sample",
            "--output",
            str(output_dir),
            "--input",
            "input",
            "--no-resume",
            "--no-sync",
            "--artifact-root",
            str(artifact_root),
        ],
    )
    assert ingest.exit_code == 0, ingest.output

    assigned = runner.invoke(
        app,
        [
            "assign-batches",
            "--mode",
            "debug_small_sample",
            "--num-batches",
            "1",
            "--output",
            str(output_dir),
            "--sync",
            "--artifact-root",
            str(artifact_root),
        ],
    )
    assert assigned.exit_code == 0, assigned.output
    assert (artifact_root / checkpoint_relative_path("phase00_ingest_assignment")).exists()


def test_ingest_resume_restores_phase00_and_skips(tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    artifact_root = tmp_path / "artifact-store"

    runner.invoke(
        app,
        [
            "ingest", "--mode", "debug_small_sample", "--output", str(output_dir), "--input", "input", "--no-resume", "--no-sync", "--artifact-root", str(artifact_root),
        ],
    )
    runner.invoke(
        app,
        [
            "assign-batches", "--mode", "debug_small_sample", "--num-batches", "1", "--output", str(output_dir), "--sync", "--artifact-root", str(artifact_root),
        ],
    )
    shutil.rmtree(output_dir / DEFAULT_RELEASE_ID)

    result = runner.invoke(
        app,
        [
            "ingest", "--mode", "debug_small_sample", "--output", str(output_dir), "--input", "input", "--resume", "--artifact-root", str(artifact_root), "--no-sync",
        ],
    )

    assert result.exit_code == 0, result.output
    assert (output_dir / DEFAULT_RELEASE_ID / "tables" / "videos.parquet").exists()
    assert "Restored phase00 checkpoint; skipping ingest." in result.output


def test_process_batch_sync_saves_phase01_checkpoint(tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    artifact_root = tmp_path / "artifact-store"

    runner.invoke(app, ["ingest", "--mode", "debug_small_sample", "--output", str(output_dir), "--input", "input", "--no-resume", "--no-sync", "--artifact-root", str(artifact_root)])
    runner.invoke(app, ["assign-batches", "--mode", "debug_small_sample", "--num-batches", "1", "--output", str(output_dir), "--no-resume", "--no-sync", "--artifact-root", str(artifact_root)])
    result = runner.invoke(
        app,
        [
            "process-batch", "--batch-id", "batch_000", "--worker-id", "worker_123", "--mode", "debug_small_sample", "--providers", "mock", "--output", str(output_dir), "--input", "input", "--sync", "--artifact-root", str(artifact_root), "--no-resume",
        ],
    )

    assert result.exit_code == 0, result.output
    assert (artifact_root / checkpoint_relative_path("phase01_structure", "batch_000")).exists()


def test_process_batch_resume_restores_phase01_and_skips(tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    artifact_root = tmp_path / "artifact-store"

    runner.invoke(app, ["ingest", "--mode", "debug_small_sample", "--output", str(output_dir), "--input", "input", "--no-resume", "--no-sync", "--artifact-root", str(artifact_root)])
    runner.invoke(app, ["assign-batches", "--mode", "debug_small_sample", "--num-batches", "1", "--output", str(output_dir), "--no-resume", "--no-sync", "--artifact-root", str(artifact_root)])
    runner.invoke(app, ["process-batch", "--batch-id", "batch_000", "--worker-id", "worker_123", "--mode", "debug_small_sample", "--providers", "mock", "--output", str(output_dir), "--input", "input", "--sync", "--artifact-root", str(artifact_root), "--no-resume"])
    shutil.rmtree(output_dir / DEFAULT_RELEASE_ID)

    result = runner.invoke(
        app,
        [
            "process-batch", "--batch-id", "batch_000", "--worker-id", "worker_123", "--mode", "debug_small_sample", "--providers", "mock", "--output", str(output_dir), "--input", "input", "--resume", "--artifact-root", str(artifact_root), "--no-sync",
        ],
    )

    assert result.exit_code == 0, result.output
    assert (output_dir / DEFAULT_RELEASE_ID / "manifests" / "worker_runtime_report_structure.json").exists()
    assert "Restored phase01 checkpoint; skipping process-batch." in result.output


def test_feature_batch_sync_saves_phase02_checkpoint(tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    artifact_root = tmp_path / "artifact-store"

    runner.invoke(app, ["ingest", "--mode", "debug_small_sample", "--output", str(output_dir), "--input", "input", "--no-resume", "--no-sync", "--artifact-root", str(artifact_root)])
    runner.invoke(app, ["assign-batches", "--mode", "debug_small_sample", "--num-batches", "1", "--output", str(output_dir), "--no-resume", "--no-sync", "--artifact-root", str(artifact_root)])
    runner.invoke(app, ["process-batch", "--batch-id", "batch_000", "--worker-id", "worker_123", "--mode", "debug_small_sample", "--providers", "mock", "--output", str(output_dir), "--input", "input", "--no-resume", "--no-sync", "--artifact-root", str(artifact_root)])
    result = runner.invoke(
        app,
        [
            "feature-batch", "--batch-id", "batch_000", "--worker-id", "worker_123", "--mode", "debug_small_sample", "--providers", "mock", "--output", str(output_dir), "--input", "input", "--sync", "--artifact-root", str(artifact_root), "--no-resume",
        ],
    )

    assert result.exit_code == 0, result.output
    assert (artifact_root / checkpoint_relative_path("phase02_features", "batch_000")).exists()


def test_default_cli_behavior_does_not_sync_phase00(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("AIC_SYNC", raising=False)
    output_dir = tmp_path / "output"
    artifact_root = tmp_path / "artifact-store"

    ingest = runner.invoke(app, ["ingest", "--mode", "debug_small_sample", "--output", str(output_dir), "--input", "input", "--artifact-root", str(artifact_root)])
    assert ingest.exit_code == 0, ingest.output
    assigned = runner.invoke(app, ["assign-batches", "--mode", "debug_small_sample", "--num-batches", "1", "--output", str(output_dir), "--artifact-root", str(artifact_root)])
    assert assigned.exit_code == 0, assigned.output

    assert not (artifact_root / checkpoint_relative_path("phase00_ingest_assignment")).exists()


def test_aic_sync_env_enables_default_cli_sync(tmp_path: Path, monkeypatch) -> None:
    import system1.cli as cli_module

    monkeypatch.setenv("AIC_SYNC", "true")
    cli_module = importlib.reload(cli_module)
    reloaded_app = cli_module.app
    output_dir = tmp_path / "output"
    artifact_root = tmp_path / "artifact-store"

    ingest = runner.invoke(reloaded_app, ["ingest", "--mode", "debug_small_sample", "--output", str(output_dir), "--input", "input", "--artifact-root", str(artifact_root), "--no-sync"])
    assert ingest.exit_code == 0, ingest.output
    assigned = runner.invoke(reloaded_app, ["assign-batches", "--mode", "debug_small_sample", "--num-batches", "1", "--output", str(output_dir), "--artifact-root", str(artifact_root)])
    assert assigned.exit_code == 0, assigned.output

    assert (artifact_root / checkpoint_relative_path("phase00_ingest_assignment")).exists()


def test_merge_help_does_not_expose_checkpoint_options() -> None:
    result = runner.invoke(app, ["merge", "--help"])

    assert result.exit_code == 0, result.output
    assert "--artifact-root" not in result.output
    assert "--sync" not in result.output
    assert "--resume" not in result.output
