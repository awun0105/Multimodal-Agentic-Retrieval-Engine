from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import pairwise
from typing import Any

import numpy as np

from .builder import SelectedKeyframe, evaluate_candidate
from .signals import (
    TextSignal,
    difference_hash,
    difference_hash_distance,
    text_edge_signal,
    text_jaccard_distance,
)


@dataclass(frozen=True)
class TemporalProbe:
    frame_id: int
    target_timestamp_sec: float
    temporal_gap_sec: float


@dataclass(frozen=True)
class TemporalProbePlan:
    probes: tuple[TemporalProbe, ...]
    coverage_cap_reached: bool
    remaining_max_probe_gap_seconds: float


@dataclass(frozen=True)
class _FrameSignals:
    frame_id: int
    timestamp_sec: float
    visual_hash: np.ndarray | None
    text_signal: TextSignal | None
    signal_errors: tuple[str, ...]


@dataclass(frozen=True)
class _Candidate:
    frame_id: int
    timestamp_sec: float
    temporal_gap_sec: float
    quality_score: float
    signals: _FrameSignals


@dataclass(frozen=True)
class _Evaluation:
    visual_score: float | None
    text_score: float | None
    visual_trigger: bool
    text_trigger: bool
    dedup_target_frame_id: int | None

    @property
    def triggered_scores(self) -> tuple[float, ...]:
        values: list[float] = []
        if self.visual_trigger and self.visual_score is not None:
            values.append(self.visual_score)
        if self.text_trigger and self.text_score is not None:
            values.append(self.text_score)
        return tuple(values)


def temporal_probe_plan_for_shot(
    shot: Mapping[str, Any],
    timeline_rows: Sequence[Mapping[str, Any]],
    config: Mapping[str, Any],
) -> TemporalProbePlan:
    policy = config["semantic_sampling"]
    if not bool(policy.get("enabled", False)):
        return TemporalProbePlan((), False, 0.0)
    if str(policy.get("policy")) != "temporal_visual_text_v1":
        raise ValueError(
            f"Unsupported semantic sampling policy: {policy.get('policy')}"
        )
    rows = sorted(
        (
            {
                "frame_id": int(row["frame_id"]),
                "pts_time": float(row["pts_time"]),
            }
            for row in timeline_rows
            if int(shot["start_frame"]) <= int(row["frame_id"]) < int(shot["end_frame"])
        ),
        key=lambda row: row["frame_id"],
    )
    if not rows:
        return TemporalProbePlan((), False, 0.0)

    start = int(shot["start_frame"])
    end = int(shot["end_frame"])
    frame_span = max(0, end - start - 1)
    seed_ratios = [
        float(config["selection"]["safe_interior_start_ratio"]),
        float(config["roles"]["early"]["target_ratio"]),
        float(config["roles"]["middle"]["target_ratio"]),
        float(config["roles"]["late"]["target_ratio"]),
        float(config["selection"]["safe_interior_end_ratio"]),
    ]
    seed_rows = [
        _nearest_row_by_frame(rows, start + ratio * frame_span) for ratio in seed_ratios
    ]
    observed = {int(row["frame_id"]): float(row["pts_time"]) for row in seed_rows}
    probes: dict[int, TemporalProbe] = {}
    target_gap = float(policy["target_max_probe_gap_seconds"])
    maximum = int(policy["max_probe_candidates_per_shot"])

    while len(probes) < maximum:
        next_probe = _next_splittable_probe(observed, rows, target_gap)
        if next_probe is None:
            break
        gap, row = next_probe
        gap_seconds, _left_frame, left_time, _right_frame, right_time = gap
        target_time = (left_time + right_time) / 2.0
        frame_id = int(row["frame_id"])
        timestamp = float(row["pts_time"])
        observed[frame_id] = timestamp
        probes[frame_id] = TemporalProbe(
            frame_id=frame_id,
            target_timestamp_sec=target_time,
            temporal_gap_sec=gap_seconds,
        )

    remaining_gap = _largest_gap(observed)
    remaining_seconds = 0.0 if remaining_gap is None else float(remaining_gap[0])
    return TemporalProbePlan(
        probes=tuple(sorted(probes.values(), key=lambda item: item.frame_id)),
        coverage_cap_reached=(
            len(probes) >= maximum and remaining_seconds > target_gap
        ),
        remaining_max_probe_gap_seconds=remaining_seconds,
    )


def select_supplemental_keyframes(
    *,
    shot: Mapping[str, Any],
    anchors: Sequence[SelectedKeyframe],
    probe_plan: TemporalProbePlan,
    decoded_frames: Mapping[int, np.ndarray],
    timestamp_by_frame: Mapping[int, float],
    config: Mapping[str, Any],
) -> tuple[list[SelectedKeyframe], list[dict[str, Any]]]:
    policy = config["semantic_sampling"]
    if not bool(policy.get("enabled", False)) or not probe_plan.probes:
        return [], []
    visual_config = policy["visual_novelty"]
    text_config = policy["text_change"]
    anchor_frame_ids = {item.frame_id for item in anchors}
    references = [
        _frame_signals(
            frame_id=item.frame_id,
            timestamp_sec=float(timestamp_by_frame[item.frame_id]),
            frame=decoded_frames[item.frame_id],
            visual_config=visual_config,
            text_config=text_config,
        )
        for item in anchors
    ]
    candidates: list[_Candidate] = []
    diagnostics_by_frame: dict[int, dict[str, Any]] = {}

    for probe in probe_plan.probes:
        timestamp = float(timestamp_by_frame[probe.frame_id])
        base = {
            "frame_id": probe.frame_id,
            "shot_id": str(shot["shot_id"]),
            "candidate_source": "temporal_probe",
            "timestamp_sec": timestamp,
            "temporal_gap_sec": probe.temporal_gap_sec,
            "coverage_cap_reached": probe_plan.coverage_cap_reached,
            "remaining_max_probe_gap_seconds": (
                probe_plan.remaining_max_probe_gap_seconds
            ),
        }
        if probe.frame_id in anchor_frame_ids:
            diagnostics_by_frame[probe.frame_id] = {
                **base,
                "quality_score": None,
                "valid": False,
                "visual_novelty_score": None,
                "text_present": None,
                "text_change_score": None,
                "visual_trigger": False,
                "text_trigger": False,
                "triggered_signal_count": 0,
                "max_triggered_signal_score": None,
                "keep": False,
                "decision_reason": "actual_anchor",
                "dedup_target_frame_id": probe.frame_id,
                "distance_to_nearest_actual_anchor_sec": 0.0,
                "signal_errors": [],
            }
            continue
        quality = evaluate_candidate(
            frame_id=probe.frame_id,
            role="supplemental",
            target_frame=float(probe.frame_id),
            frame=decoded_frames.get(probe.frame_id),
            quality_config=config["quality"],
        )
        if not quality.valid:
            diagnostics_by_frame[probe.frame_id] = {
                **base,
                "quality_score": quality.quality_score,
                "valid": False,
                "visual_novelty_score": None,
                "text_present": None,
                "text_change_score": None,
                "visual_trigger": False,
                "text_trigger": False,
                "triggered_signal_count": 0,
                "max_triggered_signal_score": None,
                "keep": False,
                "decision_reason": quality.invalid_reason or "invalid_quality",
                "dedup_target_frame_id": None,
                "distance_to_nearest_actual_anchor_sec": _nearest_anchor_seconds(
                    timestamp, references
                ),
                "signal_errors": [],
            }
            continue
        signals = _frame_signals(
            frame_id=probe.frame_id,
            timestamp_sec=timestamp,
            frame=decoded_frames[probe.frame_id],
            visual_config=visual_config,
            text_config=text_config,
        )
        candidates.append(
            _Candidate(
                frame_id=probe.frame_id,
                timestamp_sec=timestamp,
                temporal_gap_sec=probe.temporal_gap_sec,
                quality_score=quality.quality_score,
                signals=signals,
            )
        )
        diagnostics_by_frame[probe.frame_id] = {
            **base,
            "quality_score": quality.quality_score,
            "valid": True,
            "visual_novelty_score": None,
            "text_present": (
                None
                if signals.text_signal is None
                else signals.text_signal.text_present
            ),
            "text_change_score": None,
            "visual_trigger": False,
            "text_trigger": False,
            "triggered_signal_count": 0,
            "max_triggered_signal_score": None,
            "keep": False,
            "decision_reason": "not_evaluated",
            "dedup_target_frame_id": None,
            "distance_to_nearest_actual_anchor_sec": _nearest_anchor_seconds(
                timestamp, references
            ),
            "signal_errors": list(signals.signal_errors),
        }

    accepted: list[_Candidate] = []
    selected: list[SelectedKeyframe] = []
    remaining = list(candidates)
    maximum = int(policy["max_supplemental_keyframes_per_shot"])
    minimum_separation = float(policy["min_supplemental_separation_seconds"])

    while remaining and len(accepted) < maximum:
        evaluated: list[tuple[_Candidate, _Evaluation]] = []
        for candidate in remaining:
            evaluation = _evaluate(
                candidate,
                references,
                visual_threshold=float(visual_config["min_hamming_ratio"]),
                text_threshold=float(text_config["min_jaccard_distance"]),
            )
            _update_diagnostic(diagnostics_by_frame[candidate.frame_id], evaluation)
            if evaluation.triggered_scores:
                evaluated.append((candidate, evaluation))
            else:
                diagnostics_by_frame[candidate.frame_id]["decision_reason"] = (
                    "no_novel_signal"
                )
        if not evaluated:
            break
        candidate, evaluation = max(
            evaluated,
            key=lambda item: (
                len(item[1].triggered_scores),
                max(item[1].triggered_scores),
                item[0].quality_score,
                _nearest_anchor_seconds(
                    item[0].timestamp_sec, references[: len(anchors)]
                ),
                -item[0].frame_id,
            ),
        )
        if any(
            abs(candidate.timestamp_sec - item.timestamp_sec) < minimum_separation
            for item in accepted
        ):
            closest = min(
                accepted,
                key=lambda item: (
                    abs(candidate.timestamp_sec - item.timestamp_sec),
                    item.frame_id,
                ),
            )
            diagnostic = diagnostics_by_frame[candidate.frame_id]
            diagnostic["decision_reason"] = "supplemental_temporal_dedup"
            diagnostic["dedup_target_frame_id"] = closest.frame_id
            remaining.remove(candidate)
            continue

        reason = _selection_reason(evaluation)
        selected.append(
            SelectedKeyframe(
                frame_id=candidate.frame_id,
                role="supplemental",
                quality_score=candidate.quality_score,
                is_representative=False,
                selection_reason=reason,
            )
        )
        diagnostic = diagnostics_by_frame[candidate.frame_id]
        diagnostic["keep"] = True
        diagnostic["decision_reason"] = reason
        accepted.append(candidate)
        references.append(candidate.signals)
        remaining.remove(candidate)

    for candidate in remaining:
        evaluation = _evaluate(
            candidate,
            references,
            visual_threshold=float(visual_config["min_hamming_ratio"]),
            text_threshold=float(text_config["min_jaccard_distance"]),
        )
        diagnostic = diagnostics_by_frame[candidate.frame_id]
        _update_diagnostic(diagnostic, evaluation)
        if evaluation.triggered_scores and len(accepted) >= maximum:
            diagnostic["decision_reason"] = "supplemental_budget_exhausted"
        elif diagnostic["decision_reason"] == "not_evaluated":
            diagnostic["decision_reason"] = "no_novel_signal"

    return (
        sorted(selected, key=lambda item: item.frame_id),
        [diagnostics_by_frame[key] for key in sorted(diagnostics_by_frame)],
    )


def _frame_signals(
    *,
    frame_id: int,
    timestamp_sec: float,
    frame: np.ndarray,
    visual_config: Mapping[str, Any],
    text_config: Mapping[str, Any],
) -> _FrameSignals:
    errors: list[str] = []
    visual_hash: np.ndarray | None = None
    text_signal: TextSignal | None = None
    try:
        visual_hash = difference_hash(frame, hash_size=int(visual_config["hash_size"]))
    except Exception as exc:  # noqa: BLE001 - supplemental signals are fail-safe
        errors.append(f"visual:{type(exc).__name__}")
    try:
        text_signal = text_edge_signal(frame, text_config)
    except Exception as exc:  # noqa: BLE001 - supplemental signals are fail-safe
        errors.append(f"text:{type(exc).__name__}")
    return _FrameSignals(
        frame_id=frame_id,
        timestamp_sec=timestamp_sec,
        visual_hash=visual_hash,
        text_signal=text_signal,
        signal_errors=tuple(errors),
    )


def _evaluate(
    candidate: _Candidate,
    references: Sequence[_FrameSignals],
    *,
    visual_threshold: float,
    text_threshold: float,
) -> _Evaluation:
    visual_pairs = [
        (
            difference_hash_distance(
                candidate.signals.visual_hash, reference.visual_hash
            ),
            reference.frame_id,
        )
        for reference in references
        if candidate.signals.visual_hash is not None
        and reference.visual_hash is not None
    ]
    visual_score = min((value for value, _frame_id in visual_pairs), default=None)
    visual_trigger = visual_score is not None and visual_score >= visual_threshold

    text_pairs: list[tuple[float, int]] = []
    candidate_text = candidate.signals.text_signal
    if candidate_text is not None and candidate_text.text_present:
        for reference in references:
            reference_text = reference.text_signal
            if reference_text is None:
                continue
            if not reference_text.text_present:
                text_pairs.append((1.0, reference.frame_id))
            elif (
                candidate_text.signature is not None
                and reference_text.signature is not None
            ):
                text_pairs.append(
                    (
                        text_jaccard_distance(
                            candidate_text.signature, reference_text.signature
                        ),
                        reference.frame_id,
                    )
                )
    text_score = min((value for value, _frame_id in text_pairs), default=None)
    text_trigger = text_score is not None and text_score >= text_threshold

    closest_pairs = [
        (value, frame_id) for value, frame_id in visual_pairs
    ] or text_pairs
    dedup_target = (
        min(closest_pairs, key=lambda item: (item[0], item[1]))[1]
        if closest_pairs
        else None
    )
    return _Evaluation(
        visual_score=visual_score,
        text_score=text_score,
        visual_trigger=visual_trigger,
        text_trigger=text_trigger,
        dedup_target_frame_id=dedup_target,
    )


def _update_diagnostic(diagnostic: dict[str, Any], evaluation: _Evaluation) -> None:
    diagnostic["visual_novelty_score"] = evaluation.visual_score
    diagnostic["text_change_score"] = evaluation.text_score
    diagnostic["visual_trigger"] = evaluation.visual_trigger
    diagnostic["text_trigger"] = evaluation.text_trigger
    diagnostic["triggered_signal_count"] = len(evaluation.triggered_scores)
    diagnostic["max_triggered_signal_score"] = (
        max(evaluation.triggered_scores) if evaluation.triggered_scores else None
    )
    diagnostic["dedup_target_frame_id"] = evaluation.dedup_target_frame_id


def _selection_reason(evaluation: _Evaluation) -> str:
    if evaluation.visual_trigger and evaluation.text_trigger:
        return "visual_and_text_novelty"
    if evaluation.text_trigger:
        return "text_change"
    return "visual_novelty"


def _nearest_anchor_seconds(
    timestamp_sec: float, anchors: Sequence[_FrameSignals]
) -> float:
    return min(
        (abs(timestamp_sec - anchor.timestamp_sec) for anchor in anchors),
        default=0.0,
    )


def _nearest_row_by_frame(
    rows: Sequence[Mapping[str, Any]], target_frame: float
) -> Mapping[str, Any]:
    return min(
        rows,
        key=lambda row: (
            abs(float(row["frame_id"]) - target_frame),
            int(row["frame_id"]),
        ),
    )


def _nearest_row_by_time(
    rows: Sequence[Mapping[str, Any]], target_time: float
) -> Mapping[str, Any]:
    return min(
        rows,
        key=lambda row: (
            abs(float(row["pts_time"]) - target_time),
            int(row["frame_id"]),
        ),
    )


def _largest_gap(
    observed: Mapping[int, float],
) -> tuple[float, int, float, int, float] | None:
    gaps = _ordered_gaps(observed)
    return gaps[0] if gaps else None


def _next_splittable_probe(
    observed: Mapping[int, float],
    rows: Sequence[Mapping[str, Any]],
    target_gap: float,
) -> tuple[tuple[float, int, float, int, float], Mapping[str, Any]] | None:
    for gap in _ordered_gaps(observed):
        gap_seconds, _left_frame, left_time, _right_frame, right_time = gap
        if gap_seconds <= target_gap:
            return None
        row = _nearest_row_by_time(rows, (left_time + right_time) / 2.0)
        if int(row["frame_id"]) not in observed:
            return gap, row
    return None


def _ordered_gaps(
    observed: Mapping[int, float],
) -> list[tuple[float, int, float, int, float]]:
    ordered = sorted(observed.items(), key=lambda item: (item[1], item[0]))
    if len(ordered) < 2:
        return []
    gaps = [
        (right_time - left_time, left_frame, left_time, right_frame, right_time)
        for (left_frame, left_time), (right_frame, right_time) in pairwise(ordered)
    ]
    return sorted(
        gaps,
        key=lambda item: (item[0], -item[2], -item[1]),
        reverse=True,
    )
