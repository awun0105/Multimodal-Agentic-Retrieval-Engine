"""TRAKE submission file generation: frame spreading and text formatting.

Pure functions here take formatting knobs as parameters so trake.py can pass
its own (possibly monkeypatched) module-level constants through unchanged.
"""

from __future__ import annotations

import zlib

import numpy as np

from schemas import TrakeOutcome


def spread_frames(
    frame_idx: list[int],
    video_id: str,
    max_frame_idx: int,
    rows: int,
    radius: int,
) -> list[tuple[int, ...]]:
    seed = zlib.crc32(video_id.encode())
    rng = np.random.RandomState(seed)
    # Hand-pinned frames arrive here unordered, so the submitted row needs the same
    # clamp the jittered ones get — a decreasing or out-of-range row is invalid.
    result: list[tuple[int, ...]] = [_clamp_increasing(list(frame_idx), max_frame_idx)]
    seen = {result[0]}
    # A short video clamps every jitter back onto the same frames, so cap the
    # attempts instead of looping until `rows` distinct sets exist.
    attempts_left = rows * 20
    while len(result) < rows and attempts_left > 0:
        attempts_left -= 1
        offsets = rng.randint(-radius, radius + 1, size=len(frame_idx))
        candidate = _clamp_increasing(
            [base + int(offset) for base, offset in zip(frame_idx, offsets)],
            max_frame_idx,
        )
        if candidate not in seen:
            seen.add(candidate)
            result.append(candidate)
    return result


def _clamp_increasing(frames: list[int], max_frame_idx: int) -> tuple[int, ...]:
    """Jittering each event independently can reorder them; TRAKE answers must stay
    strictly increasing in time, so squeeze the sequence back into order."""
    forward: list[int] = []
    lowest = 0
    for frame in frames:
        value = max(frame, lowest)
        forward.append(value)
        lowest = value + 1
    # A run pushed past the end has to come back leftwards instead.
    highest = max_frame_idx
    for i in range(len(forward) - 1, -1, -1):
        forward[i] = max(0, min(forward[i], highest))
        highest = forward[i] - 1
    return tuple(forward)


PIN_KEY_SEPARATOR = "|"


def pin_key(video_id: str, event_index: int) -> str:
    """Pinned frames travel through gr.State to the browser, so keys must survive
    JSON — a (video_id, event_index) tuple raises TypeError there."""
    return f"{video_id}{PIN_KEY_SEPARATOR}{int(event_index)}"


def parse_pin_key(key: str) -> tuple[str, int] | None:
    """None for anything that is not a key we wrote — a malformed entry in the
    browser-held state must not take down the whole preview."""
    video_id, separator, event_index = key.rpartition(PIN_KEY_SEPARATOR)
    if not separator or not video_id:
        return None
    try:
        return video_id, int(event_index)
    except ValueError:
        return None


def build_submission(
    outcome: TrakeOutcome,
    max_rows: int,
    rows_per_video: int,
    radius: int,
    pinned_frames: dict[str, int] | None = None,
) -> list[tuple[str, tuple[int, ...]]]:
    if pinned_frames is None:
        pinned_frames = {}

    rows: list[tuple[str, tuple[int, ...]]] = []
    for video in outcome.videos:
        if len(rows) >= max_rows:
            break

        # A hand-picked frame overrides whatever the search matched.
        frames = [
            pinned_frames.get(pin_key(video.video_id, i), event.frame_idx)
            for i, event in enumerate(video.events)
        ]

        # Fall back to the last matched frame only when the video length is unknown.
        max_frame_idx = video.max_frame_idx or max(frames)
        spread = spread_frames(
            frames, video.video_id, max_frame_idx, rows=rows_per_video, radius=radius
        )
        for frame_set in spread:
            if len(rows) >= max_rows:
                break
            rows.append((video.video_id, frame_set))
    return rows[:max_rows]


def format_submission(
    rows: list[tuple[str, tuple[int, ...]]],
    delimiter: str,
    include_header: bool,
    frame_index_base: int,
) -> str:
    lines = []
    if include_header:
        lines.append(delimiter.join(["video_id", "frame_idx"]))
    for video_id, frames in rows:
        shifted = [str(f + frame_index_base) for f in frames]
        lines.append(delimiter.join([video_id, *shifted]))
    return "\n".join(lines)

import tempfile
from pathlib import Path
import time

import gradio as gr
def export_csv_file(content: str, filename: str):
    if not content.strip():
        return gr.update(value=None, visible=False), "No data to export."
    
    # Use a secure temp directory
    out_dir = Path(tempfile.gettempdir()) / "aic26_submissions"
    out_dir.mkdir(exist_ok=True)
    
    # Clean up filename, defaulting if empty
    safe_name = filename.strip()
    if not safe_name:
        timestamp = time.strftime("%y%m%d-%H%M")
        safe_name = f"submission_{timestamp}.csv"
    if not safe_name.endswith(".csv"):
        safe_name += ".csv"
        
    out_path = out_dir / safe_name
    out_path.write_text(content, encoding="utf-8")
    
    return gr.update(value=str(out_path), visible=True), f"Đã lưu thành công {safe_name} tại {out_path}."
