"""Behavior tests for running a Phase00 batch through the worker with remote storage."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pandas as pd
import pytest

from system1.worker.batch import BatchPaths, run_batch
from test_worker_video import CONFIG, Calls, _make_video, _models, _timeline

RELEASE = "rel_v001"


class LocalStore:
    """Directory-backed stand-in for HuggingFaceDatasetArtifactStore."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.uploads: list[str] = []

    def download_file(self, relative_path, target: Path, **kwargs) -> Path:
        source = self.root / str(relative_path)
        if not source.is_file():
            raise FileNotFoundError(relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        return target

    def upload_file(self, source: Path, relative_path) -> Path:
        target = self.root / str(relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        self.uploads.append(str(relative_path))
        return target

    def exists(self, relative_path) -> bool:
        return (self.root / str(relative_path)).is_file()

    def list_files(self, prefix="") -> list[Path]:
        base = self.root / str(prefix)
        return [path.relative_to(self.root) for path in base.rglob("*") if path.is_file()] if base.exists() else []


@pytest.fixture
def stores(tmp_path):
    raw, source, output = (LocalStore(tmp_path / name) for name in ("raw", "source", "output"))
    phase00 = source.root / RELEASE / "phase00_ingestion"
    (phase00 / "manifests").mkdir(parents=True)
    (phase00 / "manifests" / "batch_000.txt").write_text("V1\nV2\nV3\n")
    rows = []
    for video_id in ("V1", "V2", "V3"):
        if video_id != "V3":  # V3 is missing from raw storage
            video_path = raw.root / "canonical_raw_v001" / "raw_videos" / f"{video_id}.mp4"
            video_path.parent.mkdir(parents=True, exist_ok=True)  # cv2.VideoWriter does not create it
            _make_video(video_path)
            timeline = raw.root / "canonical_raw_v001" / "frame_timeline" / f"{video_id}.parquet"
            timeline.parent.mkdir(parents=True, exist_ok=True)
            pd.DataFrame(_timeline(video_id)).to_parquet(timeline, index=False)
        rows.append({"video_id": video_id, "canonical_prefix": "canonical_raw_v001",
                     "canonical_video_path": f"raw_videos/{video_id}.mp4",
                     "canonical_frame_timeline_path": f"frame_timeline/{video_id}.parquet"})
    (phase00 / "raw_mapping").mkdir()
    pd.DataFrame(rows).to_parquet(phase00 / "raw_mapping" / "media_store_manifest.parquet", index=False)
    return raw, source, output


def _run(stores, tmp_path, calls, **kwargs):
    raw, source, output = stores
    return run_batch(BatchPaths(release_id=RELEASE, batch_id="batch_000", worker_id="w0"), config=CONFIG,
                     models=_models(calls), raw_store=raw, source_store=source, output_store=output,
                     work_root=tmp_path / "local", **kwargs)


def test_batch_uploads_one_package_per_video_and_a_report(stores, tmp_path) -> None:
    report = _run(stores, tmp_path, Calls())
    output = stores[2]

    assert sorted(report["completed"]) == ["V1", "V2"]
    assert list(report["failed"]) == ["V3"]
    assert f"{RELEASE}/worker/artifacts/batch_000/V1.zip" in output.uploads
    saved = json.loads((output.root / RELEASE / "worker" / "reports" / "batch_000_w0.json").read_text())
    assert saved["failed"]["V3"].startswith("FileNotFoundError")


def test_videos_already_uploaded_are_skipped(stores, tmp_path) -> None:
    _run(stores, tmp_path, Calls())
    calls = Calls()
    report = _run(stores, tmp_path, calls)

    assert sorted(report["skipped"]) == ["V1", "V2"]
    assert "cuts" not in calls.count


def test_limit_processes_only_the_first_videos(stores, tmp_path) -> None:
    report = _run(stores, tmp_path, Calls(), limit=1)

    assert report["completed"] == ["V1"]


def test_local_files_are_removed_after_upload(stores, tmp_path) -> None:
    _run(stores, tmp_path, Calls())

    leftovers = [path for path in (tmp_path / "local").rglob("*") if path.is_file()]
    assert leftovers == []


def test_video_has_one_local_copy_during_processing(stores, tmp_path, monkeypatch) -> None:
    import system1.worker.batch as batch

    seen: list[list[str]] = []
    real = batch.process_video

    def counting(video, **kwargs):
        seen.append(sorted(p.name for p in (tmp_path / "local").rglob("*.mp4")))
        return real(video, **kwargs)

    monkeypatch.setattr(batch, "process_video", counting)
    _run(stores, tmp_path, Calls(), limit=1)

    assert seen == [["V1.mp4"]]


def test_video_uploaded_by_another_session_meanwhile_is_skipped(stores, tmp_path) -> None:
    output = stores[2]
    remote = f"{RELEASE}/worker/artifacts/batch_000/V1.zip"
    original = output.list_files

    def list_then_appear(prefix=""):
        files = original(prefix)
        (output.root / remote).parent.mkdir(parents=True, exist_ok=True)
        (output.root / remote).write_bytes(b"other session")
        return files

    output.list_files = list_then_appear
    report = _run(stores, tmp_path, Calls(), limit=1)

    assert report["skipped"] == ["V1"]
    assert remote not in output.uploads
    assert (output.root / remote).read_bytes() == b"other session"
