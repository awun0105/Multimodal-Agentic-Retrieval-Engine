# Overview

## Current Behavior

Notebook 00 can run Drive shadow copy and archive standardization before phase00
ingest. The workflow is wired, but audit found two production-safety gaps:

- Partial Drive copy or archive extraction errors are reported but do not stop
  the notebook.
- Re-running archive standardization against an already-populated target can
  produce duplicate/error states instead of deterministic skip behavior.

## Target Behavior

Notebook 00 should fail fast before ingest when Drive shadow or archive
standardization reports errors, unless an operator explicitly opts into partial
continuation. Archive standardization should be safe to rerun by default and
should report skipped existing outputs deterministically.

Notebook 00 should also present one primary operator workflow for Colab/Drive:
Drive shadow, archive standardization, local input readiness, phase00 ingest,
batch assignment, then required phase00 release sync to a Hugging Face Dataset
repo. Already-standardized local input remains the only fallback input shape;
canonical Hugging Face import is not part of Notebook 00's standard workflow.

## Affected Users

- System 1 operator running Notebook 00 in Colab, Kaggle, or local.
- Worker notebook users who depend on phase00 output being complete.

## Affected Product Docs

- `system1/README.md`
- `docs/stories/mvp-0.6-system1-mini-seed-and-validation.md`
- `docs/architecture/system1-ingestion.md`

## Non-Goals

- Live Google Drive or Hugging Face credential testing.
- Full MVP-0.6 SQLite/FTS5/FAISS validation completion.
- Replacing Google Drive API copy with a streaming transfer adapter.
