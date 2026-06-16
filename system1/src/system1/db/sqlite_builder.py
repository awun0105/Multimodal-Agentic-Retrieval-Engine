from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd


def write_sqlite(sqlite_path: Path, tables: dict[str, pd.DataFrame]) -> None:
    if sqlite_path.exists():
        sqlite_path.unlink()
    with sqlite3.connect(sqlite_path) as connection:
        for name in (
            "videos", "scenes", "shots", "keyframes", "asr_segments", "shot_transcript_links", "scene_transcript_links",
            "ocr", "objects", "image_captions", "shot_captions", "scene_summaries_initial", "scene_summaries_enriched",
            "embeddings_meta", "text_documents", "vector_map", "feature_availability", "release_capabilities",
        ):
            tables[name].to_sql(name, connection, index=False, if_exists="replace")
        connection.executescript(
            """
            CREATE UNIQUE INDEX pk_videos ON videos(video_id);
            CREATE UNIQUE INDEX pk_scenes ON scenes(scene_id);
            CREATE UNIQUE INDEX pk_shots ON shots(shot_id);
            CREATE UNIQUE INDEX pk_keyframes ON keyframes(keyframe_id);
            CREATE UNIQUE INDEX pk_embeddings_meta ON embeddings_meta(embedding_id);
            CREATE UNIQUE INDEX uq_vector_map_index_vector ON vector_map(index_name, vector_id);
            CREATE INDEX idx_keyframes_video_frame ON keyframes(video_id, frame_id);
            CREATE INDEX idx_keyframes_shot ON keyframes(shot_id);
            CREATE INDEX idx_keyframes_scene ON keyframes(scene_id);
            CREATE INDEX idx_shots_video_range ON shots(video_id, start_frame, end_frame);
            CREATE INDEX idx_scenes_video_range ON scenes(video_id, start_frame, end_frame);
            CREATE INDEX idx_vector_map_keyframe ON vector_map(keyframe_id);
            CREATE INDEX idx_vector_map_vector ON vector_map(index_name, vector_id);
            CREATE INDEX idx_text_documents_entity ON text_documents(level, entity_id);
            CREATE VIRTUAL TABLE text_documents_fts USING fts5(document_id UNINDEXED, normalized_text, normalized_no_diacritics, tokenize='unicode61');
            INSERT INTO text_documents_fts(document_id, normalized_text, normalized_no_diacritics)
            SELECT document_id, normalized_text, normalized_no_diacritics FROM text_documents;
            """
        )
