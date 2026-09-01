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

### Task 1: Scene Grouping Correctness

Status: Complete; awaiting review before Task 2

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

Status: Not Started

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

Status: Not Started

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

Status: Not Started

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

Status: Not Started

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
- [ ] Review and accept Task 1 before Task 2.
- [ ] Task 2: ASR Temporal Alignment.
- [ ] Review and accept Task 2 before Task 3.
- [ ] Task 3: Speech-Aware Scene Grouping.
- [ ] Review and accept Task 3 before Task 4.
- [ ] Task 4: Adaptive Scene Summary.
- [ ] Review and accept Task 4 before Task 5.
- [ ] Task 5: Dynamic Shot Understanding.
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

## Validation

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

Active. Task 1 is implemented and locally validated; Task 2 remains Not
Started pending review.

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

Checkpoint impact:

- reusable: shots, keyframes, ASR, OCR, shot captions, and shot-transcript
  links;
- invalidated: scenes, scene summaries, package, and sync.

The Task 1 commit is identified by its Git history and final handoff report; a
commit cannot embed its own final SHA without changing that SHA.
