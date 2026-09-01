from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import pairwise
from statistics import median
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
    diagnostics_schema_version: str = "scene_boundary_diagnostics_v2"
    consistency_review_round: int | None = None
    degenerate_review_triggered: bool = False
    reason: str | None = None
    confidence: float | None = None
    evidence_used: tuple[str, ...] = ()
    provider: str | None = None
    model_name: str | None = None
    model_version: str | None = None


@dataclass(frozen=True)
class ScenePartitionQuality:
    shot_count: int
    gap_count: int
    scene_count: int
    boundary_count: int
    one_shot_scene_count: int
    boundary_density: float
    one_shot_scene_rate: float
    mean_shots_per_scene: float
    median_shots_per_scene: float
    mean_scene_duration_sec: float
    median_scene_duration_sec: float
    longest_boundary_run: int
    suspicious: bool
    flags: tuple[str, ...]


@dataclass(frozen=True)
class SceneGroupingResult:
    scenes: list[dict[str, Any]]
    decisions: list[BoundaryDecision]
    initial_quality: ScenePartitionQuality
    final_quality: ScenePartitionQuality
    consistency_review_rounds_run: int
    degenerate_review_triggered: bool
    degenerate_review_rounds_run: int


class ScenePartitionQualityError(RuntimeError):
    """Terminal semantic-quality failure for a candidate scene partition."""

    def __init__(self, *, video_id: str, details: Mapping[str, Any]) -> None:
        final = details["final"]
        super().__init__(
            "Scene partition remains suspicious after bounded semantic re-review: "
            f"video={video_id}, shots={final['shot_count']}, "
            f"scenes={final['scene_count']}, "
            f"boundary_density={final['boundary_density']:.3f}, "
            f"one_shot_scene_rate={final['one_shot_scene_rate']:.3f}"
        )
        self.details = dict(details)


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
) -> SceneGroupingResult:
    if not shots:
        raise ValueError("Scene grouping requires at least one shot")
    _validate_ordered_shots(shots, video_id)
    if len(evidence) != len(shots):
        raise ValueError("Scene evidence must have exactly one item per shot")
    if len(shots) == 1:
        scenes = partition_scenes(video_id=video_id, shots=shots, decisions=[])
        quality = assess_partition_quality(
            shots=shots,
            scenes=scenes,
            decisions=(),
            policy=config["quality_guard"],
        )
        return SceneGroupingResult(
            scenes=scenes,
            decisions=[],
            initial_quality=quality,
            final_quality=quality,
            consistency_review_rounds_run=0,
            degenerate_review_triggered=False,
            degenerate_review_rounds_run=0,
        )

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

    consistency_rounds, consistency_round_by_gap = _run_consistency_reviews(
        shots=shots,
        evidence=evidence,
        judge=judge,
        config=config,
        gap_ids=gap_ids,
        votes=votes,
        provisional=provisional,
        routes=routes,
    )

    initial_decisions = _build_decisions(
        judge=judge,
        gap_ids=gap_ids,
        votes=votes,
        provisional=provisional,
        routes=routes,
        scores=scores,
        consistency_round_by_gap=consistency_round_by_gap,
        degenerate_reviewed=set(),
    )
    initial_scenes = partition_scenes(
        video_id=video_id,
        shots=shots,
        decisions=initial_decisions,
    )
    quality_policy = config["quality_guard"]
    initial_quality = assess_partition_quality(
        shots=shots,
        scenes=initial_scenes,
        decisions=initial_decisions,
        policy=quality_policy,
    )

    degenerate_reviewed: set[int] = set()
    degenerate_rounds = 0
    degenerate_policy = quality_policy["degenerate_review"]
    if (
        initial_quality.suspicious
        and bool(quality_policy["enabled"])
        and bool(degenerate_policy["enabled"])
    ):
        degenerate_rounds, degenerate_reviewed = _run_degenerate_reviews(
            shots=shots,
            evidence=evidence,
            judge=judge,
            policy=degenerate_policy,
            gap_ids=gap_ids,
            provisional=provisional,
            routes=routes,
            quality_policy=quality_policy,
        )

    decisions = _build_decisions(
        judge=judge,
        gap_ids=gap_ids,
        votes=votes,
        provisional=provisional,
        routes=routes,
        scores=scores,
        consistency_round_by_gap=consistency_round_by_gap,
        degenerate_reviewed=degenerate_reviewed,
    )
    scenes = partition_scenes(video_id=video_id, shots=shots, decisions=decisions)
    final_quality = assess_partition_quality(
        shots=shots,
        scenes=scenes,
        decisions=decisions,
        policy=quality_policy,
    )
    return SceneGroupingResult(
        scenes=scenes,
        decisions=decisions,
        initial_quality=initial_quality,
        final_quality=final_quality,
        consistency_review_rounds_run=consistency_rounds,
        degenerate_review_triggered=bool(degenerate_reviewed),
        degenerate_review_rounds_run=degenerate_rounds,
    )


def assess_partition_quality(
    *,
    shots: Sequence[Mapping[str, Any]],
    scenes: Sequence[Mapping[str, Any]],
    decisions: Sequence[BoundaryDecision],
    policy: Mapping[str, Any],
) -> ScenePartitionQuality:
    shot_count = len(shots)
    gap_count = max(0, shot_count - 1)
    boundary_labels = [bool(decision.is_boundary) for decision in decisions]
    boundary_count = sum(boundary_labels)
    scene_count = len(scenes)
    scene_sizes = [int(scene["shot_count"]) for scene in scenes]
    one_shot_scene_count = sum(size == 1 for size in scene_sizes)
    boundary_density = boundary_count / gap_count if gap_count else 0.0
    one_shot_scene_rate = (
        one_shot_scene_count / scene_count if scene_count else 0.0
    )
    mean_shots_per_scene = shot_count / scene_count if scene_count else 0.0
    median_shots_per_scene = float(median(scene_sizes)) if scene_sizes else 0.0
    scene_durations = [float(scene["duration_sec"]) for scene in scenes]
    mean_scene_duration_sec = (
        sum(scene_durations) / scene_count if scene_count else 0.0
    )
    median_scene_duration_sec = (
        float(median(scene_durations)) if scene_durations else 0.0
    )
    longest_boundary_run = _longest_true_run(boundary_labels)

    flags: list[str] = []
    suspicious = False
    if bool(policy["enabled"]) and shot_count >= int(policy["min_shot_count"]):
        all_boundaries = gap_count > 0 and boundary_count == gap_count
        extreme_density = boundary_density >= float(
            policy["suspicious_boundary_density"]
        )
        extreme_one_shot_rate = one_shot_scene_rate >= float(
            policy["suspicious_one_shot_scene_rate"]
        )
        if all_boundaries:
            flags.append("all_gaps_are_boundaries")
        if extreme_density:
            flags.append("extreme_boundary_density")
        if extreme_one_shot_rate:
            flags.append("extreme_one_shot_scene_rate")
        suspicious = all_boundaries or (extreme_density and extreme_one_shot_rate)

    return ScenePartitionQuality(
        shot_count=shot_count,
        gap_count=gap_count,
        scene_count=scene_count,
        boundary_count=boundary_count,
        one_shot_scene_count=one_shot_scene_count,
        boundary_density=boundary_density,
        one_shot_scene_rate=one_shot_scene_rate,
        mean_shots_per_scene=mean_shots_per_scene,
        median_shots_per_scene=median_shots_per_scene,
        mean_scene_duration_sec=mean_scene_duration_sec,
        median_scene_duration_sec=median_scene_duration_sec,
        longest_boundary_run=longest_boundary_run,
        suspicious=suspicious,
        flags=tuple(flags),
    )


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
                "grouping_version": "scene_grouping_v2",
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


def _diagnostics_for_gap(judge: SceneBoundaryJudge, gap_id: str) -> dict[str, Any]:
    diagnostics_for = getattr(judge, "diagnostics_for", None)
    if not callable(diagnostics_for):
        return {}
    value = diagnostics_for(gap_id)
    if not isinstance(value, Mapping):
        return {}
    reason = value.get("reason")
    confidence = value.get("confidence")
    evidence_used = value.get("evidence_used", ())
    if not isinstance(evidence_used, (list, tuple)):
        evidence_used = ()
    return {
        "reason": str(reason) if reason is not None else None,
        "confidence": float(confidence) if isinstance(confidence, (int, float)) else None,
        "evidence_used": tuple(str(item) for item in evidence_used),
        "provider": _optional_string(value.get("provider")),
        "model_name": _optional_string(value.get("model_name")),
        "model_version": _optional_string(value.get("model_version")),
    }


def _build_decisions(
    *,
    judge: SceneBoundaryJudge,
    gap_ids: tuple[str, ...],
    votes: Mapping[int, Sequence[BoundaryVote]],
    provisional: Mapping[int, bool],
    routes: Mapping[int, str],
    scores: Mapping[int, float],
    consistency_round_by_gap: Mapping[int, int],
    degenerate_reviewed: set[int],
) -> list[BoundaryDecision]:
    decisions: list[BoundaryDecision] = []
    for gap_index, gap_id in enumerate(gap_ids):
        gap_votes = votes[gap_index]
        true_weight = sum(vote.weight for vote in gap_votes if vote.is_boundary)
        false_weight = sum(vote.weight for vote in gap_votes if not vote.is_boundary)
        diagnostics = _diagnostics_for_gap(judge, gap_id)
        decisions.append(
            BoundaryDecision(
                gap_index=gap_index,
                after_shot_id=gap_id,
                is_boundary=provisional[gap_index],
                primary_boundary_score=scores[gap_index],
                vote_count=len(gap_votes),
                true_vote_weight=true_weight,
                false_vote_weight=false_weight,
                review_route=routes[gap_index],
                consistency_review_triggered=(
                    gap_index in consistency_round_by_gap
                ),
                consistency_review_round=consistency_round_by_gap.get(gap_index),
                degenerate_review_triggered=gap_index in degenerate_reviewed,
                reason=diagnostics.get("reason"),
                confidence=diagnostics.get("confidence"),
                evidence_used=tuple(diagnostics.get("evidence_used", ())),
                provider=diagnostics.get("provider"),
                model_name=diagnostics.get("model_name"),
                model_version=diagnostics.get("model_version"),
            )
        )
    return decisions


def _run_consistency_reviews(
    *,
    shots: Sequence[Mapping[str, Any]],
    evidence: Sequence[Mapping[str, Any]],
    judge: SceneBoundaryJudge,
    config: Mapping[str, Any],
    gap_ids: tuple[str, ...],
    votes: Mapping[int, Sequence[BoundaryVote]],
    provisional: dict[int, bool],
    routes: dict[int, str],
) -> tuple[int, dict[int, int]]:
    rounds_run = 0
    reviewed_round: dict[int, int] = {}
    for round_index in range(1, int(config["max_consistency_review_rounds"]) + 1):
        triggered = _consistency_trigger_gaps(provisional, votes, config)
        if not triggered:
            break
        before = dict(provisional)
        merged_regions = _merge_review_regions(
            triggered,
            gap_count=len(gap_ids),
            padding=int(config["context_shots_each_side"]),
        )
        review_regions = _split_review_regions(
            merged_regions,
            max_focus_gaps=int(config["focus_gap_count"]),
        )
        for region in review_regions:
            region_ids = tuple(gap_ids[index] for index in region)
            context_start = max(
                0,
                region[0] - int(config["context_shots_each_side"]),
            )
            context_end = min(
                len(shots),
                region[-1] + 2 + int(config["context_shots_each_side"]),
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
                reviewed_round[gap_index] = round_index
        rounds_run = round_index
        if provisional == before:
            break
    return rounds_run, reviewed_round


def _split_review_regions(
    regions: Sequence[Sequence[int]],
    *,
    max_focus_gaps: int,
) -> list[tuple[int, ...]]:
    if max_focus_gaps < 1:
        raise ValueError("max_focus_gaps must be positive")
    chunks: list[tuple[int, ...]] = []
    for region in regions:
        ordered = tuple(region)
        chunks.extend(
            ordered[start : start + max_focus_gaps]
            for start in range(0, len(ordered), max_focus_gaps)
        )
    return chunks


def _run_degenerate_reviews(
    *,
    shots: Sequence[Mapping[str, Any]],
    evidence: Sequence[Mapping[str, Any]],
    judge: SceneBoundaryJudge,
    policy: Mapping[str, Any],
    gap_ids: tuple[str, ...],
    provisional: dict[int, bool],
    routes: dict[int, str],
    quality_policy: Mapping[str, Any],
) -> tuple[int, set[int]]:
    reviewed: set[int] = set()
    rounds_run = 0
    for round_index in range(1, int(policy["max_rounds"]) + 1):
        before = dict(provisional)
        windows = plan_focus_windows(
            len(shots),
            focus_gap_count=int(policy["focus_gap_count"]),
            context_shots_each_side=int(policy["context_shots_each_side"]),
            stride=int(policy["focus_gap_count"]),
        )
        for window in windows:
            focus_ids = tuple(gap_ids[index] for index in window.focus_gap_indices)
            result = _validate_judgement(
                judge.judge(
                    request_kind="degenerate_review",
                    focus_gap_ids=focus_ids,
                    context=[evidence[index] for index in window.context_shot_indices],
                ),
                focus_ids,
            )
            for gap_index in window.focus_gap_indices:
                provisional[gap_index] = result[gap_ids[gap_index]]
                routes[gap_index] = "degenerate_review"
                reviewed.add(gap_index)
        rounds_run = round_index
        if provisional == before:
            break
        candidate_decisions = [
            BoundaryDecision(
                gap_index=index,
                after_shot_id=gap_ids[index],
                is_boundary=provisional[index],
                primary_boundary_score=0.0,
                vote_count=0,
                true_vote_weight=0.0,
                false_vote_weight=0.0,
                review_route=routes[index],
                consistency_review_triggered=False,
            )
            for index in range(len(gap_ids))
        ]
        candidate_scenes = partition_scenes(
            video_id=str(shots[0]["video_id"]),
            shots=shots,
            decisions=candidate_decisions,
        )
        if not assess_partition_quality(
            shots=shots,
            scenes=candidate_scenes,
            decisions=candidate_decisions,
            policy=quality_policy,
        ).suspicious:
            break
    return rounds_run, reviewed


def _longest_true_run(values: Sequence[bool]) -> int:
    longest = 0
    current = 0
    for value in values:
        current = current + 1 if value else 0
        longest = max(longest, current)
    return longest


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


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
