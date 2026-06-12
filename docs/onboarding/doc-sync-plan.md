# Documentation Sync Plan

## Goal

Normalize existing project documentation into the Project Harness documentation
structure without losing useful source material or treating stale docs as truth.

## Source Inventory

See: `docs/onboarding/source-inventory.md`

## Sync Table

| Source File | Current Role | Target Doc | Template | Action | Confidence | Needs Human Review | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `README.md` | setup/overview | `README.md` | `readme` | normalize | medium | yes | Keep local/LAN deployment notes. |
| `SPEC.md` | architecture/spec | `docs/requirements/SRDS.md` | `srds` | normalize | high | no | Adopt design specifications. |
| `HCMAI-RULES.md` | rules | `docs/product/rules.md` | (custom) | adopt | high | no | Keep competition facts intact. |
| `CODING_STANDARDS.md` | coding rules | `docs/harness/CONTEXT_RULES.md` | (custom) | merge | medium | yes | Resolve python/react formatting rules. |
| `UI_IMPLEMENTATION_SPEC.md` | UI spec | `docs/product/ui-spec.md` | (custom) | adopt | medium | no | Clean up and move to product folder. |
| `DATA_READY.md` | Storage spec | `docs/architecture/ingestion.md` | `data-flow` | merge | medium | no | Keep only sections compatible with canonical runtime/preprocessing split. |
| `docs/references/original-sources/INGESTION.md` | Ingestion reference | `docs/architecture/system1-ingestion.md` | (custom) | transform | no | Archived reference used to build canonical System 1 ingestion docs. |

## Actions

- `adopt`: keep as-is and register as canonical.
- `normalize`: rewrite into a registered template.
- `merge`: combine useful content into a canonical doc.
- `transform`: convert into a different artifact type.
- `conflict`: record mismatch; do not trust as truth.
- `archive`: preserve but remove from source-of-truth path after review.

## Conflicts

- Resolved: SQLite WAL + FTS5 is runtime; DuckDB is preprocessing/staging/analytics.
- Resolved: LocalFileMediaStore is MVP; MinIO is optional future adapter only.

## Human Review Required

- No open architectural blocker remains for storage direction.
- Human review is still useful before archiving older Tier 2 docs, but not required to continue planning.

## Apply Notes

We will not archive original documents until the codebase implementation begins.
