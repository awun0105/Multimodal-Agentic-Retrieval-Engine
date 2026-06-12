# System 1: Ingestion Pipelines (Offline Staging)

## Status

Canonical Ingestion Architecture. Derived from `docs/references/original-sources/INGESTION.md`.

## Architectural Position

System 1 is an **offline, preprocessing, staging, and validation system**. It does not run during active retrieval. Its output is the App-Ready dataset loaded by System 2.

```text
raw data (videos, official keyframes)
  -> Task-specific Notebooks (CLIP, Whisper, OCR, Captions)
  -> Sharded output artifacts (JSONL, Parquet, NPY)
  -> DuckDB aggregation & validation
  -> app.sqlite + visual.faiss + local thumbnails
```

---

## 1. Shard-based Preprocessing Workflow

To allow team members to parallelize processing, the dataset is split into chunks (e.g., folder-based chunk `L01`, `L02`). Members run task-specific Jupyter notebooks independently on their local GPU workstations, Colab, or Kaggle.

### Notebook 1: Visual Feature Extraction (`NB_01_Vision_CLIP.ipynb`)
- **Task**: Extract frames at 1fps (or load official keyframes) and run CLIP text/image visual encoders.
- **Rules**: Load model once; batch process frames; release memory per video using garbage collection.
- **Output**: `temp_dense/{video_name}_dense.npy` containing vector matrices.

### Notebook 2: Audio Transcription (`NB_02_Audio_Whisper.ipynb`)
- **Task**: Extract audio track from videos and run OpenAI Whisper (base or small).
- **Rules**: Output transcript segments containing text and start/end time ranges.
- **Output**: `temp_sparse/{video_name}_transcript.json`.

### Notebook 3: OCR & Metadata (`NB_03_Metadata_OCR.ipynb`)
- **Task**: Run EasyOCR/PaddleOCR on keyframes. Parse organizer metadata JSONs.
- **Output**: `temp_sparse/{video_name}_ocr.json` and `temp_metadata/{video_name}_meta.json`.

---

## 2. Notebook Safety Constraints

Every processing notebook must enforce these guardrails:
1. **Dynamic Paths**: Paths must be configurable parameters at the top. No personal machine paths hardcoded.
2. **Checkpointing**: Check if the output file already exists before running inference. Skip processed videos.
3. **Identity standard**: Use name normalization to turn `L01/V001.mp4` to `{video_id}_{frame_id}`.
4. **RAM GC**: Explicitly call `del frames, features` and `gc.collect()` at the end of each video processing loop.

---

## 3. DuckDB Staging & Aggregation

Once the processing chunks are complete, they are copied to the host machine. The aggregator script `00_Merge_To_DataReady.py` uses DuckDB to build the final runtime database.

DuckDB scope:
1. **Bulk Import**: Read sharded JSON, JSONL, Parquet, and NPY files.
2. **Normalize and Clean**: Join transcripts, OCR, object tables, and media info. Resolves frame time offsets.
3. **Build Runtime DB**: Insert aggregated rows into the runtime `app.sqlite` tables.
4. **Concatenate Vectors**: Join individual `.npy` outputs into one continuous array to build `visual.faiss`.
5. **Validation Report**: Run validation queries to check path integrity and missing dependencies.

---

## 4. Ingestion Output Contract

The completed aggregation must deposit exactly:
- `data/db/app.sqlite` (Containing SQLite WAL tables and FTS5 indices)
- `data/indexes/visual.faiss` (Vector index)
- `data/media/` (Standard structured videos, keyframes, and generated thumbnails)
