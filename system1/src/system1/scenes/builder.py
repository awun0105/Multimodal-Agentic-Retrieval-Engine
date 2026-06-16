from __future__ import annotations


def scene_id(video_id: str, scene_index: int = 0) -> str:
    return f"{video_id}_SC{scene_index:05d}"


def scene_row(video_id: str, frame_id: int, duration_seconds: float | None) -> dict[str, object]:
    return {
        "scene_id": scene_id(video_id),
        "video_id": video_id,
        "start_frame": 0,
        "end_frame": max(frame_id + 1, 1),
        "start_seconds": 0.0,
        "end_seconds": duration_seconds or 0.0,
        "construction_method": "single_scene_fallback",
    }
