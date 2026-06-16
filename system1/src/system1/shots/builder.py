from __future__ import annotations


def shot_id(video_id: str, shot_index: int = 0) -> str:
    return f"{video_id}_SH{shot_index:05d}"


def shot_row(video_id: str, frame_id: int, duration_seconds: float | None) -> dict[str, object]:
    return {
        "shot_id": shot_id(video_id),
        "video_id": video_id,
        "start_frame": 0,
        "end_frame": max(frame_id + 1, 1),
        "start_seconds": 0.0,
        "end_seconds": duration_seconds or 0.0,
        "detection_method": "single_shot_fallback",
    }
