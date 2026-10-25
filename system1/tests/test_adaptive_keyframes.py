"""Behavior tests for content-adaptive keyframe sampling (ADR 0022)."""

from __future__ import annotations

import numpy as np
import pytest

from system1.keyframes.adaptive import (
    AdaptiveKeyframePolicy,
    plan_candidate_frames,
    select_adaptive_keyframes,
)

POLICY = AdaptiveKeyframePolicy(
    candidate_interval_sec=2.0,
    min_change=0.15,
    shot_drift=0.35,
    max_shot_sec=12.0,
    edge_margin_frames=2,
)


def _timeline(frame_count: int, fps: float = 25.0) -> list[float]:
    return [index / fps for index in range(frame_count)]


def _frame(seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.integers(0, 255, size=(36, 64, 3), dtype=np.uint8)


def test_video_without_cuts_gets_candidates_across_its_whole_length() -> None:
    pts = _timeline(25 * 600)  # one 10-minute take without cuts
    frames = plan_candidate_frames(start_frame=0, end_frame=len(pts), pts=pts, policy=POLICY)

    assert len(frames) >= 290
    assert pts[frames[0]] < 2.5
    assert pts[frames[-1]] > 597.0


def test_candidates_stay_inside_the_cut_segment_and_away_from_cuts() -> None:
    pts = _timeline(1000)
    frames = plan_candidate_frames(start_frame=200, end_frame=400, pts=pts, policy=POLICY)

    assert frames == sorted(set(frames))
    assert all(202 <= frame < 398 for frame in frames)


def test_short_cut_segment_gets_one_middle_candidate() -> None:
    pts = _timeline(1000)
    frames = plan_candidate_frames(start_frame=100, end_frame=120, pts=pts, policy=POLICY)

    assert frames == [109]  # frames 100..119


def test_static_content_keeps_one_keyframe_per_max_shot_length() -> None:
    still = _frame(1)
    candidates = [(frame_id, frame_id / 25.0, still) for frame_id in range(0, 25 * 60, 50)]

    kept = select_adaptive_keyframes(candidates, policy=POLICY)

    # 60 seconds of identical frames, a new shot every 12 seconds.
    assert [item.shot_index for item in kept] == [0, 1, 2, 3, 4]
    assert all(item.reason == "shot_start" for item in kept)


def test_changing_content_keeps_every_distinct_frame() -> None:
    candidates = [(frame_id, frame_id / 25.0, _frame(frame_id)) for frame_id in range(0, 500, 50)]

    kept = select_adaptive_keyframes(candidates, policy=POLICY)

    assert [item.frame_id for item in kept] == [frame_id for frame_id, _, _ in candidates]


def test_near_duplicate_frames_are_dropped() -> None:
    base = _frame(7)
    near = base.copy()
    near[0, 0] = 0
    candidates = [(0, 0.0, base), (50, 2.0, near), (100, 4.0, _frame(8))]

    kept = select_adaptive_keyframes(candidates, policy=POLICY)

    assert [item.frame_id for item in kept] == [0, 100]


def test_undecodable_or_blank_candidates_are_skipped_not_fatal() -> None:
    black = np.zeros((36, 64, 3), dtype=np.uint8)
    candidates = [(0, 0.0, None), (50, 2.0, black), (100, 4.0, _frame(3))]

    kept = select_adaptive_keyframes(candidates, policy=POLICY)

    assert [item.frame_id for item in kept] == [100]


def test_cut_segment_without_any_valid_candidate_returns_empty() -> None:
    black = np.zeros((36, 64, 3), dtype=np.uint8)

    assert select_adaptive_keyframes([(0, 0.0, None), (50, 2.0, black)], policy=POLICY) == []


def test_policy_rejects_impossible_values() -> None:
    with pytest.raises(ValueError):
        AdaptiveKeyframePolicy(
            candidate_interval_sec=0.0,
            min_change=0.15,
            shot_drift=0.35,
            max_shot_sec=12.0,
            edge_margin_frames=2,
        )


def _blurred(frame: np.ndarray) -> np.ndarray:
    # Flat frame with a soft horizontal ramp: not blank, almost no Laplacian energy.
    ramp = np.linspace(40, 200, frame.shape[1], dtype=np.float32)
    return np.broadcast_to(ramp[None, :, None], frame.shape).astype(np.uint8)


def test_blurred_candidate_is_dropped_and_counted() -> None:
    candidates = [(0, 0.0, _frame(1)), (50, 2.0, _blurred(_frame(2))), (100, 4.0, _frame(3))]
    report: dict[str, int] = {}

    kept = select_adaptive_keyframes(candidates, policy=POLICY, report=report)

    assert [item.frame_id for item in kept] == [0, 100]
    assert report["blurred_dropped"] == 1


def test_segment_where_every_candidate_is_blurred_keeps_the_sharpest() -> None:
    soft = _blurred(_frame(1))
    sharper = soft.copy()
    sharper[10:20, 10:20] = 0
    candidates = [(0, 0.0, soft), (50, 2.0, sharper)]
    policy = AdaptiveKeyframePolicy(candidate_interval_sec=2.0, min_change=0.15, shot_drift=0.35,
                                    max_shot_sec=12.0, edge_margin_frames=2, min_sharpness_ratio=1.0)
    report: dict[str, int] = {}

    kept = select_adaptive_keyframes(candidates, policy=policy, report=report)

    assert [item.frame_id for item in kept] == [50]
    assert report["blurred_dropped"] == 1


def test_shot_split_follows_vector_drift_not_dhash() -> None:
    # Four distinct frames (large dHash distance); vectors say 0-1 and 2-3 are the same shot.
    candidates = [(frame_id, frame_id / 25.0, _frame(frame_id)) for frame_id in (0, 50, 100, 150)]
    fake = np.array([[1, 0], [0.95, 0.05], [0, 1], [0.05, 0.95]], dtype=np.float32)
    calls = []

    def embed(frames):
        calls.append(len(frames))
        return fake[: len(frames)]

    policy = AdaptiveKeyframePolicy(candidate_interval_sec=2.0, min_change=0.15, shot_drift=0.25,
                                    max_shot_sec=12.0, edge_margin_frames=2, min_sharpness_ratio=0.0)
    kept = select_adaptive_keyframes(candidates, policy=policy, embed=embed)

    assert calls == [4]
    assert [(item.frame_id, item.shot_index, item.reason) for item in kept] == [
        (0, 0, "shot_start"), (50, 0, "visual_change"), (100, 1, "shot_start"), (150, 1, "visual_change")]
    assert np.allclose(kept[2].vector, fake[2])
