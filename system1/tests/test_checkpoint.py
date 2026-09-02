from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from system1.artifacts import (
    checkpoint_metadata_relative_path,
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


def _write_checkpoint_artifact_inputs(release_dir: Path) -> None:
    (release_dir / "manifests" / "batch_000.txt").write_text("L21_V001\n", encoding="utf-8")
    (release_dir / "manifests" / "batch_001.txt").write_text("L21_V002\n", encoding="utf-8")
    (release_dir / "artifacts" / "structure").mkdir(parents=True)
    (release_dir / "artifacts" / "features").mkdir(parents=True)
    (release_dir / "manifests" / "worker_reports").mkdir(parents=True)
    for video_id in ("L21_V001", "L21_V002"):
        (release_dir / "artifacts" / "structure" / f"{video_id}_structure.zip").write_bytes(f"{video_id} structure".encode())
        (release_dir / "artifacts" / "features" / f"{video_id}_features.zip").write_bytes(f"{video_id} features".encode())
    (release_dir / "manifests" / "worker_reports" / "structure_batch_000_worker_a.json").write_text('{"ok": true}\n', encoding="utf-8")
    (release_dir / "manifests" / "worker_reports" / "structure_batch_001_worker_b.json").write_text('{"ok": true}\n', encoding="utf-8")
    (release_dir / "manifests" / "worker_reports" / "features_batch_000_worker_a.json").write_text('{"ok": true}\n', encoding="utf-8")
    (release_dir / "manifests" / "worker_reports" / "features_batch_001_worker_b.json").write_text('{"ok": true}\n', encoding="utf-8")


def _zip_names(path: Path) -> set[str]:
    with zipfile.ZipFile(path) as archive:
        return set(archive.namelist())


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
    metadata_path = artifact_root / checkpoint_metadata_relative_path("phase00_ingest_assignment")

    assert checkpoint_path == artifact_root.resolve() / checkpoint_relative_path("phase00_ingest_assignment")
    assert checkpoint_path.exists()
    assert metadata_path.exists()
    assert registry["release_id"] == release_dir.name
    latest = registry["latest"]["phase00_ingest_assignment"]
    assert latest["path"] == "checkpoints/phase00_ingest_assignment.zip"
    assert latest["checksum"]
    assert latest["size_bytes"] > 0
    assert latest["created_at"].endswith("Z")
    assert latest["phase"] == "phase00_ingest_assignment"
    assert latest["release_id"] == DEFAULT_RELEASE_ID


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


def test_checkpoint_status_prefers_individual_metadata_over_legacy_registry(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifact-store"
    release_dir = _build_phase00_release(tmp_path / "output")
    save_checkpoint(release_dir, artifact_root, "phase00_ingest_assignment")

    legacy_registry = artifact_root / "manifests" / "checkpoint_registry.json"
    legacy_registry.write_text('{"release_id":"competition_dataset_v001","latest":{}}\n', encoding="utf-8")

    status = checkpoint_status(artifact_root, release_id=release_dir.name)
    assert "phase00_ingest_assignment" in status["latest"]


def test_checkpoint_status_legacy_fallback_still_works(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifact-store"
    (artifact_root / "manifests").mkdir(parents=True)
    (artifact_root / "manifests" / "checkpoint_registry.json").write_text(
        '{"release_id":"competition_dataset_v001","latest":{"phase00_ingest_assignment":{"path":"checkpoints/phase00_ingest_assignment.zip","status":"pass","checksum":"abc","size_bytes":1,"created_at":"2026-01-01T00:00:00Z","phase":"phase00_ingest_assignment","batch_id":null,"worker_id":null,"release_id":"competition_dataset_v001"}}}\n',
        encoding="utf-8",
    )

    status = checkpoint_status(artifact_root)
    assert "phase00_ingest_assignment" in status["latest"]


def test_multiple_checkpoint_metadata_files_aggregate(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifact-store"
    release_dir = _build_phase00_release(tmp_path / "output")
    save_checkpoint(release_dir, artifact_root, "phase00_ingest_assignment")
    phase01_metadata = artifact_root / checkpoint_metadata_relative_path("phase01_structure", "batch_000")
    phase01_metadata.parent.mkdir(parents=True, exist_ok=True)
    phase01_metadata.write_text(
        '{"path":"checkpoints/phase01_structure_batch_000.zip","status":"pass","checksum":"def","size_bytes":2,"created_at":"2026-01-01T00:00:00Z","phase":"phase01_structure","batch_id":"batch_000","worker_id":"worker_123","release_id":"competition_dataset_v001"}\n',
        encoding="utf-8",
    )

    status = checkpoint_status(artifact_root)
    assert "phase00_ingest_assignment" in status["latest"]
    assert "phase01_structure_batch_000" in status["latest"]


def test_corrupt_metadata_raises_value_error(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifact-store"
    bad = artifact_root / "manifests" / "checkpoints" / "bad.json"
    bad.parent.mkdir(parents=True, exist_ok=True)
    bad.write_text('{"status":"pass"}\n', encoding="utf-8")

    with pytest.raises(ValueError):
        checkpoint_status(artifact_root)


def test_checkpoint_metadata_relative_path_helper() -> None:
    assert checkpoint_metadata_relative_path("phase00_ingest_assignment") == Path("manifests/checkpoints/phase00_ingest_assignment.json")


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


def test_save_checkpoint_phase01_scopes_to_current_batch_artifacts_and_report(tmp_path: Path) -> None:
    release_dir = _build_phase00_release(tmp_path / "output")
    _write_checkpoint_artifact_inputs(release_dir)
    artifact_root = tmp_path / "artifact-store"

    checkpoint_path = save_checkpoint(release_dir, artifact_root, "phase01_structure", batch_id="batch_000", worker_id="worker_a")

    names = _zip_names(Path(checkpoint_path))
    assert "artifacts/structure/L21_V001_structure.zip" in names
    assert "manifests/worker_reports/structure_batch_000_worker_a.json" in names
    assert "artifacts/structure/L21_V002_structure.zip" not in names
    assert "manifests/worker_reports/structure_batch_001_worker_b.json" not in names
    assert not any(name.startswith("artifacts/features/") for name in names)


def test_save_checkpoint_phase02_scopes_to_current_batch_artifacts_and_report(tmp_path: Path) -> None:
    release_dir = _build_phase00_release(tmp_path / "output")
    _write_checkpoint_artifact_inputs(release_dir)
    artifact_root = tmp_path / "artifact-store"

    checkpoint_path = save_checkpoint(release_dir, artifact_root, "phase02_features", batch_id="batch_000", worker_id="worker_a")

    names = _zip_names(Path(checkpoint_path))
    assert "artifacts/features/L21_V001_features.zip" in names
    assert "manifests/worker_reports/features_batch_000_worker_a.json" in names
    assert "artifacts/features/L21_V002_features.zip" not in names
    assert "manifests/worker_reports/features_batch_001_worker_b.json" not in names
    assert not any(name.startswith("artifacts/structure/") for name in names)


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
