# Canonical Documentation Map

## Purpose

This file records which canonical documents replace or supersede older source
materials. Original source files are preserved in `docs/references/original-sources/`.

## Canonical Source of Truth

| Topic | Canonical Document | Replaces / Supersedes |
| --- | --- | --- |
| Architecture decisions | `docs/decisions/` | scattered decisions in original `SPEC.md`, `DATA_READY.md`, and ingestion drafts |
| System 1 ingestion notebooks | `docs/architecture/system1-ingestion.md` | original ingestion drafts; archived reference is `docs/references/original-sources/INGESTION.md` |
| System 2 retrieval app | `docs/architecture/system2-retrieval.md` | runtime architecture sections in `SPEC.md` |
| General architecture overview | `docs/architecture/overview.md` | high-level architecture sections in `SPEC.md` and `README.md` |
| Ingestion architecture summary | `docs/architecture/ingestion.md` | storage/ingestion sections in draft docs |
| Data contracts | `docs/architecture/data-contracts.md` | schema and output-contract sections in `DATA_READY.md` |
| Retrieval workflows and agent mode | `docs/product/queries-and-agent.md` | query/agent sections in `SPEC.md` |
| Query workflows | `docs/product/query-workflows.md` | workflow sections in `SPEC.md` |
| Search fusion and evidence | `docs/product/search-fusion.md` | retrieval architecture sections in `SPEC.md` |
| API contracts | `docs/product/api-contracts.md` | API design sections in `SPEC.md` |
| UI implementation | `docs/product/ui-implementation.md` | `UI_IMPLEMENTATION_SPEC.md` + UI sections in `SPEC.md` |
| Competition rules | `docs/product/rules-2026.md` | `HCMAI-RULES.md` |
| Product current state | `docs/product/current-state.md` | onboarding baseline summary |
| Acceptance Criteria | `docs/stories/acceptance-criteria.md` | acceptance criteria in `SPEC.md` |
| Technical Risks | `docs/architecture/technical-risks.md` | risks section in `SPEC.md` |
| Canonicalization Gap | `docs/onboarding/canonicalization-gap-report.md` | migration gap verification report |
| Backlog | `docs/stories/backlog.md` | prior informal roadmap notes |
| Validation matrix | `docs/validation/test-matrix.md` and `harness.db` | prior placeholder matrix |

## Original Source Preservation

The following files are preserved for reference only in `docs/references/original-sources/`:

- `SPEC.md`
- `HCMAI-RULES.md`
- `DATA_READY.md`
- `CODING_STANDARDS.md`
- `UI_IMPLEMENTATION_SPEC.md`
- `INGESTION.md`
- `README.original.md`

## Rule

When canonical docs conflict with original sources, canonical docs win.
