from __future__ import annotations

REQUIRED_FILES = {
    "db/app.sqlite",
    "db/staging.duckdb",
    "indexes/vector_map.parquet",
    "indexes/index_version.json",
    "tables/videos.parquet",
    "tables/shots.parquet",
    "tables/scenes.parquet",
    "tables/keyframes.parquet",
    "tables/text_sources.parquet",
    "tables/text_documents.parquet",
    "tables/feature_availability.parquet",
    "tables/embeddings_meta.parquet",
    "manifests/dataset_manifest.json",
    "raw_mapping/media_store_manifest.parquet",
}

REQUIRED_TABLES = {
    "videos",
    "scenes",
    "shots",
    "keyframes",
    "text_documents",
    "vector_map",
    "feature_availability",
    "release_capabilities",
    "text_documents_fts",
}

MEDIA_REF_COLUMNS = {
    "videos": ("video_ref",),
    "keyframes": ("keyframe_ref", "thumbnail_ref"),
}
