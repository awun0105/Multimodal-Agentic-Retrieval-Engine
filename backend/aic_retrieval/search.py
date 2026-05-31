from __future__ import annotations

import sqlite3

from .models import SearchResult


def search_frames(connection: sqlite3.Connection, query: str, limit: int) -> list[SearchResult]:
    rows = connection.execute(
        """
        SELECT f.video_id, f.frame_id, f.timestamp, f.thumb_path, f.keyframe_path,
               snippet(frame_search, 2, '[', ']', '...', 12) AS snippet,
               bm25(frame_search) AS rank_score
        FROM frame_search
        JOIN frames f ON f.video_id = frame_search.video_id
                     AND f.frame_id = CAST(frame_search.frame_id AS INTEGER)
        WHERE frame_search MATCH ?
        ORDER BY rank_score
        LIMIT ?
        """,
        (query, limit),
    ).fetchall()

    if not rows:
        rows = connection.execute(
            """
            SELECT video_id, frame_id, timestamp, thumb_path, keyframe_path,
                   caption AS snippet, 0.0 AS rank_score
            FROM frames
            ORDER BY video_id, frame_id
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    results: list[SearchResult] = []
    for index, row in enumerate(rows):
        score = max(0.0, 1.0 - (index * 0.02))
        evidence = [row["snippet"]] if row["snippet"] else []
        results.append(
            SearchResult(
                video_id=row["video_id"],
                frame_id=row["frame_id"],
                timestamp=row["timestamp"],
                thumb_url=_media_url("thumbs", row["video_id"], row["frame_id"])
                if row["thumb_path"]
                else None,
                keyframe_url=_media_url("keyframes", row["video_id"], row["frame_id"])
                if row["keyframe_path"]
                else None,
                score=score,
                evidence=evidence,
            )
        )
    return results


def _media_url(kind: str, video_id: str, frame_id: int) -> str:
    return f"/media/{kind}/{video_id}/{frame_id}"

