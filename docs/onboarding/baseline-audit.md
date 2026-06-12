# Baseline Audit

Date: 2026-06-12

## Sources Inspected

- `README.md`
- `SPEC.md`
- `HCMAI-RULES.md`
- `DATA_READY.md`
- `CODING_STANDARDS.md`
- `UI_IMPLEMENTATION_SPEC.md`
- `docs/references/original-sources/INGESTION.md`
- `docs/harness/TEMPLATE_REGISTRY.md`
- `scripts/bin/harness-cli query matrix`

## Confirmed

- The repository is currently an onboarding/specification repository, not an implemented product codebase.
- Product target is a local-first multimedia retrieval assistant for HCMC AI Challenge.
- Product must support both Interactive Mode and Automatic Agent Mode on the same retrieval core.
- Final 2026 competition submission format is unknown, so export must stay configurable.
- Harness CLI exists at `scripts/bin/harness-cli` and the durable matrix currently has no story rows.

## Partial

- Architecture direction is defined at a design level: local-first modular monolith, layered architecture, web UI, retrieval core, evidence engine, and configurable export.
- Ingestion direction is now canonicalized in `docs/architecture/system1-ingestion.md`; original disagreements are recorded in `docs/onboarding/doc-conflicts.md`.
- UI expectations are defined in `UI_IMPLEMENTATION_SPEC.md`, but no frontend implementation exists.

## Unknown

- Official 2026 dataset contents, query types, submission format, scoring tolerance, and cloud/API rules.
- Exact runtime schema details for `app.sqlite`.
- Exact preprocessing artifact layout and validation command set.
- Exact backend/frontend frameworks because no app code or package manifests exist.

## Not Implemented

- Backend API.
- Frontend web UI.
- Ingestion CLI/scripts.
- SQLite schema for app/runtime data.
- FAISS/text indexes.
- MediaStore adapters.
- Tests, lint, build, and runtime validation commands.

## Documentation Conflicts

- See `docs/onboarding/doc-conflicts.md`.

## Recommended Next Work

- Decide MVP storage architecture.
- Create the first implementation story for repository scaffold only.
- Add executable validation commands once backend/frontend packages exist.
