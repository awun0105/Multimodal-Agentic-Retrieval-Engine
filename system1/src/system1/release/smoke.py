from __future__ import annotations

import sqlite3
from pathlib import Path

from system1.release.types import write_json


def write_smoke_report(release_dir: Path | str) -> Path:
    release_path = Path(release_dir)
    sqlite_path = release_path / "db" / "app.sqlite"
    jpg_count = len(list((release_path / "media" / "keyframes").rglob("*.jpg")))
    webp_count = len(list((release_path / "media" / "thumbnails").rglob("*.webp")))
    with sqlite3.connect(sqlite_path) as connection:
        fts_row = connection.execute("SELECT document_id FROM text_documents_fts WHERE text_documents_fts MATCH ? LIMIT 1", ("L21 OR mock OR HTV",)).fetchone()
        counts = {table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in ("videos", "scenes", "shots", "keyframes")}
        one_keyframe = connection.execute("SELECT keyframe_id, video_id, frame_id FROM keyframes ORDER BY keyframe_id LIMIT 1").fetchone()
    report = {
        "status": "pass" if fts_row and jpg_count and webp_count else "fail",
        "fts_query_returned": bool(fts_row),
        "jpg_count": jpg_count,
        "webp_count": webp_count,
        "counts": counts,
        "keyframe_mapping_ok": bool(one_keyframe and one_keyframe[0] == f"{one_keyframe[1]}:{one_keyframe[2]}"),
        "release_config_loadable": (release_path / "manifests" / "dataset_manifest.json").exists(),
    }
    target = release_path / "manifests" / "smoke_test_report.json"
    write_json(target, report)
    return target
