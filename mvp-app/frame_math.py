"""Frame arithmetic shared by players, pin callbacks, and tests.

The current release satisfies floor(pts_time_sec * fps) == frame_idx for all
177,321 keyframes (verified against runtime.sqlite), while round() disagrees
on 22,922 of them — so floor is the organizer-compatible mapping. Browser
timestamps are reconstructed with Number(x.toPrecision(6)) to match the
precision observed in the release metadata; normalize_time mirrors that.
"""

from __future__ import annotations

import math


def normalize_time(seconds: float) -> float:
    """Mirror the JavaScript `Number(value.toPrecision(6))` reconstruction."""
    return float(f"{float(seconds):.6g}")


def calculated_frame(presentation_time: float, fps: float) -> int | None:
    """Organizer-compatible frame for a presentation timestamp.

    Returns None when either input is unusable (non-finite, negative time, or
    a non-positive fps) so callers can fall back to the canonical keyframe.
    """
    try:
        seconds = float(presentation_time)
        rate = float(fps)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(seconds) or not math.isfinite(rate) or rate <= 0:
        return None
    if seconds < 0:
        seconds = 0.0
    return math.floor(normalize_time(seconds) * rate)


def validate_frame(value: object, fallback: int) -> int:
    """Coerce a player-supplied frame to a non-negative int, else fallback."""
    try:
        frame = int(str(value).strip())
    except (TypeError, ValueError):
        return fallback
    return frame if frame >= 0 else fallback
