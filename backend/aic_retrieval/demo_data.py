from __future__ import annotations

import sqlite3


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


def seed_demo_data(connection: sqlite3.Connection) -> None:
    existing = connection.execute("SELECT COUNT(*) AS count FROM frames").fetchone()["count"]
    if existing:
        return

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
            """,
            (
                video_id,
                frame_id,
                timestamp,
                f"processed/thumbs/{video_id}/{frame_id}.webp",
                f"processed/keyframes/{video_id}/{frame_id}.jpg",
                caption,
            ),
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

