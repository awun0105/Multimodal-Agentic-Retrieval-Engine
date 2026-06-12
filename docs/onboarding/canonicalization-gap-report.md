# Canonicalization Gap Report

## Status

Complete onboarding audit and canonicalization gap report.

---

## 1. Goal

Verify that all critical details from the original draft/reference sources have been safely migrated into the canonical Harness documentation structure. This report lists the status of every draft file and highlights any remaining gaps before moving to the implementation phase.

---

## 2. Migration Status by Original File

### `SPEC.md`
- **Status**: 100% migrated to canonical docs.
- **Where details reside**:
  - High-level architecture: `docs/architecture/overview.md`
  - System 2 (retrieval app) layers/adapters: `docs/architecture/system2-retrieval.md`
  - TKIS/Q&A/TRAKE/VKIS: `docs/product/query-workflows.md`
  - Modalities/fusion weights/evidence panels: `docs/product/search-fusion.md`
  - Endpoint HTTP methods & JSON bodies: `docs/product/api-contracts.md`
  - UI panels, shortcuts, memory strategy: `docs/product/ui-implementation.md`
  - Acceptance criteria: `docs/stories/acceptance-criteria.md`
  - Risks: `docs/architecture/technical-risks.md`
  - Decisions AD-001 to AD-010: `docs/decisions/0001-...` to `docs/decisions/0009-...`
- **Preservation status**: Moved to `docs/references/original-sources/SPEC.md`. Marked as reference only.

### `DATA_READY.md`
- **Status**: 100% migrated to canonical docs.
- **Where details reside**:
  - Relational schema, SQLite WAL, FTS5 virtual tables, FAISS mapping, Media paths, JSON shard artifact payload structures, storage priority tiers, and loading/access rules: `docs/architecture/data-contracts.md`.
  - Offline staging & notebook pipelines: `docs/architecture/system1-ingestion.md`.
- **Preservation status**: Moved to `docs/references/original-sources/DATA_READY.md`. Marked as reference only.

### `UI_IMPLEMENTATION_SPEC.md`
- **Status**: 100% migrated to canonical docs.
- **Where details reside**:
  - Layout panels, shortcuts, virtualized grids, and multi-session session state: `docs/product/ui-implementation.md`.
- **Preservation status**: Moved to `docs/references/original-sources/UI_IMPLEMENTATION_SPEC.md`. Marked as reference only.

### `CODING_STANDARDS.md`
- **Status**: 100% migrated to canonical docs.
- **Where details reside**:
  - Formatter/linter validation commands, type hints, Pydantic, TypeScript rules, naming conventions, and performance rules: `docs/harness/CONTEXT_RULES.md`.
- **Preservation status**: Moved to `docs/references/original-sources/CODING_STANDARDS.md`. Marked as reference only.

### `HCMAI-RULES.md`
- **Status**: 100% migrated to canonical docs.
- **Where details reside**:
  - Verified rules and historical workbook/progressive clue reveals details: `docs/product/rules-2026.md`.
- **Preservation status**: Moved to `docs/references/original-sources/HCMAI-RULES.md`. Marked as reference only.

### Ingestion Drafts
- **Status**: 100% migrated.
- **Where details reside**:
  - Aggregator and shard processing workflow planning: `docs/architecture/system1-ingestion.md`.
- **Preservation status**: Original files kept inside the `notebooks/` directory to prevent workspace breakages, but marked with a clear `SUPERSEDED` banner pointing to `system1-ingestion.md` and copies saved at `docs/references/original-sources/`.

---

## 3. Remaining Gap Log

- **None**. All details regarding schemas, formats, constraints, rules, and priorities from the draft specifications have been fully resolved and recorded in the canonical Harness documents.

---

## 4. Final Verification Checklist

- [x] No personal/individual paths hardcoded in canonical docs.
- [x] Conflict 1 resolved (SQLite WAL runtime + DuckDB staging).
- [x] Conflict 3 resolved (LocalFileMediaStore MVP + optional MinIO).
- [x] Conflict 5 resolved (SQLite FTS5 text search).
- [x] "Single Web UI + Multi-session Workflow" definition matches decision 0006.
- [x] Test-matrix updated with planned SYS1/SYS2 stories.
- [x] Backlog contains complete roadmap from MVP-0 to SYS2-005.
- [x] Original source copies preserved in reference path.
