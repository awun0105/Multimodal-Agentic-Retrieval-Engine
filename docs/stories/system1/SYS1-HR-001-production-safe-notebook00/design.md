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
