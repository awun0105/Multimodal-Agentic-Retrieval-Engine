from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


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
        "-count_packets",
        "-show_entries",
        "stream=avg_frame_rate,r_frame_rate,nb_frames,nb_read_packets,width,height,duration",
        "-of",
        "json",
        str(path),
    ]
    try:
        completed = subprocess.run(command, check=True, capture_output=True, text=True)
        stream = (json.loads(completed.stdout).get("streams") or [{}])[0]
    except (FileNotFoundError, subprocess.CalledProcessError, json.JSONDecodeError, IndexError):
        return VideoProbe(None, "ffprobe_failed", None, True, "unavailable", None, None, None, None)

    fps = _parse_rate(stream.get("avg_frame_rate")) or _parse_rate(stream.get("r_frame_rate"))
    duration = _parse_float(stream.get("duration"))
    nb_read_packets = _parse_int(stream.get("nb_read_packets"))
    nb_frames = _parse_int(stream.get("nb_frames"))
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
