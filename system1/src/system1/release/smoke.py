from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from system1.release.types import write_json


def write_smoke_report(release_dir: Path | str) -> Path:
    release_path = Path(release_dir)
    sqlite_path = release_path / "db" / "app.sqlite"
    if not sqlite_path.exists():
        raise FileNotFoundError(f"missing app.sqlite: {sqlite_path}")
    errors: list[str] = []
    with sqlite3.connect(sqlite_path) as connection:
        counts = {table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in ("videos", "scenes", "shots", "keyframes")}
        token_row = connection.execute("SELECT normalized_text, normalized_no_diacritics FROM text_documents LIMIT 20").fetchall()
        token = _sample_token(token_row)
        fts_row = None
        if token is None:
            errors.append("no searchable token in text_documents")
        else:
            fts_row = connection.execute("SELECT document_id FROM text_documents_fts WHERE text_documents_fts MATCH ? LIMIT 1", (token,)).fetchone()
            if fts_row is None:
                errors.append(f"FTS query returned no rows for token: {token}")
        sample = connection.execute("SELECT keyframe_ref, thumbnail_ref FROM keyframes ORDER BY keyframe_id LIMIT 1").fetchone()
    media_ok = False
    resolved = {}
    if sample:
        keyframe_ref, thumbnail_ref = sample
        keyframe_path = _resolve_media_ref(release_path, keyframe_ref)
        thumbnail_path = _resolve_media_ref(release_path, thumbnail_ref)
        resolved["keyframe_path"] = str(keyframe_path)
        resolved["thumbnail_path"] = str(thumbnail_path)
        media_ok = keyframe_path.exists() and thumbnail_path.exists()
        if not media_ok:
            errors.append("sample media refs do not resolve to files")
    else:
        errors.append("no keyframe rows available for media resolution")
    index_version_path = release_path / "indexes" / "index_version.json"
    faiss_checked = False
    faiss_ok = True
    if index_version_path.exists():
        index_version = json.loads(index_version_path.read_text(encoding="utf-8"))
        if index_version.get("index_backend") == "faiss":
            faiss_checked = True
            try:
                import faiss  # type: ignore
                index = faiss.read_index(str(release_path / "indexes" / "visual.faiss"))
                faiss_ok = index.ntotal >= 0
            except Exception as exc:
                faiss_ok = False
                errors.append(f"faiss smoke check failed: {exc}")
    report = {
        "status": "pass" if not errors and bool(fts_row) and media_ok and faiss_ok else "fail",
        "errors": errors,
        "fts_token": token,
        "fts_query_returned": bool(fts_row),
        "counts": counts,
        "media_resolved": media_ok,
        "resolved_media": resolved,
        "faiss_checked": faiss_checked,
        "faiss_ok": faiss_ok,
        "release_config_loadable": (release_path / "manifests" / "dataset_manifest.json").exists(),
    }
    target = release_path / "manifests" / "smoke_test_report.json"
    write_json(target, report)
    return target


def _sample_token(rows: list[tuple[object, object]]) -> str | None:
    for normalized_text, normalized_no_diacritics in rows:
        for candidate in (normalized_text, normalized_no_diacritics):
            if isinstance(candidate, str):
                words = [word for word in candidate.replace("\n", " ").split() if len(word) >= 2]
                if words:
                    return words[0]
    return None


def _resolve_media_ref(release_path: Path, media_ref: str) -> Path:
    prefix_map = {
        "media://keyframes/": release_path / "media" / "keyframes",
        "media://thumbnails/": release_path / "media" / "thumbnails",
        "media://raw_videos/": release_path / "media" / "raw_videos",
    }
    for prefix, root in prefix_map.items():
        if media_ref.startswith(prefix):
            return root / media_ref.removeprefix(prefix)
    raise ValueError(f"unsupported media ref: {media_ref}")
