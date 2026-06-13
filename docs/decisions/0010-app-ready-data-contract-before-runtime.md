# ADR 0010: App-ready Data Contract Before Runtime

## Status

Accepted

## Context

Earlier planning mixed runtime implementation with unresolved dataset assumptions. The runtime app cannot be built safely until IDs, roots, logical media refs, SQLite/FTS5/FAISS boundaries, and validation rules are fixed.

## Decision

Adopt the app-ready data contract in `docs/architecture/data-contracts.md` as a prerequisite for runtime implementation. Runtime work starts only after the contract exists and a seed dataset can validate against it.

## Alternatives Considered

- Build backend/UI first and adapt later.
- Keep raw dataset files as implicit runtime truth.

## Consequences

- `MVP-0.5` must be implemented before runtime slices.
- `MVP-0.6` seed dataset validation becomes the next implementation gate.
- Runtime code must read app-ready artifacts only.
