# Ingestion System V2

This file defines the practical ingestion system for the multimedia retrieval
web app.

The goal is simple:

```text
official data -> normalized DB/indexes/media assets -> app can search and inspect
```

Keep the original `INGESTION.md` for comparison. This version is the simplified
implementation direction.

## 1. What Ingestion Must Produce

The retrieval app needs:

- a video/frame registry;
- thumbnails for fast result grids;
- keyframes for inspection;
- raw or preview videos for playback;
- normalized object/OCR/ASR/caption/metadata evidence;
- vector and text indexes;
- stable mappings from search results to media.

The live app should not scan folders or process raw videos during search.

## 2. Storage Decision

Raw data is too large for the internal SSD, so raw media should live on the
external HDD.

Recommended split:

```text
Internal SSD:
  app.sqlite
  indexes/
  processed/thumbs_hot/        # optional cache if space allows

External HDD:
  raw/videos/
  raw/keyframes_official/
  raw/embeddings_official/
  raw/objects/
  raw/metadata/
  processed/keyframes/
  processed/thumbs/
  processed/previews/
  processed/dense_frame_cache/ # optional/on-demand only
```

Priority if SSD is small:

1. SQLite DB.
2. FAISS/text indexes.
3. hot thumbnail cache.
4. everything else on external HDD.

## 3. MinIO Position

MinIO can be used as an optional object-store layer over the external HDD.

Use MinIO for:

- raw videos;
- official keyframes;
- generated keyframes;
- preview videos;
- large immutable artifacts.

Do not depend on MinIO for search. Search reads only SQLite/FAISS/text indexes.

Recommended design:

```text
MediaStore
  - LocalFileMediaStore
  - MinioMediaStore
```

The database stores a URI, not a hardcoded local path:

```text
file:///mnt/wd/aic/raw/videos/L21_V001.mp4
s3://aic-raw/videos/L21_V001.mp4
```

The frontend should not care whether media comes from a file path or MinIO. The
backend resolves media URIs and serves URLs/streams.

## 4. Input Data We Should Support

The 2026 dataset is not confirmed, so ingestion must accept optional inputs.

Possible organizer inputs:

```text
raw videos
official keyframes
official CLIP embeddings
metadata JSON/CSV
object detection JSON
OCR/transcript/caption files if provided
query files
```

The importer should detect available folders and skip missing ones cleanly.

Do not hardcode one prior-year folder layout as the only accepted format.

## 5. App-Ready Data Layout

Use this layout for generated app data:

```text
data/
  raw/
    videos/
    keyframes_official/
    embeddings_official/
    objects/
    metadata/

  processed/
    thumbs/
    keyframes/
    previews/
    dense_frame_cache/

  indexes/
    visual.faiss
    text.sqlite

  app.sqlite
```

Notes:

- `dense_frame_cache/` is optional and generated only around inspected clips.
- Do not extract every frame from every video by default.
- Raw videos remain the playback source.
- Search uses precomputed DB/indexes and thumbnails/keyframes.

## 6. SQLite Contract

Start with one SQLite database: `app.sqlite`.

Minimum tables:

```text
videos
  video_id TEXT PRIMARY KEY
  uri TEXT
  fps REAL
  duration REAL
  width INTEGER
  height INTEGER
  metadata_json TEXT

frames
  id INTEGER PRIMARY KEY
  video_id TEXT
  frame_id INTEGER
  timestamp REAL
  thumb_uri TEXT
  keyframe_uri TEXT
  source TEXT              # official_keyframe, sampled, cache

objects
  id INTEGER PRIMARY KEY
  video_id TEXT
  frame_id INTEGER
  name TEXT
  score REAL
  box_json TEXT
  source TEXT

evidence
  id INTEGER PRIMARY KEY
  video_id TEXT
  frame_id INTEGER NULL
  start_time REAL NULL
  end_time REAL NULL
  type TEXT                # metadata, ocr, asr, caption, summary
  text TEXT
  score REAL NULL
  source TEXT

embedding_map
  row_id INTEGER
  video_id TEXT
  frame_id INTEGER
  source TEXT              # official_clip, openclip, caption_e5
```

Important:

- ASR is usually time-range evidence, not exact frame evidence.
- Object detections should keep boxes and scores, not only counts.
- Object counts can be derived later for filtering.

## 7. Index Contract

### Visual Index

Use FAISS for visual/vector search:

```text
indexes/visual.faiss
```

Mapping from FAISS row to frame:

```text
embedding_map(row_id, video_id, frame_id, source)
```

If official embeddings are provided, import them first. Generate our own
embeddings only if official embeddings are missing or weak.

### Text Index

Use SQLite FTS5 first:

```text
indexes/text.sqlite
```

Index text from:

- metadata;
- OCR;
- ASR;
- captions;
- object names;
- summaries if available.

Use heavier text search only if FTS5 is proven insufficient.

## 8. Ingestion Pipeline

Recommended steps:

```text
1. scan inputs
2. register videos
3. register official keyframes
4. generate thumbnails
5. import official embeddings
6. normalize object JSON
7. import metadata
8. optional OCR on keyframes
9. optional ASR on videos
10. optional captions on keyframes/segments
11. build FAISS index
12. build FTS5 index
13. validate app-ready dataset
```

Do not run expensive optional extraction before P0 data is usable.

## 9. Preprocessing Priority

P0:

- video registry;
- keyframe registry;
- thumbnail generation;
- official embedding import if available;
- object JSON normalization;
- metadata import;
- SQLite DB build;
- FAISS/text index build;
- validation report.

P1:

- OCR on keyframes;
- better object filters;
- preview video generation;
- similar-frame index support.

P2:

- ASR with timestamps;
- captions on representative frames/segments.

P3:

- LLM summaries;
- chronological event timelines;
- generated dense-frame cache for selected videos.

## 10. Shardable Processing

Heavy work must be shardable so teammates, Colab, and Kaggle can share it.

Example:

```text
prepare-shard --shard-id 0 --num-shards 20
prepare-shard --shard-id 1 --num-shards 20
...
merge-shards
validate-artifacts
build-indexes
```

Each shard output should contain:

```text
manifest_part.jsonl
frames_part.jsonl
objects_part.jsonl
evidence_part.jsonl
embeddings_part.npy
embedding_map_part.jsonl
checksums.json
```

Shard rules:

- deterministic naming;
- no duplicate shard ownership;
- checkpoint every video;
- skip already completed outputs;
- do not hardcode personal paths;
- write checksums.

## 11. Merge Step

The merge step runs on the host machine:

```text
1. collect shard outputs
2. verify checksums
3. merge manifests
4. build app.sqlite
5. concatenate/import embeddings
6. build visual.faiss
7. build text.sqlite
8. validate media URI resolution
9. write validation report
```

Validation must catch:

- missing video files;
- missing thumbnails;
- missing keyframes;
- duplicate video/frame IDs;
- FAISS rows without DB mapping;
- DB frames without media assets;
- object/evidence rows pointing to unknown frames;
- invalid MinIO/file URIs.

## 12. Live App Contract

At runtime, the retrieval app should:

- read `app.sqlite`;
- load FAISS/text indexes;
- return frame results with media URLs;
- show thumbnails/keyframes;
- stream raw/preview video only when a candidate is opened.

At runtime, the retrieval app should not:

- scan raw folders;
- run OCR/ASR/captioning;
- extract all frames;
- list MinIO buckets during search;
- depend on internet/cloud APIs.

## 13. Key Design Corrections From The Original Draft

- Raw videos are not used during search, but they are still needed for playback
  and final inspection.
- The input folder structure must be flexible because 2026 is not confirmed.
- JSON mappings are okay for shard/debug output, but SQLite should be the main
  registry.
- ASR should be stored as time ranges, not fake per-frame text.
- Object detections should keep boxes and scores, not only counts.
- Full-frame extraction is not a default artifact.
- LLM fusion and cloud models are optional, not required for P0.
- MinIO is a media storage option, not the search source of truth.

