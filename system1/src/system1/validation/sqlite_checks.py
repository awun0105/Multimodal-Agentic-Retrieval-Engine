from __future__ import annotations

import sqlite3

from system1.validation.constants import MEDIA_REF_COLUMNS, REQUIRED_TABLES


def check_sqlite(sqlite_path, errors: list[str], degraded: list[str]) -> dict[str, str]:
    with sqlite3.connect(sqlite_path) as connection:
        table_names = table_names_for(connection)
        for table_name in sorted(REQUIRED_TABLES):
            if table_name not in table_names:
                errors.append(f"missing required SQLite table: {table_name}")
        if not REQUIRED_TABLES.issubset(table_names):
            return {}
        check_media_refs(connection, errors)
        check_videos(connection, errors)
        check_keyframes(connection, errors)
        check_vector_map(connection, errors)
        check_text_documents(connection, table_names, errors)
        check_fts(connection, errors)
        return check_release_capabilities(connection, degraded)


def table_names_for(connection: sqlite3.Connection) -> set[str]:
    rows = connection.execute("SELECT name FROM sqlite_master WHERE type IN ('table', 'virtual')").fetchall()
    return {row[0] for row in rows}


def check_media_refs(connection: sqlite3.Connection, errors: list[str]) -> None:
    for table_name, column_names in MEDIA_REF_COLUMNS.items():
        for column_name in column_names:
            rows = connection.execute(f"SELECT {column_name} FROM {table_name}").fetchall()
            for (value,) in rows:
                if not isinstance(value, str):
                    errors.append(f"{table_name}.{column_name} is not text")
                    continue
                if value.startswith("/") or value.startswith("file://"):
                    errors.append(f"{table_name}.{column_name} stores an absolute path: {value}")
                if not value.startswith("media://"):
                    errors.append(f"{table_name}.{column_name} must use media:// refs: {value}")


def check_videos(connection: sqlite3.Connection, errors: list[str]) -> None:
    duplicate_rows = connection.execute(
        "SELECT video_id, COUNT(*) FROM videos GROUP BY video_id HAVING COUNT(*) > 1"
    ).fetchall()
    for video_id, count in duplicate_rows:
        errors.append(f"duplicate video_id: {video_id} ({count})")


def check_keyframes(connection: sqlite3.Connection, errors: list[str]) -> None:
    rows = connection.execute("SELECT keyframe_id, video_id, frame_id FROM keyframes").fetchall()
    seen_pairs: set[tuple[str, int]] = set()
    seen_keyframes: set[str] = set()
    for keyframe_id, video_id, frame_id in rows:
        if keyframe_id in seen_keyframes:
            errors.append(f"duplicate keyframe_id: {keyframe_id}")
        seen_keyframes.add(keyframe_id)
        if not isinstance(frame_id, int):
            errors.append(f"keyframes.frame_id must be integer for {keyframe_id}")
            continue
        pair = (video_id, frame_id)
        if pair in seen_pairs:
            errors.append(f"duplicate (video_id, frame_id): {video_id}, {frame_id}")
        seen_pairs.add(pair)
        expected_keyframe_id = f"{video_id}:{frame_id}"
        if keyframe_id != expected_keyframe_id:
            errors.append(f"keyframe_id mismatch: expected {expected_keyframe_id}, got {keyframe_id}")
        exists = connection.execute("SELECT 1 FROM videos WHERE video_id = ? LIMIT 1", (video_id,)).fetchone()
        if exists is None:
            errors.append(f"keyframes.video_id does not resolve: {video_id}")


def check_vector_map(connection: sqlite3.Connection, errors: list[str]) -> None:
    rows = connection.execute(
        """
        SELECT vector_map.keyframe_id
        FROM vector_map
        LEFT JOIN keyframes ON vector_map.keyframe_id = keyframes.keyframe_id
        WHERE keyframes.keyframe_id IS NULL
        """
    ).fetchall()
    for (keyframe_id,) in rows:
        errors.append(f"vector_map.keyframe_id does not resolve: {keyframe_id}")


def check_text_documents(connection: sqlite3.Connection, table_names: set[str], errors: list[str]) -> None:
    rows = connection.execute("SELECT document_id, entity_type, entity_id FROM text_documents").fetchall()
    if not rows:
        errors.append("text_documents is empty")
        return
    for document_id, entity_type, entity_id in rows:
        entity_table = entity_table_for(entity_type)
        if entity_table is None or entity_table not in table_names:
            errors.append(f"text_documents.entity_type is not implemented for {document_id}: {entity_type}")
            continue
        id_column = "keyframe_id" if entity_table == "keyframes" else "video_id"
        exists = connection.execute(
            f"SELECT 1 FROM {entity_table} WHERE {id_column} = ? LIMIT 1", (entity_id,)
        ).fetchone()
        if exists is None:
            errors.append(f"text_documents.entity_id does not resolve for {document_id}: {entity_id}")


def check_fts(connection: sqlite3.Connection, errors: list[str]) -> None:
    row = connection.execute(
        "SELECT document_id FROM text_documents_fts WHERE text_documents_fts MATCH ? LIMIT 1",
        ("L21 OR mock OR validation",),
    ).fetchone()
    if row is None:
        errors.append("FTS5 query returned no rows")


def check_release_capabilities(connection: sqlite3.Connection, degraded: list[str]) -> dict[str, str]:
    rows = connection.execute("SELECT capability, status, reason FROM release_capabilities").fetchall()
    capabilities: dict[str, str] = {}
    for capability, status, reason in rows:
        capabilities[str(capability)] = str(status)
        if status == "degraded":
            degraded.append(f"{capability}: {reason}")
    return capabilities


def entity_table_for(entity_type: str) -> str | None:
    return {"video": "videos", "keyframe": "keyframes"}.get(entity_type)
