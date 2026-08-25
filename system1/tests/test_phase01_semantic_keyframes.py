from __future__ import annotations

from itertools import pairwise
from pathlib import Path

import numpy as np

from system1.config import load_configs
from system1.keyframes import SelectedKeyframe, semantic
from system1.keyframes.semantic import (
    TemporalProbe,
    TemporalProbePlan,
    select_supplemental_keyframes,
    temporal_probe_plan_for_shot,
)
from system1.keyframes.signals import TextSignal, difference_hash_distance

CONFIG_DIR = Path(__file__).parents[1] / "configs"


def keyframe_config() -> dict:
    return load_configs(CONFIG_DIR)["media"]["keyframe"]


def frame(value: int = 127) -> np.ndarray:
    image = np.full((32, 32, 3), value, dtype=np.uint8)
    image[::2, ::2] = 255 - value
    return image


def anchors() -> list[SelectedKeyframe]:
    return [
        SelectedKeyframe(0, "early", 10.0, False, "anchor"),
        SelectedKeyframe(10, "middle", 10.0, True, "anchor"),
        SelectedKeyframe(20, "late", 10.0, False, "anchor"),
    ]


def test_dhash_distance_is_normalized_by_exact_bit_count() -> None:
    left = np.zeros(64, dtype=bool)
    right = left.copy()
    right[:16] = True

    assert difference_hash_distance(left, right) == 0.25


def test_vfr_probe_uses_pts_time_instead_of_frame_midpoint() -> None:
    config = keyframe_config()
    config["semantic_sampling"] = {
        **config["semantic_sampling"],
        "target_max_probe_gap_seconds": 7.0,
        "max_probe_candidates_per_shot": 1,
    }
    timeline = []
    for frame_id in range(101):
        if frame_id <= 50:
            pts_time = frame_id * 0.1
        elif frame_id <= 70:
            pts_time = 5.0 + (frame_id - 50) * 0.05
        elif frame_id <= 80:
            pts_time = 6.0 + (frame_id - 70)
        else:
            pts_time = 16.0 + (frame_id - 80) * 0.1
        timeline.append({"frame_id": frame_id, "pts_time": pts_time})

    plan = temporal_probe_plan_for_shot(
        {"shot_id": "v_SH00000", "start_frame": 0, "end_frame": 101},
        timeline,
        config,
    )

    assert len(plan.probes) == 1
    assert plan.probes[0].frame_id == 74
    assert plan.probes[0].frame_id != 65


def test_probe_coverage_seeds_include_safe_interior_edges() -> None:
    config = keyframe_config()
    config["semantic_sampling"] = {
        **config["semantic_sampling"],
        "target_max_probe_gap_seconds": 1.6,
        "max_probe_candidates_per_shot": 4,
    }
    seed_points = [
        (0, 0.0),
        (5, 0.0),
        (20, 2.0),
        (50, 5.0),
        (80, 8.0),
        (95, 10.0),
        (100, 10.5),
    ]

    def pts_time(frame_id: int) -> float:
        for (left_frame, left_time), (right_frame, right_time) in pairwise(seed_points):
            if left_frame <= frame_id <= right_frame:
                ratio = (frame_id - left_frame) / max(1, right_frame - left_frame)
                return left_time + ratio * (right_time - left_time)
        raise AssertionError("frame outside fixture")

    timeline = [
        {"frame_id": frame_id, "pts_time": pts_time(frame_id)}
        for frame_id in range(101)
    ]

    plan = temporal_probe_plan_for_shot(
        {"shot_id": "v_SH00000", "start_frame": 0, "end_frame": 101},
        timeline,
        config,
    )

    assert {probe.frame_id for probe in plan.probes} == {12, 35, 65, 87}


def test_short_shot_does_not_create_unnecessary_probes() -> None:
    config = keyframe_config()
    timeline = [
        {"frame_id": frame_id, "pts_time": frame_id * 0.04} for frame_id in range(8)
    ]

    plan = temporal_probe_plan_for_shot(
        {"shot_id": "v_SH00000", "start_frame": 0, "end_frame": 8},
        timeline,
        config,
    )

    assert plan.probes == ()
    assert plan.coverage_cap_reached is False


def test_probe_cap_is_best_effort_and_reports_uncovered_gap() -> None:
    config = keyframe_config()
    config["semantic_sampling"] = {
        **config["semantic_sampling"],
        "target_max_probe_gap_seconds": 1.0,
        "max_probe_candidates_per_shot": 1,
    }
    timeline = [
        {"frame_id": frame_id, "pts_time": float(frame_id)} for frame_id in range(101)
    ]

    plan = temporal_probe_plan_for_shot(
        {"shot_id": "v_SH00000", "start_frame": 0, "end_frame": 101},
        timeline,
        config,
    )

    assert len(plan.probes) == 1
    assert plan.coverage_cap_reached is True
    assert plan.remaining_max_probe_gap_seconds > 1.0


def test_unsplittable_vfr_gap_does_not_block_other_probe_intervals() -> None:
    config = keyframe_config()
    config["semantic_sampling"] = {
        **config["semantic_sampling"],
        "target_max_probe_gap_seconds": 2.0,
        "max_probe_candidates_per_shot": 3,
    }
    timeline = [
        {
            "frame_id": frame_id,
            "pts_time": (
                frame_id * 0.1 if frame_id <= 30 else 20.0 + (frame_id - 31) * 0.1
            ),
        }
        for frame_id in range(101)
    ]

    plan = temporal_probe_plan_for_shot(
        {"shot_id": "v_SH00000", "start_frame": 0, "end_frame": 101},
        timeline,
        config,
    )

    assert {30, 31}.issubset({probe.frame_id for probe in plan.probes})
    assert any(60 <= probe.frame_id <= 70 for probe in plan.probes)


def test_text_disappearance_does_not_trigger_or_influence_ranking(monkeypatch) -> None:
    visual = np.zeros(64, dtype=bool)

    def signals(*, frame_id, timestamp_sec, **_kwargs):
        return semantic._FrameSignals(
            frame_id=frame_id,
            timestamp_sec=timestamp_sec,
            visual_hash=visual,
            text_signal=(
                TextSignal(True, np.array([True, False]), 2)
                if frame_id in {0, 10, 20}
                else TextSignal(False, None, 0)
            ),
            signal_errors=(),
        )

    monkeypatch.setattr(semantic, "_frame_signals", signals)
    selected, diagnostics = select_supplemental_keyframes(
        shot={"shot_id": "v_SH00000", "start_frame": 0, "end_frame": 21},
        anchors=anchors(),
        probe_plan=TemporalProbePlan((TemporalProbe(5, 5.0, 5.0),), False, 2.0),
        decoded_frames={item: frame() for item in (0, 5, 10, 20)},
        timestamp_by_frame={0: 0.0, 5: 5.0, 10: 10.0, 20: 20.0},
        config=keyframe_config(),
    )

    assert selected == []
    assert diagnostics[0]["text_present"] is False
    assert diagnostics[0]["text_change_score"] is None
    assert diagnostics[0]["text_trigger"] is False


def test_changed_text_is_kept_when_global_visual_is_identical(monkeypatch) -> None:
    visual = np.zeros(64, dtype=bool)

    def signals(*, frame_id, timestamp_sec, **_kwargs):
        signature = (
            np.array([True, False, True, False])
            if frame_id in {0, 10, 20}
            else np.array([False, True, False, True])
        )
        return semantic._FrameSignals(
            frame_id=frame_id,
            timestamp_sec=timestamp_sec,
            visual_hash=visual,
            text_signal=TextSignal(True, signature, 2),
            signal_errors=(),
        )

    monkeypatch.setattr(semantic, "_frame_signals", signals)
    selected, diagnostics = select_supplemental_keyframes(
        shot={"shot_id": "v_SH00000", "start_frame": 0, "end_frame": 21},
        anchors=anchors(),
        probe_plan=TemporalProbePlan((TemporalProbe(5, 5.0, 5.0),), False, 2.0),
        decoded_frames={item: frame() for item in (0, 5, 10, 20)},
        timestamp_by_frame={0: 0.0, 5: 5.0, 10: 10.0, 20: 20.0},
        config=keyframe_config(),
    )

    assert [(item.frame_id, item.selection_reason) for item in selected] == [
        (5, "text_change")
    ]
    assert diagnostics[0]["visual_trigger"] is False
    assert diagnostics[0]["text_trigger"] is True
    assert diagnostics[0]["triggered_signal_count"] == 1
    assert diagnostics[0]["max_triggered_signal_score"] == 1.0


def test_same_visual_and_same_text_are_deduplicated(monkeypatch) -> None:
    visual = np.zeros(64, dtype=bool)
    text = np.array([True, False, True, False])

    def signals(*, frame_id, timestamp_sec, **_kwargs):
        return semantic._FrameSignals(
            frame_id=frame_id,
            timestamp_sec=timestamp_sec,
            visual_hash=visual,
            text_signal=TextSignal(True, text, 2),
            signal_errors=(),
        )

    monkeypatch.setattr(semantic, "_frame_signals", signals)
    selected, diagnostics = select_supplemental_keyframes(
        shot={"shot_id": "v_SH00000", "start_frame": 0, "end_frame": 21},
        anchors=anchors(),
        probe_plan=TemporalProbePlan((TemporalProbe(5, 5.0, 5.0),), False, 2.0),
        decoded_frames={item: frame() for item in (0, 5, 10, 20)},
        timestamp_by_frame={0: 0.0, 5: 5.0, 10: 10.0, 20: 20.0},
        config=keyframe_config(),
    )

    assert selected == []
    assert diagnostics[0]["decision_reason"] == "no_novel_signal"
    assert diagnostics[0]["dedup_target_frame_id"] == 0


def test_two_distinct_visual_events_survive_greedy_recompute(monkeypatch) -> None:
    hashes = {
        0: np.zeros(64, dtype=bool),
        10: np.zeros(64, dtype=bool),
        20: np.zeros(64, dtype=bool),
        5: np.concatenate([np.ones(32, dtype=bool), np.zeros(32, dtype=bool)]),
        15: np.concatenate([np.zeros(32, dtype=bool), np.ones(32, dtype=bool)]),
    }

    def signals(*, frame_id, timestamp_sec, **_kwargs):
        return semantic._FrameSignals(
            frame_id=frame_id,
            timestamp_sec=timestamp_sec,
            visual_hash=hashes[frame_id],
            text_signal=TextSignal(False, None, 0),
            signal_errors=(),
        )

    monkeypatch.setattr(semantic, "_frame_signals", signals)
    selected, diagnostics = select_supplemental_keyframes(
        shot={"shot_id": "v_SH00000", "start_frame": 0, "end_frame": 21},
        anchors=anchors(),
        probe_plan=TemporalProbePlan(
            (TemporalProbe(5, 5.0, 5.0), TemporalProbe(15, 15.0, 5.0)),
            False,
            2.0,
        ),
        decoded_frames={item: frame() for item in hashes},
        timestamp_by_frame={item: float(item) for item in hashes},
        config=keyframe_config(),
    )

    assert [item.frame_id for item in selected] == [5, 15]
    assert all(item.role == "supplemental" for item in selected)
    assert sum(bool(item["keep"]) for item in diagnostics) == 2


def test_supplemental_budget_is_enforced_deterministically(monkeypatch) -> None:
    hashes = {
        0: np.zeros(64, dtype=bool),
        10: np.zeros(64, dtype=bool),
        20: np.zeros(64, dtype=bool),
        3: np.concatenate([np.ones(16, dtype=bool), np.zeros(48, dtype=bool)]),
        7: np.concatenate(
            [
                np.zeros(16, dtype=bool),
                np.ones(16, dtype=bool),
                np.zeros(32, dtype=bool),
            ]
        ),
        15: np.concatenate(
            [
                np.zeros(32, dtype=bool),
                np.ones(16, dtype=bool),
                np.zeros(16, dtype=bool),
            ]
        ),
    }

    def signals(*, frame_id, timestamp_sec, **_kwargs):
        return semantic._FrameSignals(
            frame_id=frame_id,
            timestamp_sec=timestamp_sec,
            visual_hash=hashes[frame_id],
            text_signal=TextSignal(False, None, 0),
            signal_errors=(),
        )

    monkeypatch.setattr(semantic, "_frame_signals", signals)
    selected, diagnostics = select_supplemental_keyframes(
        shot={"shot_id": "v_SH00000", "start_frame": 0, "end_frame": 21},
        anchors=anchors(),
        probe_plan=TemporalProbePlan(
            tuple(TemporalProbe(item, float(item), 5.0) for item in (3, 7, 15)),
            False,
            2.0,
        ),
        decoded_frames={item: frame() for item in hashes},
        timestamp_by_frame={item: float(item) for item in hashes},
        config=keyframe_config(),
    )

    assert len(selected) == 2
    assert (
        sum(
            item["decision_reason"] == "supplemental_budget_exhausted"
            for item in diagnostics
        )
        == 1
    )


def test_signal_analysis_errors_are_fail_safe(monkeypatch) -> None:
    def broken_visual(*_args, **_kwargs):
        raise RuntimeError("visual failed")

    def broken_text(*_args, **_kwargs):
        raise RuntimeError("text failed")

    monkeypatch.setattr(semantic, "difference_hash", broken_visual)
    monkeypatch.setattr(semantic, "text_edge_signal", broken_text)
    selected, diagnostics = select_supplemental_keyframes(
        shot={"shot_id": "v_SH00000", "start_frame": 0, "end_frame": 21},
        anchors=anchors(),
        probe_plan=TemporalProbePlan((TemporalProbe(5, 5.0, 5.0),), False, 2.0),
        decoded_frames={item: frame() for item in (0, 5, 10, 20)},
        timestamp_by_frame={0: 0.0, 5: 5.0, 10: 10.0, 20: 20.0},
        config=keyframe_config(),
    )

    assert selected == []
    assert diagnostics[0]["signal_errors"] == [
        "visual:RuntimeError",
        "text:RuntimeError",
    ]


def test_undecodable_probe_is_dropped_without_failing_the_shot() -> None:
    selected, diagnostics = select_supplemental_keyframes(
        shot={"shot_id": "v_SH00000", "start_frame": 0, "end_frame": 21},
        anchors=anchors(),
        probe_plan=TemporalProbePlan((TemporalProbe(5, 5.0, 5.0),), False, 2.0),
        decoded_frames={item: frame() for item in (0, 10, 20)},
        timestamp_by_frame={0: 0.0, 5: 5.0, 10: 10.0, 20: 20.0},
        config=keyframe_config(),
    )

    assert selected == []
    assert diagnostics[0]["valid"] is False
    assert diagnostics[0]["decision_reason"] == "decode_failure"
