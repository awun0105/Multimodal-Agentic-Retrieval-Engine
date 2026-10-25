"""Behavior tests for the caption pass over worker packages (ADR 0025)."""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from system1.artifacts.package import validate_artifact_zip
from system1.captions.batch import CaptionPaths, run_caption_batch
from system1.captions.video import caption_video
from system1.providers.captions import CaptionResult
from system1.worker.video import VideoInput, process_video
from test_worker_batch import RELEASE, LocalStore
from test_worker_video import CONFIG, Calls, _make_video, _models, _timeline

PAYLOAD = {"caption": "Một thầy giáo đứng trước bảng xanh trong lớp học.",
           "objects": ["bảng xanh"], "actions": ["giảng bài"], "visible_text": "Vật lý 10"}


class Captioner:
    """Accepts every image except the first, which is rejected as a repetition loop."""

    def __init__(self, calls: Calls) -> None:
        self.calls = calls

    def caption(self, images):
        self.calls.hit("captions")
        return [CaptionResult(None, ("repetition_loop",)) if index == 0 else CaptionResult(PAYLOAD, ())
                for index in range(len(images))]


class Text:
    def __init__(self, calls: Calls) -> None:
        self.calls = calls

    def embed_passages(self, texts):
        self.calls.hit("text")
        return np.random.default_rng(3).normal(size=(len(texts), 4)).astype("float32")


@pytest.fixture
def worker_zip(tmp_path) -> Path:
    path = tmp_path / "V1.mp4"
    _make_video(path)
    video = VideoInput(video_id="V1", video_path=path, timeline_rows=_timeline("V1"))
    return process_video(video, config=CONFIG, models=_models(Calls()), work_root=tmp_path / "worker",
                         batch_id="batch_000", worker_id="worker_000")


def _caption(worker_zip: Path, work_root: Path, calls: Calls) -> Path:
    return caption_video(worker_zip, config=CONFIG, captioner=Captioner(calls), text_embedder=Text(calls),
                         work_root=work_root, batch_id="batch_000", worker_id="worker_000")


def _read(zip_path: Path, name: str):
    with zipfile.ZipFile(zip_path) as archive:
        if name.endswith(".parquet"):
            return pd.read_parquet(archive.open(f"V1/{name}"))
        if name.endswith(".npy"):
            return np.load(archive.open(f"V1/{name}"))
        return json.loads(archive.read(f"V1/{name}"))


def test_every_shot_gets_one_caption_row_and_rejected_captions_get_no_document(worker_zip, tmp_path) -> None:
    zip_path = _caption(worker_zip, tmp_path / "captions", Calls())

    validate_artifact_zip(zip_path)
    shots = _read(worker_zip, "shots.parquet")
    keyframes = _read(worker_zip, "keyframes.parquet")
    captions = _read(zip_path, "captions.parquet")
    documents = _read(zip_path, "text_documents.parquet")
    assert sorted(captions["shot_id"]) == sorted(shots["shot_id"])
    representatives = set(keyframes.loc[keyframes["is_representative"], "keyframe_id"])
    assert set(captions["keyframe_id"]) == representatives
    rejected = captions.iloc[0]
    assert list(rejected["problems"]) == ["repetition_loop"]
    assert rejected["shot_id"] not in set(documents["shot_ids"])
    assert set(documents["evidence_type"]) == {"caption", "visible_text"}
    assert len(documents) == 2 * (len(captions) - 1)
    assert documents["keyframe_id"].notna().all()
    assert (documents["start_sec"] == documents["end_sec"]).all()
    assert documents.loc[documents["evidence_type"] == "visible_text", "text_unaccented"].iloc[0] == "Vat ly 10"
    assert _read(zip_path, "text_vectors.npy").shape[0] == len(documents)


def test_manifest_ties_the_caption_package_to_the_worker_package(worker_zip, tmp_path) -> None:
    manifest = _read(_caption(worker_zip, tmp_path / "captions", Calls()), "manifest.json")

    assert manifest["schema_version"] == "caption_package_v1"
    assert manifest["worker_package_sha256"] == hashlib.sha256(worker_zip.read_bytes()).hexdigest()
    assert manifest["models"]["captions"] == {key: CONFIG["captions"][key] for key in ("model_id", "revision")}
    report = manifest["stages"]["captions"]
    assert report["status"] == "pass" and report["rejected"] == 1 and "seconds" in report


def test_worker_package_is_not_extracted(worker_zip, tmp_path) -> None:
    work_root = tmp_path / "captions"
    _caption(worker_zip, work_root, Calls())

    assert not [path for path in work_root.rglob("*") if path.name in ("keyframes", "thumbnails")]
    assert not list(work_root.rglob("*.jpg"))


@pytest.fixture
def stores(tmp_path, worker_zip):
    worker, output = LocalStore(tmp_path / "worker_store"), LocalStore(tmp_path / "output")
    worker.upload_file(worker_zip, f"{RELEASE}/worker/artifacts/batch_000/V1.zip")
    (worker.root / RELEASE / "worker" / "artifacts" / "batch_000" / "V2.zip").write_bytes(b"not a zip")
    return worker, output


def _run_batch(stores, tmp_path, calls, **kwargs):
    worker, output = stores
    return run_caption_batch(CaptionPaths(release_id=RELEASE, batch_id="batch_000", worker_id="w0"),
                             config=CONFIG, captioner=Captioner(calls), text_embedder=Text(calls),
                             worker_store=worker, output_store=output, work_root=tmp_path / "local", **kwargs)


def test_batch_uploads_caption_packages_records_failures_and_persists_the_report(stores, tmp_path) -> None:
    report = _run_batch(stores, tmp_path, Calls(), persist_dir=tmp_path / "kept")
    output = stores[1]

    assert report["completed"] == ["V1"]
    assert list(report["failed"]) == ["V2"]
    assert f"{RELEASE}/captions/artifacts/batch_000/V1.zip" in output.uploads
    saved = json.loads((output.root / RELEASE / "captions" / "reports" / "batch_000_w0.json").read_text())
    assert saved["completed"] == ["V1"]
    assert json.loads((tmp_path / "kept" / "report.json").read_text())["completed"] == ["V1"]
    assert not (tmp_path / "local").exists()


def test_batch_skips_videos_that_already_have_a_caption_package(stores, tmp_path) -> None:
    _run_batch(stores, tmp_path, Calls())
    calls = Calls()
    report = _run_batch(stores, tmp_path, calls)

    assert report["skipped"] == ["V1"]
    assert "captions" not in calls.count
