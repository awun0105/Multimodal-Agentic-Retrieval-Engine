from __future__ import annotations

import importlib
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from system1.artifacts import checkpoint_relative_path
from system1.cli import app
from system1.media.probe import VideoProbe, VideoProbeWithTimeline
from system1.release.types import DEFAULT_RELEASE_ID

runner = CliRunner()


@pytest.fixture(autouse=True)
def fast_frame_timeline_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIC_ALLOW_TEST_PROVIDERS", "1")
    monkeypatch.setenv("AIC_SYSTEM1_TEST_PROVIDER_PROFILE", "mock")

    def fake_probe_with_timeline(path: Path, *, video_id: str) -> VideoProbeWithTimeline:  # noqa: ARG001
        return VideoProbeWithTimeline(
            probe=VideoProbe(25.0, "test_frame_timeline", 3, False, "decoded_frame_timeline", 0.12, 640, 360, False),
            frame_timeline=[
                {"video_id": video_id, "frame_id": 0, "pts_time": 0.0, "duration_time": 0.04},
                {"video_id": video_id, "frame_id": 1, "pts_time": 0.04, "duration_time": 0.04},
                {"video_id": video_id, "frame_id": 2, "pts_time": 0.08, "duration_time": 0.04},
            ],
        )

    monkeypatch.setattr("system1.ingest.pipeline.probe_video_with_timeline", fake_probe_with_timeline)


def test_assign_batches_sync_saves_phase00_checkpoint(tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    artifact_root = tmp_path / "artifact-store"

    ingest = runner.invoke(
        app,
        [
            "ingest",
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
            "ingest", "--output", str(output_dir), "--input", "input", "--no-resume", "--no-sync", "--artifact-root", str(artifact_root),
        ],
    )
    runner.invoke(
        app,
        [
            "assign-batches", "--num-batches", "1", "--output", str(output_dir), "--sync", "--artifact-root", str(artifact_root),
        ],
    )
    shutil.rmtree(output_dir / DEFAULT_RELEASE_ID)

    result = runner.invoke(
        app,
        [
            "ingest", "--output", str(output_dir), "--input", "input", "--resume", "--artifact-root", str(artifact_root), "--no-sync",
        ],
    )

    assert result.exit_code == 0, result.output
    assert (output_dir / DEFAULT_RELEASE_ID / "tables" / "videos.parquet").exists()
    assert "Restored phase00 checkpoint; skipping ingest." in result.output


def test_process_batch_sync_saves_phase01_checkpoint(tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    artifact_root = tmp_path / "artifact-store"

    runner.invoke(app, ["ingest", "--output", str(output_dir), "--input", "input", "--no-resume", "--no-sync", "--artifact-root", str(artifact_root)])
    runner.invoke(app, ["assign-batches", "--num-batches", "1", "--output", str(output_dir), "--no-resume", "--no-sync", "--artifact-root", str(artifact_root)])
    result = runner.invoke(
        app,
        [
            "process-batch", "--batch-id", "batch_000", "--worker-id", "worker_123", "--output", str(output_dir), "--input", "input", "--sync", "--artifact-root", str(artifact_root), "--no-resume",
        ],
    )

    assert result.exit_code == 0, result.output
    assert (artifact_root / checkpoint_relative_path("phase01_structure", "batch_000")).exists()


def test_process_batch_resume_restores_phase01_and_skips(tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    artifact_root = tmp_path / "artifact-store"

    runner.invoke(app, ["ingest", "--output", str(output_dir), "--input", "input", "--no-resume", "--no-sync", "--artifact-root", str(artifact_root)])
    runner.invoke(app, ["assign-batches", "--num-batches", "1", "--output", str(output_dir), "--no-resume", "--no-sync", "--artifact-root", str(artifact_root)])
    runner.invoke(app, ["process-batch", "--batch-id", "batch_000", "--worker-id", "worker_123", "--output", str(output_dir), "--input", "input", "--sync", "--artifact-root", str(artifact_root), "--no-resume"])
    shutil.rmtree(output_dir / DEFAULT_RELEASE_ID)

    result = runner.invoke(
        app,
        [
            "process-batch", "--batch-id", "batch_000", "--worker-id", "worker_123", "--output", str(output_dir), "--input", "input", "--resume", "--artifact-root", str(artifact_root), "--no-sync",
        ],
    )

    assert result.exit_code == 0, result.output
    assert (output_dir / DEFAULT_RELEASE_ID / "manifests" / "worker_reports" / "structure_batch_000_worker_123.json").exists()
    assert "Restored phase01 checkpoint; skipping process-batch." in result.output


def test_feature_batch_sync_saves_phase02_checkpoint(tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    artifact_root = tmp_path / "artifact-store"

    runner.invoke(app, ["ingest", "--output", str(output_dir), "--input", "input", "--no-resume", "--no-sync", "--artifact-root", str(artifact_root)])
    runner.invoke(app, ["assign-batches", "--num-batches", "1", "--output", str(output_dir), "--no-resume", "--no-sync", "--artifact-root", str(artifact_root)])
    runner.invoke(app, ["process-batch", "--batch-id", "batch_000", "--worker-id", "worker_123", "--output", str(output_dir), "--input", "input", "--no-resume", "--no-sync", "--artifact-root", str(artifact_root)])
    result = runner.invoke(
        app,
        [
            "feature-batch", "--batch-id", "batch_000", "--worker-id", "worker_123", "--providers", "mock", "--output", str(output_dir), "--input", "input", "--sync", "--artifact-root", str(artifact_root), "--no-resume",
        ],
    )

    assert result.exit_code == 0, result.output
    assert (artifact_root / checkpoint_relative_path("phase02_features", "batch_000")).exists()


def test_default_cli_behavior_does_not_sync_phase00(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("AIC_SYNC", raising=False)
    output_dir = tmp_path / "output"
    artifact_root = tmp_path / "artifact-store"

    ingest = runner.invoke(app, ["ingest", "--output", str(output_dir), "--input", "input", "--artifact-root", str(artifact_root)])
    assert ingest.exit_code == 0, ingest.output
    assigned = runner.invoke(app, ["assign-batches", "--num-batches", "1", "--output", str(output_dir), "--artifact-root", str(artifact_root)])
    assert assigned.exit_code == 0, assigned.output

    assert not (artifact_root / checkpoint_relative_path("phase00_ingest_assignment")).exists()


def test_aic_sync_env_enables_default_cli_sync(tmp_path: Path, monkeypatch) -> None:
    import system1.cli as cli_module

    monkeypatch.setenv("AIC_SYNC", "true")
    cli_module = importlib.reload(cli_module)
    reloaded_app = cli_module.app
    output_dir = tmp_path / "output"
    artifact_root = tmp_path / "artifact-store"

    ingest = runner.invoke(reloaded_app, ["ingest", "--output", str(output_dir), "--input", "input", "--artifact-root", str(artifact_root), "--no-sync"])
    assert ingest.exit_code == 0, ingest.output
    assigned = runner.invoke(reloaded_app, ["assign-batches", "--num-batches", "1", "--output", str(output_dir), "--artifact-root", str(artifact_root)])
    assert assigned.exit_code == 0, assigned.output

    assert (artifact_root / checkpoint_relative_path("phase00_ingest_assignment")).exists()


def test_merge_help_does_not_expose_checkpoint_options() -> None:
    result = runner.invoke(app, ["merge", "--help"])

    assert result.exit_code == 0, result.output
    assert "--artifact-root" not in result.output
    assert "--sync" not in result.output
    assert "--resume" not in result.output


def test_phase_command_help_includes_artifact_backend() -> None:
    result = runner.invoke(app, ["assign-batches", "--help"])

    assert result.exit_code == 0, result.output
    assert "--artifact-backend" in result.output
    assert "--hf-repo-id" in result.output


def test_phase_workflow_hf_error_exits_cleanly(monkeypatch, tmp_path: Path) -> None:
    class FakeHFError(Exception):
        pass

    def fake_save_phase_checkpoint(**kwargs):
        raise FakeHFError("hf upload failed")

    monkeypatch.setattr("system1.commands.pipeline.EXPECTED_CHECKPOINT_ERRORS", (FakeHFError,))
    monkeypatch.setattr("system1.commands.pipeline.save_phase_checkpoint", fake_save_phase_checkpoint)
    output_dir = tmp_path / "output"
    artifact_root = tmp_path / "artifact-store"

    runner.invoke(app, ["ingest", "--output", str(output_dir), "--input", "input", "--no-resume", "--no-sync"])
    result = runner.invoke(app, ["assign-batches", "--num-batches", "1", "--output", str(output_dir), "--sync", "--artifact-backend", "hf_dataset", "--hf-repo-id", "org/repo", "--artifact-root", str(artifact_root)])

    assert result.exit_code != 0
    assert "Error:" in result.output
