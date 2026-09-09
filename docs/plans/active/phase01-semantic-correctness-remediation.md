# Execution Plan: Phase01 Semantic Correctness Remediation

Date: 2026-09-01

## Status

Active

## Outcome

Notebook 01 produces semantically usable Phase01 artifacts for scene grouping,
ASR-to-scene alignment, scene summaries, and dynamic shots without silently
promoting pathological scene partitions, duplicating whole ASR segments across
scenes, or inventing unsupported relationships between speech and visuals.

The final implementation must preserve the existing Phase01 checkpoint and
package architecture, invalidate only affected downstream stages, and keep
local contract evidence separate from real-provider acceptance evidence.

## Context

Repository authority and affected surfaces:

- `docs/WORKFLOW.md`
- `docs/architecture/system1-scene-grouping.md`
- `docs/architecture/system1-notebook01-production-pipeline.md`
- `docs/decisions/0014-multimodal-context-window-scene-grouping.md`
- `docs/decisions/0020-phase01-speech-aware-asr-decoding.md`
- `system1/configs/models.yaml`
- `system1/configs/phase01.yaml`
- `system1/schemas/`
- `system1/src/system1/asr/`
- `system1/src/system1/scenes/`
- `system1/src/system1/phase01/production.py`
- `system1/src/system1/phase01/validation.py`
- `system1/tests/test_phase01_scene_grouping.py`
- `system1/tests/test_phase01_production_contract.py`
- `system1/tests/test_phase01_asr*.py`

The read-only audit was performed on clean `dev` at
`19d733930196870cbb3d40d1f386ac5c2fe7fb23`, matching `origin/dev`. Each task
must re-check the current branch because this baseline will change as preceding
tasks are integrated.

Observed defects and gaps:

1. Consistency review may return `BOUNDARY` for every gap, after which package
   code partitions immediately. Structural validation accepts a pathological
   but contiguous partition such as 18 shots becoming 18 scenes.
2. `scene_transcript_links` links every overlapping ASR segment, while scene
   summary construction copies the complete segment text into every linked
   scene. A segment crossing a scene boundary can therefore leak or duplicate
   speech.
3. NeMo currently emits segment-level timestamps only. The canonical contract
   has no word/alignment representation for precise scene clipping.
4. Scene grouping receives transcript text, but has no explicit deterministic
   cross-gap speech-continuity features or coverage evidence.
5. `scene_summaries_v3` directly fuses visual and speech evidence. It has no
   independent speech/visual summaries or canonical audio-visual relation.
6. Scene transcript evidence is appended after visual evidence and the whole
   blob is truncated, so long scenes can lose speech evidence positionally.
7. Shot captions use only the representative keyframe even though Phase01 may
   retain early, middle, late, and supplemental keyframes for a dynamic shot.
8. Tests do not cover persistent all-boundary review output, cross-scene
   transcript leakage, adaptive audio-visual relations, or long dynamic-shot
   progression.
9. Some architecture and current-state documentation describes older provider,
   response, and review behavior and must be synchronized with the final code.

Corrections established by the audit:

- A one-shot scene is not inherently invalid. Only suspicious partition
  patterns require review or a promotion gate.
- Null `reason`, `confidence`, and `evidence_used` fields are intentional under
  the current label-only boundary contract; they are not evidence of a parser
  failure.
- Canonical ASR rows and checkpoint state already carry model provenance.
- `keyframes.parquet` exists inside the checkpoint bundle and directly in the
  final structure package.
- The final structure ZIP already contains `artifact_manifest.json`.

## Implementation Rule

This plan defines target semantic behavior, defects, constraints, dependencies,
and acceptance criteria. Before implementing each task, inspect the current
`dev` branch and relevant production code.

If a proposed helper, table, stage, or filename conflicts with the current
architecture, preserve the target behavior and invariants, document the
discrepancy in this plan, and choose the smallest architecture-consistent
implementation. Do not silently weaken or change the intended semantic
behavior.

Do not implement all tasks in one change. For every task:

1. update its status to In Progress;
2. implement only that task's scope;
3. add focused proof and update affected contracts/docs;
4. record files, behavior, validation, and remaining risks here;
5. commit and push the completed task when explicitly requested;
6. stop for review before starting the next task.

## Scope

In scope:

- Scene-partition semantic safety and promotion policy.
- Boundary-aware ASR alignment and scene-specific transcript construction.
- Speech-continuity evidence for scene grouping without making ASR authoritative.
- Adaptive, grounded audio-visual scene summaries.
- Dynamic multi-frame understanding for eligible long or changing shots.
- Focused regression fixtures, semantic golden cases, provenance, diagnostics,
  checkpoint invalidation, and documentation needed by those behaviors.

Out of scope:

- A separate canonical Narrative Span entity.
- System 2 retrieval/index implementation changes.
- Replacing TransNet, the checkpoint store, or the Phase01 package architecture.
- Full-dataset production execution before heterogeneous acceptance gates pass.
- Treating one ASR segment as one scene or one camera cut as one semantic scene.

## Approach

### Task 1-3 Closure

Status: Accepted

This closure pass preserves the accepted Task 1 and Task 2 contracts and the
implemented Task 3 behavior while resolving four remaining correctness gaps:
gap-local speech reliability, canonical PTS-derived shot time boundaries,
asynchronous quarantine/manual disposition for persistently suspicious scene
partitions, and the corresponding DAG/version/QA/documentation updates. It does
not begin Task 4.

Implemented from clean `dev` at `46f9252`. Aligned-speech v2 makes missing
left/right word evidence explicitly neutral; shot time boundaries now form an
exact decoded-PTS partition; persistent suspicious partitions are stored as
immutable review candidates and return without promoting scenes or blocking
other videos; exact approval resumes the existing candidate without repeating
VLM grouping, while rejection is durable. Scenes now directly depend on ASR.

Version impact: Phase01 pipeline/production v1.9,
`aligned_speech_continuity_v2`, `scene_grouping_v4`, `scenes_v4`,
`scene_boundary_diagnostics_v4`, and `scene_partition_quality_v2`. Models stay
v1.6; checkpoint state stays v2; package/video manifest stays v3; scene
summaries stay v3.

### Task 1: Scene Grouping Correctness

Status: Accepted

Objective: Prevent suspicious partitions such as every adjacent gap becoming a
boundary from being silently promoted as canonical.

Required behavior:

- Compute deterministic post-review metrics such as boundary density,
  scene-to-shot ratio, one-shot-scene rate, shots per scene, and scene duration.
- Define an authority-backed suspicious-partition policy without declaring all
  one-shot scenes invalid.
- Re-evaluate suspicious output with a wider/global semantic review when the
  configured policy permits it.
- If output remains suspicious or unresolved, fail promotion or emit an
  explicit review-required outcome according to the accepted contract; never
  silently pass solely because ranges are contiguous.
- Make configured review-round semantics match implementation.
- Replace misleading legacy-null diagnostics with useful deterministic metrics
  or document why retained fields remain nullable.
- Preserve package ownership of IDs, ranges, and final partition construction.

Focused acceptance cases:

- Primary and consistency review both return `BOUNDARY` for every gap.
- A genuine rapid montage with supported one-shot scenes is not rejected solely
  because its ratio is high.
- All-false boundaries remain a valid one-scene result.
- Review/failure paths are bounded and checkpoint promotion behavior is explicit.

### Task 2: ASR Temporal Alignment

Status: Accepted

Local contract is closed. Live T4/Colab/Kaggle provider smoke is deferred
until Tasks 3-5 are complete and is not claimed by this acceptance.

Depends on: Task 1 accepted.

Objective: Build scene-specific speech evidence without copying a complete ASR
segment into every overlapping scene.

Required behavior:

- Inspect pinned NeMo 2.7.3 and Parakeet CTC behavior before selecting an
  alignment implementation.
- Establish a provider-neutral reliable alignment contract. Native word
  timestamps may be used when trustworthy; otherwise preserve CTC alignments
  and add deterministic alignment.
- Add canonical aligned-unit storage when required, with stable IDs,
  timestamps, segment provenance, schema versioning, and validation.
- Upgrade shot/scene transcript linking or add derived scene transcript text so
  each consumer receives only speech attributable to its interval.
- Preserve overlap/coverage evidence and prevent duplicate text within a scene.
- Decide whether `scene_transcript_links` becomes a separately checkpointed
  stage based on the current DAG; document the decision and invalidate exactly
  the affected downstream stages.
- Preserve explicit behavior for no-audio, no-speech, low-confidence, and
  provider/alignment failure.

Focused acceptance cases:

- One utterance crosses two shots in one scene.
- One ASR segment crosses a real scene boundary and is not copied whole to both.
- Alignment has missing or low-confidence units.
- Empty ASR remains schema-valid and does not fabricate speech.
- Forced-split overlap does not duplicate boundary tokens.

Real-provider acceptance:

- A pinned one-video T4 smoke and inspection of rejected/aligned ASR evidence is
  required before claiming live acceptance.
- Local tests or a mock hypothesis do not substitute for this smoke.
- If credentials, artifacts, or the runtime are unavailable, record the gate as
  pending rather than weakening it.

### Task 3: Speech-Aware Scene Grouping

Status: Accepted - Live Semantic Calibration Pending

Baseline: `59b6c62`, including the retained-ASR dedup correction after the
guide's `a8d777d` snapshot. Both supplied Task 3 attachments are identical.
Current Markdown workflow supersedes the retired Harness context CLI.
Package format remains `phase01_structure_v3`: no table/file shape is added;
the versioned scene table records the new grouping implementation instead.

Implemented contract: `aligned_speech_continuity_v2` derives one immutable
evidence record per adjacent-shot gap from canonical `asr_words`, Task 2's
word-to-shot assignment, shot transcript-link coverage, and the persisted ASR
status. Same-segment crossing requires assigned words on both sides; temporal
proximity may remain positive across forced-split segment IDs. Reliability is
gap-local: even `pass` ASR is neutral when either neighboring shot lacks
aligned words. Unreliable evidence renders only its reason and
`NOT_EVALUATED`. All four VLM review routes receive the same evidence contract,
while Python voting and labels remain non-authoritative with respect to speech.

The Task 1-3 closure also replaces terminal handling of a persistently
suspicious partition with an immutable asynchronous review candidate. Exact
fingerprint approval resumes and promotes only that candidate; rejection is a
durable non-canonical disposition; other videos continue without waiting.
Canonical shot time ranges now partition decoded PTS exactly, and scenes have
a direct ASR DAG dependency because gap reliability reads persisted ASR status.

Version impact: `scene_grouping_v4`, `scenes_v4`,
`scene_boundary_diagnostics_v4`, `scene_partition_quality_v2`, Phase01
pipeline/production v1.9, and aligned-speech v2. Models remain v1.6; package,
checkpoint, ASR, transcript-link, and scene-summary formats remain unchanged.
The exact ending commit is recorded in Git history and the final handoff report
because a commit cannot contain its own final SHA.

Depends on: Task 2 accepted.

Objective: Make speech continuity explicit evidence for a scene boundary while
keeping audiovisual event continuity authoritative.

Required behavior:

- Add deterministic gap features for aligned speech spanning the left/right
  shots, including relevant coverage and alignment quality.
- Render those features clearly in primary, focused, and consistency evidence.
- Treat reliable same-utterance crossing as strong non-boundary evidence, not a
  hard constraint.
- Allow strong visual/event/topic changes to create a boundary during continuous
  documentary voice-over.
- Reduce or omit influence from missing or unreliable ASR.
- Preserve empty-ASR visual scene grouping.

Focused acceptance cases:

- Interview speaker cuts during one utterance remain one scene.
- Sports and cooking commentary spanning camera cuts supports continuity.
- Continuous documentary narration over a genuine visual/event change does not
  prohibit a boundary.
- Silent video still groups from visual/event evidence.

### Task 4: Adaptive Scene Summary

Status: Accepted - Live Semantic/Provider Validation Pending

Depends on: Task 3 accepted.

Objective: Produce grounded scene summaries that fuse speech and visuals when
aligned and explicitly separate them when they differ.

Required behavior:

- Introduce a new schema version after `scene_summaries_v3`; do not reuse the
  existing version name for a different contract.
- Represent speech semantics and visual semantics independently before final
  synthesis.
- Add a canonical audio-visual relation with accepted values covering at least
  `aligned`, `complementary`, `partial`, `b_roll`, `unrelated`,
  `contradictory`, and `no_speech`.
- Persist Vietnamese and English speech/visual/final summaries plus evidence
  identities needed for audit and retrieval.
- Use adaptive generation: natural fusion for aligned evidence, selective
  fusion for partial evidence, and explicit source separation for B-roll or
  unrelated evidence.
- Prohibit causal, identity, spatial, temporal, or organizational relationships
  not supported by the appropriate modality.
- Preserve ordered visual progression rather than treating captions as a bag of
  words.
- Allocate separate visual/caption, OCR, and speech budgets so transcript is not
  removed because it appears last.
- Define no-speech and contradictory behavior without fabricating certainty.

Focused acceptance cases:

- Aligned football commentary and action fuse naturally.
- Aligned cooking narration and ordered actions fuse naturally.
- Documentary expansion narration over cat-care B-roll separates what is said
  from what is shown.
- Partial alignment fuses supported claims and attributes narration-only facts.
- Unrelated or contradictory modalities remain explicitly separated.
- Silent scenes produce visual-first summaries with `no_speech`.

### Task 5: Dynamic Shot Understanding

Status: Implementation Complete - Review Pending

Depends on: Tasks 1-4 accepted.

Objective: Improve temporal recall for a continuous long or changing shot
without increasing every caption request unnecessarily.

Required behavior:

- Define deterministic eligibility for representative-only versus multi-frame
  captioning using available duration, novelty, text-change, and supplemental
  evidence.
- Use ordered early/middle/late/supplemental frames for eligible dynamic shots.
- Generate a temporal shot description that preserves action progression.
- Persist all source keyframe IDs/timestamps and selection policy in provenance.
- Keep the existing one-row-per-shot canonical ownership model unless a durable
  contract decision explicitly changes it.
- Avoid duplicating near-identical frames or inventing motion between unrelated
  samples.

Focused acceptance cases:

- Static short shot remains representative-only.
- Continuous cooking shot preserves `hold egg -> crack egg -> add to pan -> stir`.
- Long shot with no meaningful change does not receive unnecessary multi-frame
  processing.
- Selected source frames are traceable from the canonical caption provenance.

## Risks And Recovery

- Semantic thresholds can reject genuine montage. Mitigate with multi-signal
  suspicion, explicit review, golden fixtures, and no unconditional ratio rule.
- Alignment APIs may not match pinned NeMo/Flashlight behavior. Inspect the
  actual pinned runtime and preserve provider-neutral contracts before schema
  changes.
- New schemas can break downstream readers. Version additively, update package
  validation and consumers in scope, and retain clear migration notes.
- Prompt-only behavior is not deterministic proof. Pair prompt changes with
  structured outputs, Python validation, and behavioral fixtures.
- Expanding captions can increase VRAM and latency. Gate multi-frame requests
  deterministically and retain representative-only behavior for normal shots.
- A task regression can invalidate downstream checkpoints. Recovery is to
  revert that task's coherent commit and reuse the last validated upstream
  stage; never delete checkpoint history to hide an incompatibility.

## Progress

- [x] Read-only audit of current `dev` code, docs, schemas, and test source.
- [x] Record master remediation scope and five-task dependency order.
- [x] Task 1: Scene Grouping Correctness.
- [x] Review and accept Task 1 before Task 2.
- [x] Task 2: ASR Temporal Alignment implementation and local proof.
- [x] Review and accept Task 2 before Task 3.
- [x] Task 3: Speech-Aware Scene Grouping implementation and local proof.
- [x] Review and accept Task 3 before Task 4.
- [x] Task 4: Adaptive Scene Summary implementation and local proof.
- [x] Review and accept Task 4 before Task 5.
- [x] Task 5: Dynamic Shot Understanding implementation and local proof.
- [ ] Run required heterogeneous real-provider acceptance and close remaining
  semantic risks.
- [ ] Move this plan to `docs/plans/completed/` only after verified closure.

## Decisions

- 2026-09-01: Use a dedicated remediation plan rather than expanding the
  general Notebook 01 production plan because this work has its own dependency
  chain, recovery requirements, and semantic acceptance gates.
- 2026-09-01: Execute five reviewed tasks sequentially. Later task guides must
  be based on the branch produced by accepted earlier tasks.
- 2026-09-01: Golden semantic cases are accumulated within each task instead of
  deferred to a separate final implementation task.
- 2026-09-01: Keep dynamic-shot understanding last because it improves recall
  but does not fix the current P0 scene-partition or transcript-leakage defects.
- 2026-09-01: Treat live ASR/provider smoke as separate acceptance evidence,
  not as interchangeable with local tests.
- 2026-09-01: Task 1 started on `dev` at baseline `19d7339`; scope is limited
  to consistency-loop semantics, partition-quality assessment and recovery,
  promotion/package gates, diagnostics, current documentation, and focused
  proof.
- 2026-09-01: Task 1 uses `scene_partition_quality_v1` with a conservative
  minimum of eight shots. Every-gap boundaries are suspicious; otherwise both
  boundary density and one-shot-scene rate must cross their configured
  thresholds. The policy triggers semantic review or failure only and never
  edits labels heuristically.
- 2026-09-01: Suspicious partitions receive bounded `degenerate_review`
  requests through the existing shared Qwen/Vintern semantic client. A result
  that remains suspicious raises terminal `ScenePartitionQualityError` before
  scene outputs can be promoted.
- 2026-09-01: The material algorithm change is recorded as `scenes_v2` /
  `scene_grouping_v2`; deterministic boundary diagnostics are
  `scene_boundary_diagnostics_v2`. The existing stage hash already scopes all
  policy, model, prompt, and schema changes to scenes and downstream stages.
- 2026-09-02: Task 1 review found that consistency-trigger regions could merge
  into whole-video requests, and terminal quality failures deleted their local
  per-gap evidence. The closure patch bounds every consistency focus to eight
  gaps and its context to at most seventeen shots with current defaults,
  persists non-canonical failure diagnostics under the checkpoint failure
  namespace, and synchronizes current provider authority before Task 2.
- 2026-09-02: Failed quality evidence uses
  `failures/scenes/{scene_fingerprint}/{diagnostic_fingerprint}` and contains
  the partition-quality JSON plus per-gap boundary JSONL. It never changes the
  scenes stage to complete; checkpoint `error.details` and the worker result
  expose `diagnostics_ref` for operators.
- 2026-09-02: Task 2 started from clean `dev` at `b7bd2ee`. Installed source
  inspection confirms NeMo 2.7.3. Flashlight beam search initially produces
  token IDs, but `EncDecCTCModel.transcribe(..., return_hypotheses=True)`
  replaces the returned `Hypothesis.y_sequence` with the `T x V` CTC
  log-probability tensor and retains that tensor in `alignments`; no separate
  `logprobs` field exists on the returned hypothesis. Beam timestamp mode is
  explicitly unsupported, so Task 2 will not enable `compute_timestamps` or
  rerun greedy decoding.
- 2026-09-02: Task 2 uses a deterministic CTC Viterbi adapter over the preserved
  log probabilities and retokenizes the canonical Flashlight text with the
  loaded model's own tokenizer. Word grouping follows NeMo's model-aware
  tokenizer structure (BPE/SentencePiece for the pinned Parakeet model, with
  char-vocabulary compatibility). Output timestep duration is derived from
  `model.cfg.preprocessor.window_stride * model.encoder.subsampling_factor`,
  matching NeMo 2.7.3's forced-alignment utility; it is never hard-coded.
- 2026-09-02: Segment overlap remains provenance in transcript-link v2 tables;
  interval text is now assembled only from canonical aligned words. Assignment
  uses maximum temporal overlap and a midpoint/half-open right-boundary tie
  rule, so one canonical word is never copied into two shots or scenes.
- 2026-09-02: `scene_transcript_links` is an independent deterministic stage
  after accepted scenes. Checkpoint state v1 is migrated before v2 validation;
  the new stage starts pending and a previously complete video becomes running
  until the new stage and downstream outputs are rebuilt.
- 2026-09-04: Task 2 is accepted on local contract evidence. The operator will
  run the pinned T4 Colab/Kaggle notebook smoke once after Tasks 3-5, not as a
  per-task gate. This acceptance unblocks Task 3. It does not claim live ASR
  timestamp quality, forced-split behavior on real audio, or heterogeneous
  speech-batch proof.
- 2026-09-08: Task 3 keeps Task 2 word assignment as temporal authority and
  introduces `aligned_speech_continuity_v1` in the scene evidence layer. Shared
  segment IDs are grounded in word ownership, not interval overlap; reliable
  near-boundary speech is strong VLM context but never a deterministic
  non-boundary rule. This preserves documentary/news voice-over boundaries and
  visual-only grouping for missing or unreliable ASR.
- 2026-09-08: Task 3 keeps `phase01_structure_v3` because it adds no canonical
  table or packaged file. The changed scene semantics are versioned by
  `scenes_v3` / `scene_grouping_v3`; the existing scenes stage hash covers the
  speech policy, prompt configuration, and scene schema, so upstream ASR,
  words, links, captions, OCR, keyframes, and shots remain reusable.
- 2026-09-08: The Task 1-3 closure replaces video-level-only speech
  reliability with `aligned_speech_continuity_v2`. A gap is reliable only when
  ASR status is `pass` and both adjacent shots own aligned words. Missing-side
  evidence is rendered as neutral `NOT_EVALUATED`, never as discontinuity.
- 2026-09-08: Canonical shot time uses `next_shot_start_pts_v1`: each non-final
  shot ends at the exclusive end frame's decoded PTS, and only the final frame
  uses its positive duration. This prevents VFR frame-duration metadata from
  creating temporal gaps or overlaps.
- 2026-09-08: A partition still suspicious after deterministic and degenerate
  review is quarantined as an immutable `scene_partition_review_candidate_v1`
  instead of becoming a technical terminal failure. Exact
  `scene_partition_manual_review_v1` approval permits deferred promotion;
  rejection is durable; changed input/config cannot consume a stale decision.
- 2026-09-08: Scenes directly depend on ASR because gap reliability consumes
  `asr_status.json`. Current versions are pipeline/production v1.9,
  aligned-speech v2, grouping/scenes v4, boundary diagnostics v4, and partition
  quality v2. Models v1.6, checkpoint v2, package v3, and summaries v3 are
  intentionally unchanged.
- 2026-09-09: Task 4 replaces direct raw multimodal fusion with independent
  speech-only and visual-only summaries inside the existing scene-summaries
  stage. Only those independent Vietnamese summaries enter the strict
  audio-visual relation pass, and only the summaries plus relation enter final
  synthesis. Canonical aligned words remain speech authority; segment links
  remain provenance.
- 2026-09-09: `scene_summaries_v4` records bilingual modality summaries,
  `available | no_speech | unavailable` speech state, the eight-value relation
  taxonomy, and deterministic SHA-256 identities for the exact bounded speech
  and visual evidence. `no_audio`/`no_speech` produce deterministic visual-only
  output with relation `no_speech`; low-confidence ASR or a pass-status scene
  with zero owned words uses `speech_unavailable`, never inferred silence.
- 2026-09-09: Visual and speech evidence have independent budgets. Visual
  overflow keeps complete, evenly spaced shot blocks spanning the scene;
  speech keeps complete chronological canonical words. Text-only Qwen calls
  carry no images, while Vintern fallback receives a deterministic neutral
  placeholder rather than scene imagery. Pipeline/production are v1.10 and
  models are v1.7; checkpoint v2 and package/video-manifest v3 remain valid.
- 2026-09-10: Task 5 keeps one canonical `shot_captions_v4` row per shot and
  selects request evidence deterministically. A shot uses its representative
  image unless it has at least two distinct usable keyframes and either a
  meaningful supplemental keyframe, or it is at least three seconds long with
  a threshold-crossing dHash/OCR change. Duration alone never selects temporal
  mode.
- 2026-09-10: Eligible dynamic shots use one deterministic, chronological
  storyboard for all eight semantic fields and for the Vintern fallback. Shot
  caption requests contain visual/OCR evidence only; ASR and transcript
  evidence remain excluded. Field provenance v2 commits to the exact source
  keyframes, source image hashes, trigger metrics, storyboard hash, and semantic
  evidence fingerprint.
- 2026-09-10: Shot captions now directly depend on shots, keyframes, and OCR.
  Pipeline/production are v1.11 and models are v1.8; caption, checkpoint, and
  package schemas remain unchanged. Upstream shots, keyframes, ASR, OCR, and
  shot-transcript links remain reusable; captions and their semantic downstream
  stages recompute.

## Validation

Task 5 local proof on 2026-09-10:

- focused dynamic-shot tests: 29 passed;
- dynamic-shot, production-contract, QA, batch-orchestrator, table-schema, and
  Task 1-3 scene regression set: 203 passed;
- Phase01 suite excluding the two environment-dependent modules
  `test_phase01_vlm_client.py` and `test_phase01_asr_alignment.py`: 347 passed;
- the wider System1 suite with those two modules excluded: 553 passed and one
  pre-existing Notebook 00B assertion failed because that notebook does not
  contain `monolith-mvp-app`; Task 5 does not modify Notebook 00B;
- `test_phase01_asr_alignment.py`: 6 passed and 3 failed because this Python
  environment does not have the `nemo` package;
- the complete Phase01 collection stopped because `torch` is unavailable to
  `test_phase01_vlm_client.py`;
- repository-root `pytest -q` stopped during collection with 22 missing-runtime
  import errors across Kaggle, MVP, and System1; no test assertion ran in that
  command;
- Ruff over every Task 5 changed Python/test file, `python -m compileall`, and
  `git diff --check`: passed;
- real T4 / Parakeet / Qwen / Vintern validation: not run. Live dynamic-caption
  quality and heterogeneous semantic acceptance remain the operator gate.

Task 4 local proof on 2026-09-09:

- adaptive scene-summary tests: 27 passed; production-contract tests: 87
  passed;
- QA, generic table-schema, batch-orchestrator, and foundation tests: 39
  passed;
- Task 1-3 grouping, speech, review, ASR, and transcript-link regressions: 93
  passed;
- Phase01 suite excluding the two environment-dependent modules
  `test_phase01_vlm_client.py` and `test_phase01_asr_alignment.py`: 318 passed;
- the wider System1 suite with those two modules excluded: 525 passed and one
  pre-existing Notebook 00B smoke assertion failed because that notebook does
  not contain `monolith-mvp-app`; Task 4 does not modify Notebook 00B;
- `test_phase01_asr_alignment.py`: 6 passed and 3 failed because this Python
  environment does not have the `nemo` package;
- `test_phase01_vlm_client.py` could not collect because this Python
  environment does not have `torch`;
- repository-root `pytest -q` stopped during collection with 22 missing-runtime
  import errors across Kaggle, MVP, and System1 (`gradio_client`, `trake`,
  `torch`, `faiss`, project-local import roots); no test assertion ran in that
  command;
- Ruff 0.12.12 over every Task 4 changed Python/test file: passed;
- `python -m compileall` over System1 source and affected tests: passed;
- `git diff --check`: passed;
- real T4 / Parakeet / Qwen / Vintern validation: not run. Live heterogeneous
  semantic acceptance remains the operator gate after Tasks 4-5.

Task 1-3 closure local proof on 2026-09-08:

- closure-focused review/shot/speech/grouping/production/batch/QA/schema/
  checkpoint/ASR-link tests: 219 passed;
- expanded Phase01 set excluding the environment-dependent NeMo alignment
  module: 304 passed;
- `test_phase01_asr_alignment.py`: 6 passed and 3 could not execute because
  this Python environment does not have the `nemo` package;
- `pytest -q system1/tests/test_phase01*.py` stopped during collection because
  `torch` is unavailable to `test_phase01_vlm_client.py`;
- repository-root `pytest -q` stopped during collection with 22 missing-runtime
  import errors across Kaggle, MVP, and System1 (`gradio_client`, `trake`,
  `torch`, `faiss`, and project-specific import roots); no test assertion ran
  in that command;
- Ruff 0.12.12 over every closure-changed Python/test file: passed;
- `python -m compileall` over System1 source and focused new tests: passed;
- `git diff --check`: passed;
- live T4 / Parakeet / Qwen / Vintern validation: not run and remains an
  operator gate after Tasks 3-5.

Task 2 follow-up on 2026-09-08: local closure complete. Forced-overlap
deduplication now runs after final rejection decisions and preserves raw quality
evidence. ASR-hashed `retained_after_quality_v2` invalidates pre-fix checkpoints
and their dependent stages; shots, keyframes, OCR and captions remain reusable.
Task 3 implementation is complete and awaiting review. Real Qwen/Vintern
semantic interpretation and threshold calibration remain part of the shared
post-Task-5 GPU acceptance run.

- ASR/alignment/production-contract/checkpoint focused suite: 106 passed.
- `pytest -q tests/test_phase01*.py`: 252 passed; 463 warnings from unavailable
  NVML in the sandbox, not live GPU qualification.
- Ruff on all changed Python files: passed; `git diff --check`: passed.
- Full suite was not rerun for this bounded follow-up. Live provider smoke
  remains deferred under the existing post-Task-5 acceptance decision.

Task 3 local proof on 2026-09-08:

- focused scene-speech/grouping/config/QA/schema suite: 149 passed;
- `pytest -q tests/test_phase01*.py`: 293 passed;
- full `pytest -q`: 499 passed, with the same unrelated Notebook 00B
  `monolith-mvp-app` assertion failure described below;
- Ruff over every Task 3 changed Python file: passed;
- `git diff --check`: passed;
- real Qwen/Vintern semantic smoke was not run locally, as required by the
  Task 3 guide; operator GPU validation remains pending.

Task 1 local proof on 2026-09-01:

- `pytest -q tests/test_phase01_scene_grouping.py`: 17 passed.
- `pytest -q tests/test_phase01_production_contract.py`: 54 passed.
- focused grouping/contract/QA/schema set: 81 passed.
- `pytest -q tests/test_phase01*.py`: 219 passed.
- full `pytest -q`: 425 passed, 1 unrelated failure in
  `tests/test_smoke.py::test_notebooks_are_operator_ready_thin_orchestration_shells`
  because the existing Notebook 00B content does not contain
  `monolith-mvp-app`. Task 1 did not modify that notebook or assertion.
- Ruff over every changed Python file: passed.
- `git diff --check`: passed.

Real Qwen/Vintern semantic smoke was not run. Threshold calibration on normal
edited videos and legitimate rapid montage remains an acceptance risk, not a
local-contract failure.

Task 1 closure proof on 2026-09-02:

- focused grouping/production/checkpoint/QA tests: 92 passed;
- `pytest -q tests/test_phase01*.py`: 222 passed;
- full `pytest -q`: 428 passed, with the same one unrelated Notebook 00B smoke
  assertion failure described above;
- Ruff over every closure-changed Python file: passed;
- `git diff --check`: passed.

Task 2 local proof on 2026-09-02:

- focused ASR/alignment/link tests: 28 passed;
- checkpoint/foundation/production-contract/smoke/schema/orchestrator tests:
  116 passed before the final resume and validation additions;
- focused migration/resume/word-validation closure tests: 9 passed;
- `pytest -q tests/test_phase01*.py`: 245 passed;
- full `pytest -q`: 451 passed, with the same unrelated Notebook 00B
  `monolith-mvp-app` assertion failure described above;
- Ruff over the Task 2 ASR, config, production, checkpoint, smoke, validation,
  and focused-test scope: passed;
- repository-wide `ruff check src tests` is not clean and reports 154 findings
  across broader legacy/current surfaces; this task does not claim that check
  as passed;
- `git diff --check`: passed after final closure.

Live acceptance was not run during Task 2. The implementation host exposed a
Quadro T2000 with 4 GB VRAM rather than the required T4-class qualification
runtime, and no HF token was available. A real forced-split boundary was
therefore also not exercised. On 2026-09-04 those live gates were deferred to a
single post-Task-5 T4 Colab/Kaggle notebook run. They remain required before
claiming live/provider acceptance; they no longer block Task 2 local closure.

- Focused proof: each task must add and run behavior-specific tests described in
  its acceptance cases.
- Integration proof: affected checkpoint invalidation, package assembly, schema
  validation, and consumer compatibility.
- End-to-end proof: pinned one-video and heterogeneous real-provider smoke with
  manual inspection of scene boundaries, aligned transcripts, modality
  relations, and summaries.
- Repository-required checks: choose the current repository checks during each
  task and report commands/results without presenting them as live-provider
  proof.

## Result

Active. Tasks 1-4 and the Task 1-3 correctness closure are accepted on local
contract evidence. Task 5 is implementation-complete and awaits external code
review. It adds deterministic adaptive shot evidence without changing the
one-row-per-shot caption schema or adding ASR to visual captioning. Live/provider
smoke remains pending and is not claimed by the local proof above.

Task 1 changed:

- configuration/schema/prompt: `system1/configs/artifact.yaml`,
  `system1/configs/models.yaml`, `system1/configs/phase01.yaml`,
  `system1/schemas/scenes.schema.json`, and
  `system1/prompts/scene_boundary_degenerate_label_v1.txt`;
- grouping/runtime: `system1/src/system1/scenes/{grouping.py,vlm_judge.py,__init__.py}`
  and `system1/src/system1/phase01/{production.py,validation.py,qa.py,preflight.py}`;
- config validation: `system1/src/system1/config/loader.py`;
- focused proof: `system1/tests/test_phase01_scene_grouping.py`,
  `system1/tests/test_phase01_production_contract.py`,
  `system1/tests/test_phase01_qa.py`, and
  `system1/tests/test_table_schema_validation.py`;
- current docs: `docs/architecture/system1-scene-grouping.md`,
  `docs/architecture/system1-notebook01-production-pipeline.md`, and the
  current-version example in `docs/onboarding/system1_spec.md`.

The closure patch additionally changes `system1/src/system1/phase01/checkpoint.py`,
adds long-sequence/no-promote/failure-persistence/duration proof, and syncs ADR
0014, amended ADR 0018, the decisions index, and the active Notebook 01 plan.

Task 2 changed:

- ASR contracts/alignment/linking:
  `system1/src/system1/asr/{alignment.py,contracts.py,links.py,runtime.py,timing.py}`
  plus NeMo, Faster-Whisper, quality, VAD/runtime-artifact, and package exports;
- canonical contracts: `asr_words_v1`, transcript links v2, checkpoint state
  v2, artifact config v2, pipeline/production v1.7, models v1.5, and structure
  package/video manifest v3;
- production/checkpoint/smoke/validation wiring for atomic `asr_words`, the
  first-class scene-link stage, v1-to-v2 state migration, and deterministic
  word ownership;
- merge, SQLite, generic table validation, and the guarded legacy/debug builder
  needed to consume the additive canonical table;
- focused proof in ASR alignment/link tests and existing Phase01 contract,
  checkpoint, orchestrator, smoke, and schema suites;
- current architecture, ADR 0018/0020, and Notebook 01 plan documentation.

Task 2 checkpoint impact:

- reusable where fingerprints match: shots, keyframes, OCR, and shot captions;
- recomputed: ASR, shot-transcript links, scenes, scene-transcript links, scene
  summaries, package, and sync.

Task 3 changed:

- `system1/src/system1/scenes/speech.py` adds the provider-neutral gap contract;
- production scene evidence, all VLM review routes, diagnostics, and manual QA
  now carry the same deterministic speech facts;
- scene grouping/config/model/prompt/diagnostics versions are bumped without
  changing the checkpoint DAG or package format;
- focused tests cover word-owned crossing, provenance-only overlap,
  forced-split temporal continuity, unreliable/empty ASR, every review route,
  production wiring, config/hash behavior, and non-authoritative documentary
  boundaries;
- current architecture and ADR 0014 document the evidence semantics.

Task 3 checkpoint impact:

- reusable: shots, keyframes, ASR, OCR, shot captions, and shot-transcript
  links;
- recomputed: scenes, scene-transcript links, scene summaries, package, and
  sync.

Task 5 changed:

- `system1/src/system1/shots/understanding.py` adds deterministic eligibility,
  visual/OCR change signals, source selection, storyboard rendering, and
  evidence fingerprints;
- production uses the same representative image or storyboard for all eight
  caption fields and writes exact field-level provenance v2;
- configuration, model prompt bundle, artifact declarations, stage hashing,
  checkpoint dependencies, package validation, and manual QA reflect the new
  evidence contract;
- eight new v2 prompts preserve sparse same-shot chronology and prohibit
  unsupported motion, speech, identity, intention, or causality;
- focused proof covers static and changing shots, OCR missingness, duplicate
  removal, source budgets, storyboard order/hash, Qwen/Vintern request parity,
  provenance, config, DAG, and package validation.

Task 5 checkpoint impact:

- reusable: shots, keyframes, ASR, OCR, and shot-transcript links;
- recomputed: shot captions, scenes, scene-transcript links, scene summaries,
  package, and sync.

Task 1 checkpoint impact:

- reusable: shots, keyframes, ASR, OCR, shot captions, and shot-transcript
  links;
- invalidated: scenes, scene summaries, package, and sync.

Task commits are identified by Git history and final handoff reports; a commit
cannot embed its own final SHA without changing that SHA.
