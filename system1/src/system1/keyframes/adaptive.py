"""Content-adaptive shots and keyframes (ADR 0022).

A shot is a run of near-identical frames. A new shot starts at a cut or when
the content drifts too far from the start of the current shot. Cuts come from
TransNetV2 as cut segments; this module splits each cut segment into shots.

Candidates are planned at a fixed time interval inside each cut segment, then
kept only when they differ enough from the last kept keyframe. A shot also
ends when it reaches a maximum length, so a video recorded in one take is
covered across its whole length.
"""

from __future__ import annotations

import bisect
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np

from system1.keyframes.signals import difference_hash, difference_hash_distance, laplacian_variance

HASH_SIZE = 8
BLANK_LUMA_STD = 4.0


@dataclass(frozen=True)
class AdaptiveKeyframePolicy:
    candidate_interval_sec: float
    min_change: float
    shot_drift: float
    max_shot_sec: float
    edge_margin_frames: int
    # A candidate sharper than this fraction of the segment median is kept; 0 disables the filter.
    min_sharpness_ratio: float = 0.3

    def __post_init__(self) -> None:
        if self.candidate_interval_sec <= 0 or self.max_shot_sec <= 0:
            raise ValueError("candidate_interval_sec and max_shot_sec must be positive")
        # min_change is a dHash distance; shot_drift is a cosine distance with
        # image vectors and a dHash distance without them.
        if not (0 < self.min_change <= 1 and 0 < self.shot_drift <= 1):
            raise ValueError("expected 0 < min_change <= 1 and 0 < shot_drift <= 1")
        if self.edge_margin_frames < 0:
            raise ValueError("edge_margin_frames must be non-negative")
        if not 0 <= self.min_sharpness_ratio <= 1:
            raise ValueError("expected 0 <= min_sharpness_ratio <= 1")


@dataclass(frozen=True)
class AdaptiveKeyframe:
    frame_id: int
    timestamp_sec: float
    shot_index: int  # index of the shot inside its cut segment
    reason: str  # "shot_start" or "visual_change"
    vector: np.ndarray | None = None  # image vector, when an embedder was given


def plan_candidate_frames(
    *,
    start_frame: int,
    end_frame: int,
    pts: Sequence[float],
    policy: AdaptiveKeyframePolicy,
) -> list[int]:
    """Return candidate frame IDs for one cut segment `[start_frame, end_frame)`.

    `pts` holds the decoded presentation time of every frame in the video,
    indexed by frame ID. Frames within `edge_margin_frames` of a cut are
    avoided; a segment shorter than one candidate interval gets its middle frame.
    """

    first = start_frame + policy.edge_margin_frames
    last = end_frame - 1 - policy.edge_margin_frames
    if last < first or float(pts[last]) - float(pts[first]) < policy.candidate_interval_sec:
        return [(start_frame + end_frame - 1) // 2]
    frames: list[int] = []
    target = float(pts[first])
    while target <= float(pts[last]):
        frame = bisect.bisect_left(pts, target, lo=first, hi=last + 1)
        frames.append(min(frame, last))
        target += policy.candidate_interval_sec
    return sorted(set(frames))


def select_adaptive_keyframes(
    candidates: Sequence[tuple[int, float, np.ndarray | None]],
    *,
    policy: AdaptiveKeyframePolicy,
    embed: Callable[[list[np.ndarray]], np.ndarray] | None = None,
    report: dict[str, int] | None = None,
) -> list[AdaptiveKeyframe]:
    """Split one cut segment into shots and keep keyframes that add visual information.

    `candidates` are `(frame_id, timestamp_sec, rgb_frame)` in time order.
    Undecodable (`None`), blank, and blurred frames are skipped; a blurred frame
    has a Laplacian variance below `min_sharpness_ratio` times the segment
    median, and the sharpest frame is kept when all are blurred. With `embed`,
    the usable frames are embedded in one call and a new shot starts when the
    cosine distance to the shot start vector exceeds `shot_drift`; without it
    the dHash distance is used. `report["blurred_dropped"]` is incremented by
    the number of blurred frames dropped. An empty result means the segment
    had no usable frame; the caller logs it.
    """

    usable = [(int(frame_id), float(timestamp), frame) for frame_id, timestamp, frame in candidates
              if frame is not None and not _is_blank(frame)]
    if usable and policy.min_sharpness_ratio > 0:
        sharpness = [laplacian_variance(frame) for _, _, frame in usable]
        floor = policy.min_sharpness_ratio * float(np.median(sharpness))
        sharp = [item for item, value in zip(usable, sharpness) if value >= floor]
        if not sharp:
            sharp = [usable[int(np.argmax(sharpness))]]
        if report is not None:
            report["blurred_dropped"] = report.get("blurred_dropped", 0) + len(usable) - len(sharp)
        usable = sharp
    vectors: list[np.ndarray | None] = [None] * len(usable)
    if embed is not None and usable:
        embedded = np.asarray(embed([frame for _, _, frame in usable]), dtype=np.float32)
        if embedded.shape[0] != len(usable):
            raise ValueError(f"embedder returned {embedded.shape[0]} vectors for {len(usable)} frames")
        vectors = list(embedded)

    kept: list[AdaptiveKeyframe] = []
    last_hash: np.ndarray | None = None
    shot_hash: np.ndarray | None = None
    shot_vector: np.ndarray | None = None
    shot_start = 0.0
    shot_index = -1
    for (frame_id, timestamp, frame), vector in zip(usable, vectors):
        signature = difference_hash(frame, hash_size=HASH_SIZE)
        if shot_hash is None or timestamp - shot_start >= policy.max_shot_sec:
            new_shot = True
        elif vector is not None:
            new_shot = _cosine_distance(vector, shot_vector) > policy.shot_drift
        else:
            new_shot = difference_hash_distance(signature, shot_hash) >= policy.shot_drift
        if new_shot:
            shot_index += 1
            shot_hash = signature
            shot_vector = vector
            shot_start = timestamp
            reason = "shot_start"
        elif difference_hash_distance(signature, last_hash) >= policy.min_change:
            reason = "visual_change"
        else:
            continue
        kept.append(AdaptiveKeyframe(frame_id, timestamp, shot_index, reason, vector))
        last_hash = signature
    return kept


def _cosine_distance(left: np.ndarray, right: np.ndarray) -> float:
    norm = float(np.linalg.norm(left) * np.linalg.norm(right))
    return 1.0 - float(np.dot(left, right)) / norm if norm > 0 else 1.0


def _is_blank(frame: np.ndarray) -> bool:
    return float(np.asarray(frame, dtype=np.float32).mean(axis=-1).std()) < BLANK_LUMA_STD
