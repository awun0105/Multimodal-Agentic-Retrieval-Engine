from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path


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


def probe_video(path: Path) -> VideoProbe:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=avg_frame_rate,r_frame_rate,nb_frames,width,height,duration",
        "-of",
        "json",
        str(path),
    ]
    try:
        completed = subprocess.run(command, check=True, capture_output=True, text=True)
        stream = (json.loads(completed.stdout).get("streams") or [{}])[0]
    except (subprocess.CalledProcessError, json.JSONDecodeError, IndexError):
        return VideoProbe(None, "ffprobe_failed", None, True, "unavailable", None, None, None, None)

    fps = _parse_rate(stream.get("avg_frame_rate")) or _parse_rate(stream.get("r_frame_rate"))
    duration = _parse_float(stream.get("duration"))
    nb_frames = _parse_int(stream.get("nb_frames"))
    estimated = nb_frames is None
    frame_count = nb_frames
    method = "ffprobe_nb_frames"
    if frame_count is None and fps and duration:
        frame_count = max(1, round(fps * duration))
        method = "estimated_from_duration_and_fps"
    return VideoProbe(
        fps_detected=fps,
        fps_source="ffprobe_avg_frame_rate" if fps else "unavailable",
        frame_count=frame_count,
        frame_count_estimated=estimated,
        frame_count_method=method,
        duration_seconds=duration,
        width=_parse_int(stream.get("width")),
        height=_parse_int(stream.get("height")),
        is_vfr=False if fps else None,
    )


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
