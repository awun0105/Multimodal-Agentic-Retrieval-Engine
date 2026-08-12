# Validation

## Proof Strategy

Use deterministic local tests and fake provider clients for cloud-facing logic.
Do not require live Google Drive or Hugging Face credentials for CI-grade proof.

## Test Plan

| Layer | Cases |
| --- | --- |
| Unit | Archive standardization flattens `.mp4`, `.wav`, and `.json`; existing matching files are skipped on rerun; unsafe zip paths are rejected. |
| Integration | CLI exits non-zero for partial Drive/archive results unless `--allow-partial` is provided. |
| E2E | Not required for this hardening slice. |
| Platform | Notebook JSON/code cells validate, package imports resolve to the synchronized repo, and CLI contracts are inspected structurally rather than through terminal-rendered help text. |
| Performance | Rerun skips existing matching files without re-copying. |
| Logs/Audit | JSON reports include skipped and failed item rows. |

## Fixtures

- Temporary zip archives built during pytest.
- Fake Google Drive service objects.
- Monkeypatched CLI functions for partial-result exit tests.

## Commands

```text
uv run pytest
jq empty system1/notebooks/00_master_ingestion_and_assignment.ipynb
jq empty system1/notebooks/00A_master_ingestion_and_assignment.ipynb
jq empty system1/notebooks/00B_master_ingestion_and_assignment.ipynb
jq empty "system1/notebooks/00C_master_ingestion_and_assignment (local).ipynb"
jq empty system1/notebooks/01_worker_structure_pipeline.ipynb
git diff --check
system1/.venv/bin/system1 --help
```

## Acceptance Evidence

The historical entries below prove the earlier streaming, disk-safety, audit,
and inventory behavior. Current focused tests additionally prove ADR 0016
canonical generation, organizer-source reference/checksum, missing-organizer
semantics, inventory agreement, provenance propagation, and Notebook 00B/00C
gates. The 2026-08-11 implementation additionally proves required decoded
timeline generation in bounded raw scratch, retry/validation, resume backfill,
compact HF ingest without MP4 download, stale local timeline/batch cleanup,
scoped hash-based Phase00 reconciliation, and the Notebook 01 production gate.
Only the live full-dataset HF rehearsal remains pending for this story.

- `python -m pytest -q`: 188 passed on 2026-08-12 after adding streaming
  Parquet and bounded timeline-worker coverage.
- Real-file equivalence on `L21_V002`: both implementations produced the same
  31,720 rows and probe values. Streaming peak RSS was 115,652 KB versus
  132,852 KB for the former in-memory path; elapsed time was approximately 52
  seconds for each single-worker scan.
- Real two-worker smoke on `L21_V001` and `L21_V003`: 37,849 and 29,946 rows
  passed concurrently in 78.04 seconds with 122,060 KB peak RSS. This validates
  local concurrency mechanics; Colab throughput still depends on runtime CPU
  and disk allocation.
- Notebook 00B/00C JSON and IPython-transformed compilation passed for 40 code
  cells; Ruff `E9,F,I` passed for all changed Python files.
- `uv run pytest -q`: 183 passed on 2026-08-11.
- Preflight regression slice: 4 passed; it checks the module entrypoint, the
  structured CLI contract used by 00A/00B/00C/01, notebook source guards, and
  the streaming disk-safe option binding.
- Narrow-terminal reproduction with `COLUMNS=40`: CLI exit code remained `0`
  while rendered help omitted the full `--frame-timeline-policy` spelling,
  proving that rendered text is not a valid option-availability signal.
- JSON validation and Python compilation passed for 75 code cells across
  Notebooks 00A, 00B, 00C, and 01.
- Focused timeline/raw/HF/sync/notebook suite: 95 passed on 2026-08-11.
- Ruff `E9,F,I` checks passed for every changed Python file.
- Notebook JSON, cleared output/execution state, and code-cell compilation
  checks passed for 00B, 00C, and 01.
- `git diff --check`: passed on 2026-08-11.

- `python -m pytest tests/test_canonical_metadata.py tests/test_smoke.py -k
  "canonical_metadata or canonical_inventory_match or
  notebooks_are_operator_ready or upload_standardized_raw_to_hf or
  stream_standardize_upload_raw_to_hf or ingest_from_canonical_hf_manifest"`:
  18 passed.
- Real-file smoke: `L21_V001`, `L21_V002`, and `L21_V003` each produced valid
  schema 1.0 metadata with `probe_status=pass` on the first attempt.
- Mixed-history progress tests verify repo/prefix isolation and latest-status
  semantics, while Notebook 00B/00C checks require prefix-specific progress
  files and legacy checkpoint migration.

- `uv run pytest tests/test_smoke.py -q`: 37 passed.
- `uv run pytest`: 103 passed.
- `jq empty system1/notebooks/00_master_ingestion_and_assignment.ipynb`: passed.
- `git diff --check`: passed.
- `system1/.venv/bin/system1 drive-shadow --help`: exposes `--allow-partial`.
- `system1/.venv/bin/system1 standardize-archives --help`: exposes
  `--allow-partial` and keeps `--overwrite/--no-overwrite`.
- The retired legacy Harness story verification passed before the Repository
  Harness Core migration.
- Notebook 00 now presents Drive shadow -> standardize archives -> input
  readiness -> ingest -> assign batches -> phase00 sync to HF Dataset as the
  primary operator workflow, requires `AIC_HF_REPO_ID`, and requires an archive
  source path when Drive shadow is enabled.
- `uv run pytest tests/test_smoke.py -q`: 37 passed after simplifying the
  Notebook 00 workflow presentation.
- `uv run pytest`: 103 passed after simplifying the Notebook 00 workflow
  presentation.
- `jq empty system1/notebooks/00_master_ingestion_and_assignment.ipynb`: passed
  after simplifying the Notebook 00 workflow presentation.
- `git diff --check`: passed after simplifying the Notebook 00 workflow
  presentation.
- Notebook 00 now uses the exact primary workflow Drive shadow -> standardize
  archives -> input readiness -> local ingest -> assign batches -> required
  `sync-phase00-ingestion` to `AIC_HF_REPO_ID`. The notebook no longer runs
  `import-canonical` or `ingest --canonical-hf-repo-id`.
- `python -m pytest tests/test_smoke.py -k "standardize_archive_source or
  local_ingest_video_primary_tolerates_missing_and_unmatched_metadata or
  tolerant_input_discovery_reports_missing_and_unmatched_metadata"`: 6 passed
  after standardize began writing `missing_metadata.json` and
  `unmatched_metadata.json` pairing audit reports.
- `python -m pytest tests/test_smoke.py -k "upload_standardized_raw_to_hf or
  ingest_from_canonical_hf_manifest"`: 8 passed after raw upload began writing
  `canonical_video_inventory.parquet` and HF canonical ingest stopped
  downloading `raw_videos/*.mp4` by default.
- `python -m pytest tests/test_smoke.py -k "drivefs or
  upload_standardized_raw_to_hf or ingest_from_canonical_hf_manifest or
  standardize_archive_source_flattens_zip_inputs"`: 11 passed after DriveFS
  probe/upload staging and zip `member_stage_*` cleanup were verified.
- `python -m pytest tests/test_hf_artifact_store.py`: 11 passed after
  confirming HF artifact-store behavior stayed intact.
- `python -m pytest tests/test_smoke.py -k "stream_standardize_upload_raw or notebooks_are_operator_ready" -q`:
  validates the 00B/00C streaming command references, split video/metadata zip
  pairing, batched HF upload, disk-safe stream options, scratch cleanup, and
  canonical raw manifests.
- Current 00B/00C notebook contract checks also require
  `manifests/frame_timeline_manifest.parquet` in phase00 output and preview
  decoded `frame_timeline/{video_id}.parquet` availability when present.
- `uv run pytest tests/test_smoke.py -q`: 37 passed after making HF Dataset
  release sync required.
- `uv run pytest`: 103 passed after making HF Dataset release sync required.
- `jq empty system1/notebooks/00_master_ingestion_and_assignment.ipynb`: passed
  after making HF Dataset release sync required.
- `git diff --check`: passed after making HF Dataset release sync required.
