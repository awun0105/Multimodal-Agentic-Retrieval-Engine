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
  phase00_ingestion/, phase01_structure/, phase02_features/,
  phase03_merged/, releases/, checkpoints/, logs/
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
Notebook 00 outputs. Restore keeps the canonical
`phase00_ingestion/` snapshot and materializes `tables/`, `raw_mapping/`,
`frame_timeline/`, and `manifests/` into the active local release layout used by
`process-batch`.
`sync-structure-artifacts` and
`restore-structure-artifacts` map local phase01 structure ZIPs and worker
reports to and from the Hugging Face `phase01_structure` layout. Notebook 01 is
the thin worker orchestration for the production `phase01-worker-run` path. Package
code now owns release resolution/restore, persistent per-stage resume,
TransNet V2, search-band keyframes, default faster-whisper ASR with optional
pinned NeMo/Parakeet Vietnamese ASR, Vintern OCR, Qwen2.5-VL default shot
captions, and Gemini scene grouping/summaries, strict packaging, remote
checksum verification, and reports.

## Local setup

```bash
cd system1
uv sync

# Required for the production Notebook 01 path.
uv sync --extra phase01-production
```

## Main phase-based pipeline

Notebook 01 uses one package launcher. In every fresh runtime it runs a real
one-video smoke from pinned Hugging Face test data, then starts the assigned
batch only after smoke passes. There is no mode or provider selector. A typical
invocation after Phase00 is:

```bash
system1 phase01-worker-run \
  --batch-id batch_000 \
  --worker-id worker_000 \
  --release-id-override canonical_release_v001 \
  --hf-release-repo your-org/AIOU26_release \
  --hf-checkpoint-repo your-org/AIOU26_checkpoints \
  --output output \
  --sync
```

The smoke uses the package-configured release/checkpoint test repositories and
isolated `_smoke/<run_id>` prefixes; these are independent from the production
repository options above. Set `--skip-real-smoke` only when the current runtime
has already been verified and the operator intentionally accepts the skip.

Before changing the production NumPy/NeMo/Transformers contract, qualify a full
candidate stack in a fresh Colab Python 3.13 runtime:

```bash
python -m pip install -e system1
system1-phase01-qualify \
  --workspace /content/aic_phase01 \
  --candidate py313-nemo273
```

Installation and model checks run in separate subprocesses. Only a PASS
`phase01_runtime_qualification_v1.json` authorizes synchronizing the qualified
versions into `pyproject.toml`, `configs/models.yaml`, and `uv.lock`.

The override is needed for legacy Phase00 manifests without `completed_at`;
new manifests are auto-resolved when it is omitted. The checkpoint repository
may be public or private, but the configured token must have write access and
the preflight must pass its write/read proof. A public repository exposes its
intermediate checkpoint artifacts publicly. Before the first production run,
provision the verified TransNet artifact and set its generated `weights_sha256`
in `configs/models.yaml` as described below.

The older mock E2E remains a developer test path, injected only through guarded
test environment variables. It is not a user-facing Notebook 01 choice.

Verified clean mock E2E sequence:

```bash
rm -rf output/competition_dataset_v001

system1 ingest \
  --input input \
  --output output

system1 assign-batches \
  --num-batches 1 \
  --output output

AIC_ALLOW_TEST_PROVIDERS=1 AIC_SYSTEM1_TEST_PROVIDER_PROFILE=mock system1 process-batch \
  --worker-id worker_clean \
  --batch-id batch_000 \
  --input input \
  --output output

system1 feature-batch \
  --worker-id worker_clean \
  --batch-id batch_000 \
  --providers mock \
  --input input \
  --output output

system1 merge \
  --output output

system1 build-index \
  --output output

system1 build-db \
  --output output

system1 validate \
  --output output

system1 smoke-test \
  --release output/competition_dataset_v001
```

Expected mock E2E result:

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

Notebook 01 responsibility:

```text
setup runtime + package
  -> fresh subprocess runtime/import preflight
  -> pinned one-video HF smoke in test release/checkpoint namespaces
  -> require every Phase01 stage source=computed and validate remote checksum
  -> cleanup local smoke artifacts while retaining shared model cache
  -> restore Phase00 core tables + selected batch manifest from AIOU26_release
  -> restore only frame_timeline files referenced by that batch
  -> read manifests/{batch_id}.txt
  -> resolve versioned config and validate production dependencies
  -> restore and validate per-video/per-stage checkpoints
  -> process only that batch through the fixed production stages
  -> write artifacts/structure/{video_id}_structure.zip
  -> write manifests/worker_reports/structure_{batch_id}_{worker_id}.json
  -> sync those batch artifacts to phase01_structure
```

`process-batch` reuses Phase00 video facts from `tables/videos.parquet`
and `raw_mapping/media_store_manifest.parquet`, plus
`frame_timeline/{video_id}.parquet` when available, instead of re-probing every
video. It may stage only the current video/metadata pair from `AIOU26_raw` or a
local input directory into scratch, but it must not copy the full raw dataset
into runtime storage. If a decoded frame timeline is unavailable, the package
must fail that production video because canonical `frame_id` values require the
decoded original timeline. Explicit estimated/degraded mapping may remain only
in debug/test profiles and must never be hidden in notebook code.

The Phase01 structure package is semantic structure, not feature enrichment.
It contains shot rows, selected keyframes, thumbnails, production
ASR/transcript rows, OCR rows from selected keyframes, one canonical bilingual
shot-caption row per shot generated from that shot's representative keyframe,
scene rows, bilingual Gemini scene summaries, package manifests, checksums, and
errors.
Production phase01 standardizes on TransNet V2 for shot boundaries and
keyframes selected from bands centered at 20%/50%/80% of each shot. ASR defaults
to faster-whisper large-v3; Notebook 01 can opt into the pinned NeMo/Parakeet
Vietnamese provider through `asr_provider = "nemo"`. Legacy mock/fallback code
remains reachable only through guarded test injection and cannot be selected
from Notebook 01 or the public CLI.

The complete accepted production sequence and failure policy are documented in
`docs/architecture/system1-notebook01-production-pipeline.md`.

The accepted production scene-grouping target is documented in
`docs/architecture/system1-scene-grouping.md`. It uses overlapping multimodal
context/focus windows and structured boundary judgements, but deterministic
package code remains responsible for the complete scene partition, canonical
IDs/ranges, mappings, and validation. Unresolved Gemini/provider failure fails
the production video. The production implementation is in
`src/system1/scenes/grouping.py` and `src/system1/scenes/gemini_judge.py`;
fallback behavior is test/debug only.

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
python -m pip install -q -e ".[phase01-production]"
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
python -m pip install -q -e ".[phase01-production]"
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

For mirror artifacts, `configs/models.yaml` must intentionally set
`phase01.shot_detection.conversion_verified: false`; runtime validation rejects
unverified conversion manifests unless the resolved config explicitly selects
that policy. Until the checksum is configured, production preflight fails
intentionally before video processing.

Target per-video structure ZIP layout:

```text
{video_id}_structure.zip
└── {video_id}/
    ├── metadata_normalized.json
    ├── asr_segments.parquet
    ├── shots.parquet
    ├── scenes.parquet
    ├── keyframes.parquet
    ├── shot_captions.parquet
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

Target Notebook 02 consumes only these project-generated keyframes and emits
Gemini OCR, configured object detections, and separate SigLIP/BEiT3 embedding
matrices/index inputs. The final runtime release uses `siglip.faiss` and
`beit3.faiss` with shared `embeddings_meta` and `vector_map` keyed by
`(index_name, vector_id)`. The current `feature-batch`/single-index path remains
debug compatibility code and is not production Notebook 02 completion.

Hugging Face shared target layout:

```text
AIOU26_release/canonical_release_vXXX/
  phase00_ingestion/
    tables/
    raw_mapping/
    frame_timeline/
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
AIOU26_release/canonical_release_vXXX/releases/competition_dataset_vXXX/
```

Legacy flat paths under
`canonical_release_vXXX/{manifests,tables,raw_mapping}` are deprecated. New
outputs should use
`canonical_release_vXXX/phase00_ingestion/{manifests,tables,raw_mapping,frame_timeline,reports}`.

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
