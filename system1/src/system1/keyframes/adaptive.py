"""Content-adaptive keyframe sampling (ADR 0022).

Keyframe density follows visual change instead of shot count. Candidates are
planned at a fixed time interval inside each shot, then kept only when they
differ enough from the last kept keyframe. Long shots are split into sub-shots
when content drifts or a maximum length is reached, so one-shot videos are
covered across their whole length.
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
    subshot_drift: float
    max_subshot_sec: float
    edge_margin_frames: int

    def __post_init__(self) -> None:
        if self.candidate_interval_sec <= 0 or self.max_subshot_sec <= 0:
            raise ValueError("candidate_interval_sec and max_subshot_sec must be positive")
        if not 0 < self.min_change <= self.subshot_drift <= 1:
            raise ValueError("expected 0 < min_change <= subshot_drift <= 1")
        if self.edge_margin_frames < 0:
            raise ValueError("edge_margin_frames must be non-negative")


@dataclass(frozen=True)
class AdaptiveKeyframe:
    frame_id: int
    timestamp_sec: float
    sub_shot_index: int
    reason: str  # "subshot_start" or "visual_change"


def plan_candidate_frames(
    *,
    start_frame: int,
    end_frame: int,
    pts: Sequence[float],
    policy: AdaptiveKeyframePolicy,
) -> list[int]:
    """Return candidate frame IDs for one shot `[start_frame, end_frame)`.

    `pts` holds the decoded presentation time of every frame in the video,
    indexed by frame ID. Frames within `edge_margin_frames` of a cut are
    avoided; a shot shorter than one candidate interval gets its middle frame.
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
    """Keep candidates that add visual information.

    `candidates` are `(frame_id, timestamp_sec, rgb_frame)` in time order for
    one shot. Undecodable (`None`) and blank frames are skipped. An empty
    result means the shot had no usable frame; the caller logs it.
    """

    kept: list[AdaptiveKeyframe] = []
    last_hash: np.ndarray | None = None
    subshot_hash: np.ndarray | None = None
    subshot_start = 0.0
    subshot_index = -1
    for frame_id, timestamp, frame in candidates:
        if frame is None or _is_blank(frame):
            continue
        signature = difference_hash(frame, hash_size=HASH_SIZE)
        new_subshot = (
            subshot_hash is None
            or timestamp - subshot_start >= policy.max_subshot_sec
            or difference_hash_distance(signature, subshot_hash) >= policy.subshot_drift
        )
        if new_subshot:
            subshot_index += 1
            subshot_hash = signature
            subshot_start = timestamp
            reason = "subshot_start"
        elif difference_hash_distance(signature, last_hash) >= policy.min_change:
            reason = "visual_change"
        else:
            continue
        kept.append(AdaptiveKeyframe(int(frame_id), float(timestamp), subshot_index, reason))
        last_hash = signature
    return kept


def _is_blank(frame: np.ndarray) -> bool:
    return float(np.asarray(frame, dtype=np.float32).mean(axis=-1).std()) < BLANK_LUMA_STD
