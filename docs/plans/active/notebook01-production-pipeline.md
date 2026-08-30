# Execution Plan: Notebook 01 Production Pipeline

Date: 2026-08-13

## Status

Active

## Outcome

Notebook 01 exposes one production pipeline and a minimal `USER SETTINGS` cell.
`Run All` restores Phase00 and valid per-video stage checkpoints, processes one
video at a time, retries safely, packages and syncs completed videos, and
continues after retryable video failures. Every artifact is reproducible from a
persisted resolved config and stage provenance.

## Context

- Production contract:
  `docs/architecture/system1-notebook01-production-pipeline.md`.
- Scene grouping design: `docs/architecture/system1-scene-grouping.md`.
- Self-generated evidence decision:
  `docs/decisions/0015-system1-self-generated-production-evidence.md`.
- Semantic-event keyframe decision:
  `docs/decisions/0019-phase01-semantic-event-keyframes.md`.
- Phase00 handoff: `docs/architecture/system1-ingestion.md`.
- Current orchestration: `system1/notebooks/01_worker_structure_pipeline.ipynb`.
- Current package entry point: `system1/src/system1/structure/builder.py`.

The legacy structure builder remains only for guarded debug/test injection.
The default public `process-batch` route and Notebook 01 now call the production
runner, which restores Phase00, resolves config, preflights dependencies and
persistent storage, resumes per-video stages, packages strict outputs, and
syncs verified artifacts.

## Scope

In scope:

- One production pipeline with no execution mode and no user-facing provider
  profile.
- Repository-owned deterministic YAML configuration merged with minimal user
  and detected runtime settings into one persisted `ResolvedConfig`.
- Automatic Phase00 release resolution unless an explicit release override is
  supplied.
- Per-video, per-stage persistent checkpoint state, fingerprint validation, and
  dependency-aware invalidation.
- Sequential video processing and single-heavy-model GPU residency for
  Colab/Kaggle safety.
- Public or private Hugging Face checkpoint repositories, selected by project
  configuration rather than enforced as a runtime privacy policy.
- Per-run and per-video Hugging Face download caches under disposable scratch,
  plus operator-visible video/stage/disk progress and post-run remote layout
  verification.
- TransNet V2 shots, mandatory search-band anchors plus bounded semantic-event
  supplemental keyframes, NVIDIA Vietnamese FastConformer ASR, gated Vintern
  OCR, shared 4-bit Qwen2.5-VL caption/grouping/summaries, scoped Gemini
  fallback, package, sync, and scratch cleanup.
- Focused, integration, recovery, and real-provider acceptance tests.

Out of scope:

- Notebook 02 feature extraction and indexes.
- System 2 retrieval behavior.
- Treating test doubles as production providers or production evidence.
- Adding execution modes, quality tiers, pipeline selectors, or user-facing
  `mock`/`real`/`rule_based`/`vlm` choices.

## Target Runtime Contract

The only notebook-editable settings are:

```text
batch_id
worker_id
release_id_override (optional)
storage/repository overrides (optional)
secret names or secret-store lookups
```

Secrets are read from environment, Colab Secrets, or Kaggle Secrets and never
persisted. Model IDs/revisions, schemas, prompts, media encoding, TransNet, ASR,
keyframe selection, scene grouping, retry/concurrency, and artifact layout come
only from versioned repository YAML.

Runtime resolution is:

```text
repo YAML + USER SETTINGS + detected environment + resolved Phase00 release
  -> ResolvedConfig
  -> resolved_config.json + config_hash in manifests/checkpoints
```

The stage graph is:

```text
shots
  -> keyframes -> ocr -> shot_captions
asr
shots + asr -> shot_transcript_links
shots + keyframes + ocr + shot_captions + shot_transcript_links -> scenes
scenes + keyframes + ocr + shot_captions + shot_transcript_links -> scene_summaries
all canonical stages -> package -> sync
```

Every stage state contains status, input fingerprint, config hash,
model/revision, prompt version when applicable, schema version, output
checksums, completion time, and failure details when applicable. A stage is
complete only after local validation, checksum, persistent upload, and atomic
state update have all succeeded.

## Approach

### Work Package 0: Contract, Config, Schema, And Tests

1. Record the single-pipeline, resolved-config, checkpoint, Colab/Kaggle, OOM,
   API-concurrency, and search-band keyframe decisions in architecture/ADR.
2. Add versioned Phase01, model, media, artifact, and storage configuration.
3. Add resolved-config and per-video checkpoint-state JSON schemas.
4. Extend `keyframes.parquet` with `quality_score`, `is_representative`, and
   `selection_reason` while retaining semantic early/middle/late anchor roles.
5. Add contract tests. Required but undecided production values remain explicit
   `null` values and fail readiness validation instead of receiving guessed
   defaults.

### Work Package 1: Resolved Config And Notebook UX

1. Implement package-side Phase00 release discovery and ambiguity handling.
2. Implement the deterministic config merge, secret redaction, full config hash,
   persistence, and production-readiness preflight.
3. Replace the Notebook 01 config cell with one minimal `USER SETTINGS` cell.
4. Remove the provider selector from Notebook 01 and the public Phase01 CLI.
   Test doubles remain injectable only from tests.
5. Add Notebook preflight proving config, secrets, Phase00, checkpoint store,
   disk, CUDA/model cache, and CLI/package compatibility before expensive work.
6. Restore only Phase00 core tables, the selected batch manifest, and that
   batch's timelines, with checksum-based incremental recovery.
7. Pin Notebook 01 to the active `monolith-mvp-app` branch and verify the
   uploaded `phase01_structure` artifact/report paths after `Run All`.

### Work Package 2: Checkpoint Engine

1. Implement persistent layout
   `phase01_checkpoints/{release_id}/{video_id}/` with one `state.json`.
2. Implement local-temp write, validation, checksum, persistent sync, and atomic
   state promotion for every stage.
3. Compute input fingerprints from upstream checksums plus only the relevant
   config/model/prompt/schema subset.
4. Implement dependency invalidation without invalidating independent stages.
5. Restore the checkpoint index at startup and skip only complete, checksum-
   valid, fingerprint-matching stages.
6. Batch all outputs of one stage and the matching complete state into one
   atomic backend commit; verify recorded checksums during promotion/resume.

### Work Package 3: Shots And Search-Band Keyframes

1. Implement TransNet V2 production inference and explicit no-cut success.
2. Process early `10-30%` around `20%`, middle `40-60%` around `50%`, and late
   `70-90%` around `80%`; sample at most five evenly spaced candidates per band.
3. Reject decode failures and configured abnormal near-black/near-white frames;
   compare Laplacian variance after a common resize without a dataset-wide blur
   threshold.
4. Pick the sharpest valid candidate in each band, tie-breaking toward its
   target; expand inward while avoiding shot boundaries if a band has no valid
   candidate.
5. Deduplicate frame IDs for short shots. Fail the video if no valid frame can
   be decoded.
6. Prefer middle as representative when its quality is at least `0.85` of the
   best selected role; otherwise use the highest-quality role, tie-breaking
   toward the temporal center.

### Work Package 4: ASR, OCR, And Semantic Stages

1. Use pinned NeMo/FastConformer Vietnamese ASR by default while preserving
   Faster-Whisper Large-v3 as a config override.
2. Gate Vintern OCR with a conservative OpenCV text-presence filter; uncertain
   and detector-error frames still run Vintern, while confident no-text frames
   emit canonical empty OCR rows.
3. Load Qwen2.5-VL-7B once per chunk in explicit bitsandbytes NF4 4-bit mode
   after Vintern is released; reuse it for caption, boundary, and summary.
4. Batch one-image local requests through `request_many`: OCR defaults to four
   requests and captions to two, with adaptive CUDA OOM reduction to one.
5. Keep scene-boundary and scene-summary requests at one because each request
   contains larger multi-image/context evidence.
6. Fall back only an isolated invalid/schema-failing request to Gemini. Open a
   per-chunk Qwen circuit only for load failure, repeated batch-one OOM, or an
   unusable local runtime; do not increase Gemini concurrency.
7. Keep request-level cache in stage scratch; use the persistent completed
   stage itself as the cross-session cache to avoid per-request HF commits.

### Work Package 5: Orchestrator, Package, And Sync

1. Process one video at a time in manifest order.
2. Resume at the first invalid/missing stage; checkpoint immediately after each
   completed stage.
3. Mark exhausted OOM/transient failures `failed_retryable`, persist the error,
   clean scratch/GPU state, and continue with the next video.
4. Validate/package/sync only complete videos. Mark `sync` complete only after
   remote checksum verification.
5. Persist batch summary counts for complete, skipped, failed-retryable, and
   terminal failures without replacing per-video state.
6. Keep raw-media, checkpoint-restore, remote-verification, and model-artifact
   HF caches inside disposable scratch. Emit progress before and after every
   video/stage with current scratch free space.

### Work Package 6: Production Proof

1. Unit-test config hashing, stage fingerprints, invalidation, candidate
   selection, representative selection, OOM fallback, and state transitions.
2. Integration-test runtime restart at every atomic checkpoint boundary and
   corrupt/missing persistent outputs.
3. Run one real video through all applicable production stages.
4. Run a heterogeneous small batch proving resume, failure isolation, bounded
   concurrency, memory cleanup, API cache reuse, package, sync, and restore.
5. Run full Batch 1 only after the prior proof passes.

### Work Package 7: Runtime Memory And Lifecycle Hardening

1. Make the chunk scheduler RAM-aware and block heavy model loads below the
   configured minimum after deterministic cleanup/recheck.
2. Advance the shared semantic client through explicit caption, scene, and
   summary yields; clear generator references before the owner closes Qwen.
3. Reject Qwen CPU/disk offload, record process RSS and stage memory
   milestones, and cleanup chunk-local references before measuring chunk end.
4. Print Git/config/model identity before expensive work so stale Notebook code
   is visible immediately.
5. Preserve checkpoint semantics: caption failure leaves the first four stages
   complete and downstream unpromoted; missing complete artifacts invalidate
   the affected stage and downstream.

### Work Package 8: Production Audit Hardening

1. Guard NeMo/Faster-Whisper loads with the existing host-RAM pre-load policy
   and reject Vintern CPU/disk offload.
2. Validate fixed execution and shared semantic primary/fallback invariants.
3. Isolate non-systemic local batch errors to singleton requests and reduce
   multi-image evidence evenly only after an observed CUDA OOM.
4. Align checkpoint/package documentation with the atomic HF commit and
   diagnostics layout used by code.
5. Validate path-safe batch/worker identifiers and stream ZIP payload checksum
   verification.

### Work Package 9: Semantic-Event Keyframe Recall

1. Preserve frame-ratio early/middle/late anchor selection and add bounded,
   VFR-safe timestamp probes before the existing one-pass grouped decode.
2. Select supplemental evidence with config-versioned dHash visual novelty,
   candidate-present masked-edge text change, greedy recomputation, timestamp
   separation, and deterministic ranking.
3. Migrate `keyframes_v2` to `keyframes_v3` with a non-representative
   `supplemental` role; keep caption and summary-image policies representative
   only.
4. Run supplemental frames through OCR and preserve every supplemental path in
   focused scene evidence/contact sheets.
5. Persist config-hashed keep/drop diagnostics and test VFR coverage, static
   dedup, text change, budget, package, and downstream behavior.

### Work Package 10: Local Structured-Output Recovery

1. Version the OCR prompt without changing the canonical OCR response schema.
2. Attach the exact JSON Schema contract to every local Vintern/Qwen request
   and include the contract version in local request-cache identity.
3. Emit bounded parse-failure samples so provider output can be diagnosed
   without flooding logs.
4. Classify OCR health against actual Vintern requests and refuse checkpoint
   promotion when every Vintern request fails.
5. Preserve the OCR gate, batching, model revision, and image preprocessing;
   validate locally before any one-video real-provider smoke.

### Work Package 11: Python 3.13 Qualification And Optional Real Smoke

1. Add a lightweight `system1-phase01-qualify` entry point outside the eager
   `system1.phase01` import chain. Compose its candidate manifest from the
   union of base dependencies and `phase01-production`, replacing only the
   candidate specifiers while preserving extras and markers.
2. Run candidate installation and qualification in separate subprocesses and
   emit `phase01_runtime_qualification_v1.json` on both success and failure.
   Candidate NeMo 2.7.3 and 3.0.0 runs require separate fresh runtimes.
3. Keep the production dependency contract unchanged until a fresh Colab
   Python 3.13 qualification proves Parquet/CUDA plus real NeMo, Vintern-1B,
   Vintern-3B, and Qwen inference. Then synchronize exact runtime-critical
   versions across `pyproject.toml`, `models.yaml`, and `uv.lock`.
4. Split runtime-only checks from the composite Phase01 preflight so the smoke
   flow can validate the fresh process before restoring its deterministic
   Phase00 fixture.
5. Add explicit `computed`/`restored` execution provenance at each checkpoint
   reuse decision. Require all ten production stages through `sync` to be
   computed in the real one-video smoke.
6. Keep the smoke implementation package-owned, but expose it only through the
   explicit `phase01-smoke` developer command and a Markdown block that can be
   copied into a new Notebook code cell. Use isolated `_smoke/<run_id>`
   release/checkpoint prefixes, quantitative GPU cleanup, sanitized reports,
   and exact-file remote retention. Normal `process-batch` workers never run or
   wait for smoke.

## Dependencies And Invalidation

The minimum invalidation rules are:

- `shots` change invalidates `keyframes`, `shot_captions`,
  `shot_transcript_links`, `scenes`, `scene_summaries`, `package`, and `sync`.
- `keyframes` change invalidates `shot_captions`, `scenes`, `scene_summaries`,
  `package`, and `sync`.
- `ocr` change invalidates `shot_captions`, `scenes`, `scene_summaries`,
  `package`, and `sync`.
- `asr` change invalidates `shot_transcript_links`, `scenes`,
  `scene_summaries`, `package`, and `sync`.
- `shot_captions` change invalidates `scenes`, `scene_summaries`, `package`, and
  `sync`.
- `shot_transcript_links` change invalidates `scenes`, `scene_summaries`,
  `package`, and `sync`.
- `scenes` change invalidates `scene_summaries`, `package`, and `sync`.
- `scene_summaries` change invalidates `package` and `sync`.
- `package` change invalidates only `sync`.

Changing an unrelated stage configuration does not invalidate an independent
completed stage.

## Risks And Recovery

- Risk: an incomplete checkpoint is mistaken for complete. Mitigation: validate
  outputs and checksums in persistent storage before atomically marking a stage
  complete.
- Risk: config drift reuses incompatible artifacts. Mitigation: stage-specific
  config hashes and upstream output fingerprints.
- Risk: Colab/Kaggle disconnect, OOM, or API timeout loses work. Mitigation:
  per-stage persistent commits, one-video scheduling, bounded retry, explicit
  retryable status, and next-video continuation.
- Risk: hidden test providers leak into production. Mitigation: no public
  provider selector, production config readiness gate, and manifests that
  reject test-provider provenance.
- Risk: undecided thresholds/model revisions become accidental defaults.
  Mitigation: explicit nulls plus a failing production-readiness preflight.
- Recovery: all work is additive/versioned until the final CLI cutover. Revert
  the individual work-package commit and restore the preceding checkpoint
  schema/config version if a migration fails.

## Progress

- [x] Accept the one-pipeline Notebook 01 UX and production stage order.
- [x] Accept the search-band and representative-keyframe policy.
- [x] Complete Work Package 0 contract/config/schema/test update.
- [ ] Provision and record the one remaining production-required value: the
  generated TransNet PyTorch weight checksum.
- [x] Complete Work Package 1 resolved-config and Notebook UX.
- [x] Complete Work Package 2 checkpoint engine.
- [x] Complete Work Package 3 shots and keyframes.
- [x] Complete Work Package 4 ASR, OCR, and local-first semantic stages.
- [x] Complete Work Package 5 orchestration/package/sync.
- [ ] Complete Work Package 6 real production proof.
- [x] Complete Work Package 7 runtime memory and lifecycle hardening.
- [x] Complete Work Package 8 production audit hardening.
- [x] Complete Work Package 9 semantic-event keyframe recall.
- [x] Complete Work Package 10 local structured-output recovery.
- [ ] Complete Work Package 11 Python 3.13 qualification and optional real smoke.
  - [x] Implement reproducible candidate composition, installer/worker process
    split, sanitized qualification artifact, and fresh-runtime fallback guard.
  - [x] Implement runtime-only preflight, checkpoint decision provenance,
    isolated HF smoke runner, cleanup/reporting, smoke-only CLI, and thin
    optional Notebook orchestration block.
  - [x] Run Gate 1 on a fresh Colab Python 3.13 GPU, pin the qualified
    production dependency tuple, and regenerate the complete lock.
  - [ ] Run Gate 2 one-video full-pipeline smoke from the pinned production
    commit before the heterogeneous batch proof.

## Decisions

- 2026-08-13: Notebook 01 has one production pipeline; user-facing execution
  modes and provider profiles are prohibited.
- 2026-08-13: Notebook settings contain only operator/environment inputs.
  Deterministic behavior belongs to versioned repository config.
- 2026-08-13: Resume authority is per `video_id + stage` in persistent storage;
  local notebook storage is scratch only.
- 2026-08-13: Videos run sequentially and GPU-heavy models are not resident at
  the same time.
- 2026-08-13: The three keyframe percentages are search-band centers rather
  than exact-frame requirements. Representative selection uses the `0.85`
  middle-quality rule.
- 2026-08-13: Exact model revisions and numeric quality/retry/scene settings are
  versioned. The converted TransNet weight checksum remains a blocker until the
  parity-verified artifact is produced.
- 2026-08-13: Keyframe candidate decoding uses one sequential video pass and
  retains only one shot's candidate group, bounding peak RAM on Colab/Kaggle.
- 2026-08-16: Gemini request caching is stage-local. Persistent resume
  authority is one atomic backend commit containing the stage outputs and
  matching complete state marker; resume revalidates every recorded checksum.
- 2026-08-16: Phase00 restore is batch-scoped and checksum-resumable; unrelated
  batch timelines are not downloaded into Colab/Kaggle scratch.
- 2026-08-24: Checkpoint repository visibility is an operator choice. Public
  repositories are accepted; the preflight proves access and write/read
  behavior without imposing a private-repository policy.
- 2026-08-24: Hugging Face download caches used for raw media, checkpoint
  restore/verification, model artifacts, and remote artifact verification are
  disposable scratch scoped to the run or video. Notebook 01 exposes
  video/stage/disk progress and verifies the remote Phase01 layout after a run.
- 2026-08-25: NeMo/FastConformer Vietnamese is the ASR default. One shared
  Qwen2.5-VL-7B NF4 runtime is primary for caption, scene boundaries, and scene
  summaries; Gemini is a request-scoped fallback unless a systemic local
  failure opens the remainder-of-chunk circuit breaker.
- 2026-08-25: OCR runs a conservative config-hashed OpenCV text-presence gate
  before Vintern and maps confident no-text results to canonical `ocr_v2`
  `status=empty` rows without inventing a new status.
- 2026-08-25: Runtime chunks use configured RAM pressure limits of 8/4 GiB for
  4/2/1 video planning. Heavy model loads require at least 4 GiB available
  after cleanup, and Qwen CPU/disk offload is a systemic provider failure.
- 2026-08-25: The pinned logical NeMo model ID resolves on Hugging Face to the
  canonical Vietnamese source repository at the same immutable revision, so
  no model identity migration is required.
- 2026-08-25: A checkpoint stage promotion is one atomic backend commit
  containing outputs and the matching state marker. Resume accepts it only
  after checksum validation; documentation must not describe a separate state
  commit.
- 2026-08-25: Mandatory anchor selection remains frame-ratio based. Supplemental
  probes alone use exact `pts_time`; only visual/text novelty may produce a
  bounded non-representative `supplemental` row, while captions and summary
  images stay representative-only.
- 2026-08-25: Local Vintern/Qwen generation receives a versioned exact JSON
  Schema contract. OCR may degrade per request, but a video with zero
  successful Vintern responses must fail the OCR stage before promotion.
- 2026-08-29: Runtime qualification is a separate lightweight console entry
  point because the main CLI eagerly imports Phase01. Candidate manifests are
  the union of base and production-extra direct dependencies and preserve
  NeMo's `[asr]` extra and requirement markers.
- 2026-08-29: Production dependency pins may change only after an isolated
  fresh-Colab Python 3.13 qualification artifact passes. Candidate B may not
  reuse candidate A's runtime.
- 2026-08-29: An explicit smoke run performs runtime-only preflight, restores a
  pinned one-video fixture, then runs composite preflight and the unchanged
  production batch core. All required stages must record `computed` at the
  actual reuse decision for the smoke report to pass.
- 2026-08-30: Package implementation now provides
  `system1-phase01-qualify`, `run_phase01_runtime_preflight()`,
  `run_phase01_smoke()`, and `phase01-smoke`. Notebook 01 invokes production
  `process-batch` directly; the smoke-only CLI appears in Markdown for a
  developer to copy into a new code cell when one-time implementation proof is
  wanted.
- 2026-08-30: The isolated `py313-nemo273` candidate pins Transformers
  `4.57.6`, the latest patch in the `~=4.57.0` minor required by NeMo 2.7.3
  ASR.
- 2026-08-30: Gate 1 run `20260830T061502Z_d6a7d17c` passed all checks on
  Colab Python `3.13.15` with a Tesla T4 and set `ready_to_pin_production=true`.
  Production now pins NumPy `2.1.3`, NeMo `2.7.3`, and Transformers `4.57.6`;
  Torch `2.8.0`, TorchVision `0.23.0`, and TorchAudio `2.8.0` remain unchanged.

## Still Required Before A Production Run

All code/config decisions are authoritative except the checksum generated by
the one-time official TransNet converter parity job. Before a production run:

- run `scripts/prepare_transnetv2_artifact.py`, upload the bundle to the
  configured writable model-artifact store, and set the printed
  `weights_sha256` in `models.yaml`;
- create/verify a writable checkpoint repository (public or private) and
  configure secrets;
- allow Phase00 auto-resolution when the completion manifest contains
  `completed_at`; use `release_id_override` only for legacy snapshots without
  that field;
- choose a real one-video fixture and heterogeneous small batch, complete the
  generated 12-item stratified manual review, then authorize the full batch.

## Validation

- Focused proof covers config/hash/readiness, Phase00 resolution, checkpoint
  batch-scoped restore/corruption recovery, checkpoint grouped promotion,
  restore/corruption/invalidation, TransNet partitioning, one-pass grouped
  frame decoding, search-band selection, both ASR providers, OCR gate behavior,
  true/adaptive local batching, request/systemic fallback separation, shared
  Qwen residency, scene voting/review, strict package assembly, and QA sampling.
- The current local suite passes 394 tests. Notebook 01 code cells compile,
  both new YAML contracts parse, both CLI help surfaces load, and
  `git diff --check` and `uv lock --check` pass. The lock records the
  qualification helper's `packaging` dependency and no longer advertises the
  removed `google-genai[aiohttp]` production extra. Fresh-Colab Gate 1 run
  `20260830T061502Z_d6a7d17c` subsequently passed the complete dependency,
  CUDA, real-provider, and cleanup contract and selected the production tuple.
- Runtime-hardening tests prove one Qwen load/close per chunk across captions,
  scenes, and summaries; Vintern-before-Qwen release ordering; request/systemic
  fallback separation; RAM-aware 4/2/1 scheduling; pre-load RAM blocking;
  checkpoint failure semantics; and release of chunk client references.
- CLI/notebook contracts prove that no Phase01 provider selector is exposed and
  Notebook 01 has one package invocation with minimal settings.
- Local structured-output recovery proof passes 37 focused OCR/VLM/orchestrator
  tests and 39 Phase01 production-contract tests. It proves that exact schemas
  reach both Vintern and Qwen, cache identity changes with the contract version,
  parse telemetry is bounded, and all-request Vintern failure cannot promote
  the OCR checkpoint. Ruff F/E9/I passed at that work-package checkpoint; Ruff
  is not installed in the current local environment.
- Real-provider one-video, heterogeneous-batch, disconnect-at-every-boundary,
  and Colab/Kaggle platform proof remain Work Package 6.

## Result

Active. Work Packages 0-5, 7, and 8 are implemented locally. On 2026-08-25 the
production defaults moved to NeMo/FastConformer ASR, gated Vintern OCR, and a
shared 4-bit Qwen semantic runtime with scoped Gemini fallback. Phase01 now
also preserves mandatory anchors while adding bounded visual/text-novel
supplemental keyframes. These paths, checkpoint invalidation, lifecycle
telemetry, RAM guards, batching isolation, supplemental evidence, and packaging
are covered by the 393-test local suite. OCR and the shared Qwen runtime now
receive the exact versioned JSON Schema in their prompts; OCR records bounded
parse diagnostics and fails before checkpoint promotion when every Vintern
request fails. The intentionally deferred gate is
operational proof: provision the parity-verified TransNet artifact/checksum,
then run one real video, a heterogeneous small batch with manual review, and the
target Colab/Kaggle batch. Until those observable runs pass, the implementation
must not be described as production-validated. Work Package 11 code and local
contracts are implemented; its live Python 3.13 qualification and real HF/GPU
smoke acceptance remain pending.
