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
    result: list[tuple[int, ...]] = [tuple(frame_idx)]
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


def build_submission(
    outcome: TrakeOutcome,
    max_rows: int,
    rows_per_video: int,
    radius: int,
    pinned_frames: dict[tuple[str, int], int] | None = None,
) -> list[tuple[str, tuple[int, ...]]]:
    if pinned_frames is None:
        pinned_frames = {}
    
    rows: list[tuple[str, tuple[int, ...]]] = []
    for video in outcome.videos:
        if len(rows) >= max_rows:
            break
        
        # Merge pinned frames with algorithmic frames
        frames = []
        for i, event in enumerate(video.events):
            pinned = pinned_frames.get((video.video_id, i))
            if pinned is not None:
                frames.append(pinned)
            else:
                frames.append(event.frame_idx)
        
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
