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
    subshot_drift=0.35,
    max_subshot_sec=12.0,
    edge_margin_frames=2,
)


def _timeline(frame_count: int, fps: float = 25.0) -> list[float]:
    return [index / fps for index in range(frame_count)]


def _frame(seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.integers(0, 255, size=(36, 64, 3), dtype=np.uint8)


def test_one_shot_video_gets_candidates_across_its_whole_length() -> None:
    pts = _timeline(25 * 600)  # one 10-minute shot
    frames = plan_candidate_frames(start_frame=0, end_frame=len(pts), pts=pts, policy=POLICY)

    assert len(frames) >= 290
    assert pts[frames[0]] < 2.5
    assert pts[frames[-1]] > 597.0


def test_candidates_stay_inside_the_shot_and_away_from_cuts() -> None:
    pts = _timeline(1000)
    frames = plan_candidate_frames(start_frame=200, end_frame=400, pts=pts, policy=POLICY)

    assert frames == sorted(set(frames))
    assert all(202 <= frame < 398 for frame in frames)


def test_short_shot_gets_one_middle_candidate() -> None:
    pts = _timeline(1000)
    frames = plan_candidate_frames(start_frame=100, end_frame=120, pts=pts, policy=POLICY)

    assert frames == [109]  # frames 100..119


def test_static_content_keeps_one_keyframe_per_max_subshot_length() -> None:
    still = _frame(1)
    candidates = [(frame_id, frame_id / 25.0, still) for frame_id in range(0, 25 * 60, 50)]

    kept = select_adaptive_keyframes(candidates, policy=POLICY)

    # 60 seconds of identical frames, a new sub-shot every 12 seconds.
    assert [item.sub_shot_index for item in kept] == [0, 1, 2, 3, 4]
    assert all(item.reason == "subshot_start" for item in kept)


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


def test_shot_without_any_valid_candidate_returns_empty() -> None:
    black = np.zeros((36, 64, 3), dtype=np.uint8)

    assert select_adaptive_keyframes([(0, 0.0, None), (50, 2.0, black)], policy=POLICY) == []


def test_policy_rejects_impossible_values() -> None:
    with pytest.raises(ValueError):
        AdaptiveKeyframePolicy(
            candidate_interval_sec=0.0,
            min_change=0.15,
            subshot_drift=0.35,
            max_subshot_sec=12.0,
            edge_margin_frames=2,
        )
