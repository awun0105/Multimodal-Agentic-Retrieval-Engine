"""Behavior tests for the per-video worker (docs/architecture/system1-target.md)."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from system1.artifacts.package import validate_artifact_zip
from system1.providers.captions import CaptionResult
from system1.shots.transnet import scenes_to_shot_rows
from system1.text.evidence import AsrSegment
from system1.worker.package import PackageError, validate_package
from system1.worker.video import VideoInput, WorkerModels, process_video

CONFIG = yaml.safe_load((Path(__file__).parents[1] / "configs" / "worker.yaml").read_text())
FPS = 25
FRAMES = 150  # 6 seconds, two shots


def _make_video(path: Path) -> None:
    import cv2

    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), FPS, (64, 48))
    rng = np.random.default_rng(0)
    for index in range(FRAMES):
        frame = rng.integers(0, 255, size=(48, 64, 3), dtype=np.uint8) if index % 25 == 0 else frame
        writer.write(frame)
    writer.release()


def _timeline(video_id: str) -> list[dict]:
    return [{"video_id": video_id, "frame_id": i, "pts_time": i / FPS, "duration_time": 1 / FPS}
            for i in range(FRAMES)]


class Calls:
    def __init__(self) -> None:
        self.count: dict[str, int] = {}

    def hit(self, name: str) -> None:
        self.count[name] = self.count.get(name, 0) + 1


def _models(calls: Calls, *, asr_error: bool = False) -> WorkerModels:
    def shots(video_path, timeline_rows, work_dir):
        calls.hit("shots")
        return scenes_to_shot_rows(video_id="V1", scenes_inclusive=[[0, 74], [75, 149]],
                                   frame_timeline=timeline_rows)

    class Image:
        def embed_images(self, images):
            calls.hit("image")
            return np.random.default_rng(1).normal(size=(len(images), 8)).astype("float32")

    class Asr:
        def transcribe(self, video_path, wav_path):
            calls.hit("asr")
            if asr_error:
                raise RuntimeError("decoder crashed")
            return [AsrSegment(0.5, 2.5, "xin chào các em"), AsrSegment(3.0, 5.5, "hôm nay học vật lý")]

    class Ocr:
        def read(self, image):
            calls.hit("ocr")
            # The logo is on every keyframe; the name caption only on the first.
            return ["tuoitreTV", "Thầy Lê Tấn Phát"] if calls.count["ocr"] == 1 else ["tuoitreTV"]

    class Captioner:
        def caption(self, images):
            calls.hit("captions")
            payload = {"caption": "Một thầy giáo đứng trước bảng xanh trong lớp học.",
                       "objects": ["bảng xanh"], "actions": ["giảng bài"], "visible_text": ""}
            return [CaptionResult(payload, ()) for _ in images]

    class Text:
        def embed_passages(self, texts):
            calls.hit("text")
            return np.random.default_rng(2).normal(size=(len(texts), 4)).astype("float32")

    return WorkerModels(shots=shots, image=Image(), asr=Asr(), ocr=Ocr(), captioner=Captioner(),
                        text=Text())


@pytest.fixture
def video(tmp_path) -> VideoInput:
    path = tmp_path / "V1.mp4"
    _make_video(path)
    return VideoInput(video_id="V1", video_path=path, timeline_rows=_timeline("V1"))


def _run(video, tmp_path, models):
    return process_video(video, config=CONFIG, models=models, work_root=tmp_path / "work",
                         batch_id="batch_000", worker_id="worker_000")


def _table(zip_path: Path, name: str) -> pd.DataFrame:
    with zipfile.ZipFile(zip_path) as archive:
        with archive.open(f"V1/{name}") as handle:
            return pd.read_parquet(handle)


def test_video_is_packaged_with_aligned_tables_and_vectors(video, tmp_path) -> None:
    zip_path = _run(video, tmp_path, _models(Calls()))

    validate_artifact_zip(zip_path)
    keyframes = _table(zip_path, "keyframes.parquet")
    documents = _table(zip_path, "text_documents.parquet")
    assert len(keyframes) >= 2
    assert all(kf == f"V1:{frame}" for kf, frame in zip(keyframes["keyframe_id"], keyframes["frame_id"]))
    assert set(documents["evidence_type"]) == {"asr", "ocr", "caption"}
    with zipfile.ZipFile(zip_path) as archive:
        image_vectors = np.load(archive.open("V1/image_vectors.npy"))
        text_vectors = np.load(archive.open("V1/text_vectors.npy"))
        manifest = json.loads(archive.read("V1/manifest.json"))
    assert image_vectors.shape[0] == len(keyframes)
    assert text_vectors.shape[0] == len(documents)
    assert manifest["stages"]["asr"]["status"] == "pass"


def test_logo_repeated_on_every_keyframe_is_not_indexed(video, tmp_path) -> None:
    documents = _table(_run(video, tmp_path, _models(Calls())), "text_documents.parquet")

    ocr_text = " ".join(documents.loc[documents["evidence_type"] == "ocr", "text"])
    assert "tuoitreTV" not in ocr_text


def test_text_documents_have_accent_free_copies(video, tmp_path) -> None:
    documents = _table(_run(video, tmp_path, _models(Calls())), "text_documents.parquet")

    row = documents[documents["evidence_type"] == "asr"].iloc[0]
    assert row["text_unaccented"] == "xin chao cac em hom nay hoc vat ly"


def test_rerun_reuses_finished_stages(video, tmp_path) -> None:
    calls = Calls()
    _run(video, tmp_path, _models(calls))
    first = dict(calls.count)
    _run(video, tmp_path, _models(calls))

    assert calls.count == first


def test_failed_asr_is_recorded_and_the_video_still_packages(video, tmp_path) -> None:
    zip_path = _run(video, tmp_path, _models(Calls(), asr_error=True))

    with zipfile.ZipFile(zip_path) as archive:
        manifest = json.loads(archive.read("V1/manifest.json"))
    documents = _table(zip_path, "text_documents.parquet")
    assert manifest["stages"]["asr"]["status"] == "failed"
    assert "decoder crashed" in manifest["stages"]["asr"]["error"]
    assert "asr" not in set(documents["evidence_type"])


def test_validator_rejects_vectors_that_do_not_match_keyframes(video, tmp_path) -> None:
    _run(video, tmp_path, _models(Calls()))
    package_dir = tmp_path / "work" / "V1" / "package"
    np.save(package_dir / "image_vectors.npy", np.zeros((1, 8), dtype="float32"))

    with pytest.raises(PackageError, match="image_vectors"):
        validate_package(package_dir, video_id="V1")
