# System 1

System 1 is the offline HCMAI data factory. It converts raw videos and metadata into app-ready release artifacts for System 2.

## Expected input layout

```text
input/
  raw_videos/*.mp4
  metadata/*.json
```

Video and metadata are paired by filename stem.

## Sample input requirement

The phase-based pipeline expects:

```text
input/
  raw_videos/
    *.mp4
  metadata/
    *.json
```

Each video and metadata file must share the same stem, for example:

```text
input/raw_videos/L21_V001.mp4
input/metadata/L21_V001.json
```

A clean clone will not run E2E until this input directory is prepared.

Primary shared storage uses exactly two Hugging Face Dataset repos:

```text
AIC26_raw
  canonical raw dataset repo: raw_videos/, metadata/, raw-level manifests,
  raw-level missing/unmatched audit manifests
  canonical_raw_vXXX/manifests/missing_metadata.json
  canonical_raw_vXXX/manifests/unmatched_metadata.json

AIC26_release
  processed workspace + final release repo:
  phase00_ingestion/, phase01_structure/, phase02_features/,
  phase03_merged/, releases/, checkpoints/, logs/
```

Google Drive may still be used as an organizer handoff source or operator
scratch area, but it is not the primary shared storage contract.

Notebook 00 has two upload targets:

```text
Canonical raw output
  -> AIC26_raw/canonical_raw_vXXX/

Phase00 ingestion, batch planning, and pipeline reports
  -> AIC26_release/canonical_release_vXXX/phase00_ingestion/
```

`missing_metadata.json` and `unmatched_metadata.json` are raw-level audit
manifests in `AIC26_raw`. The release repo may also snapshot them under
`AIC26_release/canonical_release_vXXX/phase00_ingestion/reports/` for a
particular run.

Notebook 00 workflow for Colab/local source preparation:

```text
organizer Google Drive folder
  -> drive-shadow into your Drive folder
  -> 00A: standardize-archives into input/raw_videos + input/metadata, then upload canonical raw files to AIC26_raw
  -> 00B: stream-standardize-upload-raw extracts one zip pair at a time into local scratch and uploads canonical raw files to AIC26_raw
  -> ingest from AIC26_raw
  -> assign-batches
  -> upload phase00 ingestion outputs to AIC26_release/phase00_ingestion
```

Use these commands directly only when debugging outside the notebook:

```bash
system1 import-canonical-raw \
  --source-dir /content/drive/MyDrive/AIC2026/raw_dataset \
  --output input \
  --raw-import-id canonical_raw_v003

system1 drive-shadow \
  --source-folder-id organizer-folder-id \
  --dest-folder-id your-drive-folder-id \
  --report-path output/drive_shadow_report.json

system1 standardize-archives \
  --source-dir /content/drive/MyDrive/AIC2026/raw_dataset \
  --target-dir input \
  --temp-dir /content/temp_extraction

system1 stream-standardize-upload-raw \
  --source-dir /content/drive/MyDrive/AIC2026/raw_dataset \
  --target-hf-repo-id your-org/AIC26_raw \
  --raw-import-id canonical_raw_v003 \
  --scratch-dir /content/aic_scratch \
  --progress-path /content/drive/MyDrive/AIC2026/stream_standardize_upload_progress.jsonl

system1 ingest \
  --mode debug_small_sample \
  --input input \
  --output output

system1 assign-batches \
  --mode debug_small_sample \
  --num-batches 1 \
  --output output

system1 sync-phase00-ingestion \
  --output output \
  --hf-repo-id your-org/AIC26_release

system1 restore-phase00-ingestion \
  --release-id canonical_release_v003 \
  --hf-repo-id your-org/AIC26_release \
  --output output

system1 sync-structure-artifacts \
  --output output \
  --hf-repo-id your-org/AIC26_release \
  --release-id canonical_release_v003 \
  --batch-id batch_000 \
  --worker-id worker_local_01

system1 restore-structure-artifacts \
  --output output \
  --hf-repo-id your-org/AIC26_release \
  --release-id canonical_release_v003 \
  --batch-id batch_000
```

`standardize-archives` writes:

```text
input/
  raw_videos/
  metadata/
  standardize_archives_report.json
```

By default it moves `.mp4`, `.mov`, `.mkv`, `.avi`, `.webm`, and `.wav`
files into `raw_videos/`, and `.json` files into `metadata/`.
Both commands fail non-zero when item-level errors are recorded. Existing
matching archive outputs are skipped on rerun; use `--overwrite` only when you
intend to replace target files. Use `--allow-partial` only for manual recovery
when ingest should proceed despite a partial input-prep report.

Fallback, use an existing standardized input directory:

```bash
cp -R /path/to/sample/input ./input
```

`import-canonical-raw` is the CLI wrapper around source-folder staging,
standardization, probing, and raw upload. `sync-phase00-ingestion` and
`restore-phase00-ingestion` use the phase00 Hugging Face layout for
Notebook 00 outputs. Restore keeps the canonical
`phase00_ingestion/` snapshot and materializes `tables/`, `raw_mapping/`, and
`manifests/` into the active local release layout used by `process-batch`.
`sync-structure-artifacts` and
`restore-structure-artifacts` map local phase01 structure ZIPs and worker
reports to and from the Hugging Face `phase01_structure` layout. Notebook 01 is
the thin worker orchestration for those commands; the current package can
produce valid structure artifact packages, but the production semantic
algorithms behind `process-batch` are still provider work.

## Local setup

```bash
cd system1
uv sync
```

## Main phase-based pipeline

Run this exact order for the current MVP mock pipeline:

Verified clean mock E2E sequence:

```bash
rm -rf output/competition_dataset_v001

system1 ingest \
  --mode debug_small_sample \
  --input input \
  --output output

system1 assign-batches \
  --mode debug_small_sample \
  --num-batches 1 \
  --output output

system1 process-batch \
  --worker-id worker_clean \
  --batch-id batch_000 \
  --mode debug_small_sample \
  --providers mock \
  --input input \
  --output output

system1 feature-batch \
  --worker-id worker_clean \
  --batch-id batch_000 \
  --mode debug_small_sample \
  --providers mock \
  --input input \
  --output output

system1 merge \
  --mode debug_small_sample \
  --output output

system1 build-index \
  --mode debug_small_sample \
  --output output

system1 build-db \
  --mode debug_small_sample \
  --output output

system1 validate \
  --mode debug_small_sample \
  --output output

system1 smoke-test \
  --release output/competition_dataset_v001
```

Expected debug/mock E2E result:

- `validation_report.json` status: `pass`
- `smoke_test_report.json` status: `pass`
- `release_usable`: `true`
- `visual_search`: `degraded` in debug mode because the visual index may be a stub
- `media_resolved`: `true`
- `FTS query returned`: `true`

## Notebook order

Run notebooks in this order:

1. `notebooks/00_master_ingestion_and_assignment.ipynb`
2. `notebooks/01_worker_structure_pipeline.ipynb`
3. `notebooks/02_worker_feature_enrichment.ipynb`
4. `notebooks/03_merge_validate_index_release.ipynb`

Notebooks are thin orchestration only. They should call CLI commands or thin `src/system1` helpers, not reimplement pipeline logic.

## Release output layout

Current local package layout produced by the System 1 CLI:

```text
output/competition_dataset_v001/
  artifacts/
    structure/
      L21_V001_structure.zip
      L21_V002_structure.zip
    features/
      L21_V001_features.zip
      L21_V002_features.zip
  manifests/
    worker_reports/
      structure_batch_000_worker_000.json
      features_batch_000_worker_000.json
```

The local CLI packages artifact ZIPs and worker reports in the release output
tree. Phase01 structure Hugging Face sync/restore is handled by
`sync-structure-artifacts` and `restore-structure-artifacts`; phase02 features
sync/restore remains a separate future workflow target.

Phase01 structure mapping:

```text
Local:
  artifacts/structure/{video_id}_structure.zip
  manifests/worker_reports/structure_{batch_id}_{worker_id}.json

HF:
  canonical_release_vXXX/phase01_structure/artifacts/{batch_id}/{video_id}_structure.zip
  canonical_release_vXXX/phase01_structure/worker_reports/structure_{batch_id}_{worker_id}.json
```

`sync-structure-artifacts` reads `manifests/{batch_id}.txt`, validates each
structure ZIP manifest/checksum before upload, and uploads only artifacts in
that batch. `restore-structure-artifacts` downloads structure ZIPs and worker
reports for one batch back into the local layout; it does not extract ZIPs.

Notebook 01 target responsibility:

```text
setup runtime + package
  -> restore phase00_ingestion from AIC26_release
  -> materialize tables/raw_mapping/manifests for process-batch
  -> read manifests/{batch_id}.txt
  -> process only that batch
  -> write artifacts/structure/{video_id}_structure.zip
  -> write manifests/worker_reports/structure_{batch_id}_{worker_id}.json
  -> sync those batch artifacts to phase01_structure
```

`process-batch` should reuse phase00 video facts from `tables/videos.parquet`
and `raw_mapping/media_store_manifest.parquet` instead of re-probing every
video. It may stage only the current video/metadata pair from `AIC26_raw` or a
local input directory into scratch, but it must not copy the full raw dataset
into runtime storage.

The target phase01 structure package is semantic-light structure, not final
feature enrichment. It should contain shot rows, selected keyframes, thumbnails,
ASR/transcript rows when configured, minimum keyframe/image caption rows needed
for scene construction, scene rows, scene summaries, package manifests,
checksums, and errors. Algorithm choices are provider/config driven; docs
should not hardcode a specific shot detector, captioning model, or ASR model
before those providers are chosen. Current mock/fallback code may emit one
full-video shot/scene and first-frame keyframe while those providers are
unfinished.

Target per-video structure ZIP layout:

```text
{video_id}_structure.zip
└── {video_id}/
    ├── metadata_normalized.json
    ├── asr_segments.parquet
    ├── shots.parquet
    ├── scenes.parquet
    ├── keyframes.parquet
    ├── image_captions.parquet
    ├── shot_transcript_links.parquet
    ├── scene_transcript_links.parquet
    ├── scene_summaries.parquet
    ├── keyframes/
    ├── thumbnails/
    ├── manifest.json
    ├── artifact_manifest.json
    ├── checksums.json
    └── errors.jsonl
```

Hugging Face shared target layout:

```text
AIC26_release/canonical_release_vXXX/
  phase00_ingestion/
    tables/
    raw_mapping/
    manifests/
    reports/
  phase01_structure/
    artifacts/
      batch_000/
        L21_V001_structure.zip
    worker_reports/
      structure_batch_000_worker_000.json
  phase02_features/
    artifacts/
      batch_000/
        L21_V001_features.zip
    worker_reports/
      features_batch_000_worker_000.json
  phase03_merged/
  releases/
  checkpoints/
  logs/
```

`phase00_ingestion` is not the final runtime release. The final app-ready
release for System 2 lives under:

```text
AIC26_release/canonical_release_vXXX/releases/competition_dataset_vXXX/
```

Legacy flat paths under
`canonical_release_vXXX/{manifests,tables,raw_mapping}` are deprecated. New
outputs should use
`canonical_release_vXXX/phase00_ingestion/{manifests,tables,raw_mapping,reports}`.

Local final release layout after merge/index/release:

```text
output/competition_dataset_v001/
  tables/
  artifacts/
  media/
  indexes/
  db/
  manifests/
  raw_mapping/
```

## Inspect release health

Check these first:

- `manifests/validation_report.json`
- `manifests/smoke_test_report.json`
- `manifests/merge_report.json`

## Legacy dev helper

The legacy `build-mini-seed` one-command helper has been removed from the main CLI. Use the phase-based workflow above for dev, tests, and releases.
The main path for the current MVP is the phase-based CLI pipeline above.
