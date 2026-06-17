from __future__ import annotations

import json
import shutil
from pathlib import Path

from typer.testing import CliRunner

from system1.artifacts import checkpoint_relative_path
from system1.cli import app
from system1.release.types import DEFAULT_RELEASE_ID


runner = CliRunner()


def _build_phase00_release(root: Path, release_id: str = DEFAULT_RELEASE_ID) -> Path:
    release_dir = root / release_id
    (release_dir / "tables").mkdir(parents=True)
    (release_dir / "raw_mapping").mkdir(parents=True)
    (release_dir / "manifests").mkdir(parents=True)
    (release_dir / "tables" / "videos.parquet").write_bytes(b"videos")
    (release_dir / "raw_mapping" / "media_store_manifest.parquet").write_bytes(b"manifest")
    (release_dir / "manifests" / "dataset_report.json").write_text('{"ok": true}\n', encoding="utf-8")
    (release_dir / "manifests" / "ingestion_errors.jsonl").write_text("", encoding="utf-8")
    (release_dir / "manifests" / "batch_manifest.csv").write_text("batch_id\n", encoding="utf-8")
    (release_dir / "manifests" / "batch_000.txt").write_text("L21_V001\n", encoding="utf-8")
    return release_dir


def test_checkpoint_status_empty_artifact_root(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifact-store"

    result = runner.invoke(app, ["checkpoint-status", "--artifact-root", str(artifact_root)])

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload == {"latest": {}, "release_id": DEFAULT_RELEASE_ID}


def test_checkpoint_status_accepts_explicit_local_backend(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifact-store"

    result = runner.invoke(app, ["checkpoint-status", "--artifact-root", str(artifact_root), "--artifact-backend", "local"])

    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == {"latest": {}, "release_id": DEFAULT_RELEASE_ID}


def test_checkpoint_save_phase00_creates_zip_and_registry(tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    artifact_root = tmp_path / "artifact-store"
    release_dir = _build_phase00_release(output_dir)

    result = runner.invoke(
        app,
        [
            "checkpoint-save",
            "--phase",
            "phase00_ingest_assignment",
            "--release",
            str(release_dir),
            "--artifact-root",
            str(artifact_root),
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert (artifact_root / checkpoint_relative_path("phase00_ingest_assignment")).exists()
    assert (artifact_root / "manifests" / "checkpoint_registry.json").exists()


def test_checkpoint_restore_phase00_restores_required_files(tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    artifact_root = tmp_path / "artifact-store"
    release_dir = _build_phase00_release(output_dir)
    save = runner.invoke(
        app,
        [
            "checkpoint-save",
            "--phase",
            "phase00_ingest_assignment",
            "--release",
            str(release_dir),
            "--artifact-root",
            str(artifact_root),
        ],
    )
    assert save.exit_code == 0, save.stdout
    shutil.rmtree(release_dir)

    result = runner.invoke(
        app,
        [
            "checkpoint-restore",
            "--phase",
            "phase00_ingest_assignment",
            "--output",
            str(output_dir),
            "--artifact-root",
            str(artifact_root),
        ],
    )

    assert result.exit_code == 0, result.stdout
    restored = output_dir / DEFAULT_RELEASE_ID
    assert (restored / "tables" / "videos.parquet").exists()
    assert (restored / "raw_mapping" / "media_store_manifest.parquet").exists()
    assert (restored / "manifests" / "batch_000.txt").exists()


def test_checkpoint_restore_no_overwrite_exits_nonzero_when_release_exists(tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    artifact_root = tmp_path / "artifact-store"
    release_dir = _build_phase00_release(output_dir)
    save = runner.invoke(
        app,
        [
            "checkpoint-save",
            "--phase",
            "phase00_ingest_assignment",
            "--release",
            str(release_dir),
            "--artifact-root",
            str(artifact_root),
        ],
    )
    assert save.exit_code == 0, save.stdout

    result = runner.invoke(
        app,
        [
            "checkpoint-restore",
            "--phase",
            "phase00_ingest_assignment",
            "--output",
            str(output_dir),
            "--artifact-root",
            str(artifact_root),
            "--no-overwrite",
        ],
    )

    assert result.exit_code != 0
    assert "Error:" in result.output or str(output_dir / DEFAULT_RELEASE_ID) in result.output


def test_checkpoint_save_missing_required_file_exits_nonzero(tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    artifact_root = tmp_path / "artifact-store"
    release_dir = _build_phase00_release(output_dir)
    (release_dir / "manifests" / "dataset_report.json").unlink()

    result = runner.invoke(
        app,
        [
            "checkpoint-save",
            "--phase",
            "phase00_ingest_assignment",
            "--release",
            str(release_dir),
            "--artifact-root",
            str(artifact_root),
        ],
    )

    assert result.exit_code != 0
    assert "Error:" in result.output
    assert "dataset_report.json" in result.output


def test_help_includes_checkpoint_commands() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0, result.stdout
    assert "checkpoint-status" in result.stdout
    assert "checkpoint-save" in result.stdout
    assert "checkpoint-restore" in result.stdout


def test_checkpoint_help_includes_backend_options() -> None:
    result = runner.invoke(app, ["checkpoint-status", "--help"])

    assert result.exit_code == 0, result.output
    assert "--artifact-backend" in result.output
    assert "--hf-repo-id" in result.output


def test_checkpoint_status_hf_error_exits_cleanly(monkeypatch, tmp_path: Path) -> None:
    class FakeHFError(Exception):
        pass

    def fake_status(*args, **kwargs):
        raise FakeHFError("hf unavailable")

    monkeypatch.setattr("system1.commands.checkpoint.EXPECTED_CLI_ERRORS", (FakeHFError,))
    monkeypatch.setattr("system1.commands.checkpoint.checkpoint_status", fake_status)
    artifact_root = tmp_path / "artifact-store"

    result = runner.invoke(app, ["checkpoint-status", "--artifact-root", str(artifact_root), "--artifact-backend", "hf_dataset", "--hf-repo-id", "org/repo"])

    assert result.exit_code != 0
    assert "Error:" in result.output


def test_checkpoint_cli_status_uses_individual_metadata_over_legacy_registry(tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    artifact_root = tmp_path / "artifact-store"
    release_dir = output_dir / DEFAULT_RELEASE_ID
    (release_dir / "tables").mkdir(parents=True)
    (release_dir / "raw_mapping").mkdir(parents=True)
    (release_dir / "manifests").mkdir(parents=True)
    (release_dir / "tables" / "videos.parquet").write_bytes(b"videos")
    (release_dir / "raw_mapping" / "media_store_manifest.parquet").write_bytes(b"manifest")
    (release_dir / "manifests" / "dataset_report.json").write_text('{"ok": true}\n', encoding="utf-8")
    (release_dir / "manifests" / "ingestion_errors.jsonl").write_text("", encoding="utf-8")
    (release_dir / "manifests" / "batch_manifest.csv").write_text("batch_id\n", encoding="utf-8")
    (release_dir / "manifests" / "batch_000.txt").write_text("L21_V001\n", encoding="utf-8")

    save = runner.invoke(app, ["checkpoint-save", "--phase", "phase00_ingest_assignment", "--release", str(release_dir), "--artifact-root", str(artifact_root)])
    assert save.exit_code == 0, save.output
    (artifact_root / "manifests" / "checkpoint_registry.json").write_text('{"release_id":"competition_dataset_v001","latest":{}}\n', encoding="utf-8")

    result = runner.invoke(app, ["checkpoint-status", "--artifact-root", str(artifact_root)])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert "phase00_ingest_assignment" in payload["latest"]
