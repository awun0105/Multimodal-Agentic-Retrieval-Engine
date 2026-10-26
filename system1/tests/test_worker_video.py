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
from system1.providers.cuts import TransNetStream
from system1.text.evidence import AsrSegment
from system1.worker.package import PackageError, representative_keyframes, validate_package
from system1.worker.video import VideoInput, WorkerModels, process_video

CONFIG = yaml.safe_load((Path(__file__).parents[1] / "configs" / "worker.yaml").read_text())
FPS = 25
FRAMES = 150  # 6 seconds, two cut segments, new content every second


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


class FakeCuts:
    """TransNet stand-in: fixed per-frame predictions with the real 100-frame window lag."""

    threshold = 0.5

    def __init__(self, calls: Calls, predictions, *, error_at: int | None = None) -> None:
        self.calls, self.predictions, self.error_at = calls, np.asarray(predictions, dtype=float), error_at

    def start(self) -> TransNetStream:
        self.calls.hit("cuts")
        pushed = {"frames": 0}

        def predict_window(frames):
            if self.error_at is not None and pushed["frames"] >= self.error_at:
                raise RuntimeError("CUDA error: device-side assert")
            begin = stream.emitted
            values = self.predictions[begin:begin + 50]
            return np.pad(values, (0, 50 - len(values)))

        stream = TransNetStream(predict_window)
        push = stream.push

        def counted_push(frame):
            pushed["frames"] += 1
            return push(frame)

        stream.push = counted_push
        return stream


def _cut_predictions(frame_count: int, cut_frames: list[int]) -> np.ndarray:
    predictions = np.zeros(frame_count)
    predictions[cut_frames] = 0.9
    return predictions


def _models(calls: Calls, *, asr_error: bool = False) -> WorkerModels:
    cuts = FakeCuts(calls, _cut_predictions(FRAMES, [74]))  # cut segments [0, 75) and [75, 150)

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
        def read(self, image, cache=None):
            calls.hit("ocr")
            # The logo is on every keyframe; the name caption only on the first.
            return ["tuoitreTV", "Thầy Lê Tấn Phát"] if calls.count["ocr"] == 1 else ["tuoitreTV"]

    class Text:
        def embed_passages(self, texts):
            calls.hit("text")
            return np.random.default_rng(2).normal(size=(len(texts), 4)).astype("float32")

    return WorkerModels(cuts=cuts, image=Image(), asr=Asr(), ocr=Ocr(), text=Text())


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
    assert set(documents["evidence_type"]) == {"asr", "ocr"}
    with zipfile.ZipFile(zip_path) as archive:
        image_vectors = np.load(archive.open("V1/image_vectors.npy"))
        text_vectors = np.load(archive.open("V1/text_vectors.npy"))
        manifest = json.loads(archive.read("V1/manifest.json"))
    assert image_vectors.shape[0] == len(keyframes)
    assert text_vectors.shape[0] == len(documents)
    assert manifest["schema_version"] == "worker_package_v2"
    assert "captions" not in manifest["stages"] and "captions" not in manifest["models"]
    assert manifest["stages"]["asr"]["status"] == "pass"
    assert all("seconds" in report for report in manifest["stages"].values())


def test_cut_segments_with_changing_content_split_into_shots(video, tmp_path) -> None:
    zip_path = _run(video, tmp_path, _models(Calls()))

    cuts = _table(zip_path, "cut_segments.parquet")
    shots = _table(zip_path, "shots.parquet")
    keyframes = _table(zip_path, "keyframes.parquet")
    assert len(cuts) == 2
    assert len(shots) > len(cuts)
    assert set(keyframes["shot_id"]) == set(shots["shot_id"])
    for cut in cuts.itertuples():
        inside = shots[shots["cut_segment_id"] == cut.cut_segment_id].sort_values("start_frame")
        assert inside["start_frame"].iloc[0] == cut.start_frame
        assert inside["end_frame"].iloc[-1] == cut.end_frame
        assert (inside["start_frame"].iloc[1:].values == inside["end_frame"].iloc[:-1].values).all()


def test_failed_cut_detection_falls_back_to_one_segment(video, tmp_path) -> None:
    models = _models(Calls())

    class BrokenCuts:
        threshold = 0.5

        def start(self):
            raise RuntimeError("TransNet weights missing")

    models.cuts = BrokenCuts()
    zip_path = _run(video, tmp_path, models)

    cuts = _table(zip_path, "cut_segments.parquet")
    with zipfile.ZipFile(zip_path) as archive:
        manifest = json.loads(archive.read("V1/manifest.json"))
    assert cuts[["start_frame", "end_frame"]].values.tolist() == [[0, FRAMES]]
    assert manifest["stages"]["cuts"]["status"] == "fallback"
    assert "TransNet weights missing" in manifest["stages"]["cuts"]["error"]
    assert len(_table(zip_path, "shots.parquet")) > 1


def test_rerun_after_cut_fallback_retries_cuts_and_rebuilds_shots(video, tmp_path) -> None:
    calls = Calls()
    models = _models(calls)
    working_cuts = models.cuts

    class BrokenCuts:
        threshold = 0.5

        def start(self):
            raise RuntimeError("TransNet weights missing")

    models.cuts = BrokenCuts()
    _run(video, tmp_path, models)
    models.cuts = working_cuts
    zip_path = _run(video, tmp_path, models)

    assert len(_table(zip_path, "cut_segments.parquet")) == 2
    assert set(_table(zip_path, "shots.parquet")["cut_segment_id"]) == {"V1_CS00000", "V1_CS00001"}


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


def test_asr_documents_have_null_keyframe_id(video, tmp_path) -> None:
    import pyarrow.parquet as pq

    zip_path = _run(video, tmp_path, _models(Calls()))
    with zipfile.ZipFile(zip_path) as archive:
        table = pq.read_table(archive.open("V1/text_documents.parquet"))

    assert str(table.schema.field("keyframe_id").type) in ("string", "large_string")
    rows = table.to_pylist()
    assert [row["keyframe_id"] for row in rows if row["evidence_type"] == "asr"] == [None, None]
    assert all(row["keyframe_id"] for row in rows if row["evidence_type"] == "ocr")


def test_asr_window_documents_follow_chunks_and_are_flagged(video, tmp_path) -> None:
    documents = _table(_run(video, tmp_path, _models(Calls())), "text_documents.parquet")

    asr = documents[documents["evidence_type"] == "asr"]
    assert list(asr["doc_id"]) == ["V1:asr:00000", "V1:asr:00001"]
    assert list(asr["window"]) == [False, True]
    assert not documents.loc[documents["evidence_type"] == "ocr", "window"].any()


def test_package_satisfies_v2_schemas_with_null_scene_and_one_representative(video, tmp_path) -> None:
    zip_path = _run(video, tmp_path, _models(Calls()))

    shots = _table(zip_path, "shots.parquet")
    keyframes = _table(zip_path, "keyframes.parquet")
    assert shots["scene_id"].isna().all()
    assert (keyframes.groupby("shot_id")["is_representative"].sum() == 1).all()


def test_validator_rejects_a_schema_violation(video, tmp_path) -> None:
    _run(video, tmp_path, _models(Calls()))
    package_dir = tmp_path / "work" / "V1" / "package"
    shots = pd.read_parquet(package_dir / "shots.parquet")
    shots.loc[0, "start_sec"] = float("nan")
    shots.to_parquet(package_dir / "shots.parquet", index=False)

    with pytest.raises(PackageError, match="shots row 0"):
        validate_package(package_dir, video_id="V1")

    shots.loc[0, "start_sec"] = 0.0
    shots.loc[0, "shot_id"] = "V1_shot_zero"
    shots.to_parquet(package_dir / "shots.parquet", index=False)
    with pytest.raises(PackageError, match="shots.schema.json at shot_id"):
        validate_package(package_dir, video_id="V1")


def test_validator_rejects_text_documents_without_window(video, tmp_path) -> None:
    _run(video, tmp_path, _models(Calls()))
    package_dir = tmp_path / "work" / "V1" / "package"
    documents = pd.read_parquet(package_dir / "text_documents.parquet")
    documents.drop(columns=["window"]).to_parquet(package_dir / "text_documents.parquet", index=False)

    with pytest.raises(PackageError, match="window"):
        validate_package(package_dir, video_id="V1")


def test_image_vectors_come_from_one_embed_call_per_cut_segment(video, tmp_path) -> None:
    calls = Calls()
    zip_path = _run(video, tmp_path, _models(calls))

    keyframes = _table(zip_path, "keyframes.parquet")
    with zipfile.ZipFile(zip_path) as archive:
        image_vectors = np.load(archive.open("V1/image_vectors.npy"))
        manifest = json.loads(archive.read("V1/manifest.json"))
    assert image_vectors.shape[0] == len(keyframes)
    assert calls.count["image"] == len(_table(zip_path, "cut_segments.parquet")) == 2
    assert calls.count["image"] < len(keyframes)
    assert "blurred_dropped" in manifest["stages"]["keyframes"]


def test_representative_is_the_keyframe_nearest_the_shot_centroid(video, tmp_path) -> None:
    zip_path = _run(video, tmp_path, _models(Calls()))
    keyframes = _table(zip_path, "keyframes.parquet")
    with zipfile.ZipFile(zip_path) as archive:
        vectors = np.load(archive.open("V1/image_vectors.npy"))

    for shot_id, group in keyframes.groupby("shot_id"):
        rows = vectors[group.index]
        rows = rows / np.linalg.norm(rows, axis=1, keepdims=True)
        expected = group["keyframe_id"].iloc[int(np.argmax(rows @ rows.mean(axis=0)))]
        assert group.loc[group["is_representative"], "keyframe_id"].tolist() == [expected]


def test_representative_uses_vectors_over_the_middle_rule() -> None:
    keyframes = pd.DataFrame({"shot_id": ["S"] * 3, "keyframe_id": ["a", "b", "c"]})
    vectors = np.array([[1, 0], [0, 1], [1, 0.1]], dtype=np.float32)

    assert representative_keyframes(keyframes)["keyframe_id"].tolist() == ["b"]
    assert representative_keyframes(keyframes, vectors)["keyframe_id"].tolist() in (["a"], ["c"])


def test_gpu_failure_mid_video_falls_back_without_a_second_attempt(video, tmp_path) -> None:
    calls = Calls()
    models = _models(calls)
    models.cuts = FakeCuts(calls, _cut_predictions(FRAMES, [74]), error_at=120)
    zip_path = _run(video, tmp_path, models)

    with zipfile.ZipFile(zip_path) as archive:
        manifest = json.loads(archive.read("V1/manifest.json"))
    assert calls.count["cuts"] == 1  # no CPU retry (plan Step 5f item 11)
    assert manifest["stages"]["cuts"]["status"] == "fallback"
    assert "device-side assert" in manifest["stages"]["cuts"]["error"]
    assert _table(zip_path, "cut_segments.parquet")[["start_frame", "end_frame"]].values.tolist() == [[0, FRAMES]]
    keyframes = _table(zip_path, "keyframes.parquet")
    with zipfile.ZipFile(zip_path) as archive:
        images = {name for name in archive.namelist() if name.startswith("V1/keyframes/")}
    assert images == {f"V1/{ref}" for ref in keyframes["keyframe_ref"]}


def _make_equivalence_video(path: Path, frame_count: int) -> None:
    """Hard cuts at frames 100 and 200, a slow blend inside the middle segment, motion in the first."""

    import cv2

    rng = np.random.default_rng(7)
    first, second, third, fourth = (rng.integers(0, 255, size=(64, 96, 3), dtype=np.uint8) for _ in range(4))
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), FPS, (96, 64))
    for index in range(frame_count):
        if index < 100:
            frame = np.roll(first, index, axis=1)
        elif index < 200:
            weight = (index - 100) / 99
            frame = ((1 - weight) * second + weight * third).astype(np.uint8)
        else:
            frame = fourth
        writer.write(frame)
    writer.release()


def test_single_pass_matches_two_pass_cuts_shots_and_keyframes(tmp_path) -> None:
    from system1.keyframes.adaptive import iter_cut_segment_frames, plan_candidate_frames
    from system1.keyframes.builder import iter_decode_frame_groups
    from system1.shots.transnet import scenes_to_shot_rows
    from system1.shots.transnet_worker import predictions_to_scenes
    from system1.worker.video import _policy, _single_pass, _split_shots

    frame_count = 300
    path = tmp_path / "V2.mp4"
    _make_equivalence_video(path, frame_count)
    timeline = [{"video_id": "V2", "frame_id": i, "pts_time": i / FPS, "duration_time": 1 / FPS}
                for i in range(frame_count)]
    video = VideoInput(video_id="V2", video_path=path, timeline_rows=timeline)
    # A one-frame cut, a five-frame dissolve run, and runs touching both ends (not cuts).
    predictions = _cut_predictions(frame_count, [0, 1, 99, 198, 199, 200, 201, 202, 297, 298, 299])
    scenes = predictions_to_scenes(predictions, 0.5)
    assert scenes == [[0, 99], [100, 200], [201, 299]]

    class MeanColor:  # coarse grey layout, centred, so a content change moves the vector
        def embed_images(self, images):
            vectors = [np.asarray(image.convert("L").resize((8, 8)), dtype="float32").reshape(-1)
                       for image in images]
            return np.stack([vector - vector.mean() + 1e-3 for vector in vectors])

    settings = CONFIG["keyframes"]
    rows = scenes_to_shot_rows(video_id="V2", scenes_inclusive=scenes, frame_timeline=timeline)
    two_pass_cuts = pd.DataFrame(
        [{"cut_segment_id": f"V2_CS{index:05d}", "video_id": "V2",
          **{key: row[key] for key in ("start_frame", "end_frame", "start_sec", "end_sec")}}
         for index, row in enumerate(rows)])
    two_pass = _split_shots(video, two_pass_cuts, settings, tmp_path / "two", MeanColor())
    single_cuts, single = _single_pass(video, settings, tmp_path / "one", MeanColor(),
                                       FakeCuts(Calls(), predictions))

    assert pd.DataFrame(single_cuts).equals(two_pass_cuts)
    assert single[0] == two_pass[0] and single[1] == two_pass[1] and single[3] == two_pass[3]
    np.testing.assert_array_equal(single[2], two_pass[2])
    assert len(single[0]) > len(scenes)  # the blend and the motion split segments into shots
    for row in single[1]:
        assert (tmp_path / "one" / row["keyframe_ref"]).read_bytes() == \
            (tmp_path / "two" / row["keyframe_ref"]).read_bytes()

    # Candidate frames are the same arrays the two-pass decoder returns.
    pts = [row["pts_time"] for row in timeline]
    policy = _policy(settings)
    plans = [plan_candidate_frames(start_frame=s, end_frame=e + 1, pts=pts, policy=policy) for s, e in scenes]
    single_groups = list(iter_cut_segment_frames(path, pts=pts, policy=policy,
                                                 predictor=FakeCuts(Calls(), predictions).start(), threshold=0.5))
    assert [(s, e, plan) for s, e, plan, _ in single_groups] == \
        [(s, e + 1, plan) for (s, e), plan in zip(scenes, plans)]
    for (_, _, _, frames), expected in zip(single_groups, iter_decode_frame_groups(path, plans)):
        assert frames.keys() == expected.keys()
        assert all(np.array_equal(frames[key], expected[key]) for key in frames)


@pytest.mark.parametrize("frame_count", [1, 50, 74, 75, 100, 151])
def test_transnet_stream_gives_each_frame_its_window_prediction(frame_count) -> None:
    # Each window predicts its middle 50 frames (25..74); frame i must get the value computed from itself.
    def predict_window(frames):
        return [float(frame[0, 0, 0]) + 1000 * float(frame[0, 0, 1]) for frame in frames[25:75]]

    stream = TransNetStream(predict_window)
    values: list[float] = []
    for index in range(frame_count):
        frame = np.zeros((27, 48, 3), dtype=np.uint8)
        frame[0, 0, 0], frame[0, 0, 1] = index % 256, index // 256
        values.extend(stream.push(frame))
    values.extend(stream.finish())
    assert values == [float(index) for index in range(frame_count)]
