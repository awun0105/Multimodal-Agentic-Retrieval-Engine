from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .config import get_settings
from .ingest import ingest_manifest_file

VIDEO_EXTENSIONS = {".avi", ".m4v", ".mkv", ".mov", ".mp4", ".webm"}
IMAGE_EXTENSIONS = {".jpeg", ".jpg", ".png", ".webp"}


def build_manifest(
    data_root: Path,
    fps: float = 25.0,
    object_score_min: float = 0.2,
) -> dict[str, list[dict[str, Any]]]:
    data_root = data_root.resolve()
    videos = _discover_videos(data_root, fps)
    frame_map: dict[tuple[str, int], dict[str, Any]] = {}
    _attach_images(frame_map, data_root, "keyframe_path", _image_roots(data_root, "keyframes"), fps)
    _attach_images(frame_map, data_root, "thumb_path", _image_roots(data_root, "thumbs"), fps)
    _attach_objects(frame_map, data_root, object_score_min, fps)

    for frame in frame_map.values():
        if not frame.get("thumb_path") and frame.get("keyframe_path"):
            frame["thumb_path"] = frame["keyframe_path"]
        object_names = [item["name"] for item in frame.get("objects", [])]
        if object_names and not frame.get("caption"):
            frame["caption"] = " ".join(object_names)
        if frame["video_id"] not in videos:
            videos[frame["video_id"]] = {
                "video_id": frame["video_id"],
                "path": f"raw/videos/{frame['video_id']}.mp4",
                "fps": fps,
                "duration": None,
                "width": None,
                "height": None,
            }

    return {
        "videos": sorted(videos.values(), key=lambda item: item["video_id"]),
        "frames": sorted(frame_map.values(), key=lambda item: (item["video_id"], item["frame_id"])),
    }


def prepare_dataset(
    data_root: Path,
    manifest_path: Path,
    database_path: Path,
    fps: float = 25.0,
    object_score_min: float = 0.2,
) -> dict[str, int]:
    manifest = build_manifest(data_root, fps=fps, object_score_min=object_score_min)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return ingest_manifest_file(database_path, manifest_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare a local AIC dataset for the app")
    parser.add_argument("data_root", type=Path)
    parser.add_argument("--database", type=Path, default=None)
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--fps", type=float, default=25.0)
    parser.add_argument("--object-score-min", type=float, default=0.2)
    args = parser.parse_args()

    settings = get_settings()
    manifest_path = args.manifest or args.data_root / "manifest.generated.json"
    database_path = args.database or settings.database_path
    stats = prepare_dataset(
        args.data_root,
        manifest_path,
        database_path,
        fps=args.fps,
        object_score_min=args.object_score_min,
    )
    print(json.dumps({"manifest": str(manifest_path), **stats}, indent=2))


def _discover_videos(data_root: Path, fps: float) -> dict[str, dict[str, Any]]:
    videos: dict[str, dict[str, Any]] = {}
    for root in (data_root / "raw" / "videos", data_root / "videos"):
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.suffix.lower() not in VIDEO_EXTENSIONS:
                continue
            video_id = path.stem
            videos[video_id] = {
                "video_id": video_id,
                "path": _relative(path, data_root),
                "fps": fps,
                "duration": None,
                "width": None,
                "height": None,
            }
    return videos


def _image_roots(data_root: Path, kind: str) -> list[Path]:
    return [data_root / "processed" / kind, data_root / kind]


def _attach_images(
    frame_map: dict[tuple[str, int], dict[str, Any]],
    data_root: Path,
    field: str,
    roots: list[Path],
    fps: float,
) -> None:
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.suffix.lower() not in IMAGE_EXTENSIONS:
                continue
            frame_id = _parse_frame_id(path)
            if frame_id is None:
                continue
            video_id = path.parent.name
            frame = _frame_record(frame_map, video_id, frame_id, fps)
            frame[field] = _relative(path, data_root)


def _attach_objects(
    frame_map: dict[tuple[str, int], dict[str, Any]],
    data_root: Path,
    object_score_min: float,
    fps: float,
) -> None:
    root = data_root / "objects"
    if not root.exists():
        return
    for path in root.rglob("*.json"):
        frame_id = _parse_frame_id(path)
        if frame_id is None:
            continue
        video_id = path.parent.name
        objects = _parse_object_file(path, object_score_min)
        frame = _frame_record(frame_map, video_id, frame_id, fps)
        frame["objects"] = objects


def _parse_object_file(path: Path, object_score_min: float) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    names = payload.get("detection_class_entities", [])
    scores = payload.get("detection_scores", [])
    boxes = payload.get("detection_boxes", [])
    objects: list[dict[str, Any]] = []
    for index, name in enumerate(names):
        score = _float_at(scores, index)
        if not name or score < object_score_min:
            continue
        objects.append(
            {
                "name": str(name),
                "score": score,
                "box": boxes[index] if index < len(boxes) else [],
            }
        )
    return objects


def _frame_record(
    frame_map: dict[tuple[str, int], dict[str, Any]],
    video_id: str,
    frame_id: int,
    fps: float,
) -> dict[str, Any]:
    return frame_map.setdefault(
        (video_id, frame_id),
        {
            "video_id": video_id,
            "frame_id": frame_id,
            "timestamp": frame_id / fps,
            "thumb_path": None,
            "keyframe_path": None,
            "caption": "",
            "objects": [],
        },
    )


def _parse_frame_id(path: Path) -> int | None:
    digits = "".join(char for char in path.stem if char.isdigit())
    if not digits:
        return None
    return int(digits)


def _float_at(values: list[Any], index: int) -> float:
    if index >= len(values):
        return 0.0
    try:
        return float(values[index])
    except (TypeError, ValueError):
        return 0.0


def _relative(path: Path, data_root: Path) -> str:
    return path.resolve().relative_to(data_root).as_posix()


if __name__ == "__main__":
    main()
