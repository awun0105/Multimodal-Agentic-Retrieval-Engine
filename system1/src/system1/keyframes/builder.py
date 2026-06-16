from __future__ import annotations

from pathlib import Path

from system1.keyframes.extractor import extract_keyframe_and_thumbnail
from system1.release.types import CHECKPOINT_VERSION, BuildOptions, config_hash, file_checksum


def keyframe_id(video_id: str, frame_id: int) -> str:
    return f"{video_id}:{frame_id}"


def keyframe_refs(video_id: str, frame_id: int) -> tuple[str, str]:
    return (
        f"media://keyframes/{video_id}/{video_id}_f{frame_id:07d}.jpg",
        f"media://thumbnails/{video_id}/{video_id}_f{frame_id:07d}.webp",
    )


def materialize_keyframe(
    *,
    release_dir: Path,
    video_id: str,
    video_path: Path,
    frame_id: int,
    options: BuildOptions,
    previous_checkpoint: dict | None,
) -> tuple[dict[str, object], dict[str, object], Path]:
    keyframe_ref, thumbnail_ref = keyframe_refs(video_id, frame_id)
    keyframe_path = release_dir / "media" / "keyframes" / video_id / f"{video_id}_f{frame_id:07d}.jpg"
    thumbnail_path = release_dir / "media" / "thumbnails" / video_id / f"{video_id}_f{frame_id:07d}.webp"
    input_checksum = file_checksum(video_path)
    previous_video = (previous_checkpoint or {}).get("videos", {}).get(video_id, {})
    can_reuse_media = previous_video.get("input_checksum") == input_checksum and keyframe_path.exists() and thumbnail_path.exists()
    extraction_method = "reused_existing_keyframe_thumbnail" if can_reuse_media else extract_keyframe_and_thumbnail(video_path, keyframe_path, thumbnail_path)
    reuse_row = {
        "video_id": video_id,
        "input_checksum": input_checksum,
        "keyframe_checksum": file_checksum(keyframe_path),
        "thumbnail_checksum": file_checksum(thumbnail_path),
        "media_reused": can_reuse_media,
        "config_hash": config_hash(options),
        "schema_version": CHECKPOINT_VERSION,
    }
    return {
        "keyframe_id": keyframe_id(video_id, frame_id),
        "video_id": video_id,
        "frame_id": frame_id,
        "time_seconds": 0.0,
        "keyframe_ref": keyframe_ref,
        "thumbnail_ref": thumbnail_ref,
        "selection_method": extraction_method,
    }, reuse_row, keyframe_path
