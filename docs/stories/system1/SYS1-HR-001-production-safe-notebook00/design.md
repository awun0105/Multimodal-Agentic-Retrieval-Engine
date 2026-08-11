# Design

## Domain Model

- Drive shadow result: copied files, created folders, skipped Google-native
  files, and error count.
- Archive standardization result: zip count, moved media/metadata counts,
  skipped count, and error count.
- Partial result: a result with non-zero `error_count`.

## Application Flow

Notebook 00A preserves the older Colab/Drive path:

1. `system1 drive-shadow` when Drive folder IDs are configured.
2. `system1 standardize-archives` when an archive source folder is configured.
3. Local standardized input readiness check.
4. Phase00 ingest.
5. Batch assignment.
6. Required `system1 sync-phase00-ingestion` to the configured Hugging Face Dataset repo.

Notebook 00B/00C are the current large-dataset streaming paths. They stream raw
video plus optional organizer-metadata pairs, create one canonical metadata JSON
and one decoded frame timeline per video, and upload all three artifacts to
`AIC26_raw`. Canonical HF raw ingest then validates and reuses the compact
timeline Parquet without downloading the video again, and produces the phase00
release tables, raw mapping, batch files, and reports.

Notebook 00B is the Colab-free-CPU streaming variant for large zip handoffs:

1. `system1 drive-shadow` copies the organizer folder into the operator/team
   Drive folder.
2. `system1 stream-standardize-upload-raw` scans zip members globally, builds
   video/metadata pairs by `video_id`, extracts pair batches bounded by
   `RAW_UPLOAD_BATCH_SIZE` files and scratch bytes into local scratch, probes
   each video, merges organizer fields when present, creates and validates
   canonical metadata and decoded frame timeline, uploads the video, metadata,
   and timeline batch to `AIC26_raw` with the existing batched HF commit helper,
   records per-pair progress, and deletes the batch scratch directories before
   moving on. Timeline probing uses one lightweight header query plus one
   decoded-frame scan; it does not add a redundant full `-count_packets` scan.
3. Canonical HF ingest reads the raw repo manifests, canonical metadata, and
   inventory, downloads each compact timeline Parquet, validates it, and copies
   it into Phase00. It does not download raw video only to regenerate a timeline.
4. Batch assignment atomically replaces the current batch plan and removes
   stale `batch_*.txt` files.
5. Required `system1 sync-phase00-ingestion` reconciles the exact configured
   Phase00 prefix and writes its completion manifest last.

The streaming variant does not materialize full `raw_videos/` and `metadata/`
folders on Google Drive.

Notebook 00C is the local-machine variant of the same streaming flow:

1. The operator downloads organizer zip files to a local folder and points
   `AIC_LOCAL_DATASET_DIR` or `archive_source_dir` at that folder.
2. The notebook skips Google Drive mount/remount and `drive-shadow`.
3. `system1 stream-standardize-upload-raw` uses local scratch, the same
   disk-safe options, batched HF raw uploads, and per-pair progress JSONL.
4. Canonical HF ingest, batch assignment, frame timeline manifest checks, and
   `sync-phase00-ingestion` match Notebook 00B.

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

`system1 stream-standardize-upload-raw`:

- Fails non-zero when pair scan, extraction, probe, or upload records errors.
- Supports `--allow-partial` for manual recovery.
- Uses `--resume` by default and appends pair progress to JSONL. Progress is
  scoped by canonical HF repo plus `raw_import_id`; resume and notebook gates
  use only the latest record per video. Notebook 00B/00C use a prefix-specific
  progress filename and migrate matching latest records from the legacy shared
  file when needed. Phase00 snapshot, upload validation, and remote validation
  reuse that exact configured filename rather than a second hard-coded name.
- Uses `--overwrite` only for explicit remote replacement.
- Rejects Google Drive paths as `--scratch-dir`.
- Reuses `RAW_UPLOAD_BATCH_SIZE` and batched HF commits instead of committing
  one pair at a time.
- Reuses the same disk-safe option family as `standardize-archives`:
  `--min-free-gb`, `--drive-sync-sleep-seconds`, `--cleanup-every-files`, and
  `--cleanup-every-gb`.
- Creates and validates `metadata/{video_id}.json` for every video using ADR
  0016; it never fabricates organizer title/channel/URL values.
- `--frame-timeline-policy` supports `required`, `if-available`, and `disabled`.
  Notebook 00B/00C use `required`; a video is not recorded as passed until its
  timeline exists and validates.
- Records organizer source reference/checksum when available and its absence
  before canonical generation; it does not upload a duplicate organizer JSON.

## Data Model

No database schema change.

Reports remain JSON files, and canonical per-video metadata becomes a versioned
JSON contract:

- `drive_shadow_report.json`
- `standardize_archives_report.json`
- `missing_metadata.json`
- `unmatched_metadata.json`

`missing_metadata.json` and `unmatched_metadata.json` are produced by the
raw-video/original-organizer-metadata pairing audit before canonical metadata
generation. They are raw-level audit
manifests in `AIC26_raw/canonical_raw_vXXX/manifests/`. The release repo may
also snapshot them under
`AIC26_release/canonical_release_vXXX/phase00_ingestion/reports/` for a
particular run. Canonical Hugging Face ingest should consume the raw-level
manifests rather than re-scan or download raw videos solely for pairing audit.

`upload-standardized-raw` also writes
`manifests/canonical_video_inventory.parquet` beside the canonical file
manifest. The inventory carries `video_id`, canonical video/metadata/timeline
paths, timeline status/row count/size, organizer-presence/generated flags,
duration, dimensions, detected fps, frame count, VFR state, and video size. It
is a projection of canonical metadata plus the decoded timeline result and must
validate against both artifacts. Canonical Hugging Face ingest must use these
small artifacts by default and must not download `raw_videos/*.mp4` only to
repeat probing or timeline decoding.

`stream-standardize-upload-raw` writes the same canonical raw manifests and
inventory while each video is present in local scratch. Required resume treats
an older pass row without a valid remote timeline as incomplete and backfills
only the missing timeline when the video and metadata already exist.

When standardized raw videos are mounted from Colab DriveFS under
`/content/drive`, `upload-standardized-raw` stages each video read used for
probe/upload into local runtime temp storage first. Direct DriveFS probing is a
debug-only path behind `AIC_ALLOW_DRIVEFS_PROBE=1`. HF canonical ingest fallback
downloads, when explicitly enabled, use per-run staging/cache directories and
clean them in `finally`; the package must not blindly delete the user's global
Hugging Face cache.

Phase00 release output is synced under
`AIC26_release/canonical_release_vXXX/phase00_ingestion/` in the configured
Hugging Face Dataset repo. The synced snapshot includes `tables/`,
`raw_mapping/`, required `frame_timeline/`, `manifests/`, and `reports/`.
Synchronization compares SHA-256 plus size, skips unchanged files, uploads and
deletes in bounded retryable commits, deletes stale files only under that exact
Phase00 prefix, and uploads `reports/phase00_sync_manifest.json` last as the
completion marker.

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
