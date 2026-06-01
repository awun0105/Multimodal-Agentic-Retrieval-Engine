from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any

from .config import get_settings
from .db import connect, init_db


def ingest_manifest(connection: sqlite3.Connection, manifest: dict[str, Any]) -> dict[str, int]:
    videos = manifest.get("videos", [])
    frames = manifest.get("frames", [])
    if not isinstance(videos, list) or not isinstance(frames, list):
        raise ValueError("Manifest must contain 'videos' and 'frames' lists")

    video_count = 0
    frame_count = 0
    object_count = 0
    for video in videos:
        _upsert_video(connection, video)
        video_count += 1

    for frame in frames:
        _upsert_frame(connection, frame)
        frame_count += 1
        object_count += _replace_objects(connection, frame)
        _replace_search_text(connection, frame)

    connection.commit()
    return {"videos": video_count, "frames": frame_count, "objects": object_count}


def ingest_manifest_file(database_path: Path, manifest_path: Path) -> dict[str, int]:
    init_db(database_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    with connect(database_path) as connection:
        return ingest_manifest(connection, manifest)


def main() -> None:
    parser = argparse.ArgumentParser(description="Import a local AIC retrieval manifest")
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--database", type=Path, default=None)
    args = parser.parse_args()

    settings = get_settings()
    database_path = args.database or settings.database_path
    stats = ingest_manifest_file(database_path, args.manifest)
    print(json.dumps(stats, indent=2))


def _upsert_video(connection: sqlite3.Connection, video: dict[str, Any]) -> None:
    video_id = _required(video, "video_id")
    connection.execute(
        """
        INSERT INTO videos(video_id, path, fps, duration, width, height)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(video_id) DO UPDATE SET
          path=excluded.path,
          fps=excluded.fps,
          duration=excluded.duration,
          width=excluded.width,
          height=excluded.height
        """,
        (
            video_id,
            video.get("path", ""),
            video.get("fps"),
            video.get("duration"),
            video.get("width"),
            video.get("height"),
        ),
    )


def _upsert_frame(connection: sqlite3.Connection, frame: dict[str, Any]) -> None:
    connection.execute(
        """
        INSERT INTO frames(video_id, frame_id, timestamp, thumb_path, keyframe_path, caption)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(video_id, frame_id) DO UPDATE SET
          timestamp=excluded.timestamp,
          thumb_path=excluded.thumb_path,
          keyframe_path=excluded.keyframe_path,
          caption=excluded.caption
        """,
        (
            _required(frame, "video_id"),
            int(_required(frame, "frame_id")),
            float(frame.get("timestamp", 0.0)),
            frame.get("thumb_path"),
            frame.get("keyframe_path"),
            frame.get("caption", ""),
        ),
    )


def _replace_objects(connection: sqlite3.Connection, frame: dict[str, Any]) -> int:
    video_id = _required(frame, "video_id")
    frame_id = int(_required(frame, "frame_id"))
    objects = frame.get("objects", [])
    if not isinstance(objects, list):
        raise ValueError("Frame objects must be a list")

    connection.execute("DELETE FROM objects WHERE video_id=? AND frame_id=?", (video_id, frame_id))
    for detected in objects:
        if not isinstance(detected, dict):
            raise ValueError("Each object must be a JSON object")
        connection.execute(
            """
            INSERT INTO objects(video_id, frame_id, name, score, box_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                video_id,
                frame_id,
                _required(detected, "name"),
                float(detected.get("score", 0.0)),
                json.dumps(detected.get("box", [])),
            ),
        )
    return len(objects)


def _replace_search_text(connection: sqlite3.Connection, frame: dict[str, Any]) -> None:
    video_id = _required(frame, "video_id")
    frame_id = int(_required(frame, "frame_id"))
    object_names = [
        detected["name"]
        for detected in frame.get("objects", [])
        if isinstance(detected, dict) and detected.get("name")
    ]
    text = " ".join([frame.get("caption", ""), *object_names]).strip()
    connection.execute(
        "DELETE FROM frame_search WHERE video_id=? AND frame_id=?",
        (video_id, str(frame_id)),
    )
    connection.execute(
        "INSERT INTO frame_search(video_id, frame_id, text) VALUES (?, ?, ?)",
        (video_id, str(frame_id), text),
    )


def _required(data: dict[str, Any], key: str) -> Any:
    value = data.get(key)
    if value is None or value == "":
        raise ValueError(f"Missing required field: {key}")
    return value


if __name__ == "__main__":
    main()
