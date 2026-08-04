# Execution Plan: Preliminary Ready E2E

Date: 2026-08-04

## Status

Active

## Outcome

System 1 and System 2 are ready for the AIC 2026 preliminary round workflow:
System 1 produces a validated app-ready release from official videos and useful
support artifacts, and System 2 can run Textual KIS, Q&A, and TRAKE end to end
against that release with exact `video_id` / `frame_id` inspection and top-100
answer export.

## Context

- Official source: `docs/product/official/aic2026-preliminary-round-batch1/`.
- Product truth: `docs/product/requirements-truth-set.md`.
- Rules profile: `docs/product/rules-2026.md`.
- App-ready contract: `docs/architecture/data-contracts.md`.
- System 1 preprocessing contract: `docs/architecture/system1-ingestion.md`.
- System 2 API shape: `docs/product/api-contracts.md`.
- Current implementation status: `docs/product/current-state.md`.
- Validation tracker: `docs/validation/test-matrix.md`.

## Scope

In scope:

- Align product and architecture docs with the official preliminary-round Batch
  1 information.
- Preserve the System 1 / System 2 boundary: System 1 creates reusable,
  query-independent app-ready artifacts; System 2 performs query-specific
  retrieval, TRAKE alignment, exact-frame refinement, and export.
- Import organizer-provided keyframes, objects, CLIP features, media-info, and
  map-keyframes when they validate cleanly and improve retrieval or frame
  mapping.
- Keep metadata as optional evidence. Missing metadata must not exclude a video
  from the app-ready dataset when video identity and frame mapping are valid.
- Implement enough System 2 runtime behavior for preliminary use, not only a UI
  scaffold.

Out of scope:

- Precomputing a canonical `temporal_search.parquet` or all possible TRAKE
  event sequences.
- Adding multiple visual embedding models by default before a measured need.
- Building a hard dependency on online providers for core retrieval correctness.
- Hard-coding final organizer API submission transport before the official
  endpoint or upload schema is known.
- Refactoring metadata handling as a standalone workstream.

## Approach

1. Align docs with official preliminary rules and dataset facts.
2. Update System 1 ingestion/release contracts for organizer support artifact
   import, frame-safe mapping, optional metadata, and managed video access.
3. Update System 2 contracts for top-100 answer export, larger internal
   candidate pools, TRAKE sequence ranking, and exact-frame refinement.
4. Implement System 1 import and validation increments against small fixtures
   before full Batch 1 runs.
5. Implement System 2 backend search/export capabilities against a seed release,
   then connect the frontend inspection workflow.
6. Rehearse TKIS, Q&A, and TRAKE with known-answer fixtures and a Batch 1 smoke
   slice before calling the system preliminary-ready.

## Risks And Recovery

- Risk: organizer support artifacts have inconsistent mapping or ordering.
  Mitigation: treat them as optional imported evidence and require validation
  against `video_id`, `frame_id`, media-info, and map-keyframes before indexing.
- Risk: exact frame IDs drift because of FPS math or VFR media.
  Mitigation: prefer decoded frame mapping or organizer map-keyframes/media-info
  evidence; mark any fallback estimated and expose exact-frame resolver behavior.
- Risk: System 2 becomes too broad before basic retrieval works.
  Mitigation: implement one common retrieval pipeline with query-type strategies
  and keep agent automation out of the critical preliminary path.
- Recovery: each implementation increment must be independently reversible by
  git commit; docs-only contract changes can be reviewed independently from code.

## Progress

- [x] Store official preliminary-round Batch 1 source files under
  `docs/product/official/aic2026-preliminary-round-batch1/`.
- [x] Align product and architecture contracts with official preliminary facts.
- [ ] Implement and validate System 1 support-artifact import.
- [ ] Build a competition release containing app-ready SQLite, FTS, FAISS,
  vector mappings, logical media refs, and exact-frame inspection support.
- [ ] Implement System 2 TKIS/Q&A/TRAKE search, refinement, candidate, and
  export flows.
- [ ] Run fixture and Batch 1 smoke rehearsals for all official preliminary
  query types.

## Decisions

- 2026-08-04: TRAKE is a System 2 runtime workflow, not a canonical System 1
  artifact, because event sequences are query-specific while System 1 artifacts
  must be reusable across queries.
- 2026-08-04: Metadata is optional evidence. It should be used when present but
  missing metadata is not a critical-path failure if video/frame mapping and
  retrieval evidence are valid.
- 2026-08-04: Organizer keyframes, objects, CLIP features, media-info, and
  map-keyframes are support inputs, not the official source of truth. Import
  them only when validation proves their mapping is usable.
- 2026-08-04: Preliminary readiness means top-100 answer export and exact-frame
  inspection for TKIS, Q&A, and TRAKE. Direct organizer API submission remains a
  thin adapter until official transport details exist.

Promote lasting product or architecture decisions into `docs/decisions/`.

## Validation

- Focused proof: docs diff review and targeted search for stale requirements
  such as organizer "raw video + metadata only", hard metadata pairing failure,
  and canonical `temporal_search.parquet`.
- Integration or end-to-end proof: later System 1 seed release and System 2
  fixture search/export rehearsal for TKIS, Q&A, and TRAKE.
- Repository-required checks: markdown/link sanity and focused code tests when
  implementation begins.

## Result

Pending.
