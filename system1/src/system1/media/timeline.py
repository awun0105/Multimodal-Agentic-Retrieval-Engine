from __future__ import annotations

import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path

import pandas as pd

from system1.media.probe import (
    VideoProbe,
    VideoProbeWithTimeline,
    probe_video,
    probe_video_with_timeline,
)

FRAME_TIMELINE_COLUMNS = ("video_id", "frame_id", "pts_time", "duration_time")
FRAME_TIMELINE_MAX_ATTEMPTS = 3
FRAME_TIMELINE_RETRY_DELAYS_SECONDS = (0.5, 1.0)
FRAME_TIMELINE_POLICIES = {"required", "if-available", "disabled"}


class FrameTimelineError(ValueError):
    pass


@dataclass(frozen=True)
class FrameTimelineBuildResult:
    probe: VideoProbe
    rows: list[dict[str, float | int | str | None]]
    attempts: int
    status: str


def normalize_frame_timeline_policy(value: str) -> str:
    normalized = value.strip().lower().replace("_", "-")
    aliases = {"optional": "if-available", "ifavailable": "if-available", "skip": "disabled"}
    normalized = aliases.get(normalized, normalized)
    if normalized not in FRAME_TIMELINE_POLICIES:
        raise FrameTimelineError(
            "frame timeline policy must be required, if-available, or disabled"
        )
    return normalized


def build_frame_timeline_with_retry(
    video_path: Path,
    *,
    video_id: str,
    policy: str,
    probe_fn: Callable[..., VideoProbeWithTimeline] = probe_video_with_timeline,
    basic_probe_fn: Callable[[Path], VideoProbe] = probe_video,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> FrameTimelineBuildResult:
    normalized_policy = normalize_frame_timeline_policy(policy)
    if normalized_policy == "disabled":
        return FrameTimelineBuildResult(
            probe=basic_probe_fn(video_path),
            rows=[],
            attempts=1,
            status="disabled",
        )

    last_result: VideoProbeWithTimeline | None = None
    last_error: Exception | None = None
    for attempt in range(1, FRAME_TIMELINE_MAX_ATTEMPTS + 1):
        candidate: VideoProbeWithTimeline | None = None
        try:
            candidate = probe_fn(video_path, video_id=video_id)
            validate_frame_timeline_rows(candidate.frame_timeline, expected_video_id=video_id)
            return FrameTimelineBuildResult(
                probe=candidate.probe,
                rows=candidate.frame_timeline,
                attempts=attempt,
                status="pass",
            )
        except Exception as exc:  # noqa: BLE001 - ffprobe is an external retry boundary
            last_error = exc
            if candidate is not None:
                last_result = candidate
            if attempt < FRAME_TIMELINE_MAX_ATTEMPTS:
                sleep_fn(FRAME_TIMELINE_RETRY_DELAYS_SECONDS[attempt - 1])

    if normalized_policy == "required":
        raise FrameTimelineError(
            f"decoded frame timeline unavailable for video_id={video_id} after "
            f"{FRAME_TIMELINE_MAX_ATTEMPTS} attempts: {last_error}"
        ) from last_error
    fallback_probe = last_result.probe if last_result is not None else basic_probe_fn(video_path)
    return FrameTimelineBuildResult(
        probe=fallback_probe,
        rows=[],
        attempts=FRAME_TIMELINE_MAX_ATTEMPTS,
        status="unavailable",
    )


def validate_frame_timeline_rows(
    rows: list[dict[str, float | int | str | None]],
    *,
    expected_video_id: str,
) -> None:
    if not rows:
        raise FrameTimelineError(f"decoded frame timeline is empty for video_id={expected_video_id}")
    frame_ids: list[int] = []
    pts_values: list[float] = []
    for index, row in enumerate(rows):
        if row.get("video_id") != expected_video_id:
            raise FrameTimelineError(
                f"frame timeline video_id mismatch at row={index}: "
                f"expected={expected_video_id} actual={row.get('video_id')}"
            )
        frame_id = row.get("frame_id")
        if not isinstance(frame_id, int) or isinstance(frame_id, bool):
            raise FrameTimelineError(f"frame timeline frame_id must be an integer at row={index}")
        pts_time = row.get("pts_time")
        if (
            not isinstance(pts_time, (int, float))
            or isinstance(pts_time, bool)
            or not math.isfinite(float(pts_time))
        ):
            raise FrameTimelineError(f"frame timeline pts_time must be numeric at row={index}")
        duration_time = row.get("duration_time")
        if duration_time is not None and (
            not isinstance(duration_time, (int, float))
            or isinstance(duration_time, bool)
            or not math.isfinite(float(duration_time))
            or float(duration_time) < 0
        ):
            raise FrameTimelineError(
                f"frame timeline duration_time must be non-negative or null at row={index}"
            )
        frame_ids.append(frame_id)
        pts_values.append(float(pts_time))
    if frame_ids != list(range(len(rows))):
        raise FrameTimelineError(
            f"frame timeline frame_id values must be contiguous from zero for video_id={expected_video_id}"
        )
    if any(current < previous for previous, current in pairwise(pts_values)):
        raise FrameTimelineError(
            f"frame timeline pts_time must be non-decreasing for video_id={expected_video_id}"
        )


def write_frame_timeline(path: Path, result: FrameTimelineBuildResult, *, video_id: str) -> int:
    if result.status != "pass":
        raise FrameTimelineError(
            f"cannot write frame timeline with status={result.status} for video_id={video_id}"
        )
    validate_frame_timeline_rows(result.rows, expected_video_id=video_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(result.rows, columns=FRAME_TIMELINE_COLUMNS).to_parquet(path, index=False)
    return len(result.rows)


def validate_frame_timeline_file(path: Path, *, expected_video_id: str) -> int:
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(path)
    frame_df = pd.read_parquet(path)
    missing = sorted(set(FRAME_TIMELINE_COLUMNS) - set(frame_df.columns))
    if missing:
        raise FrameTimelineError(f"frame timeline file is missing columns: {missing}")
    rows = frame_df.loc[:, FRAME_TIMELINE_COLUMNS].to_dict("records")
    validate_frame_timeline_rows(rows, expected_video_id=expected_video_id)
    return len(rows)
