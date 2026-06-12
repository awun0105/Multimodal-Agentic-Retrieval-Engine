# Source Inventory

## Goal

Identify source material that may inform Project Harness baseline docs without
treating unaudited material as truth.

## Existing Docs Found

| File | Current Role | Freshness | Confidence | Evidence | Notes |
| --- | --- | --- | --- | --- | --- |
| `README.md` | overview/setup | unknown | medium | No code exists yet | Wait for implementation |
| `SPEC.md` | Core specification | active | high | Tier 1 source of truth | Local-first modular monolith defined |
| `HCMAI-RULES.md` | Competition rules | active | high | Tier 1 source of truth | Constrains export format & external deps |
| `docs/references/original-sources/CODING_STANDARDS.md` | Coding guidelines | archived | medium | reference only | Canonicalized into `docs/harness/CONTEXT_RULES.md`. |
| `docs/references/original-sources/UI_IMPLEMENTATION_SPEC.md` | UI design | archived | medium | reference only | Canonicalized into `docs/product/ui-implementation.md`. |
| `docs/references/original-sources/DATA_READY.md` | Data architecture | archived | medium | reference only | Canonicalized into `docs/architecture/data-contracts.md`. |
| `docs/references/original-sources/INGESTION.md` | Ingestion reference | archived | medium | reference only | Canonicalized into `docs/architecture/system1-ingestion.md` and `docs/architecture/ingestion.md`. |

## Code And Runtime Sources Found

| Source | Current Role | Confidence | Evidence | Notes |
| --- | --- | --- | --- | --- |
| (None) | Application code | not implemented | No files found | Repository is currently docs-only. |

## Test And Proof Sources Found

| Source | Proof Type | Confidence | Evidence | Notes |
| --- | --- | --- | --- | --- |
| (None) | Tests | not implemented | No tests found | Repository is currently docs-only. |

## Source Labels

- `confirmed`: current evidence supports the claim.
- `partial`: evidence exists but is incomplete or weak.
- `unknown`: evidence is insufficient.
- `not implemented`: no implementation evidence found.

## Review Notes

- Database choice is now resolved: SQLite WAL is runtime source of truth; DuckDB is preprocessing/staging/analytics only.
