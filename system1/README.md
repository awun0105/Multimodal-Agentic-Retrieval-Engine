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

Two supported ways to prepare sample input:

Option A, copy an existing local sample input directory:

```bash
cp -R /path/to/sample/input ./input
```

Option B, import from an organizer source:

```bash
system1 import-source \
  --source-uri /path/or/google-drive-folder-url \
  --data-root input
```

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

`build-mini-seed` is a legacy dev helper that builds a tiny end-to-end debug release in one command.
The main path for the current MVP is the phase-based CLI pipeline above.
