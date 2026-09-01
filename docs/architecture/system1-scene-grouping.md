# System 1 Phase01 Scene Grouping

Date: 2026-09-01

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
  -> pass and promote, or fail closed
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
- overlapping ASR text; and
- timeline order.

Organizer detections, embeddings, and organizer metadata are not boundary
evidence. Scene summaries run only after the scene partition is accepted and
cannot alter its boundaries.

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

## Partition Quality Guard

After ordinary review, Python constructs a candidate partition and computes the
versioned deterministic `scene_partition_quality_v1` report:

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

## Degenerate Review And Fail-Closed Promotion

A suspicious candidate partition can enter one bounded recovery pass using the
`scene_boundary_degenerate_label_v1` prompt. The pass re-evaluates every gap
exactly once per configured round in non-overlapping focus blocks with bounded
context. It does not force `SAME_SCENE`, select another provider, or send an
unbounded whole-video prompt.

Python rebuilds and reassesses the partition after recovery:

- normal result: status `pass_after_review`, then promote;
- suspicious result: raise `ScenePartitionQualityError`, mark the scenes stage
  `failed_terminal`, and do not promote scenes or run downstream scene
  summaries/package/sync.

The failure stores compact structured policy/metrics under checkpoint
`error.details`. Upstream shots, keyframes, ASR, OCR, captions, and shot links
remain reusable.

## Deterministic Scene Partition

Python scans ordered shots and splits after each accepted boundary. Every scene
contains at least one consecutive shot and uses the first/last shot for its
frame/time range.

```text
scene_id            = {video_id}_SC{scene_index:05d}
boundary_convention = [start_frame, end_frame)
grouping_method     = multimodal_context_focus
grouping_version    = scene_grouping_v2
schema              = scenes_v2
```

The structural validator requires complete shot coverage, canonical ordering,
and no frame gap or overlap. A one-shot video produces one scene,
`boundary_density = 0`, and is not suspicious.

## Outputs And Diagnostics

The successful scenes checkpoint contains:

```text
scenes.parquet
scene_transcript_links.parquet
scene_boundary_diagnostics.jsonl
scene_partition_quality.json
```

`scene_boundary_diagnostics_v2` records deterministic audit fields including:

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
```

Legacy `reason`, `confidence`, and `evidence_used` fields may remain null/empty
for compatibility; they are not authoritative under the label-only contract.
Manual QA surfaces the deterministic fields plus compact partition context.

`scene_partition_quality.json` records the policy, initial/final metrics,
review counts, and one of:

```text
pass
pass_after_review
failed_quality_gate
```

Only the first two statuses can appear in a successful package. Package
validation requires the report, verifies its video/counts, and requires
`final.suspicious = false`.

## Reproducibility And Checkpoints

The scenes stage fingerprint already includes the complete
`phase01.scene_grouping` policy, scene-boundary model/prompt configuration, and
relevant schema versions. Therefore changes to quality thresholds, review
policy, prompts, or `scenes_v2` invalidate scenes and downstream stages without
invalidating upstream artifacts.

Provider requests continue through the shared stage-local content-addressed
client cache. Diagnostics and caches must not expose credentials.

## Implementation Map

```text
system1/src/system1/scenes/grouping.py
  deterministic windows, voting, reviews, quality assessment, partition

system1/src/system1/scenes/vlm_judge.py
  contact sheets, one strict label request per gap, provider diagnostics

system1/src/system1/phase01/production.py
  evidence loading, quality artifact, promotion gate, terminal failure

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
- suspicious all-boundary recovery and unresolved failure;
- legitimate isolated one-shot scenes;
- single-shot videos;
- scene-stage fingerprint invalidation;
- terminal failure classification and structured error details;
- quality report packaging and package validation; and
- deterministic manual-QA diagnostics.

These tests prove the contract, not real-model semantic accuracy. Before a full
dataset run, rerun a heterogeneous real Qwen/Vintern smoke and calibrate the
quality thresholds against normal edited video and legitimate rapid montage.
