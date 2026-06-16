from __future__ import annotations

import subprocess
from pathlib import Path


def extract_keyframe_and_thumbnail(video_path: Path, keyframe_path: Path, thumbnail_path: Path) -> str:
    keyframe_path.parent.mkdir(parents=True, exist_ok=True)
    thumbnail_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-i", str(video_path), "-frames:v", "1", str(keyframe_path)],
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-i", str(keyframe_path), "-vf", "scale=320:-1", str(thumbnail_path)],
            check=True,
            capture_output=True,
            text=True,
        )
        return "ffmpeg_first_frame"
    except subprocess.CalledProcessError:
        keyframe_path.write_bytes(b"SYSTEM1_PLACEHOLDER_KEYFRAME\n")
        thumbnail_path.write_bytes(b"SYSTEM1_PLACEHOLDER_THUMBNAIL\n")
        return "placeholder_after_ffmpeg_failure"
