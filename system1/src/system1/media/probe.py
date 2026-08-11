from __future__ import annotations

import csv
import json
import logging
import math
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

VFR_ABS_TOLERANCE_SECONDS = 1e-4
VFR_REL_TOLERANCE = 0.01


@dataclass(frozen=True)
class VideoProbe:
    fps_detected: float | None
    fps_source: str
    frame_count: int | None
    frame_count_estimated: bool
    frame_count_method: str
    duration_seconds: float | None
    width: int | None
    height: int | None
    is_vfr: bool | None


@dataclass(frozen=True)
class VideoProbeWithTimeline:
    probe: VideoProbe
    frame_timeline: list[dict[str, float | int | str | None]]


def probe_video(path: Path) -> VideoProbe:
    try:
        payload = _run_ffprobe_stream(path)
        stream = _first_stream(payload)
    except (FileNotFoundError, subprocess.CalledProcessError, json.JSONDecodeError, IndexError):
        return VideoProbe(None, "ffprobe_failed", None, True, "unavailable", None, None, None, None)
    return _build_probe_from_stream(path, stream, timeline_rows=None)


def probe_video_with_timeline(path: Path, *, video_id: str) -> VideoProbeWithTimeline:
    try:
        # The decoded-frame query below already scans the full stream and gives
        # the exact row count. Avoid a second full `-count_packets` pass here.
        payload = _run_ffprobe_stream(path, count_packets=False)
        stream = _first_stream(payload)
    except (FileNotFoundError, subprocess.CalledProcessError, json.JSONDecodeError, IndexError):
        return VideoProbeWithTimeline(
            probe=VideoProbe(None, "ffprobe_failed", None, True, "unavailable", None, None, None, None),
            frame_timeline=[],
        )
    try:
        frame_csv = _run_ffprobe_frame_csv(path)
        timeline_rows = _frame_timeline_rows_from_csv(frame_csv, video_id=video_id)
    except (FileNotFoundError, subprocess.CalledProcessError):
        timeline_rows = []
    return VideoProbeWithTimeline(
        probe=_build_probe_from_stream(path, stream, timeline_rows=timeline_rows),
        frame_timeline=timeline_rows,
    )


def _run_ffprobe_stream(path: Path, *, count_packets: bool = True) -> dict[str, Any]:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
    ]
    stream_fields = "avg_frame_rate,r_frame_rate,nb_frames,width,height,duration"
    if count_packets:
        command.append("-count_packets")
        stream_fields += ",nb_read_packets"
    command.extend(["-show_entries", f"stream={stream_fields}"])
    command.extend(["-of", "json", str(path)])
    completed = subprocess.run(command, check=True, capture_output=True, text=True)
    return json.loads(completed.stdout)


def _run_ffprobe_frame_csv(path: Path) -> str:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "frame=best_effort_timestamp_time,duration_time,pkt_duration_time",
        "-of",
        "csv=p=0",
        str(path),
    ]
    completed = subprocess.run(command, check=True, capture_output=True, text=True)
    return completed.stdout


def _first_stream(payload: dict[str, Any]) -> dict[str, Any]:
    return (payload.get("streams") or [{}])[0]


def _build_probe_from_stream(
    path: Path,
    stream: dict[str, Any],
    *,
    timeline_rows: list[dict[str, float | int | str | None]] | None,
) -> VideoProbe:
    fps = _parse_rate(stream.get("avg_frame_rate")) or _parse_rate(stream.get("r_frame_rate"))
    duration = _parse_float(stream.get("duration"))
    nb_read_packets = _parse_int(stream.get("nb_read_packets"))
    nb_frames = _parse_int(stream.get("nb_frames"))
    if timeline_rows:
        frame_count = len(timeline_rows)
        estimated = False
        method = "decoded_frame_timeline"
    else:
        frame_count = nb_read_packets
        estimated = False
        method = "ffprobe_nb_read_packets"
    if frame_count is None and nb_frames is not None:
        frame_count = nb_frames
        method = "ffprobe_nb_frames"
    elif frame_count is None and fps and duration:
        frame_count = round(fps * duration)
        estimated = True
        method = "estimated_from_duration_and_fps"
        logger.warning(
            "Frame count for %s estimated from duration and FPS; potential Frame ID drift for VFR or malformed videos.",
            path,
        )
    elif frame_count is None:
        estimated = True
        method = "unavailable"
    is_vfr = _detect_vfr(timeline_rows) if timeline_rows else None
    return VideoProbe(
        fps_detected=fps,
        fps_source="ffprobe_avg_frame_rate" if fps else "unavailable",
        frame_count=frame_count,
        frame_count_estimated=estimated,
        frame_count_method=method,
        duration_seconds=duration,
        width=_parse_int(stream.get("width")),
        height=_parse_int(stream.get("height")),
        is_vfr=is_vfr,
    )


def _frame_timeline_rows_from_csv(text: str, *, video_id: str) -> list[dict[str, float | int | str | None]]:
    rows: list[dict[str, float | int | str | None]] = []
    for fields in csv.reader(text.splitlines()):
        if not fields:
            continue
        pts_time = _first_float(fields[0] if len(fields) > 0 else None)
        duration_time = _first_float(fields[1] if len(fields) > 1 else None, fields[2] if len(fields) > 2 else None)
        if pts_time is None:
            continue
        rows.append(
            {
                "video_id": video_id,
                "frame_id": len(rows),
                "pts_time": pts_time,
                "duration_time": duration_time,
            }
        )
    return rows


def _detect_vfr(rows: list[dict[str, float | int | str | None]] | None) -> bool | None:
    if not rows or len(rows) < 3:
        return None
    pts_values = [float(row["pts_time"]) for row in rows if row.get("pts_time") is not None]
    if len(pts_values) < 3:
        return None
    deltas = [b - a for a, b in zip(pts_values, pts_values[1:], strict=False) if b > a]
    if len(deltas) < 2:
        return None
    median_delta = sorted(deltas)[len(deltas) // 2]
    if median_delta <= 0:
        return None
    tolerance = max(VFR_ABS_TOLERANCE_SECONDS, abs(median_delta) * VFR_REL_TOLERANCE)
    return any(not math.isclose(delta, median_delta, rel_tol=VFR_REL_TOLERANCE, abs_tol=tolerance) for delta in deltas)


def _first_float(*values: object) -> float | None:
    for value in values:
        parsed = _parse_float(value)
        if parsed is not None:
            return parsed
    return None


def _parse_rate(value: object) -> float | None:
    if not isinstance(value, str) or value in {"0/0", ""}:
        return None
    if "/" in value:
        numerator, denominator = value.split("/", 1)
        denominator_float = float(denominator)
        return float(numerator) / denominator_float if denominator_float else None
    return float(value)


def _parse_int(value: object) -> int | None:
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _parse_float(value: object) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None
