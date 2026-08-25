from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from system1.config import load_configs
from system1.keyframes.builder import (
    candidate_frame_ids_for_shot,
    evaluate_candidate,
    iter_decode_frame_groups,
    select_keyframes_for_shot,
    write_keyframe_images,
)
from system1.shots.transnet import load_transnet_artifact, scenes_to_shot_rows
from system1.shots.transnet_worker import predictions_to_scenes

CONFIG_DIR = Path(__file__).parents[1] / "configs"


def keyframe_config() -> dict:
    return load_configs(CONFIG_DIR)["media"]["keyframe"]


def checkerboard(size: int = 64) -> np.ndarray:
    grid = np.indices((size, size)).sum(axis=0) % 2
    return np.repeat((grid * 255).astype(np.uint8)[:, :, None], 3, axis=2)


def test_transnet_scene_conversion_preserves_exclusive_canonical_ranges() -> None:
    timeline = [
        {"frame_id": index, "pts_time": index * 0.04, "duration_time": 0.04}
        for index in range(6)
    ]
    rows = scenes_to_shot_rows(
        video_id="L21_V001",
        scenes_inclusive=[[0, 2], [3, 5]],
        frame_timeline=timeline,
    )
    assert [(row["start_frame"], row["end_frame"]) for row in rows] == [(0, 3), (3, 6)]
    assert rows[-1]["end_sec"] == 0.24000000000000002


def test_transnet_all_false_and_all_true_predictions_are_one_shot() -> None:
    assert predictions_to_scenes(np.zeros(4), 0.5) == [[0, 3]]
    assert predictions_to_scenes(np.ones(4), 0.5) == [[0, 3]]


def test_transnet_transition_spans_collapse_without_dropping_frames() -> None:
    predictions = np.array([0, 0, 1, 1, 1, 0, 0, 1, 1, 0], dtype=float)
    scenes = predictions_to_scenes(predictions, 0.5)
    assert scenes == [[0, 3], [4, 7], [8, 9]]
    flattened = [frame for start, end in scenes for frame in range(start, end + 1)]
    assert flattened == list(range(len(predictions)))


def test_transnet_artifact_pins_source_and_weight_checksums(tmp_path: Path) -> None:
    source = tmp_path / "transnetv2_pytorch.py"
    weights = tmp_path / "weights.pth"
    source.write_bytes(b"official-source")
    weights.write_bytes(b"converted-weights")
    source_sha = hashlib.sha256(source.read_bytes()).hexdigest()
    weights_sha = hashlib.sha256(weights.read_bytes()).hexdigest()
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "transnetv2_model_artifact_v1",
                "upstream_commit": "pinned-commit",
                "conversion_verified": True,
                "source_file": source.name,
                "source_sha256": source_sha,
                "weights_file": weights.name,
                "weights_sha256": weights_sha,
            }
        ),
        encoding="utf-8",
    )

    artifact = load_transnet_artifact(
        tmp_path,
        expected_commit="pinned-commit",
        expected_source_sha256=source_sha,
        expected_weights_sha256=weights_sha,
    )
    assert artifact.source_path == source
    with pytest.raises(ValueError, match="source checksum does not match"):
        load_transnet_artifact(
            tmp_path,
            expected_commit="pinned-commit",
            expected_source_sha256="0" * 64,
            expected_weights_sha256=weights_sha,
        )


def test_transnet_preconverted_artifact_requires_explicit_policy(tmp_path: Path) -> None:
    source = tmp_path / "transnetv2_pytorch.py"
    weights = tmp_path / "weights.pth"
    source.write_bytes(b"official-source")
    weights.write_bytes(b"preconverted-weights")
    source_sha = hashlib.sha256(source.read_bytes()).hexdigest()
    weights_sha = hashlib.sha256(weights.read_bytes()).hexdigest()
    manifest_path = tmp_path / "manifest.json"
    manifest = {
        "schema_version": "transnetv2_model_artifact_v1",
        "artifact_origin": "preconverted_huggingface_mirror",
        "upstream_commit": "pinned-commit",
        "conversion_verified": False,
        "source_file": source.name,
        "source_sha256": source_sha,
        "weights_file": weights.name,
        "weights_sha256": weights_sha,
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="conversion parity was not verified"):
        load_transnet_artifact(
            tmp_path,
            expected_commit="pinned-commit",
            expected_source_sha256=source_sha,
            expected_weights_sha256=weights_sha,
        )

    artifact = load_transnet_artifact(
        tmp_path,
        expected_commit="pinned-commit",
        expected_source_sha256=source_sha,
        expected_weights_sha256=weights_sha,
        expected_conversion_verified=False,
    )
    assert artifact.weights_path == weights

    manifest["artifact_origin"] = "unknown_mirror"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="preconverted artifact origin is not trusted"):
        load_transnet_artifact(
            tmp_path,
            expected_commit="pinned-commit",
            expected_source_sha256=source_sha,
            expected_weights_sha256=weights_sha,
            expected_conversion_verified=False,
        )


def test_candidate_search_bands_are_centered_around_20_50_80() -> None:
    ids = candidate_frame_ids_for_shot(
        {"shot_id": "v_SH00000", "start_frame": 100, "end_frame": 201},
        keyframe_config(),
    )
    assert 120 in ids["early"]
    assert 150 in ids["middle"]
    assert 180 in ids["late"]


def test_quality_rejects_near_black_and_prefers_sharp_relative_candidate() -> None:
    config = keyframe_config()
    black = np.zeros((64, 64, 3), dtype=np.uint8)
    smooth = np.full((64, 64, 3), 100, dtype=np.uint8)
    sharp = checkerboard()
    rejected = evaluate_candidate(
        frame_id=1,
        role="middle",
        target_frame=1,
        frame=black,
        quality_config=config["quality"],
    )
    smooth_score = evaluate_candidate(
        frame_id=2,
        role="middle",
        target_frame=2,
        frame=smooth,
        quality_config=config["quality"],
    )
    sharp_score = evaluate_candidate(
        frame_id=3,
        role="middle",
        target_frame=3,
        frame=sharp,
        quality_config=config["quality"],
    )
    assert rejected.invalid_reason == "near_black"
    assert rejected.mean_luma == 0.0
    assert rejected.black_ratio == 1.0
    assert rejected.target_distance == 0.0
    assert sharp_score.quality_score > smooth_score.quality_score
    assert sharp_score.mean_luma is not None
    assert sharp_score.white_ratio is not None


def test_representative_uses_best_frame_when_middle_is_blurred() -> None:
    config = keyframe_config()
    shot = {"shot_id": "v_SH00000", "start_frame": 0, "end_frame": 101}
    candidates = candidate_frame_ids_for_shot(shot, config)
    frames = {frame_id: np.full((64, 64, 3), 100, dtype=np.uint8) for ids in candidates.values() for frame_id in ids}
    early_target = 20
    middle_target = 50
    late_target = 80
    frames[early_target] = checkerboard()
    frames[middle_target] = np.full((64, 64, 3), 100, dtype=np.uint8)
    frames[late_target] = np.roll(checkerboard(), 1, axis=0)
    selected, _diagnostics = select_keyframes_for_shot(shot, frames, config)
    representative = [item for item in selected if item.is_representative]
    assert len(representative) == 1
    assert representative[0].role in {"early", "late"}


def test_short_shot_deduplicates_roles_and_writes_expected_media(tmp_path: Path) -> None:
    config = keyframe_config()
    shot = {"shot_id": "v_SH00000", "start_frame": 7, "end_frame": 8}
    selected, _diagnostics = select_keyframes_for_shot(shot, {7: checkerboard()}, config)
    assert [(item.frame_id, item.role, item.is_representative) for item in selected] == [
        (7, "middle", True)
    ]
    keyframe = tmp_path / "frame.jpg"
    thumbnail = tmp_path / "frame.webp"
    write_keyframe_images(checkerboard(120), keyframe_path=keyframe, thumbnail_path=thumbnail)
    with Image.open(keyframe) as image:
        assert max(image.size) == 960
    with Image.open(thumbnail) as image:
        assert image.width == 256


def test_frame_groups_are_decoded_in_one_forward_pass(monkeypatch) -> None:
    class Capture:
        def __init__(self, _path: str) -> None:
            self.next_index = 0
            self.current_index = -1
            self.grab_count = 0

        def isOpened(self) -> bool:
            return True

        def grab(self) -> bool:
            if self.next_index >= 8:
                return False
            self.current_index = self.next_index
            self.next_index += 1
            self.grab_count += 1
            return True

        def retrieve(self):
            frame = np.full((2, 2, 3), self.current_index, dtype=np.uint8)
            return True, frame

        def release(self) -> None:
            return None

    capture = Capture("unused")
    fake_cv2 = SimpleNamespace(
        VideoCapture=lambda _path: capture,
        COLOR_BGR2RGB=1,
        cvtColor=lambda frame, _conversion: frame,
    )
    monkeypatch.setitem(sys.modules, "cv2", fake_cv2)

    groups = list(iter_decode_frame_groups("unused.mp4", ({1, 3}, {5, 7})))

    assert [sorted(group) for group in groups] == [[1, 3], [5, 7]]
    assert int(groups[1][7][0, 0, 0]) == 7
    assert capture.grab_count == 8
