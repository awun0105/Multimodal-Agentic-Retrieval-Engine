from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import duckdb
import pandas as pd

TABLE_FILES = (
    "videos",
    "scenes",
    "shots",
    "keyframes",
    "asr_segments",
    "shot_transcript_links",
    "scene_transcript_links",
    "ocr",
    "objects",
    "shot_captions",
    "scene_summaries",
    "embeddings_meta",
    "text_documents",
    "feature_availability",
    "release_capabilities",
)


def _sqlite_safe(frame: pd.DataFrame) -> pd.DataFrame:
    copy = frame.copy()
    for column in copy.columns:
        copy[column] = copy[column].map(lambda value: json.dumps(value) if isinstance(value, (list, dict)) else value)
    return copy


def write_sqlite(sqlite_path: Path, tables: dict[str, pd.DataFrame]) -> None:
    if sqlite_path.exists():
        sqlite_path.unlink()
    with sqlite3.connect(sqlite_path) as connection:
        runtime_table_names = {
            "videos","scenes","shots","keyframes","asr_segments","shot_transcript_links","scene_transcript_links",
            "ocr","objects","shot_captions","scene_summaries",
            "embeddings_meta","text_documents","vector_map","feature_availability","release_capabilities",
        }
        for name, frame in tables.items():
            if name not in runtime_table_names:
                continue
            _sqlite_safe(frame).to_sql(name, connection, index=False, if_exists="replace")
        connection.executescript(
            """
            CREATE UNIQUE INDEX pk_videos ON videos(video_id);
            CREATE UNIQUE INDEX pk_scenes ON scenes(scene_id);
            CREATE UNIQUE INDEX pk_shots ON shots(shot_id);
            CREATE UNIQUE INDEX pk_keyframes ON keyframes(keyframe_id);
            CREATE UNIQUE INDEX pk_embeddings_meta ON embeddings_meta(embedding_id);
            CREATE INDEX idx_keyframes_video_frame ON keyframes(video_id, frame_id);
            CREATE INDEX idx_keyframes_shot ON keyframes(shot_id);
            CREATE INDEX idx_keyframes_scene ON keyframes(scene_id);
            CREATE INDEX idx_vector_map_keyframe ON vector_map(keyframe_id);
            CREATE INDEX idx_vector_map_vector ON vector_map(vector_id);
            CREATE INDEX idx_text_documents_entity ON text_documents(entity_type, entity_id);
            CREATE VIRTUAL TABLE text_documents_fts USING fts5(document_id UNINDEXED, normalized_text, normalized_no_diacritics, tokenize='unicode61');
            INSERT INTO text_documents_fts(document_id, normalized_text, normalized_no_diacritics)
            SELECT document_id, normalized_text, normalized_no_diacritics FROM text_documents;

            -- OCR Specific Schema Support
            CREATE TABLE IF NOT EXISTS ocr_texts (
                keyframe_id TEXT PRIMARY KEY,
                video_id TEXT NOT NULL,
                full_text TEXT NOT NULL,
                FOREIGN KEY (keyframe_id) REFERENCES keyframes (keyframe_id)
            );
            CREATE TABLE IF NOT EXISTS ocr_boxes (
                box_id INTEGER PRIMARY KEY AUTOINCREMENT,
                keyframe_id TEXT NOT NULL,
                text TEXT NOT NULL,
                score REAL NOT NULL,
                ymin REAL NOT NULL,
                xmin REAL NOT NULL,
                ymax REAL NOT NULL,
                xmax REAL NOT NULL,
                FOREIGN KEY (keyframe_id) REFERENCES keyframes (keyframe_id)
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS ocr_fts USING fts5(
                keyframe_id UNINDEXED,
                full_text
            );
            INSERT OR IGNORE INTO ocr_texts (keyframe_id, video_id, full_text)
            SELECT entity_id, video_id, raw_text FROM text_documents
            WHERE entity_type = 'keyframe' AND source_type = 'ocr';
            INSERT OR IGNORE INTO ocr_fts (keyframe_id, full_text)
            SELECT keyframe_id, full_text FROM ocr_texts;
            """
        )


def build_app_sqlite(release_dir: Path | str) -> Path:
    release_path = Path(release_dir)
    tables: dict[str, pd.DataFrame] = {}
    for name in TABLE_FILES:
        table_path = release_path / "tables" / f"{name}.parquet"
        if table_path.exists():
            tables[name] = pd.read_parquet(table_path)
    required = {"videos", "scenes", "shots", "keyframes", "text_documents", "feature_availability", "release_capabilities"}
    missing = sorted(required - set(tables))
    if missing:
        raise FileNotFoundError(f"missing merged table artifacts: {', '.join(missing)}")
    vector_map_path = release_path / "indexes" / "vector_map.parquet"
    if vector_map_path.exists():
        tables["vector_map"] = pd.read_parquet(vector_map_path)
    else:
        tables["vector_map"] = pd.DataFrame(columns=["index_name","index_version","embedding_model","vector_id","embedding_id","keyframe_id","video_id","frame_id"])
    sqlite_path = release_path / "db" / "app.sqlite"
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    write_sqlite(sqlite_path, tables)
    duckdb_path = release_path / "db" / "staging.duckdb"
    if duckdb_path.exists():
        duckdb_path.unlink()
    connection = duckdb.connect(str(duckdb_path))
    try:
        for name, frame in tables.items():
            connection.register("frame", _sqlite_safe(frame))
            connection.execute(f"CREATE TABLE {name} AS SELECT * FROM frame")
            connection.unregister("frame")
    finally:
        connection.close()
    return sqlite_path
