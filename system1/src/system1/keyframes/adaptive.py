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
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from system1.keyframes.signals import difference_hash, difference_hash_distance

HASH_SIZE = 8
BLANK_LUMA_STD = 4.0


@dataclass(frozen=True)
class AdaptiveKeyframePolicy:
    candidate_interval_sec: float
    min_change: float
    shot_drift: float
    max_shot_sec: float
    edge_margin_frames: int

    def __post_init__(self) -> None:
        if self.candidate_interval_sec <= 0 or self.max_shot_sec <= 0:
            raise ValueError("candidate_interval_sec and max_shot_sec must be positive")
        if not 0 < self.min_change <= self.shot_drift <= 1:
            raise ValueError("expected 0 < min_change <= shot_drift <= 1")
        if self.edge_margin_frames < 0:
            raise ValueError("edge_margin_frames must be non-negative")


@dataclass(frozen=True)
class AdaptiveKeyframe:
    frame_id: int
    timestamp_sec: float
    shot_index: int  # index of the shot inside its cut segment
    reason: str  # "shot_start" or "visual_change"


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
) -> list[AdaptiveKeyframe]:
    """Split one cut segment into shots and keep keyframes that add visual information.

    `candidates` are `(frame_id, timestamp_sec, rgb_frame)` in time order.
    Undecodable (`None`) and blank frames are skipped. An empty result means
    the segment had no usable frame; the caller logs it.
    """

    kept: list[AdaptiveKeyframe] = []
    last_hash: np.ndarray | None = None
    shot_hash: np.ndarray | None = None
    shot_start = 0.0
    shot_index = -1
    for frame_id, timestamp, frame in candidates:
        if frame is None or _is_blank(frame):
            continue
        signature = difference_hash(frame, hash_size=HASH_SIZE)
        new_shot = (
            shot_hash is None
            or timestamp - shot_start >= policy.max_shot_sec
            or difference_hash_distance(signature, shot_hash) >= policy.shot_drift
        )
        if new_shot:
            shot_index += 1
            shot_hash = signature
            shot_start = timestamp
            reason = "shot_start"
        elif difference_hash_distance(signature, last_hash) >= policy.min_change:
            reason = "visual_change"
        else:
            continue
        kept.append(AdaptiveKeyframe(int(frame_id), float(timestamp), shot_index, reason))
        last_hash = signature
    return kept


def _is_blank(frame: np.ndarray) -> bool:
    return float(np.asarray(frame, dtype=np.float32).mean(axis=-1).std()) < BLANK_LUMA_STD
