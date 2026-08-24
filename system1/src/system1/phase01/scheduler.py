from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class RuntimeChunk:
    """A transient scheduling unit; it never changes batch assignment."""

    video_ids: tuple[str, ...]
    raw_bytes: int


def plan_runtime_chunks(
    video_ids: Sequence[str],
    *,
    raw_bytes_by_video: Mapping[str, int | None],
    free_disk_gb: float,
    policy: Mapping[str, object],
) -> list[RuntimeChunk]:
    """Partition manifest-ordered videos by disk pressure and raw input bytes."""

    max_videos = _positive_int(policy, "max_chunk_videos")
    max_raw_bytes = _positive_int(policy, "max_chunk_raw_bytes")
    min_free_disk_gb = _non_negative_float(policy, "min_free_disk_gb")
    medium_free_disk_gb = _non_negative_float(policy, "medium_free_disk_gb")
    medium_max_videos = _positive_int(policy, "medium_max_chunk_videos")
    low_disk_max_videos = _positive_int(policy, "low_disk_max_chunk_videos")
    if medium_free_disk_gb < min_free_disk_gb:
        raise ValueError("medium_free_disk_gb must be >= min_free_disk_gb")

    if free_disk_gb < min_free_disk_gb:
        effective_max_videos = min(max_videos, low_disk_max_videos)
    elif free_disk_gb <= medium_free_disk_gb:
        effective_max_videos = min(max_videos, medium_max_videos)
    else:
        effective_max_videos = max_videos

    chunks: list[RuntimeChunk] = []
    current_ids: list[str] = []
    current_raw_bytes = 0
    for raw_video_id in video_ids:
        video_id = str(raw_video_id)
        raw_bytes = _raw_bytes_for_video(
            raw_bytes_by_video.get(video_id), max_raw_bytes=max_raw_bytes
        )
        exceeds_count = len(current_ids) >= effective_max_videos
        exceeds_bytes = bool(current_ids) and current_raw_bytes + raw_bytes > max_raw_bytes
        if exceeds_count or exceeds_bytes:
            chunks.append(RuntimeChunk(tuple(current_ids), current_raw_bytes))
            current_ids = []
            current_raw_bytes = 0
        current_ids.append(video_id)
        current_raw_bytes += raw_bytes
    if current_ids:
        chunks.append(RuntimeChunk(tuple(current_ids), current_raw_bytes))
    return chunks


def _raw_bytes_for_video(value: int | None, *, max_raw_bytes: int) -> int:
    if value is None:
        return max_raw_bytes
    try:
        raw_bytes = int(value)
    except (TypeError, ValueError):
        return max_raw_bytes
    return raw_bytes if raw_bytes >= 0 else max_raw_bytes


def _positive_int(policy: Mapping[str, object], key: str) -> int:
    try:
        value = int(policy[key])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"chunk scheduler {key} must be a positive integer") from exc
    if value < 1:
        raise ValueError(f"chunk scheduler {key} must be a positive integer")
    return value


def _non_negative_float(policy: Mapping[str, object], key: str) -> float:
    try:
        value = float(policy[key])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"chunk scheduler {key} must be non-negative") from exc
    if value < 0:
        raise ValueError(f"chunk scheduler {key} must be non-negative")
    return value
