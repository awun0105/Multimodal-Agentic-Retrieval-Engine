# System 1: Ingestion And Preprocessing

## Status

Canonical for offline preprocessing. System 1 produces the app-ready contract in `docs/architecture/data-contracts.md` and never serves live user queries.

## Responsibility

System 1 converts raw organizer data and generated signals into validated app-ready artifacts. System 2 reads only SQLite, FTS5 tables, FAISS indexes, and logical media refs produced by this system.

```text
raw organizer files
  -> dataset registration
  -> media discovery
  -> metadata normalization
  -> thumbnail/keyframe normalization
  -> OCR / ASR / caption / object extraction or import
  -> embedding generation/import
  -> DuckDB staging and validation
  -> SQLite WAL + FTS5 + FAISS + validation reports
```

## Required Stages

| Stage | Required Output | Notes |
| --- | --- | --- |
| Dataset registration | `datasets` row and build manifest | Assign stable `dataset_id`, source version, build time, and source roots. |
| Media discovery | `videos`, discovered media manifest | Discover videos/keyframes from configurable roots; do not hardcode personal paths. |
| Metadata normalization | normalized staging tables | Titles, source/channel, duration, fps, dimensions, official annotations, and tags. |
| Keyframe normalization | `keyframes` rows and media refs | Use `keyframe_id = "{video_id}:{frame_id}"`; store logical refs only. |
| Thumbnail generation | `thumbnail_ref` per keyframe | Generate missing thumbnails under `${AIC_DATA_ROOT}/processed/media/thumbnails/`. |
| OCR import/generation | `ocr_texts`, `ocr_fts` | Preserve confidence and optional boxes when available. |
| ASR import/generation | `asr_segments`, `asr_fts` | ASR is usually time-range evidence on `video_id`; optional alignment links to keyframes. |
| Caption import/generation | `captions`, `caption_fts` | Captions may be keyframe-level or segment-level, but UI results resolve to keyframes. |
| Object/concept import | `objects`, `object_fts` | Preserve label, score, optional box, source, and model/version. |
| Embedding import/generation | FAISS index + `vector_map` | FAISS rows must resolve through SQLite before returning results. |
| Validation | validation report and failure status | App-ready build is usable only when required checks pass. |

## CLI Contract

Preprocessing must be runnable from batch CLI scripts. Minimum interface:

```text
aic-prepare build \
  --dataset-id aic2026 \
  --input-root ${AIC_DATA_ROOT}/raw \
  --data-root ${AIC_DATA_ROOT} \
  --runtime-root ${AIC_RUNTIME_ROOT} \
  --report ${AIC_DATA_ROOT}/staging/reports/aic2026-validation.json
```

CLI rules:

- Accept input roots and output roots as config or flags.
- Write large media/staging artifacts under `${AIC_DATA_ROOT}`.
- Write hot runtime artifacts under `${AIC_RUNTIME_ROOT}`.
- Emit machine-readable validation reports.
- Fail non-zero when required validation checks fail.
- Support resumable shard processing for long-running OCR/ASR/embedding jobs.
- Never require absolute paths embedded in SQLite.

## Artifact Outputs

```text
${AIC_DATA_ROOT}/processed/media/videos/{video_id}.mp4
${AIC_DATA_ROOT}/processed/media/keyframes/{video_id}/{frame_id_padded}.jpg
${AIC_DATA_ROOT}/processed/media/thumbnails/{video_id}/{frame_id_padded}.webp
${AIC_DATA_ROOT}/warehouse/warehouse.duckdb
${AIC_DATA_ROOT}/staging/reports/{dataset_id}-validation.json
${AIC_RUNTIME_ROOT}/db/app.sqlite
${AIC_RUNTIME_ROOT}/indexes/visual.faiss
${AIC_RUNTIME_ROOT}/indexes/visual_index_manifest.json
```

The earlier `data/` tree in source material is a logical artifact layout, not a physical repository layout.

## Validation Gate

System 1 must prove:

- No duplicate `video_id` and no duplicate `(video_id, frame_id)`.
- Every `keyframe_id` matches `"{video_id}:{frame_id}"`.
- Every logical media ref resolves through `MediaStorePort`.
- Every keyframe has a thumbnail ref.
- Every FAISS vector has a `vector_map` row.
- Every `vector_map.keyframe_id` exists in `keyframes`.
- Caption, OCR, and object rows point to existing keyframes.
- ASR rows point to existing videos and valid time ranges.
- SQLite contains no absolute or machine-specific paths.
- FTS5 row counts match source relational tables or documented expectations.
