from __future__ import annotations

from itertools import pairwise
from pathlib import Path

import numpy as np
import pytest

from system1.config import load_configs
from system1.keyframes import (
    SelectedKeyframe,
    candidate_frame_ids_for_shot,
    select_keyframes_for_shot,
    semantic,
)
from system1.keyframes.semantic import (
    TemporalProbe,
    TemporalProbePlan,
    select_supplemental_keyframes,
    temporal_probe_plan_for_shot,
)
from system1.keyframes.signals import (
    TextSignal,
    difference_hash_distance,
    text_jaccard_distance,
)
from system1.phase01 import production

CONFIG_DIR = Path(__file__).parents[1] / "configs"


def keyframe_config() -> dict:
    return load_configs(CONFIG_DIR)["media"]["keyframe"]


def frame(value: int = 127) -> np.ndarray:
    image = np.full((32, 32, 3), value, dtype=np.uint8)
    image[::2, ::2] = 255 - value
    return image


def checkerboard(size: int = 64) -> np.ndarray:
    grid = np.indices((size, size)).sum(axis=0) % 2
    return np.repeat((grid * 255).astype(np.uint8)[:, :, None], 3, axis=2)


def anchors() -> list[SelectedKeyframe]:
    return [
        SelectedKeyframe(0, "early", 10.0, False, "anchor"),
        SelectedKeyframe(10, "middle", 10.0, True, "anchor"),
        SelectedKeyframe(20, "late", 10.0, False, "anchor"),
    ]


def anchors_for_long_shot() -> list[SelectedKeyframe]:
    return [
        SelectedKeyframe(20, "early", 10.0, False, "anchor"),
        SelectedKeyframe(50, "middle", 10.0, True, "anchor"),
        SelectedKeyframe(80, "late", 10.0, False, "anchor"),
    ]


def test_dhash_distance_is_normalized_by_exact_bit_count() -> None:
    left = np.zeros(64, dtype=bool)
    right = left.copy()
    right[:16] = True

    assert difference_hash_distance(left, right) == 0.25


def test_text_jaccard_distance_primitive() -> None:
    signature = np.array([True, True, False, False])
    overlap = np.array([True, False, True, False])
    empty = np.zeros(4, dtype=bool)

    assert text_jaccard_distance(signature, signature) == 0.0
    assert text_jaccard_distance(signature, overlap) == pytest.approx(2.0 / 3.0)
    assert text_jaccard_distance(empty, empty) == 0.0


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


def test_changed_nominal_middle_seed_can_become_supplemental(
    monkeypatch,
) -> None:
    config = keyframe_config()
    timeline = [
        {"frame_id": frame_id, "pts_time": frame_id * 0.2} for frame_id in range(101)
    ]
    shot = {"shot_id": "v_SH00000", "start_frame": 0, "end_frame": 101}
    plan = temporal_probe_plan_for_shot(shot, timeline, config)
    candidate_ids = {
        frame_id
        for role_ids in candidate_frame_ids_for_shot(shot, config).values()
        for frame_id in role_ids
    } | {item.frame_id for item in plan.semantic_candidates}
    decoded = {frame_id: frame(100) for frame_id in candidate_ids}
    decoded[45] = checkerboard()
    decoded[50] = np.full((64, 64, 3), 100, dtype=np.uint8)
    selected_anchors, _diagnostics = select_keyframes_for_shot(shot, decoded, config)
    assert (
        next(item.frame_id for item in selected_anchors if item.role == "middle") == 45
    )

    visual = np.zeros(64, dtype=bool)
    default_text = np.array([True, False, True, False])
    changed_text = np.array([False, True, False, True])

    def signals(*, frame_id, timestamp_sec, **_kwargs):
        return semantic._FrameSignals(
            frame_id=frame_id,
            timestamp_sec=timestamp_sec,
            visual_hash=visual,
            text_signal=TextSignal(
                True,
                changed_text if frame_id == 50 else default_text,
                2,
            ),
            signal_errors=(),
        )

    monkeypatch.setattr(semantic, "_frame_signals", signals)
    supplemental, supplemental_diagnostics = select_supplemental_keyframes(
        shot=shot,
        anchors=selected_anchors,
        probe_plan=plan,
        decoded_frames=decoded,
        timestamp_by_frame={
            int(item["frame_id"]): float(item["pts_time"]) for item in timeline
        },
        config=config,
    )

    assert [(item.frame_id, item.selection_reason) for item in supplemental] == [
        (50, "text_change")
    ]
    middle_seed = next(
        item for item in supplemental_diagnostics if item["frame_id"] == 50
    )
    assert middle_seed["candidate_source"] == "coverage_seed_middle"
    assert middle_seed["keep"] is True


def test_coverage_seed_matching_actual_anchor_is_not_duplicated(monkeypatch) -> None:
    config = keyframe_config()
    timeline = [
        {"frame_id": frame_id, "pts_time": frame_id * 0.2} for frame_id in range(101)
    ]
    shot = {"shot_id": "v_SH00000", "start_frame": 0, "end_frame": 101}
    plan = temporal_probe_plan_for_shot(shot, timeline, config)
    actual_anchors = [
        SelectedKeyframe(20, "early", 10.0, False, "anchor"),
        SelectedKeyframe(50, "middle", 10.0, True, "anchor"),
        SelectedKeyframe(80, "late", 10.0, False, "anchor"),
    ]
    decoded_ids = {
        item.frame_id for item in (*actual_anchors, *plan.semantic_candidates)
    }
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
    supplemental, diagnostics = select_supplemental_keyframes(
        shot=shot,
        anchors=actual_anchors,
        probe_plan=plan,
        decoded_frames={frame_id: frame() for frame_id in decoded_ids},
        timestamp_by_frame={
            int(item["frame_id"]): float(item["pts_time"]) for item in timeline
        },
        config=config,
    )

    assert supplemental == []
    middle_rows = [item for item in diagnostics if item["frame_id"] == 50]
    assert len(middle_rows) == 1
    assert middle_rows[0]["decision_reason"] == "actual_anchor"


def test_build_keyframes_decodes_anchors_seeds_and_probes_in_one_pass(
    tmp_path: Path,
    monkeypatch,
) -> None:
    media_config = load_configs(CONFIG_DIR)["media"]
    probe_plan = TemporalProbePlan(
        probes=(TemporalProbe(35, 0.7, 1.0),),
        coverage_cap_reached=False,
        remaining_max_probe_gap_seconds=1.0,
        coverage_seeds=(TemporalProbe(5, 0.1, None, "coverage_seed_safe_start"),),
    )
    decoded_calls: list[list[set[int]]] = []

    monkeypatch.setattr(
        production,
        "candidate_frame_ids_for_shot",
        lambda *_args: {"early": (20,), "middle": (50,), "late": (80,)},
    )
    monkeypatch.setattr(
        production,
        "temporal_probe_plan_for_shot",
        lambda *_args: probe_plan,
    )

    def decode_once(_video_path, groups):
        captured = [set(group) for group in groups]
        decoded_calls.append(captured)
        return iter([{frame_id: frame() for frame_id in captured[0]}])

    monkeypatch.setattr(production, "iter_decode_frame_groups", decode_once)
    monkeypatch.setattr(
        production,
        "select_keyframes_for_shot",
        lambda *_args: (anchors_for_long_shot(), []),
    )
    monkeypatch.setattr(
        production,
        "select_supplemental_keyframes",
        lambda **_kwargs: ([], []),
    )
    monkeypatch.setattr(
        production, "write_keyframe_images", lambda *_args, **_kwargs: None
    )

    production._build_keyframes(
        video_id="v",
        video_path=tmp_path / "video.mp4",
        shots=[
            {
                "shot_id": "v_SH00000",
                "start_frame": 0,
                "end_frame": 101,
                "start_sec": 0.0,
                "end_sec": 2.02,
            }
        ],
        timeline=[
            {"frame_id": frame_id, "pts_time": frame_id * 0.02}
            for frame_id in range(101)
        ],
        output_dir=tmp_path / "output",
        config=media_config,
    )

    assert decoded_calls == [[{5, 20, 35, 50, 80}]]


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
    assert plan.coverage_seeds == ()
    assert plan.semantic_candidates == ()
    assert plan.coverage_cap_reached is False


def test_short_shot_does_not_evaluate_novel_coverage_seeds(monkeypatch) -> None:
    config = keyframe_config()
    timeline = [
        {"frame_id": frame_id, "pts_time": frame_id * 0.04} for frame_id in range(8)
    ]
    shot = {"shot_id": "v_SH00000", "start_frame": 0, "end_frame": 8}
    plan = temporal_probe_plan_for_shot(shot, timeline, config)
    actual_anchors = [
        SelectedKeyframe(1, "early", 10.0, False, "anchor"),
        SelectedKeyframe(3, "middle", 10.0, True, "anchor"),
        SelectedKeyframe(6, "late", 10.0, False, "anchor"),
    ]
    signal_calls: list[int] = []

    def maximally_novel_signals(*, frame_id, timestamp_sec, **_kwargs):
        signal_calls.append(frame_id)
        return semantic._FrameSignals(
            frame_id=frame_id,
            timestamp_sec=timestamp_sec,
            visual_hash=np.ones(64, dtype=bool),
            text_signal=TextSignal(True, np.ones(64, dtype=bool), 64),
            signal_errors=(),
        )

    monkeypatch.setattr(semantic, "_frame_signals", maximally_novel_signals)
    supplemental, diagnostics = select_supplemental_keyframes(
        shot=shot,
        anchors=actual_anchors,
        probe_plan=plan,
        decoded_frames={frame_id: frame() for frame_id in range(8)},
        timestamp_by_frame={
            int(item["frame_id"]): float(item["pts_time"]) for item in timeline
        },
        config=config,
    )

    assert supplemental == []
    assert diagnostics == []
    assert signal_calls == []


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
