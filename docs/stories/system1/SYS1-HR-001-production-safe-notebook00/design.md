# Design

## Domain Model

- Drive shadow result: copied files, created folders, skipped Google-native
  files, and error count.
- Archive standardization result: zip count, moved media/metadata counts,
  skipped count, and error count.
- Partial result: a result with non-zero `error_count`.

## Application Flow

Notebook 00 presents the Colab/Drive path as the primary flow:

1. `system1 drive-shadow` when Drive folder IDs are configured.
2. `system1 standardize-archives` when an archive source folder is configured.
3. Local standardized input readiness check.
4. Phase00 ingest.
5. Batch assignment.
6. Required `system1 sync-release` to the configured Hugging Face Dataset repo.

Already-standardized local input remains a fallback when Drive/archive config is
empty. Canonical Hugging Face import is intentionally excluded from Notebook
00's standard workflow to keep the operator path singular.

The safety gate belongs in the CLI commands so Notebook 00, shell users, and
tests share the same behavior.

## Interface Contract

`system1 drive-shadow`:

- Fails non-zero when copy reports errors.
- Supports `--allow-partial` to keep the old continue-on-partial behavior.

`system1 standardize-archives`:

- Fails non-zero when extraction/move reports errors.
- Supports `--allow-partial`.
- Skips existing targets with identical size by default.
- Uses `--overwrite` for explicit replacement.

## Data Model

No database schema change.

Reports remain JSON files:

- `drive_shadow_report.json`
- `standardize_archives_report.json`
- `missing_metadata.json`
- `unmatched_metadata.json`

`missing_metadata.json` and `unmatched_metadata.json` are produced by the
standardized raw-video/metadata pairing audit. They are raw-level audit
manifests in `AIC26_raw/canonical_raw_vXXX/manifests/`. The release repo may
also snapshot them under
`AIC26_release/canonical_release_vXXX/phase00_ingestion/reports/` for a
particular run. Canonical Hugging Face ingest should consume the raw-level
manifests rather than re-scan or download raw videos solely for pairing audit.

`upload-standardized-raw` also writes
`manifests/canonical_video_inventory.parquet` beside the canonical file
manifest. The inventory carries `video_id`, canonical video/metadata paths,
duration, detected fps, frame count, and video size. Canonical Hugging Face
ingest must use this small inventory by default and must not download
`raw_videos/*.mp4` for probing unless the operator explicitly enables the
legacy fallback with `AIC_ALLOW_HF_VIDEO_DOWNLOAD_FOR_PROBE=1`.

When standardized raw videos are mounted from Colab DriveFS under
`/content/drive`, `upload-standardized-raw` stages each video read used for
probe/upload into local runtime temp storage first. Direct DriveFS probing is a
debug-only path behind `AIC_ALLOW_DRIVEFS_PROBE=1`. HF canonical ingest fallback
downloads, when explicitly enabled, use per-run staging/cache directories and
clean them in `finally`; the package must not blindly delete the user's global
Hugging Face cache.

Phase00 release output is synced under `releases/<AIC_RELEASE_ID>/...` in the
configured Hugging Face Dataset repo.

## UI / Platform Impact

Notebook 00 stops earlier and more clearly when input preparation is incomplete.
Operators can rerun standardization without cleaning the target first.

## Observability

JSON reports retain item-level statuses. Skipped existing files are represented
as explicit report rows.

## Alternatives Considered

1. Keep partial errors as report-only and add notebook-side checks. Rejected
   because CLI users would still get unsafe behavior.
2. Always overwrite existing standardized files. Rejected because it can replace
   operator-reviewed outputs unexpectedly.
3. Skip matching existing files by size. Chosen as a conservative idempotency
   baseline with low overhead.
