# Execution Plan: Preliminary Ready E2E

Date: 2026-08-05

## Status

Active

## Outcome

System 1 and System 2 are ready for the AIC 2026 preliminary round workflow:
System 1 produces a validated app-ready release from official videos and
optional metadata while regenerating all derived evidence, and System 2 can run
Textual KIS, Q&A, and TRAKE end to end
against that release with exact `video_id` / `frame_id` inspection and top-100
answer export.

## Context

- Official source: `docs/product/official/aic2026-preliminary-round-batch1/`.
- Product truth: `docs/product/requirements-truth-set.md`.
- Rules profile: `docs/product/rules-2026.md`.
- App-ready contract: `docs/architecture/data-contracts.md`.
- System 1 preprocessing contract: `docs/architecture/system1-ingestion.md`.
- Phase01 scene-grouping design:
  `docs/architecture/system1-scene-grouping.md`.
- Notebook 01 production pipeline:
  `docs/architecture/system1-notebook01-production-pipeline.md`.
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
- Generate all derived retrieval data from official videos; do not import
  organizer keyframes, objects, CLIP features, media-info, or map-keyframes.
- Keep metadata as one useful evidence source. System 1 should use it when
  present, but System 2 readiness depends on the complete retrieval-ready
  release rather than metadata presence alone.
- Implement enough System 2 runtime behavior for preliminary use, not only a UI
  scaffold.

Out of scope:

- Precomputing a canonical `temporal_search.parquet` or all possible TRAKE
  event sequences.
- Adding visual embedding models beyond the accepted SigLIP and BEiT3 indexes
  before a measured need.
- Building a hard dependency on online providers in System 2 runtime retrieval;
  offline System 1 preprocessing may use the accepted Gemini stages with cache
  and resume.
- Hard-coding final organizer API submission transport before the official
  endpoint or upload schema is known.
- Refactoring metadata handling as a standalone workstream.

## Approach

1. Align docs with official preliminary rules and dataset facts.
2. Complete Notebook 01 production structure processing: shots, keyframes, ASR,
   canonical shot captions, multimodal scene grouping, summaries, mappings,
   validation, and per-video structure artifacts.
3. Update System 1 ingestion/release contracts for self-generated evidence,
   frame-safe mapping, optional metadata, and managed video access.
4. Update System 2 contracts for top-100 answer export, larger internal
   candidate pools, TRAKE sequence ranking, and exact-frame refinement.
5. Implement System 1 provider and validation increments against one real video
   and a small batch before full Batch 1 runs.
6. Implement System 2 backend search/export capabilities against a seed release,
   then connect the frontend inspection workflow.
7. Rehearse TKIS, Q&A, and TRAKE with known-answer fixtures and a Batch 1 smoke
   slice before calling the system preliminary-ready.

## Risks And Recovery

- Risk: regenerating every derived signal increases model/API cost and runtime.
  Mitigation: content-addressed cache, resumable checkpoints, rate limiting,
  one-video proof, and a heterogeneous small-batch rehearsal before Batch 1.
- Risk: exact frame IDs drift because of FPS math or VFR media.
  Mitigation: use the project-decoded frame timeline and original decoded frame
  indexes; do not depend on organizer map-keyframes/media-info.
- Risk: System 2 becomes too broad before basic retrieval works.
  Mitigation: implement one common retrieval pipeline with query-type strategies
  and keep agent automation out of the critical preliminary path.
- Recovery: each implementation increment must be independently reversible by
  git commit; docs-only contract changes can be reviewed independently from code.

## Progress

- [x] Store official preliminary-round Batch 1 source files under
  `docs/product/official/aic2026-preliminary-round-batch1/`.
- [x] Align product and architecture contracts with official preliminary facts.
- [x] Clean up active planning, story, validation, and onboarding docs that still
  implied required metadata pairing or over-emphasized "video-first" wording.
- [x] Accept and document the Phase01 multimodal context-focus scene-grouping
  design, canonical schema mappings, validation, caching, and failure behavior.
- [x] Accept the video-plus-optional-metadata source policy and production
  Notebook 01/02 provider contract in ADR 0015.
- [x] Accept canonical per-video metadata for Notebook 00B/00C in ADR 0016:
  normalize a required canonical JSON with `ffprobe` facts and provenance,
  retain source reference/checksum when available, avoid a duplicate organizer
  metadata tree, and retain the pre-generation missing audit.
- [x] Migrate canonical caption/summary schemas and debug compatibility rows to
  one bilingual row per shot/scene; retain and validate both transcript-link
  tables; retire `image_captions`.
- [x] Implement ADR 0016 in both raw upload package paths used by Notebook
  00B/00C, update notebook validation gates, and propagate metadata provenance
  through canonical HF ingest and Phase00.
- [x] Build production decoded timelines while each raw video is already in
  bounded upload scratch, then reuse the compact timeline during HF ingest.
- [x] Bound timeline memory with chunked atomic Parquet writes and add a
  Colab-safe `auto|1|2` worker setting while keeping extraction, progress, and
  HF commits coordinator-owned.
- [ ] Implement and validate Notebook 01 production structure providers and
  multimodal scene grouping.
- [ ] Build a competition release containing app-ready SQLite, FTS, separate
  SigLIP/BEiT3 FAISS indexes, shared vector mappings, logical media refs, and
  exact-frame inspection support.
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
- 2026-08-05: Although the organizer provides baseline support artifacts,
  System 1 consumes only official videos and optional metadata and regenerates
  all derived evidence. Organizer keyframes, objects, CLIP, map-keyframes, and
  media-info are not imported.
- 2026-08-04: Preliminary readiness means top-100 answer export and exact-frame
  inspection for TKIS, Q&A, and TRAKE. Direct organizer API submission remains a
  thin adapter until official transport details exist.
- 2026-08-05: Phase01 scene grouping uses overlapping multimodal context/focus
  windows. The VLM judges Boolean adjacent-shot boundaries only; deterministic
  package code owns voting, follow-up review, partitioning, IDs/ranges,
  validation, cache provenance, and explicit failure behavior. See ADR 0014.
- 2026-08-05: Notebook 01 production uses TransNet V2, 20/50/80 keyframes,
  faster-whisper large-v3, Gemini bilingual captions/grouping/summaries, and
  explicit failure after bounded retry. Notebook 02 generates Gemini OCR,
  configured objects, and separate SigLIP/BEiT3 indexes. See ADR 0015.
- 2026-08-10: Notebook 00B/00C are the primary large-dataset ingestion paths.
  Organizer metadata remains optional input, but each raw video receives one
  schema-valid canonical metadata JSON. Missing organizer values are
  null/empty, `ffprobe` supplies technical facts, provenance points to source
  storage without duplicating organizer JSON on HF, and missing-organizer audit
  state survives generation. See ADR 0016.
- 2026-08-11: Notebook 00B/00C require decoded timelines during raw streaming.
  Canonical HF ingest validates the uploaded compact Parquet without a second
  raw-video download; production Notebook 01 rejects missing timelines.
- 2026-08-12: Timeline creation streams into one atomic Parquet per video and
  uses at most two external `ffprobe` workers. Raw remains authoritative;
  Phase00 release contains the validated worker snapshot. Upload and progress
  remain single-coordinator operations.

Promote lasting product or architecture decisions into `docs/decisions/`.

## Validation

- Focused proof: docs diff review, schema/tests for the bilingual
  caption/summary contract, and targeted searches for stale organizer-import,
  single-index, hard metadata-pairing, and canonical `temporal_search.parquet`
  requirements.
- Integration or end-to-end proof: canonical metadata has deterministic local
  uploader/HF-ingest tests and a three-video real-file probe smoke; live HF
  upload remains for the operator run. Later System 1 seed release and System 2
  fixture search/export rehearsal for TKIS, Q&A, and TRAKE.
- Repository-required checks: markdown/link sanity and focused code tests when
  implementation begins.

## Result

The decision/docs alignment and ADR 0016 package implementation are complete.
Automated tests cover canonical generation, both upload paths, inventory
agreement, HF ingest, provenance propagation, and Notebook 00B/00C gates; three
local sample videos also pass real `ffprobe`. A real 31,720-frame comparison
also proves the streamed timeline is row-identical to the former in-memory
writer. The overall plan remains active
because the live HF `canonical_raw_v009` run, Notebook 01 providers, Notebook
02 dual-index pipeline, final release, and
System 2 runtime are not complete.
