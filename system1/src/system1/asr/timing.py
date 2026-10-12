from __future__ import annotations

import bisect
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FrameTimelineIndex:
    frame_ids: tuple[int, ...]
    timestamps: tuple[float, ...]


def index_frame_timeline(
    timeline: Sequence[Mapping[str, Any]],
) -> FrameTimelineIndex:
    ordered = sorted(timeline, key=lambda row: int(row["frame_id"]))
    return FrameTimelineIndex(
        frame_ids=tuple(int(row["frame_id"]) for row in ordered),
        timestamps=tuple(float(row["pts_time"]) for row in ordered),
    )


def time_range_to_frames(
    start: float,
    end: float,
    timeline: Sequence[Mapping[str, Any]] | FrameTimelineIndex,
) -> tuple[int | None, int | None]:
    if not (math.isfinite(start) and math.isfinite(end) and 0 <= start < end):
        raise ValueError("time range must be finite, non-negative, and non-empty")
    index = (
        timeline
        if isinstance(timeline, FrameTimelineIndex)
        else index_frame_timeline(timeline)
    )
    if not index.frame_ids:
        return None, None
    start_position = max(0, bisect.bisect_right(index.timestamps, start) - 1)
    end_position = bisect.bisect_left(index.timestamps, end)
    end_position = min(
        len(index.frame_ids), max(start_position + 1, end_position)
    )
    exclusive_end = (
        index.frame_ids[end_position]
        if end_position < len(index.frame_ids)
        else index.frame_ids[-1] + 1
    )
    return index.frame_ids[start_position], exclusive_end
