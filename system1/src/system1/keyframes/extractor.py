from __future__ import annotations

import base64
import subprocess
from pathlib import Path

_VALID_PLACEHOLDER_JPEG = base64.b64decode(
    b"/9j/4AAQSkZJRgABAQAAAQABAAD/2wCEAAkGBxAQEBAQEA8PEA8PDw8PDw8PDw8PDw8QFREWFhURFRUYHSggGBolGxUVITEhJSkrLi4uFx8zODMsNygtLisBCgoKDg0OGhAQGi0lHyUtLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLf/AABEIAAEAAQMBEQACEQEDEQH/xAAXAAEBAQEAAAAAAAAAAAAAAAAAAQID/8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAwDAQACEAMQAAAB6A//xAAXEAEBAQEAAAAAAAAAAAAAAAAAAREC/9oACAEBAAEFAm0qf//EABQRAQAAAAAAAAAAAAAAAAAAABD/2gAIAQMBAT8BP//EABQRAQAAAAAAAAAAAAAAAAAAABD/2gAIAQIBAT8BP//Z"
)
_VALID_PLACEHOLDER_WEBP = base64.b64decode(
    b"UklGRjwAAABXRUJQVlA4IDAAAADQAQCdASoBAAEAAQAcJaQAA3AA/v89WAAAAA=="
)


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
            ["ffmpeg", "-y", "-v", "error", "-i", str(keyframe_path), "-vf", "scale=256:-1", str(thumbnail_path)],
            check=True,
            capture_output=True,
            text=True,
        )
        return "ffmpeg_first_frame"
    except subprocess.CalledProcessError:
        keyframe_path.write_bytes(_VALID_PLACEHOLDER_JPEG)
        thumbnail_path.write_bytes(_VALID_PLACEHOLDER_WEBP)
        return "valid_placeholder_after_ffmpeg_failure"
