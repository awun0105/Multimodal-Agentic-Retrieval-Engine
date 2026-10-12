# System 1 Phase01 Scene Grouping

Date: 2026-09-08

## Status

Accepted production design for Notebook 01 / `phase01_structure`.

Qwen2.5-VL is the local semantic primary. The shared semantic client unloads
Qwen and activates the pinned Vintern-3B-R fallback when its existing sticky
fallback policy requires it. Boundary requests use a strict plain-text label:

```text
BOUNDARY | SAME_SCENE
```

Python owns voting, review routing, scene IDs and ranges, partition validation,
quality policy, promotion, and failure status. Fake-judge tests prove the
deterministic contract. A heterogeneous real-model smoke remains required to
calibrate semantic quality thresholds.

## Canonical Definition

A shot is an editing unit between camera cuts. A scene is a semantic unit made
of one or more consecutive shots belonging to the same principal event,
setting, or topic. A camera cut does not by itself create a scene boundary.

```text
ordered shots + multimodal shot evidence
  -> overlapping primary judgements
  -> weighted vote aggregation
  -> focused review of ambiguous gaps
  -> bounded consistency review
  -> candidate partition
  -> partition-level quality assessment
  -> optional bounded degenerate review
  -> pass and promote, or quarantine for exact manual disposition
```

The VLM decides only whether the gap after a named shot is a boundary. It does
not generate scene IDs, timestamps, confidence scores, reasons, or a partition.

## Scope And Inputs

Scene grouping runs after shots, keyframes, ASR, OCR, shot captions, and
shot-to-transcript links. Each ordered `ShotEvidence` item contains:

- shot ID and frame/time range;
- representative image and available early/late/supplemental images;
- Vietnamese and English caption, objects, actions, and visible-text summary;
- canonical OCR text;
- temporally attributed word-level shot transcript;
- deterministic aligned-speech evidence for the gap after the shot; and
- timeline order.

Organizer detections, embeddings, and organizer metadata are not boundary
evidence. Scene summaries run only after the scene partition is accepted and
cannot alter its boundaries.

## Aligned-Speech Gap Evidence

Task 2 word timing remains the only text-attribution authority. Before any VLM
request, `build_speech_gap_evidence()` assigns canonical ASR words to the
ordered shot intervals using the same maximum-overlap and midpoint tie rules as
shot transcript construction. For each real adjacent-shot gap it records the
versioned `aligned_speech_continuity_v2` facts:

```text
ASR status and evidence reliability
aligned word count on each side
ASR segment IDs that own words on both sides
last-left and first-right word times
each word's distance from the shot boundary
the inter-word gap
near-boundary speech continuity
selected shared-segment word counts and link coverage
```

A segment crosses a gap only when the same canonical `asr_segment_id` owns at
least one aligned word in both shots. Segment interval overlap alone is only
provenance and does not establish crossing. Near-boundary continuity can remain
true across different segment IDs, including a forced split, when reliable
words occur within the configured one-second boundary and inter-word limits.
When multiple segments cross one gap, every ID is retained in lexical order;
the first ID is selected only for compact link-coverage fields.

Reliability is evaluated per gap, not only per video. `pass` ASR is eligible
for positive evidence only when both neighboring shots own aligned words.
Missing left, right, or both-side words therefore produce an explicit neutral
reason such as `missing_left_aligned_words`; `no_audio`, `no_speech`, and
`low_confidence` remain neutral video-level reasons. An unreliable block is
rendered compactly as `CONTINUITY_EVALUATION: NOT_EVALUATED` and omits false
continuity facts. Missing or rejected speech is never interpreted as a semantic
break. The thresholds are evidence policy, not a scene rule.

Every primary, focused, consistency, and degenerate request receives the same
compact `SPEECH_GAP_EVIDENCE` block through the shared gap renderer. Reliable
speech spanning a camera cut is strong continuity evidence for interviews,
sports, and instructional activity. It is never Python authority: no score,
vote, review route, or final label is changed mechanically. A documentary or
news voice-over may continue across a genuine event, topic, setting, or time
change, and `BOUNDARY` remains valid.

## Context-Focus Windows And Primary Votes

`plan_focus_windows()` produces overlapping focus-gap windows with bounded
left/right shot context. Every real adjacent-shot gap must appear in at least
one focus window and no gap exists after the final shot.

The provider contract is one request per gap. Requests in the same window share
the bounded context contact sheet and textual evidence, but each response is
exactly one allowed label. Unknown, missing, extra, duplicated, or non-Boolean
normalized decisions fail validation.

Overlapping windows can vote on the same gap. A vote at focus position `j` in a
window of `m` gaps receives:

```text
depth(j, m)  = min(j, m - 1 - j)
max_depth(m) = max(1, floor((m - 1) / 2))
weight(j, m) = 1 + depth(j, m) / max_depth(m)
```

The deterministic boundary score is the weighted fraction of `BOUNDARY` votes.
Scores above `boundary_threshold` become boundaries; scores below
`non_boundary_threshold` become non-boundaries; scores between the thresholds
go through focused review.

## Focused And Consistency Review

Focused review re-evaluates one ambiguous gap with bounded neighboring context
and configured early/late/supplemental keyframes. Its strict label replaces the
ambiguous provisional decision.

Consistency review detects:

- adjacent boundaries that create a one-shot scene;
- dense local boundary regions; and
- strong disagreement among overlapping primary votes.

`max_consistency_review_rounds` is a real upper bound. After each round Python
recomputes the triggers. Review stops when no trigger remains, the configured
round limit is reached, or a round changes no decision. A valid review replaces
only the requested gaps. One-shot scenes remain legal; they merely contribute
to review/quality evidence.

Logical trigger regions may span much of a long video, but provider requests
may not. Python splits every merged region into chunks no larger than the
configured `focus_gap_count`; each chunk receives only its own focus shots plus
`context_shots_each_side`. With the production defaults, a consistency request
contains at most 8 focus gaps and 17 context shots, including the shot on each
side of those gaps. Dense pathological output therefore cannot create a
whole-video contact sheet or repeat whole-video text for every gap.

## Partition Quality Guard

After ordinary review, Python constructs a candidate partition and computes the
versioned deterministic `scene_partition_quality_v2` report:

```text
shot_count
gap_count
scene_count
boundary_count
one_shot_scene_count
boundary_density
one_shot_scene_rate
mean_shots_per_scene
median_shots_per_scene
mean_scene_duration_sec
median_scene_duration_sec
longest_boundary_run
suspicious
flags
```

The initial v1 suspicious rule is intentionally small:

```text
if shot_count < min_shot_count:
    normal
elif every gap is BOUNDARY:
    suspicious
elif boundary_density >= configured threshold
     and one_shot_scene_rate >= configured threshold:
    suspicious
else:
    normal
```

This rule is a safety trigger, not a semantic truth rule. It does not declare
that every one-shot scene is invalid, target a scene count, or mutate labels.

## Degenerate Review And Asynchronous Quarantine

A suspicious candidate partition can enter one bounded recovery pass using the
`scene_boundary_degenerate_label_v2` prompt. The pass re-evaluates every gap
exactly once per configured round in non-overlapping focus blocks with bounded
context. It does not force `SAME_SCENE`, select another provider, or send an
unbounded whole-video prompt.

Python rebuilds and reassesses the partition after recovery:

- normal result: status `pass_after_review`, then promote;
- suspicious result: persist an immutable review candidate, return
  `review_required`, keep the scenes stage pending, and skip scene links,
  summaries, package, and sync for that video while other videos continue.

The review candidate and its evidence are stored outside canonical stage
outputs:

```text
phase01_checkpoints/{release_id}/{video_id}/
  reviews/scene_partition/{candidate_fingerprint}/
    candidate.json
    scene_partition_quality.json
    scene_boundary_diagnostics.jsonl
    decision.json                 # only after disposition
```

The candidate fingerprint commits to the exact scene input/config hashes,
ordered decisions and scenes, initial/final quality, grouping version, and
review metadata; creation time is excluded. Public review helpers list/get
pending candidates and write one immutable `approve` or `reject` decision with
a non-empty reviewer and timezone-aware review time.

On rerun, only the exact candidate may consume its decision. Approval promotes
that exact suspicious partition with `pass_after_manual_review`; rejection is
a durable `review_rejected` outcome and never pretends to remain pending. A
changed input or scene config has a different identity, so a stale decision
cannot apply. Candidate reuse also prevents repeating VLM grouping merely to
resume an already quarantined video. The candidate files are inspectable
evidence, not canonical stage outputs. Upstream stages remain reusable.

## Deterministic Scene Partition

Python scans ordered shots and splits after each accepted boundary. Every scene
contains at least one consecutive shot and uses the first/last shot for its
frame/time range.

```text
scene_id            = {video_id}_SC{scene_index:05d}
boundary_convention = [start_frame, end_frame)
grouping_method     = multimodal_context_focus
grouping_version    = scene_grouping_v4
schema              = scenes_v4
```

The structural validator requires complete shot coverage, canonical ordering,
and no frame gap or overlap. A one-shot video produces one scene,
`boundary_density = 0`, and is not suspicious.

## Outputs And Diagnostics

The successful scenes checkpoint contains:

```text
scenes.parquet
scene_boundary_diagnostics.jsonl
scene_partition_quality.json
```

After accepted scenes are promoted, the deterministic first-class
`scene_transcript_links` stage writes `scene_transcript_links.parquet` from
scene/segment overlap. That table preserves segment provenance; word-level
assignment owns scene-specific transcript text.

`scene_boundary_diagnostics_v4` records deterministic audit fields including:

```text
gap_index
after_shot_id
is_boundary
primary_boundary_score
vote_count
true_vote_weight
false_vote_weight
review_route
consistency_review_triggered
consistency_review_round
degenerate_review_triggered
provider
model_name
model_version
speech_contract_version
speech_asr_status
speech_evidence_reliable
speech_reliability_reason
speech_left_aligned_word_count
speech_right_aligned_word_count
speech_shared_segment_crosses_gap
speech_shared_segment_ids
speech_left_word_distance_to_boundary_sec
speech_right_word_distance_to_boundary_sec
speech_inter_word_gap_sec
speech_near_boundary_continuity
```

Legacy `reason`, `confidence`, and `evidence_used` fields may remain null/empty
for compatibility; they are not authoritative under the label-only contract.
Manual QA surfaces the main speech-continuity fields plus compact partition
context. The evidence is recorded independently from the final label, so a
diagnostic may correctly contain both strong speech continuity and
`is_boundary = true`.

`scene_partition_quality.json` records the policy, initial/final metrics,
review counts, and one of:

```text
pass
pass_after_review
review_required
pass_after_manual_review
```

`review_required` exists only in the quarantined candidate. The first two
statuses require a non-suspicious final partition. A successful package may
also contain `pass_after_manual_review`, but only with the exact embedded
approved decision and decision reference; its final partition remains marked
suspicious by the deterministic policy rather than being rewritten. Package
validation verifies the report, counts, and approval identity.

## Reproducibility And Checkpoints

The scenes stage fingerprint already includes the complete
`phase01.scene_grouping` policy, scene-boundary model/prompt configuration, and
relevant schema versions. Therefore changes to quality thresholds, review
policy, prompts, or `scenes_v4` invalidate scenes and downstream stages without
invalidating upstream artifacts.

The checkpoint DAG declares ASR as a direct scenes dependency because the
aligned-speech evidence reads `asr_status.json` as well as word/link outputs.

Provider requests continue through the shared stage-local content-addressed
client cache. Diagnostics and caches must not expose credentials.

## Implementation Map

```text
system1/src/system1/scenes/grouping.py
  deterministic windows, voting, reviews, quality assessment, partition

system1/src/system1/scenes/speech.py
  provider-neutral word-aligned evidence for each adjacent-shot gap

system1/src/system1/scenes/vlm_judge.py
  contact sheets, one strict label request per gap, provider diagnostics

system1/src/system1/phase01/production.py
  evidence loading, quality artifact, quarantine, exact approval, promotion

system1/src/system1/phase01/review.py
  immutable candidate identity, listing, approval, and rejection

system1/src/system1/phase01/validation.py
  successful-package defense-in-depth

system1/src/system1/phase01/qa.py
  operator-facing boundary and partition evidence
```

Notebook 01 remains thin orchestration and contains no grouping algorithm,
prompt, parsing, or partition logic.

## Required Proof

Deterministic tests cover:

- focus-window coverage and weighted votes;
- ambiguous focused review;
- bounded consistency rounds and stable early stop;
- all-false one-scene behavior;
- short videos below the safety threshold;
- suspicious all-boundary recovery and asynchronous quarantine;
- bounded consistency focus/context for long all-boundary sequences;
- legitimate isolated one-shot scenes;
- single-shot videos;
- scene-stage fingerprint invalidation;
- deterministic candidate identity, pending discovery, approval, and rejection;
- stale-decision rejection and approved-candidate resume without VLM rerun;
- direct proof that unapproved suspicious output cannot call scenes promotion;
- quality report packaging and package validation;
- deterministic manual-QA diagnostics;
- same-segment crossing based on assigned words rather than segment overlap;
- near-boundary continuity across shared and forced-split segments;
- explicit unreliable/empty-ASR behavior;
- identical speech rendering in every review route; and
- interview, sports, cooking, documentary voice-over, and silent-video cases.

These tests prove the contract, not real-model semantic accuracy. Before a full
dataset run, rerun a heterogeneous real Qwen/Vintern smoke and calibrate the
quality thresholds against normal edited video and legitimate rapid montage.
