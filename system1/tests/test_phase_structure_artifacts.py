from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from system1.artifacts.package import write_artifact_zip
from system1.cli import app
from system1.release.phase_artifacts import (
    phase01_structure_artifact_remote_path,
    phase01_structure_worker_report_remote_path,
    plan_structure_artifact_restore,
    plan_structure_artifact_sync,
    upload_structure_artifacts_to_hf,
)


runner = CliRunner()


def _write_structure_zip(
    release_dir: Path,
    video_id: str,
    *,
    batch_id: str = "batch_000",
    artifact_type: str = "structure",
) -> Path:
    artifact_dir = release_dir / "artifacts" / "structure" / video_id
    artifact_dir.mkdir(parents=True, exist_ok=True)
    (artifact_dir / "manifest.json").write_text('{"status":"pass"}\n', encoding="utf-8")
    (artifact_dir / "shots.parquet").write_bytes(f"{video_id} shots".encode())
    return write_artifact_zip(
        artifact_dir=artifact_dir,
        zip_path=release_dir / "artifacts" / "structure" / f"{video_id}_structure.zip",
        video_id=video_id,
        artifact_type=artifact_type,
        batch_id=batch_id,
        worker_id="worker_local_01",
        status="complete",
    )


def _build_structure_release(root: Path, *, release_id: str = "canonical_release_v003") -> Path:
    release_dir = root / release_id
    (release_dir / "manifests" / "worker_reports").mkdir(parents=True)
    (release_dir / "manifests" / "batch_000.txt").write_text("L21_V001\nL21_V002\n", encoding="utf-8")
    (release_dir / "manifests" / "batch_001.txt").write_text("L21_V003\n", encoding="utf-8")
    for video_id, batch_id in (("L21_V001", "batch_000"), ("L21_V002", "batch_000"), ("L21_V003", "batch_001")):
        _write_structure_zip(release_dir, video_id, batch_id=batch_id)
    (release_dir / "manifests" / "worker_reports" / "structure_batch_000_worker_local_01.json").write_text(
        '{"status":"completed"}\n',
        encoding="utf-8",
    )
    (release_dir / "manifests" / "worker_reports" / "structure_batch_001_worker_other.json").write_text(
        '{"status":"completed"}\n',
        encoding="utf-8",
    )
    return release_dir


def test_plan_structure_artifact_sync_scopes_to_current_batch_and_worker_report(tmp_path: Path) -> None:
    release_dir = _build_structure_release(tmp_path / "output")

    plan = plan_structure_artifact_sync(
        release_dir,
        release_id="canonical_release_v003",
        batch_id="batch_000",
        worker_id="worker_local_01",
    )

    remote_paths = {item.remote_path for item in plan}
    assert remote_paths == {
        "canonical_release_v003/phase01_structure/artifacts/batch_000/L21_V001_structure.zip",
        "canonical_release_v003/phase01_structure/artifacts/batch_000/L21_V002_structure.zip",
        "canonical_release_v003/phase01_structure/worker_reports/structure_batch_000_worker_local_01.json",
    }
    assert not any("L21_V003" in item.remote_path for item in plan)
    assert not any("worker_other" in item.remote_path for item in plan)


def test_upload_structure_artifacts_uses_single_batch_upload(monkeypatch, tmp_path: Path) -> None:
    release_dir = _build_structure_release(tmp_path / "output")
    calls: dict[str, object] = {}

    class FakeStore:
        def upload_files(self, files, *, commit_message: str, num_threads: int = 2):
            calls["files"] = [(source.name, str(remote_path)) for source, remote_path in files]
            calls["commit_message"] = commit_message
            return [Path("hf:/org/AIC26_release") / str(remote_path) for _, remote_path in files]

    monkeypatch.setattr("system1.release.phase_artifacts._store", lambda **kwargs: FakeStore())

    result = upload_structure_artifacts_to_hf(
        release_dir,
        repo_id="org/AIC26_release",
        release_id="canonical_release_v003",
        batch_id="batch_000",
        worker_id="worker_local_01",
    )

    assert result.file_count == 3
    assert calls["commit_message"] == "Upload phase01 structure artifacts canonical_release_v003/batch_000"
    assert calls["files"] == [
        ("L21_V001_structure.zip", "canonical_release_v003/phase01_structure/artifacts/batch_000/L21_V001_structure.zip"),
        ("L21_V002_structure.zip", "canonical_release_v003/phase01_structure/artifacts/batch_000/L21_V002_structure.zip"),
        (
            "structure_batch_000_worker_local_01.json",
            "canonical_release_v003/phase01_structure/worker_reports/structure_batch_000_worker_local_01.json",
        ),
    ]


def test_sync_structure_artifacts_cli_maps_paths(monkeypatch, tmp_path: Path) -> None:
    _build_structure_release(tmp_path / "output")
    calls: dict[str, object] = {}

    class FakeStore:
        def upload_files(self, files, *, commit_message: str, num_threads: int = 2):
            calls["remote_paths"] = [str(remote_path) for _, remote_path in files]
            return [Path("hf:/org/AIC26_release") / str(remote_path) for _, remote_path in files]

    monkeypatch.setattr("system1.release.phase_artifacts._store", lambda **kwargs: FakeStore())

    result = runner.invoke(
        app,
        [
            "sync-structure-artifacts",
            "--output",
            str(tmp_path / "output"),
            "--hf-repo-id",
            "org/AIC26_release",
            "--release-id",
            "canonical_release_v003",
            "--batch-id",
            "batch_000",
            "--worker-id",
            "worker_local_01",
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert calls["remote_paths"] == [
        "canonical_release_v003/phase01_structure/artifacts/batch_000/L21_V001_structure.zip",
        "canonical_release_v003/phase01_structure/artifacts/batch_000/L21_V002_structure.zip",
        "canonical_release_v003/phase01_structure/worker_reports/structure_batch_000_worker_local_01.json",
    ]


def test_plan_structure_artifact_restore_maps_remote_batch_and_reports(tmp_path: Path) -> None:
    files = plan_structure_artifact_restore(
        tmp_path / "output",
        release_id="canonical_release_v003",
        batch_id="batch_000",
        remote_files=[
            "canonical_release_v003/phase01_structure/artifacts/batch_000/L21_V001_structure.zip",
            "canonical_release_v003/phase01_structure/artifacts/batch_001/L21_V002_structure.zip",
            "canonical_release_v003/phase01_structure/worker_reports/structure_batch_000_worker_local_01.json",
            "canonical_release_v003/phase01_structure/worker_reports/features_batch_000_worker_local_01.json",
        ],
    )

    assert [(item.remote_path, item.local_path.relative_to(tmp_path / "output").as_posix()) for item in files] == [
        (
            "canonical_release_v003/phase01_structure/artifacts/batch_000/L21_V001_structure.zip",
            "canonical_release_v003/artifacts/structure/L21_V001_structure.zip",
        ),
        (
            "canonical_release_v003/phase01_structure/worker_reports/structure_batch_000_worker_local_01.json",
            "canonical_release_v003/manifests/worker_reports/structure_batch_000_worker_local_01.json",
        ),
    ]


def test_restore_structure_artifacts_cli_downloads_without_extracting(monkeypatch, tmp_path: Path) -> None:
    remote_files = [
        "canonical_release_v003/phase01_structure/artifacts/batch_000/L21_V001_structure.zip",
        "canonical_release_v003/phase01_structure/worker_reports/structure_batch_000_worker_local_01.json",
    ]
    downloads: list[tuple[str, str]] = []

    class FakeStore:
        def list_files(self, prefix):
            assert str(prefix) == "canonical_release_v003/phase01_structure"
            return [Path(path) for path in remote_files]

        def download_file(self, relative_path, target: Path):
            downloads.append((str(relative_path), target.relative_to(tmp_path / "output").as_posix()))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"downloaded")
            return target

    monkeypatch.setattr("system1.release.phase_artifacts._store", lambda **kwargs: FakeStore())

    result = runner.invoke(
        app,
        [
            "restore-structure-artifacts",
            "--output",
            str(tmp_path / "output"),
            "--hf-repo-id",
            "org/AIC26_release",
            "--release-id",
            "canonical_release_v003",
            "--batch-id",
            "batch_000",
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert downloads == [
        (
            "canonical_release_v003/phase01_structure/artifacts/batch_000/L21_V001_structure.zip",
            "canonical_release_v003/artifacts/structure/L21_V001_structure.zip",
        ),
        (
            "canonical_release_v003/phase01_structure/worker_reports/structure_batch_000_worker_local_01.json",
            "canonical_release_v003/manifests/worker_reports/structure_batch_000_worker_local_01.json",
        ),
    ]
    assert (tmp_path / "output" / "canonical_release_v003" / "artifacts" / "structure" / "L21_V001_structure.zip").exists()
    assert not (tmp_path / "output" / "canonical_release_v003" / "staging" / "extracted_artifacts").exists()


def test_sync_structure_artifacts_fails_on_invalid_artifact_type(tmp_path: Path) -> None:
    release_dir = tmp_path / "output" / "canonical_release_v003"
    (release_dir / "manifests" / "worker_reports").mkdir(parents=True)
    (release_dir / "manifests" / "batch_000.txt").write_text("L21_V001\n", encoding="utf-8")
    _write_structure_zip(release_dir, "L21_V001", batch_id="batch_000", artifact_type="features")
    (release_dir / "manifests" / "worker_reports" / "structure_batch_000_worker_local_01.json").write_text(
        '{"status":"completed"}\n',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="artifact type mismatch"):
        plan_structure_artifact_sync(
            release_dir,
            release_id="canonical_release_v003",
            batch_id="batch_000",
            worker_id="worker_local_01",
        )


def test_sync_structure_artifacts_fails_on_missing_batch_file(tmp_path: Path) -> None:
    release_dir = tmp_path / "output" / "canonical_release_v003"

    with pytest.raises(FileNotFoundError, match="batch_000.txt"):
        plan_structure_artifact_sync(
            release_dir,
            release_id="canonical_release_v003",
            batch_id="batch_000",
            worker_id="worker_local_01",
        )


def test_sync_structure_artifacts_fails_on_missing_batch_zip(tmp_path: Path) -> None:
    release_dir = tmp_path / "output" / "canonical_release_v003"
    (release_dir / "manifests").mkdir(parents=True)
    (release_dir / "manifests" / "batch_000.txt").write_text("L21_V001\n", encoding="utf-8")

    with pytest.raises(FileNotFoundError, match="L21_V001_structure.zip"):
        plan_structure_artifact_sync(
            release_dir,
            release_id="canonical_release_v003",
            batch_id="batch_000",
            worker_id="worker_local_01",
        )


def test_restore_structure_artifacts_fails_when_remote_batch_empty(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="no structure artifacts"):
        plan_structure_artifact_restore(
            tmp_path / "output",
            release_id="canonical_release_v003",
            batch_id="batch_000",
            remote_files=[],
        )


def test_phase01_structure_path_helpers() -> None:
    assert (
        phase01_structure_artifact_remote_path("canonical_release_v003", "batch_000", "L21_V001")
        == "canonical_release_v003/phase01_structure/artifacts/batch_000/L21_V001_structure.zip"
    )
    assert (
        phase01_structure_worker_report_remote_path("canonical_release_v003", "structure_batch_000_worker.json")
        == "canonical_release_v003/phase01_structure/worker_reports/structure_batch_000_worker.json"
    )
