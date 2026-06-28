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
  --hf-repo-id your-org/AIC26_release \
  --hf-prefix canonical_release_v003/phase00_ingestion

system1 restore-phase00-ingestion \
  --release-id competition_dataset_v001 \
  --hf-repo-id your-org/AIC26_release \
  --hf-prefix canonical_release_v003/phase00_ingestion \
  --output output
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
Notebook 00 outputs.

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

Hugging Face shared layout:

```text
AIC26_release/canonical_release_vXXX/
  phase00_ingestion/
    tables/
    raw_mapping/
    manifests/
    reports/
  phase01_structure/
  phase02_features/
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

Local final release layout:

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
