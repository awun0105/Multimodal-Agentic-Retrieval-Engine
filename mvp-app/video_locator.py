"""Locate video files dynamically from the mounted HDD path."""

import os
import functools
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

@functools.lru_cache(maxsize=1)
def _get_video_map(video_root: str) -> dict[str, str]:
    """Scan the VIDEO_ROOT directory once and map video_id to absolute path."""
    video_map = {}
    root_path = Path(video_root)
    if not root_path.is_dir():
        logger.warning(f"VIDEO_ROOT {video_root} is not a directory.")
        return video_map
    
    # We expect files like L21_V001.mp4 somewhere in this tree
    for mp4_file in root_path.rglob("*.mp4"):
        video_id = mp4_file.stem
        video_map[video_id] = str(mp4_file)
        
    logger.info(f"Scanned {len(video_map)} proxy videos from {video_root}")
    return video_map

def get_video_path(video_id: str) -> str | None:
    """Find the absolute path to a proxy video by its video_id."""
    video_root = os.environ.get("VIDEO_ROOT")
    if not video_root:
        return None
    video_map = _get_video_map(video_root)
    return video_map.get(video_id)
