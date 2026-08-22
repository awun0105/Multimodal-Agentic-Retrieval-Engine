from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import pairwise
from typing import Any, Protocol


@dataclass(frozen=True)
class FocusWindow:
    focus_gap_indices: tuple[int, ...]
    context_shot_indices: tuple[int, ...]


@dataclass(frozen=True)
class BoundaryVote:
    gap_index: int
    is_boundary: bool
    weight: float
    window_index: int


@dataclass(frozen=True)
class BoundaryDecision:
    gap_index: int
    after_shot_id: str
    is_boundary: bool
    primary_boundary_score: float
    vote_count: int
    true_vote_weight: float
    false_vote_weight: float
    review_route: str
    consistency_review_triggered: bool


class SceneBoundaryJudge(Protocol):
    def judge(
        self,
        *,
        request_kind: str,
        focus_gap_ids: tuple[str, ...],
        context: Sequence[Mapping[str, Any]],
    ) -> Mapping[str, bool]: ...


def plan_focus_windows(
    shot_count: int,
    *,
    focus_gap_count: int = 8,
    context_shots_each_side: int = 4,
    stride: int = 6,
) -> list[FocusWindow]:
    gap_count = max(0, shot_count - 1)
    if gap_count == 0:
        return []
    if focus_gap_count < 1 or stride < 1:
        raise ValueError("focus_gap_count and stride must be positive")
    starts = list(range(0, gap_count, stride))
    windows: list[FocusWindow] = []
    covered: set[int] = set()
    for start in starts:
        end = min(gap_count, start + focus_gap_count)
        focus = tuple(range(start, end))
        if not focus:
            continue
        context_start = max(0, start - context_shots_each_side)
        context_end = min(shot_count, end + 1 + context_shots_each_side)
        windows.append(FocusWindow(focus, tuple(range(context_start, context_end))))
        covered.update(focus)
        if end == gap_count:
            break
    missing = sorted(set(range(gap_count)) - covered)
    if missing:
        raise ValueError(f"Focus-window planner missed gap indices: {missing}")
    return windows


def vote_weight(position: int, gap_count: int) -> float:
    depth = min(position, gap_count - 1 - position)
    maximum_depth = max(1, (gap_count - 1) // 2)
    return 1.0 + depth / maximum_depth


def group_scenes(
    *,
    video_id: str,
    shots: Sequence[Mapping[str, Any]],
    evidence: Sequence[Mapping[str, Any]],
    judge: SceneBoundaryJudge,
    config: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], list[BoundaryDecision]]:
    if not shots:
        raise ValueError("Scene grouping requires at least one shot")
    _validate_ordered_shots(shots, video_id)
    if len(evidence) != len(shots):
        raise ValueError("Scene evidence must have exactly one item per shot")
    if len(shots) == 1:
        scenes = partition_scenes(video_id=video_id, shots=shots, decisions=[])
        return scenes, []

    windows = plan_focus_windows(
        len(shots),
        focus_gap_count=int(config["focus_gap_count"]),
        context_shots_each_side=int(config["context_shots_each_side"]),
        stride=int(config["stride"]),
    )
    gap_ids = tuple(str(shot["shot_id"]) for shot in shots[:-1])
    votes: dict[int, list[BoundaryVote]] = {index: [] for index in range(len(gap_ids))}
    for window_index, window in enumerate(windows):
        focus_ids = tuple(gap_ids[index] for index in window.focus_gap_indices)
        result = _validate_judgement(
            judge.judge(
                request_kind="primary",
                focus_gap_ids=focus_ids,
                context=[evidence[index] for index in window.context_shot_indices],
            ),
            focus_ids,
        )
        for position, gap_index in enumerate(window.focus_gap_indices):
            votes[gap_index].append(
                BoundaryVote(
                    gap_index=gap_index,
                    is_boundary=result[gap_ids[gap_index]],
                    weight=vote_weight(position, len(window.focus_gap_indices)),
                    window_index=window_index,
                )
            )

    provisional: dict[int, bool] = {}
    routes: dict[int, str] = {}
    scores: dict[int, float] = {}
    for gap_index, gap_votes in votes.items():
        if not gap_votes:
            raise ValueError(f"No primary judgement for gap {gap_ids[gap_index]}")
        total = sum(vote.weight for vote in gap_votes)
        score = sum(vote.weight for vote in gap_votes if vote.is_boundary) / total
        scores[gap_index] = score
        if score >= float(config["boundary_threshold"]):
            provisional[gap_index] = True
            routes[gap_index] = "primary"
        elif score <= float(config["non_boundary_threshold"]):
            provisional[gap_index] = False
            routes[gap_index] = "primary"
        else:
            context_indices = _focused_context_indices(
                gap_index,
                shot_count=len(shots),
                each_side=int(config["context_shots_each_side"]),
            )
            focused = _validate_judgement(
                judge.judge(
                    request_kind="focused_review",
                    focus_gap_ids=(gap_ids[gap_index],),
                    context=[evidence[index] for index in context_indices],
                ),
                (gap_ids[gap_index],),
            )
            provisional[gap_index] = focused[gap_ids[gap_index]]
            routes[gap_index] = "focused_review"

    triggered = _consistency_trigger_gaps(provisional, votes, config)
    reviewed: set[int] = set()
    if triggered and int(config["max_consistency_review_rounds"]) > 0:
        for region in _merge_review_regions(
            triggered,
            gap_count=len(gap_ids),
            padding=int(config["context_shots_each_side"]),
        ):
            region_ids = tuple(gap_ids[index] for index in region)
            context_start = max(0, region[0] - int(config["context_shots_each_side"]))
            context_end = min(
                len(shots), region[-1] + 2 + int(config["context_shots_each_side"])
            )
            result = _validate_judgement(
                judge.judge(
                    request_kind="consistency_review",
                    focus_gap_ids=region_ids,
                    context=evidence[context_start:context_end],
                ),
                region_ids,
            )
            for gap_index in region:
                provisional[gap_index] = result[gap_ids[gap_index]]
                routes[gap_index] = "consistency_review"
                reviewed.add(gap_index)

    decisions: list[BoundaryDecision] = []
    for gap_index in range(len(gap_ids)):
        gap_votes = votes[gap_index]
        true_weight = sum(vote.weight for vote in gap_votes if vote.is_boundary)
        false_weight = sum(vote.weight for vote in gap_votes if not vote.is_boundary)
        decisions.append(
            BoundaryDecision(
                gap_index=gap_index,
                after_shot_id=gap_ids[gap_index],
                is_boundary=provisional[gap_index],
                primary_boundary_score=scores[gap_index],
                vote_count=len(gap_votes),
                true_vote_weight=true_weight,
                false_vote_weight=false_weight,
                review_route=routes[gap_index],
                consistency_review_triggered=gap_index in reviewed,
            )
        )
    return partition_scenes(video_id=video_id, shots=shots, decisions=decisions), decisions


def partition_scenes(
    *,
    video_id: str,
    shots: Sequence[Mapping[str, Any]],
    decisions: Sequence[BoundaryDecision],
) -> list[dict[str, Any]]:
    boundaries = {decision.gap_index for decision in decisions if decision.is_boundary}
    ranges: list[tuple[int, int]] = []
    start = 0
    for gap_index in range(len(shots) - 1):
        if gap_index in boundaries:
            ranges.append((start, gap_index))
            start = gap_index + 1
    ranges.append((start, len(shots) - 1))
    scenes: list[dict[str, Any]] = []
    for scene_index, (start_index, end_index) in enumerate(ranges):
        first = shots[start_index]
        last = shots[end_index]
        start_frame = int(first["start_frame"])
        end_frame = int(last["end_frame"])
        start_sec = float(first["start_sec"])
        end_sec = float(last["end_sec"])
        scenes.append(
            {
                "scene_id": f"{video_id}_SC{scene_index:05d}",
                "video_id": video_id,
                "scene_index": scene_index,
                "start_shot_id": str(first["shot_id"]),
                "end_shot_id": str(last["shot_id"]),
                "start_frame": start_frame,
                "end_frame": end_frame,
                "start_sec": start_sec,
                "end_sec": end_sec,
                "duration_sec": max(0.0, end_sec - start_sec),
                "frame_count": end_frame - start_frame,
                "shot_count": end_index - start_index + 1,
                "keyframe_count": 0,
                "scene_type": "semantic",
                "grouping_method": "multimodal_context_focus",
                "grouping_version": "scene_grouping_v1",
                "confidence": None,
                "boundary_convention": "[start_frame, end_frame)",
                "status": "pass",
            }
        )
    _validate_partition(shots, scenes)
    return scenes


def _validate_judgement(
    result: Mapping[str, bool], expected_gap_ids: tuple[str, ...]
) -> dict[str, bool]:
    if set(result) != set(expected_gap_ids):
        raise ValueError(
            f"Scene judgement gap set mismatch: expected={expected_gap_ids}, got={tuple(result)}"
        )
    normalized: dict[str, bool] = {}
    for gap_id in expected_gap_ids:
        value = result[gap_id]
        if type(value) is not bool:
            raise ValueError(f"Scene judgement must be Boolean for gap {gap_id}")
        normalized[gap_id] = value
    return normalized


def _focused_context_indices(gap_index: int, *, shot_count: int, each_side: int) -> range:
    return range(max(0, gap_index - each_side), min(shot_count, gap_index + 2 + each_side))


def _consistency_trigger_gaps(
    provisional: Mapping[int, bool],
    votes: Mapping[int, Sequence[BoundaryVote]],
    config: Mapping[str, Any],
) -> set[int]:
    boundaries = sorted(index for index, value in provisional.items() if value)
    triggered: set[int] = set()
    # Adjacent boundaries make the shot between them a one-shot scene.
    for left, right in pairwise(boundaries):
        if right == left + 1:
            triggered.update((left, right))
    window = int(config["dense_boundary_gap_window"])
    minimum = int(config["dense_boundary_count"])
    gap_count = len(provisional)
    for start in range(max(1, gap_count - window + 1)):
        region = range(start, min(gap_count, start + window))
        found = [index for index in region if provisional[index]]
        if len(found) >= minimum:
            triggered.update(region)
    minimum_votes = int(config["strong_disagreement_min_votes"])
    for gap_index, gap_votes in votes.items():
        labels = {vote.is_boundary for vote in gap_votes}
        if len(gap_votes) >= minimum_votes and labels == {False, True}:
            triggered.add(gap_index)
    return triggered


def _merge_review_regions(
    triggered: set[int], *, gap_count: int, padding: int
) -> list[tuple[int, ...]]:
    intervals = [
        (max(0, index - padding), min(gap_count - 1, index + padding))
        for index in sorted(triggered)
    ]
    merged: list[list[int]] = []
    for start, end in intervals:
        if not merged or start > merged[-1][1] + 1:
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)
    return [tuple(range(start, end + 1)) for start, end in merged]


def _validate_ordered_shots(shots: Sequence[Mapping[str, Any]], video_id: str) -> None:
    expected_start = int(shots[0]["start_frame"])
    for index, shot in enumerate(shots):
        if str(shot["video_id"]) != video_id:
            raise ValueError("Shot video_id mismatch")
        if int(shot["shot_index"]) != index:
            raise ValueError("Shots are not in canonical index order")
        if int(shot["start_frame"]) != expected_start:
            raise ValueError("Shots are not contiguous")
        expected_start = int(shot["end_frame"])


def _validate_partition(
    shots: Sequence[Mapping[str, Any]], scenes: Sequence[Mapping[str, Any]]
) -> None:
    covered = sum(int(scene["shot_count"]) for scene in scenes)
    if covered != len(shots):
        raise ValueError("Scene partition does not cover every shot exactly once")
    for previous, current in pairwise(scenes):
        if int(previous["end_frame"]) != int(current["start_frame"]):
            raise ValueError("Scene partition has a frame gap or overlap")
