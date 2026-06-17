from __future__ import annotations

from pathlib import Path
import zipfile

import pytest

from system1.artifacts import (
    checkpoint_name,
    checkpoint_relative_path,
    checkpoint_status,
    restore_checkpoint,
    save_checkpoint,
)
from system1.artifacts.store import make_artifact_store
from system1.release.types import DEFAULT_RELEASE_ID


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


def test_checkpoint_name_rules() -> None:
    assert checkpoint_name("phase00_ingest_assignment") == "phase00_ingest_assignment"
    assert checkpoint_name("phase01_structure", "batch_000") == "phase01_structure_batch_000"
    assert checkpoint_name("phase02_features", "batch_000") == "phase02_features_batch_000"
    assert checkpoint_name("phase03_final_release") == "phase03_final_release"
    with pytest.raises(ValueError):
        checkpoint_name("phase01_structure")
    with pytest.raises(ValueError):
        checkpoint_name("phase02_features")
    with pytest.raises(ValueError):
        checkpoint_name("phase99_unknown")


def test_save_checkpoint_phase00_creates_zip_and_registry(tmp_path: Path) -> None:
    release_dir = _build_phase00_release(tmp_path / "output")
    artifact_root = tmp_path / "artifact-store"

    checkpoint_path = save_checkpoint(release_dir, artifact_root, "phase00_ingest_assignment")
    registry = checkpoint_status(artifact_root, release_id=release_dir.name)

    assert checkpoint_path == artifact_root.resolve() / checkpoint_relative_path("phase00_ingest_assignment")
    assert checkpoint_path.exists()
    assert registry["release_id"] == release_dir.name
    latest = registry["latest"]["phase00_ingest_assignment"]
    assert latest["path"] == "checkpoints/phase00_ingest_assignment.zip"
    assert latest["checksum"]
    assert latest["size_bytes"] > 0
    assert latest["created_at"].endswith("Z")


def test_restore_checkpoint_phase00_restores_required_files(tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    artifact_root = tmp_path / "artifact-store"
    release_dir = _build_phase00_release(output_dir)

    save_checkpoint(release_dir, artifact_root, "phase00_ingest_assignment")
    restored_source = output_dir / DEFAULT_RELEASE_ID
    assert restored_source.exists()
    import shutil
    shutil.rmtree(restored_source)

    restored = restore_checkpoint(output_dir, artifact_root, "phase00_ingest_assignment")

    assert restored == output_dir / DEFAULT_RELEASE_ID
    assert (restored / "tables" / "videos.parquet").exists()
    assert (restored / "raw_mapping" / "media_store_manifest.parquet").exists()
    assert (restored / "manifests" / "batch_000.txt").exists()


def test_checkpoint_status_empty_then_populated(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifact-store"
    empty = checkpoint_status(artifact_root)
    assert empty == {"release_id": DEFAULT_RELEASE_ID, "latest": {}}

    release_dir = _build_phase00_release(tmp_path / "output")
    save_checkpoint(release_dir, artifact_root, "phase00_ingest_assignment")
    populated = checkpoint_status(artifact_root, release_id=release_dir.name)
    assert "phase00_ingest_assignment" in populated["latest"]


def test_restore_checkpoint_overwrite_false_raises_if_target_exists(tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    artifact_root = tmp_path / "artifact-store"
    release_dir = _build_phase00_release(output_dir)
    save_checkpoint(release_dir, artifact_root, "phase00_ingest_assignment")

    with pytest.raises(FileExistsError):
        restore_checkpoint(output_dir, artifact_root, "phase00_ingest_assignment", overwrite=False)


def test_save_checkpoint_phase00_missing_required_file_raises(tmp_path: Path) -> None:
    release_dir = _build_phase00_release(tmp_path / "output")
    artifact_root = tmp_path / "artifact-store"
    (release_dir / "manifests" / "dataset_report.json").unlink()

    with pytest.raises(FileNotFoundError):
        save_checkpoint(release_dir, artifact_root, "phase00_ingest_assignment")


def test_restore_checkpoint_rejects_zip_slip(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifact-store"
    output_dir = tmp_path / "output"
    store = make_artifact_store(artifact_root)
    malicious_zip = tmp_path / "malicious.zip"
    with zipfile.ZipFile(malicious_zip, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("../evil.txt", "owned")
        archive.writestr("tables/videos.parquet", "ok")
    store.upload_file(malicious_zip, checkpoint_relative_path("phase00_ingest_assignment"))

    with pytest.raises(ValueError):
        restore_checkpoint(output_dir, artifact_root, "phase00_ingest_assignment")

    assert not (tmp_path / "evil.txt").exists()
    assert not (output_dir / DEFAULT_RELEASE_ID).exists()


def test_restore_checkpoint_corrupt_zip_leaves_no_release_dir(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifact-store"
    output_dir = tmp_path / "output"
    store = make_artifact_store(artifact_root)
    corrupt_zip = tmp_path / "corrupt.zip"
    corrupt_zip.write_bytes(b"not a zip")
    store.upload_file(corrupt_zip, checkpoint_relative_path("phase00_ingest_assignment"))

    with pytest.raises(zipfile.BadZipFile):
        restore_checkpoint(output_dir, artifact_root, "phase00_ingest_assignment")

    assert not (output_dir / DEFAULT_RELEASE_ID).exists()


def test_restore_checkpoint_validation_failure_leaves_no_release_dir(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifact-store"
    output_dir = tmp_path / "output"
    store = make_artifact_store(artifact_root)
    incomplete_zip = tmp_path / "incomplete.zip"
    with zipfile.ZipFile(incomplete_zip, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("tables/videos.parquet", "videos")
    store.upload_file(incomplete_zip, checkpoint_relative_path("phase00_ingest_assignment"))

    with pytest.raises(FileNotFoundError):
        restore_checkpoint(output_dir, artifact_root, "phase00_ingest_assignment")

    assert not (output_dir / DEFAULT_RELEASE_ID).exists()
