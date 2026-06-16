from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pandas as pd

from system1.validation.release_validator import validate_release


RELEASE_NAME = "competition_dataset_v001"
VIDEO_ID = "L01_V001"
FRAME_ID = 250
KEYFRAME_ID = f"{VIDEO_ID}:{FRAME_ID}"


def build_mini_seed(output_dir: Path | str, *, validate: bool = True) -> Path:
    release_dir = Path(output_dir) / RELEASE_NAME
    _create_directories(release_dir)

    tables = _build_tables()
    _write_parquet_tables(release_dir, tables)
    _write_index_version(release_dir)
    _write_sqlite(release_dir / "db" / "app.sqlite", tables)
    _write_manifest(release_dir)

    if validate:
        validate_release(release_dir)
    else:
        _write_json(release_dir / "manifests" / "validation_report.json", {"status": "not_run", "errors": []})
        (release_dir / "manifests" / "validation_errors.jsonl").write_text("", encoding="utf-8")

    return release_dir


def _create_directories(release_dir: Path) -> None:
    for relative_path in ("db", "indexes", "tables", "manifests"):
        (release_dir / relative_path).mkdir(parents=True, exist_ok=True)


def _build_tables() -> dict[str, pd.DataFrame]:
    videos = pd.DataFrame(
        [
            {
                "video_id": VIDEO_ID,
                "video_ref": "media://raw_videos/L01_V001.mp4",
                "source_stem": VIDEO_ID,
                "fps_detected": 25.0,
                "frame_count_method": "seed_fixture",
                "is_vfr": False,
            }
        ]
    )
    keyframes = pd.DataFrame(
        [
            {
                "keyframe_id": KEYFRAME_ID,
                "video_id": VIDEO_ID,
                "frame_id": FRAME_ID,
                "keyframe_ref": "media://keyframes/L01_V001/L01_V001_f0000250.jpg",
                "thumbnail_ref": "media://thumbnails/L01_V001/L01_V001_f0000250.webp",
            }
        ]
    )
    text_documents = pd.DataFrame(
        [
            {
                "document_id": "doc:L01_V001:250:caption",
                "entity_type": "keyframe",
                "entity_id": KEYFRAME_ID,
                "text_kind": "caption",
                "text": "A minimal seed keyframe for System 1 validation.",
            }
        ]
    )
    vector_map = pd.DataFrame(
        [
            {
                "vector_id": 0,
                "embedding_model": "seed-fixture",
                "keyframe_id": KEYFRAME_ID,
            }
        ]
    )
    feature_availability = pd.DataFrame(
        [
            {
                "entity_type": "keyframe",
                "entity_id": KEYFRAME_ID,
                "has_caption": True,
                "has_embedding": True,
                "has_ocr": False,
                "has_asr": False,
            }
        ]
    )
    return {
        "videos": videos,
        "keyframes": keyframes,
        "text_documents": text_documents,
        "vector_map": vector_map,
        "feature_availability": feature_availability,
    }


def _write_parquet_tables(release_dir: Path, tables: dict[str, pd.DataFrame]) -> None:
    for table_name, data_frame in tables.items():
        data_frame.to_parquet(release_dir / "tables" / f"{table_name}.parquet", index=False)


def _write_index_version(release_dir: Path) -> None:
    _write_json(
        release_dir / "indexes" / "index_version.json",
        {
            "release_name": RELEASE_NAME,
            "index_version": "seed-v001",
            "vector_index": "not_built_phase_1_seed_fixture",
        },
    )


def _write_manifest(release_dir: Path) -> None:
    _write_json(
        release_dir / "manifests" / "dataset_manifest.json",
        {
            "release_name": RELEASE_NAME,
            "dataset_version": "v001",
            "system": "system1",
            "tables": [
                "videos",
                "keyframes",
                "text_documents",
                "vector_map",
                "feature_availability",
            ],
        },
    )


def _write_sqlite(sqlite_path: Path, tables: dict[str, pd.DataFrame]) -> None:
    with sqlite3.connect(sqlite_path) as connection:
        for table_name, data_frame in tables.items():
            data_frame.to_sql(table_name, connection, if_exists="replace", index=False)

        connection.execute(
            """
            CREATE TABLE release_capabilities (
                capability TEXT PRIMARY KEY,
                enabled INTEGER NOT NULL,
                detail TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "INSERT INTO release_capabilities VALUES (?, ?, ?)",
            ("sqlite_fts5_text_search", 1, "Phase 1 seed text search fixture"),
        )
        connection.execute(
            "CREATE VIRTUAL TABLE text_documents_fts USING fts5(document_id, entity_type, entity_id, text)"
        )
        connection.execute(
            """
            INSERT INTO text_documents_fts (document_id, entity_type, entity_id, text)
            SELECT document_id, entity_type, entity_id, text FROM text_documents
            """
        )


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
