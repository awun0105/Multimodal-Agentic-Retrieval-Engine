# System 1

System 1 is the offline HCMAI data factory. It converts raw videos and metadata into app-ready release artifacts for System 2.

## Expected input layout

```text
input/
  raw_videos/*.mp4
  metadata/*.json
```

Video and canonical metadata are paired by filename stem. Organizer metadata is
optional source evidence, but the Notebook 00B/00C target creates one
schema-valid canonical metadata JSON for every video before raw upload.

## Sample input requirement

The phase-based pipeline expects:

```text
input/
  raw_videos/
    *.mp4
  metadata/
    *.json
```

Each video and canonical metadata file must share the same stem, for example:

```text
input/raw_videos/L21_V001.mp4
input/metadata/L21_V001.json
```

A clean clone will not run E2E until this input directory is prepared.

Primary shared storage uses exactly two Hugging Face Dataset repos:

```text
AIOU26_raw
  canonical raw dataset repo: raw_videos/, required canonical metadata/,
  raw-level manifests and audits; no duplicate organizer_metadata/ tree
  canonical_raw_vXXX/manifests/missing_metadata.json
  canonical_raw_vXXX/manifests/unmatched_metadata.json

AIOU26_release
  processed workspace + final release repo:
  phase00_ingestion/, worker and caption packages, checkpoints/, logs/
```

Google Drive may still be used as an organizer handoff source or operator
scratch area, but it is not the primary shared storage contract.

Notebook 00 has two upload targets:

```text
Canonical raw output
  -> AIOU26_raw/canonical_raw_vXXX/

Phase00 ingestion, batch planning, and pipeline reports
  -> AIOU26_release/canonical_release_vXXX/phase00_ingestion/
```

`missing_metadata.json` and `unmatched_metadata.json` are raw-level audit
manifests in `AIOU26_raw`. The release repo may also snapshot them under
`AIOU26_release/canonical_release_vXXX/phase00_ingestion/reports/` for a
particular run.

Notebook 00 workflow for Colab/local source preparation:

```text
organizer Google Drive folder
  -> drive-shadow into your Drive folder
  -> 00A: older full-standardization compatibility path
  -> 00B: Colab/Drive streaming path
  -> 00C: local-machine streaming path
  -> stream path extracts one video/organizer-metadata pair at a time,
     probes the video, creates canonical metadata, validates it, and uploads
     canonical raw files to AIOU26_raw
  -> ingest from AIOU26_raw
  -> assign-batches
  -> upload phase00 ingestion outputs to AIOU26_release/phase00_ingestion
```

Use these commands directly only when debugging outside the notebook:

```bash
system1 import-canonical-raw \
  --source-dir /content/drive/MyDrive/AIOU26/raw_dataset \
  --output input \
  --raw-import-id canonical_raw_v003

system1 drive-shadow \
  --source-folder-id organizer-folder-id \
  --dest-folder-id your-drive-folder-id \
  --report-path output/drive_shadow_report.json

system1 standardize-archives \
  --source-dir /content/drive/MyDrive/AIOU26/raw_dataset \
  --target-dir input \
  --temp-dir /content/temp_extraction

system1 stream-standardize-upload-raw \
  --source-dir /content/drive/MyDrive/AIOU26/raw_dataset \
  --target-hf-repo-id your-org/AIOU26_raw \
  --raw-import-id canonical_raw_v003 \
  --scratch-dir /content/aic_scratch \
  --progress-path /content/drive/MyDrive/AIOU26/stream_standardize_upload_progress.jsonl

system1 ingest \
  --input input \
  --output output

system1 assign-batches \
  --num-batches 1 \
  --output output

system1 sync-phase00-ingestion \
  --output output \
  --hf-repo-id your-org/AIOU26_release

system1 restore-phase00-ingestion \
  --release-id canonical_release_v003 \
  --hf-repo-id your-org/AIOU26_release \
  --output output

system1 sync-structure-artifacts \
  --output output \
  --hf-repo-id your-org/AIOU26_release \
  --release-id canonical_release_v003 \
  --batch-id batch_000 \
  --worker-id worker_local_01

system1 restore-structure-artifacts \
  --output output \
  --hf-repo-id your-org/AIOU26_release \
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

Canonical metadata retains the ten observed organizer fields (`author`,
`channel_id`, `channel_url`, `description`, `keywords`, `length`,
`publish_date`, `thumbnail_url`, `title`, and `watch_url`) plus `video_id`,
`organizer_metadata_present`, `media` probe facts, and `provenance`. Missing
organizer scalar values are `null`, missing keywords are `[]`, and the package
must not fabricate a title or URL. See ADR 0016 and
`docs/architecture/data-contracts.md` for the full contract.

Fallback, use an existing standardized input directory:

```bash
cp -R /path/to/sample/input ./input
```

`import-canonical-raw` is the CLI wrapper around source-folder staging,
standardization, probing, and raw upload. `sync-phase00-ingestion` and
`restore-phase00-ingestion` use the phase00 Hugging Face layout for
Notebook 00 outputs. Restore keeps the canonical `phase00_ingestion/` snapshot
and materializes `tables/`, `raw_mapping/`, `frame_timeline/`, and
`manifests/` into the local release layout.

## Local setup

```bash
cd system1
uv sync                    # Phase00 ingest and tests
uv sync --extra worker     # per-video worker and caption pass (GPU)
uv sync --extra release    # build-release --publish (huggingface_hub 1.x)
```

## Pipeline commands

After Phase00 (`ingest`, `assign-batches`, `sync-phase00-ingestion`):

- `system1 worker-batch`: per-video worker (ADR 0023), one package per video.
- `system1 caption-batch`: caption pass over worker packages (ADR 0025).
- `system1 build-release [--publish --bucket-id ... --bucket-prefix ...]`:
  merges packages, groups scenes (ADR 0026), writes SQLite, FAISS, and WebP
  media, and optionally publishes to the Storage Bucket.

Settings live in `configs/worker.yaml`. The old `process-batch`,
`feature-batch`, `merge`, `build-db`, `build-index`, `validate`,
`smoke-test`, `release`, and structure sync commands were removed on
2026-10-26 (plan `system1-pipeline-simplification` Step 6).

## Notebook order

Run notebooks in this order (runbook: `notebooks/README.md`):

1. `notebooks/00B_master_ingestion_and_assignment.ipynb` (Colab, Drive) or
   `notebooks/00C_master_ingestion_local.ipynb` (local)
2. `notebooks/01_worker_batch.ipynb`
3. `notebooks/02_caption_batch.ipynb`
4. `notebooks/03_build_release.ipynb`

Notebooks hold settings and one CLI call each. They do not reimplement pipeline logic.

## Release output layout

The release layout and tables are defined in
`docs/architecture/data-contracts.md` and `schemas/v2/`.

## One-time TransNet artifact preparation

Runtime workers never convert TransNet weights. Prepare the project-owned
artifact once, upload it to the checkpoint dataset, then use the printed
checksum in `configs/models.yaml`.

### Canonical verified conversion

This is the preferred path when upstream Git LFS can serve the official
TensorFlow weights. In a controlled Colab preparation runtime with TensorFlow,
PyTorch, Git LFS, and an `HF_TOKEN` that can write to the checkpoint dataset,
run:

```bash
git clone --branch ASR --single-branch https://github.com/awun0105/Multimodal-Agentic-Retrieval-Engine.git
cd Multimodal-Agentic-Retrieval-Engine/system1
git lfs install
python -m pip install -q -e ".[worker]"
python -m pip install -q tensorflow torch
python scripts/prepare_transnetv2_artifact.py \
  --output-dir /content/transnetv2-artifact \
  --repo-id 1thesudden/AIOU26_checkpoints \
  --repo-type dataset \
  --revision main \
  --path-in-repo model_artifacts/transnetv2/85cef72af9a916bdfd7cc94a670c9cdfbf12d1ed
```

The script checks out the pinned official commit, runs the official converter's
single-head and many-head parity tests, uploads the resulting artifact to the
configured checkpoint dataset, and prints the exact checksum to place at
`phase01.shot_detection.weights_sha256` in `configs/models.yaml`. Public and
private checkpoint datasets are supported; pass `--require-private` only when a
private model-artifact repo is required.

If this path fails with `This repository exceeded its LFS budget`, the blocker
is upstream GitHub LFS quota on `soCzech/TransNetV2`; it is not an `HF_TOKEN` or
checkpoint dataset permission issue.

### Mirror-based unblock path

Use this only when the canonical Git LFS path is quota-blocked and the project
accepts a preconverted PyTorch mirror. This path still copies
`transnetv2_pytorch.py` from the pinned official commit, verifies the official
source SHA-256, downloads the preconverted weights from Hugging Face, verifies
the expected weights SHA-256, and writes
`artifact_origin=preconverted_huggingface_mirror` with
`conversion_verified=false` in the manifest.

```bash
git clone --branch ASR --single-branch https://github.com/awun0105/Multimodal-Agentic-Retrieval-Engine.git
cd Multimodal-Agentic-Retrieval-Engine/system1
python -m pip install -q -e ".[worker]"
python scripts/prepare_transnetv2_artifact.py \
  --output-dir /content/transnetv2-artifact \
  --preconverted-weights-repo-id Sn4kehead/TransNetV2 \
  --preconverted-weights-filename transnetv2-pytorch-weights.pth \
  --expected-weights-sha256 834b10f25ae9e1b4e4f2652fe2843bd2b1388057a435d68b7c52635578fcc04d \
  --repo-id 1thesudden/AIOU26_checkpoints \
  --repo-type dataset \
  --revision main \
  --path-in-repo model_artifacts/transnetv2/85cef72af9a916bdfd7cc94a670c9cdfbf12d1ed
```

For mirror artifacts, `configs/worker.yaml` sets `models.shot_detection.conversion_verified: false`;
the worker rejects unverified conversion manifests unless that flag says so.
