"""Locate video files dynamically from the mounted HDD path."""

import functools
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

@functools.lru_cache(maxsize=1)
def _get_video_map(video_root: str) -> dict[str, str]:
    """Scan the VIDEO_ROOT directory once and map video_id to absolute path."""
    video_map = {}
    root_path = Path(video_root)
    if not root_path.is_dir():
        logger.warning(f"VIDEO_ROOT {video_root} is not a directory.")
        return video_map
    
    for root, dirs, files in os.walk(video_root):
        # Prevent descending into massive directories that only contain images/features
        dirs[:] = [
            d for d in dirs 
            if not d.startswith("Keyframes_") 
            and not d.startswith("clip-features") 
            and not d.startswith("objects")
            and not d.startswith("map-keyframes")
            and not d.startswith("media-info")
            and not d.startswith(".")
        ]
        for f in files:
            if f.endswith(".mp4"):
                video_id = f[:-4]
                video_map[video_id] = os.path.join(root, f)
        
    logger.info(f"Scanned {len(video_map)} proxy videos from {video_root}")
    return video_map

def get_video_path(video_id: str) -> str | None:
    """Find the absolute path to a proxy video by its video_id."""
    video_root = os.environ.get("VIDEO_ROOT")
    if not video_root:
        return None
    video_map = _get_video_map(video_root)
    return video_map.get(video_id)
