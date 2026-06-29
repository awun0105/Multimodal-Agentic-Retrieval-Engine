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
| Platform | Notebook JSON validates and command strings reference safer CLI options. |
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
git diff --check
system1/.venv/bin/system1 --help
```

## Acceptance Evidence

- `uv run pytest tests/test_smoke.py -q`: 37 passed.
- `uv run pytest`: 103 passed.
- `jq empty system1/notebooks/00_master_ingestion_and_assignment.ipynb`: passed.
- `git diff --check`: passed.
- `system1/.venv/bin/system1 drive-shadow --help`: exposes `--allow-partial`.
- `system1/.venv/bin/system1 standardize-archives --help`: exposes
  `--allow-partial` and keeps `--overwrite/--no-overwrite`.
- `scripts/bin/harness-cli story verify SYS1-HR-001`: pass.
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
  validates the 00B streaming command, split video/metadata zip pairing,
  batched HF upload, scratch cleanup, canonical raw manifests, and notebook
  command references.
- `uv run pytest tests/test_smoke.py -q`: 37 passed after making HF Dataset
  release sync required.
- `uv run pytest`: 103 passed after making HF Dataset release sync required.
- `jq empty system1/notebooks/00_master_ingestion_and_assignment.ipynb`: passed
  after making HF Dataset release sync required.
- `git diff --check`: passed after making HF Dataset release sync required.
