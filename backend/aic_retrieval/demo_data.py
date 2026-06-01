from __future__ import annotations

import sqlite3
from pathlib import Path


DEMO_FRAMES = [
    (
        "L21_V001",
        1,
        0.04,
        "Night city festival with lanterns, skyscrapers, towers, posters and bright lights.",
        "Lantern Skyscraper Tower Building Poster",
    ),
    (
        "L05_V010",
        250,
        10.0,
        "Cycling race on a city street with athletes crossing the finish line.",
        "Bicycle Helmet Road Person",
    ),
    (
        "L10_V003",
        420,
        16.8,
        "Cooking video showing beef, onion and vegetables touching a hot pan.",
        "Pan Food Onion Meat",
    ),
]


def ensure_demo_media(data_root: Path) -> None:
    for index, (video_id, frame_id, _timestamp, caption, objects) in enumerate(DEMO_FRAMES):
        color = ["#1d4ed8", "#047857", "#b45309"][index % 3]
        title = f"{video_id} / frame {frame_id}"
        labels = objects.replace(" ", " · ")
        svg = _svg(title, caption, labels, color)
        for kind in ("thumbs", "keyframes"):
            path = data_root / "processed" / kind / video_id / f"{frame_id}.svg"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(svg, encoding="utf-8")


def seed_demo_data(connection: sqlite3.Connection) -> None:
    for video_id, frame_id, timestamp, caption, objects in DEMO_FRAMES:
        connection.execute(
            """
            INSERT OR IGNORE INTO videos(video_id, path, fps, duration, width, height)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (video_id, f"raw/videos/{video_id}.mp4", 25.0, 120.0, 1920, 1080),
        )
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
                video_id,
                frame_id,
                timestamp,
                f"processed/thumbs/{video_id}/{frame_id}.svg",
                f"processed/keyframes/{video_id}/{frame_id}.svg",
                caption,
            ),
        )
        connection.execute(
            "DELETE FROM frame_search WHERE video_id=? AND frame_id=?",
            (video_id, str(frame_id)),
        )
        connection.execute(
            """
            INSERT INTO frame_search(video_id, frame_id, text)
            VALUES (?, ?, ?)
            """,
            (video_id, str(frame_id), f"{caption} {objects}"),
        )
        for object_name in objects.split():
            connection.execute(
                """
                INSERT INTO objects(video_id, frame_id, name, score, box_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (video_id, frame_id, object_name, 0.8, "[]"),
            )
    connection.commit()


def _svg(title: str, caption: str, labels: str, color: str) -> str:
    safe_caption = caption[:120]
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="960" height="540" viewBox="0 0 960 540">
  <rect width="960" height="540" fill="#0d131d"/>
  <rect x="32" y="32" width="896" height="476" rx="28" fill="{color}" opacity="0.86"/>
  <text x="64" y="118" fill="#ffffff" font-size="42" font-family="Arial, sans-serif" font-weight="700">{title}</text>
  <text x="64" y="190" fill="#dbeafe" font-size="24" font-family="Arial, sans-serif">{labels}</text>
  <foreignObject x="64" y="242" width="820" height="170">
    <div xmlns="http://www.w3.org/1999/xhtml" style="font: 30px Arial, sans-serif; color: #fff; line-height: 1.35;">{safe_caption}</div>
  </foreignObject>
</svg>
"""
