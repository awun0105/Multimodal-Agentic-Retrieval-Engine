from __future__ import annotations

import sqlite3

from .models import SearchResult


def search_frames(
    connection: sqlite3.Connection,
    query: str,
    limit: int,
    object_filters: list[str] | None = None,
) -> list[SearchResult]:
    filters = _normalize_filters(object_filters or [])
    object_clause, object_params = _object_clause(filters)
    rows = connection.execute(
        f"""
        SELECT f.video_id, f.frame_id, f.timestamp, f.thumb_path, f.keyframe_path,
               snippet(frame_search, 2, '[', ']', '...', 12) AS snippet,
               (
                 SELECT group_concat(DISTINCT o.name)
                 FROM objects o
                 WHERE o.video_id = f.video_id AND o.frame_id = f.frame_id
               ) AS object_names,
               bm25(frame_search) AS rank_score
        FROM frame_search
        JOIN frames f ON f.video_id = frame_search.video_id
                     AND f.frame_id = CAST(frame_search.frame_id AS INTEGER)
        WHERE frame_search MATCH ?
        {object_clause}
        ORDER BY rank_score
        LIMIT ?
        """,
        (query, *object_params, limit),
    ).fetchall()

    if not rows:
        rows = connection.execute(
            f"""
            SELECT f.video_id, f.frame_id, f.timestamp, f.thumb_path, f.keyframe_path,
                   caption AS snippet,
                   (
                     SELECT group_concat(DISTINCT o.name)
                     FROM objects o
                     WHERE o.video_id = f.video_id AND o.frame_id = f.frame_id
                   ) AS object_names,
                   0.0 AS rank_score
            FROM frames f
            WHERE 1=1
            {object_clause}
            ORDER BY video_id, frame_id
            LIMIT ?
            """,
            (*object_params, limit),
        ).fetchall()

    results: list[SearchResult] = []
    for index, row in enumerate(rows):
        score = max(0.0, 1.0 - (index * 0.02))
        evidence = [row["snippet"]] if row["snippet"] else []
        if row["object_names"]:
            evidence.append(f"objects: {row['object_names']}")
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


def list_object_names(connection: sqlite3.Connection, limit: int = 200) -> list[str]:
    rows = connection.execute(
        """
        SELECT name
        FROM objects
        GROUP BY lower(name)
        ORDER BY COUNT(*) DESC, lower(name)
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [row["name"] for row in rows]


def _normalize_filters(filters: list[str]) -> list[str]:
    return sorted({value.strip().lower() for value in filters if value.strip()})


def _object_clause(filters: list[str]) -> tuple[str, tuple[str, ...]]:
    if not filters:
        return "", ()
    placeholders = ", ".join("?" for _ in filters)
    return (
        f"""
        AND EXISTS (
          SELECT 1
          FROM objects o
          WHERE o.video_id = f.video_id
            AND o.frame_id = f.frame_id
            AND lower(o.name) IN ({placeholders})
        )
        """,
        tuple(filters),
    )


def _media_url(kind: str, video_id: str, frame_id: int) -> str:
    return f"/media/{kind}/{video_id}/{frame_id}"
