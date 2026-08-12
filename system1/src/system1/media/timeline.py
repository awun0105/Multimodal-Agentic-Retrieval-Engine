from __future__ import annotations

import math
import os
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from itertools import pairwise
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from system1.media.probe import (
    VFR_ABS_TOLERANCE_SECONDS,
    VFR_REL_TOLERANCE,
    VideoProbe,
    VideoProbeWithTimeline,
    iter_frame_timeline_rows,
    probe_video,
    probe_video_header,
    probe_video_with_timeline,
)

FRAME_TIMELINE_COLUMNS = ("video_id", "frame_id", "pts_time", "duration_time")
FRAME_TIMELINE_MAX_ATTEMPTS = 3
FRAME_TIMELINE_RETRY_DELAYS_SECONDS = (0.5, 1.0)
FRAME_TIMELINE_POLICIES = {"required", "if-available", "disabled"}
FRAME_TIMELINE_CHUNK_ROWS = 8192
FRAME_TIMELINE_WORKER_CHOICES = {1, 2}


class FrameTimelineError(ValueError):
    pass


@dataclass(frozen=True)
class FrameTimelineBuildResult:
    probe: VideoProbe
    rows: list[dict[str, float | int | str | None]]
    attempts: int
    status: str


@dataclass(frozen=True)
class FrameTimelineFileBuildResult:
    probe: VideoProbe
    path: Path | None
    row_count: int
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


def resolve_timeline_workers(value: str | int) -> int:
    """Resolve the Colab-safe timeline worker setting to one or two processes."""
    normalized = str(value).strip().lower()
    if normalized == "auto":
        try:
            cpu_count = len(os.sched_getaffinity(0))
        except (AttributeError, OSError):
            cpu_count = os.cpu_count() or 1
        return max(1, min(2, cpu_count))
    try:
        worker_count = int(normalized)
    except ValueError as exc:
        raise FrameTimelineError("timeline workers must be auto, 1, or 2") from exc
    if worker_count not in FRAME_TIMELINE_WORKER_CHOICES:
        raise FrameTimelineError("timeline workers must be auto, 1, or 2")
    return worker_count


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


def build_frame_timeline_file_with_retry(
    video_path: Path,
    target_path: Path,
    *,
    video_id: str,
    policy: str,
    chunk_rows: int = FRAME_TIMELINE_CHUNK_ROWS,
    row_iter_fn: Callable[..., Iterable[dict[str, float | int | str | None]]] = iter_frame_timeline_rows,
    header_probe_fn: Callable[[Path], VideoProbe] = probe_video_header,
    basic_probe_fn: Callable[[Path], VideoProbe] = probe_video,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> FrameTimelineFileBuildResult:
    """Build one timeline Parquet atomically while streaming ffprobe rows."""
    normalized_policy = normalize_frame_timeline_policy(policy)
    if chunk_rows <= 0:
        raise FrameTimelineError("frame timeline chunk_rows must be positive")
    if normalized_policy == "disabled":
        return FrameTimelineFileBuildResult(
            probe=basic_probe_fn(video_path),
            path=None,
            row_count=0,
            attempts=1,
            status="disabled",
        )

    target_path.parent.mkdir(parents=True, exist_ok=True)
    partial_path = target_path.with_suffix(f"{target_path.suffix}.partial")
    last_probe: VideoProbe | None = None
    last_error: Exception | None = None
    for attempt in range(1, FRAME_TIMELINE_MAX_ATTEMPTS + 1):
        partial_path.unlink(missing_ok=True)
        try:
            header_probe = header_probe_fn(video_path)
            last_probe = header_probe
            if header_probe.fps_source == "ffprobe_failed":
                raise FrameTimelineError(f"ffprobe stream header unavailable for video_id={video_id}")
            row_count, is_vfr = _write_frame_timeline_stream(
                partial_path,
                row_iter_fn(video_path, video_id=video_id),
                expected_video_id=video_id,
                chunk_rows=chunk_rows,
            )
            probe = replace(
                header_probe,
                frame_count=row_count,
                frame_count_estimated=False,
                frame_count_method="decoded_frame_timeline",
                is_vfr=is_vfr,
            )
            _validate_streamed_timeline_summary(partial_path, expected_row_count=row_count)
            partial_path.replace(target_path)
            return FrameTimelineFileBuildResult(
                probe=probe,
                path=target_path,
                row_count=row_count,
                attempts=attempt,
                status="pass",
            )
        except Exception as exc:  # noqa: BLE001 - ffprobe is an external retry boundary
            last_error = exc
            partial_path.unlink(missing_ok=True)
            if attempt < FRAME_TIMELINE_MAX_ATTEMPTS:
                sleep_fn(FRAME_TIMELINE_RETRY_DELAYS_SECONDS[attempt - 1])

    if normalized_policy == "required":
        raise FrameTimelineError(
            f"decoded frame timeline unavailable for video_id={video_id} after "
            f"{FRAME_TIMELINE_MAX_ATTEMPTS} attempts: {last_error}"
        ) from last_error
    return FrameTimelineFileBuildResult(
        probe=last_probe if last_probe is not None else basic_probe_fn(video_path),
        path=None,
        row_count=0,
        attempts=FRAME_TIMELINE_MAX_ATTEMPTS,
        status="unavailable",
    )


def _write_frame_timeline_stream(
    path: Path,
    rows: Iterable[dict[str, float | int | str | None]],
    *,
    expected_video_id: str,
    chunk_rows: int,
) -> tuple[int, bool | None]:
    schema = pa.schema(
        [
            pa.field("video_id", pa.string(), nullable=False),
            pa.field("frame_id", pa.int64(), nullable=False),
            pa.field("pts_time", pa.float64(), nullable=False),
            pa.field("duration_time", pa.float64(), nullable=True),
        ]
    )
    buffers: dict[str, list[object]] = {column: [] for column in FRAME_TIMELINE_COLUMNS}
    writer: pq.ParquetWriter | None = None
    row_count = 0
    previous_pts: float | None = None
    positive_deltas: list[float] = []

    def flush() -> None:
        nonlocal writer
        if not buffers["frame_id"]:
            return
        table = pa.Table.from_pydict(buffers, schema=schema)
        if writer is None:
            writer = pq.ParquetWriter(path, schema)
        writer.write_table(table, row_group_size=len(buffers["frame_id"]))
        for values in buffers.values():
            values.clear()

    try:
        for row in rows:
            _validate_streamed_timeline_row(
                row,
                expected_video_id=expected_video_id,
                expected_frame_id=row_count,
                previous_pts=previous_pts,
            )
            pts_time = float(row["pts_time"])
            duration = row.get("duration_time")
            if previous_pts is not None and pts_time > previous_pts:
                positive_deltas.append(pts_time - previous_pts)
            buffers["video_id"].append(expected_video_id)
            buffers["frame_id"].append(row_count)
            buffers["pts_time"].append(pts_time)
            buffers["duration_time"].append(None if duration is None else float(duration))
            previous_pts = pts_time
            row_count += 1
            if len(buffers["frame_id"]) >= chunk_rows:
                flush()
        if row_count == 0:
            raise FrameTimelineError(
                f"decoded frame timeline is empty for video_id={expected_video_id}"
            )
        flush()
    finally:
        if writer is not None:
            writer.close()
    return row_count, _detect_vfr_from_deltas(positive_deltas)


def _validate_streamed_timeline_row(
    row: dict[str, float | int | str | None],
    *,
    expected_video_id: str,
    expected_frame_id: int,
    previous_pts: float | None,
) -> None:
    if row.get("video_id") != expected_video_id:
        raise FrameTimelineError(
            f"frame timeline video_id mismatch at row={expected_frame_id}: "
            f"expected={expected_video_id} actual={row.get('video_id')}"
        )
    frame_id = row.get("frame_id")
    if not isinstance(frame_id, int) or isinstance(frame_id, bool) or frame_id != expected_frame_id:
        raise FrameTimelineError(
            f"frame timeline frame_id values must be contiguous from zero for video_id={expected_video_id}"
        )
    pts_time = row.get("pts_time")
    if (
        not isinstance(pts_time, (int, float))
        or isinstance(pts_time, bool)
        or not math.isfinite(float(pts_time))
    ):
        raise FrameTimelineError(f"frame timeline pts_time must be numeric at row={expected_frame_id}")
    if previous_pts is not None and float(pts_time) < previous_pts:
        raise FrameTimelineError(
            f"frame timeline pts_time must be non-decreasing for video_id={expected_video_id}"
        )
    duration_time = row.get("duration_time")
    if duration_time is not None and (
        not isinstance(duration_time, (int, float))
        or isinstance(duration_time, bool)
        or not math.isfinite(float(duration_time))
        or float(duration_time) < 0
    ):
        raise FrameTimelineError(
            f"frame timeline duration_time must be non-negative or null at row={expected_frame_id}"
        )


def _detect_vfr_from_deltas(deltas: list[float]) -> bool | None:
    if len(deltas) < 2:
        return None
    deltas.sort()
    median_delta = deltas[len(deltas) // 2]
    if median_delta <= 0:
        return None
    tolerance = max(VFR_ABS_TOLERANCE_SECONDS, abs(median_delta) * VFR_REL_TOLERANCE)
    return any(
        not math.isclose(
            delta,
            median_delta,
            rel_tol=VFR_REL_TOLERANCE,
            abs_tol=tolerance,
        )
        for delta in deltas
    )


def _validate_streamed_timeline_summary(path: Path, *, expected_row_count: int) -> None:
    parquet_file = pq.ParquetFile(path)
    if tuple(parquet_file.schema_arrow.names) != FRAME_TIMELINE_COLUMNS:
        raise FrameTimelineError(
            f"frame timeline file columns mismatch: {parquet_file.schema_arrow.names}"
        )
    if parquet_file.metadata.num_rows != expected_row_count:
        raise FrameTimelineError(
            "frame timeline file row count mismatch: "
            f"expected={expected_row_count} actual={parquet_file.metadata.num_rows}"
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
