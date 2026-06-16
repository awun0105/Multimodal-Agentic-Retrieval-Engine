from __future__ import annotations

import json
from pathlib import Path
from typing import Any

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm"}


def discover_paired_inputs(input_dir: Path | str) -> list[dict[str, str]]:
    root = Path(input_dir)
    raw_root = root / "raw_videos"
    metadata_root = root / "metadata"
    if not raw_root.exists():
        raise FileNotFoundError(f"missing raw video directory: {raw_root}")
    if not metadata_root.exists():
        raise FileNotFoundError(f"missing metadata directory: {metadata_root}")

    videos = {path.stem: path for path in raw_root.iterdir() if path.suffix.lower() in VIDEO_EXTENSIONS}
    metadata = {path.stem: path for path in metadata_root.glob("*.json")}
    missing_metadata = sorted(set(videos) - set(metadata))
    missing_videos = sorted(set(metadata) - set(videos))
    if missing_metadata or missing_videos:
        raise ValueError(f"input pairing failed: missing metadata={missing_metadata}, missing videos={missing_videos}")
    return [{"video_id": stem, "video_path": str(videos[stem]), "metadata_path": str(metadata[stem])} for stem in sorted(videos)]


def read_metadata(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))
