# System 1 Phase01 Scene Grouping

Date: 2026-08-05

## Status

Accepted and implemented package design for Notebook 01 /
`phase01_structure`. Deterministic fake-judge tests cover windowing, voting,
review routing, partitioning, and failure validation. Qwen2.5-VL is the local
primary and Gemini is its structured fallback; real-provider and manual quality
review remain pending. `TimelineAwareFallbackProvider` is available only
through guarded debug/test injection.

## Canonical Definition

A scene is one or more consecutive shots that belong to the same principal
event, setting, or topic.

Scene grouping uses multimodal context-window segmentation:

```text
ordered shots
+ representative images
+ canonical shot captions
+ caption objects/actions and canonical OCR
+ ASR transcripts
+ decoded timeline
  -> VLM judges candidate boundaries in overlapping context/focus windows
  -> package validates and aggregates judgements
  -> package resolves ambiguous boundaries
  -> package reviews locally inconsistent regions
  -> package creates one contiguous partition of the complete shot timeline
  -> scenes.parquet + scene mappings
```

The VLM decides only whether a gap between two adjacent shots is a scene
boundary. Package code remains authoritative for IDs, frame/time ranges,
partition construction, validation, status, and provenance.

## Scope And Phase Boundary

This workflow belongs to Notebook 01 after shot detection, keyframe selection,
canonical shot captioning, ASR, and shot-to-transcript linking.

Notebook 01 generates canonical OCR and caption objects/actions before scene
grouping, and these are inputs to the grouper. Organizer object detections and
visual embeddings remain Phase02 concerns and are not canonical boundary
evidence.

Scene summaries are generated after the partition exists. They may reuse the
same multimodal evidence, but summary generation is not allowed to alter scene
boundaries implicitly.

## 1. Canonical Inputs

The grouper operates on one video's unpacked per-video structure workspace.
Parquet names and fields below follow the current repository contract.

### `shots.parquet`

Required scene-grouping fields:

```text
shot_id
video_id
start_frame
end_frame
start_sec
end_sec
```

Useful additional fields include `shot_index`, `detection_method`, `confidence`,
`status`, and `boundary_convention`.

`representative_keyframe_id` is not required on a shot row. The canonical join
to the representative image is:

```text
shots.shot_id
  -> shot_captions.shot_id
  -> shot_captions.representative_keyframe_id
  -> keyframes.keyframe_id
```

### `keyframes.parquet`

Relevant fields:

```text
keyframe_id
video_id
frame_id
shot_id
keyframe_role
is_representative
keyframe_ref
thumbnail_ref
```

Exactly one representative keyframe is expected per shot. A normal shot has
early/middle/late rows selected from search bands centered at 20%/50%/80%; a
short shot may have fewer roles after duplicate frame IDs are removed. Focused
review selects available early/late rows through `keyframe_role`; role does not
change the canonical `keyframe_id = "{video_id}:{frame_id}"` convention.

At scene-grouping input time, `keyframes.scene_id` may be null or provisional.
It is assigned from the final shot partition after grouping.

### `shot_captions.parquet`

Relevant fields:

```text
shot_caption_id
video_id
shot_id
representative_keyframe_id
representative_timestamp_sec
caption_vi
caption_en
provider
model_name
model_version
prompt_version
schema_version
confidence
status
```

Phase01 has one canonical bilingual caption row per shot. Both
`caption_vi` and `caption_en` are required for a successful production row.

### `asr_segments.parquet`

Relevant fields:

```text
asr_segment_id
video_id
start_sec
end_sec
text
language
confidence
model_name
status
```

The canonical identifier is `asr_segment_id`, not `segment_id`.

### `shot_transcript_links.parquet`

Relevant fields:

```text
shot_id
asr_segment_id
video_id
coverage
```

The evidence builder uses these rows to select ASR segments for a shot. It
sorts selected segments by `(start_sec, end_sec, asr_segment_id)` and joins
their non-empty text in timeline order. When a segment overlaps multiple shots,
each relevant link may exist with its own coverage value; text must not be
duplicated within one shot because of duplicate link rows.

### Timeline context

The Phase00 decoded frame timeline remains the authority for exact frame/time
mapping. Scene ranges are derived from shot rows, so the grouper must not
recompute frames using `timestamp * fps`.

Metadata is preserved elsewhere in the structure artifact but is not a
canonical scene-boundary input. OCR and caption objects/actions are Phase01
evidence; embeddings and organizer object outputs remain Phase02 outputs.

## 2. Internal `ShotEvidence`

Package code builds one immutable internal record per ordered shot. This is an
ephemeral processing type, not a new canonical Parquet table.

```python
@dataclass(frozen=True)
class ShotEvidence:
    shot_id: str
    video_id: str
    start_frame: int
    end_frame: int
    start_sec: float
    end_sec: float

    representative_keyframe_id: str
    representative_image: Path
    early_image: Path | None
    late_image: Path | None

    caption_vi: str
    caption_en: str
    transcript: str
```

Image `Path` values are resolved temporary local paths used by the provider.
Canonical artifact rows continue to store logical `keyframe_ref` and
`thumbnail_ref` values, not machine-specific paths.

Example evidence rendered for a provider request:

```text
SHOT: L21_V001_SH00012
TIME: 32.10-36.80

CAPTION_VI:
Một người đứng trước quầy vé trong nhà ga.

CAPTION_EN:
A person stands in front of a ticket counter inside a train station.

SPEECH:
Bây giờ tôi sẽ mua vé tại quầy này.
```

Empty ASR is valid evidence and must be represented explicitly. Missing or
failed representative-image/caption evidence follows the Phase01 error policy;
it must not be concealed by notebook code.

## 3. Context-Focus Window Planning

For `N` ordered shots, there are `N - 1` candidate gaps. Gap `i` is identified
by the shot immediately before it, `after_shot_id = shots[i].shot_id`, and lies
between `shots[i]` and `shots[i + 1]`. There is no gap after the final shot.

Initial configuration:

```yaml
scene_grouping:
  focus_gap_count: 8
  context_shots_each_side: 4
  stride: 6
```

- `focus_gap_count = 8`: one primary request judges at most eight gaps.
- `context_shots_each_side = 4`: include up to four additional shots before
  and after the shots participating in the focus gaps.
- `stride = 6`: adjacent focus ranges overlap by two gaps when full-sized.

Example:

```text
context shots:  SH001 ... SH017
focus gaps:     SH005|SH006 ... SH012|SH013
```

The planner clips context at video boundaries and handles short videos with one
smaller window. It must guarantee that every candidate gap appears in at least
one focus range and that no focus range contains a gap outside the video.

This avoids judging every adjacent pair in isolation. A context window can see
alternating camera angles such as person A, person B, person A, and a wide shot
while retaining one continuous scene when the principal event continues.

## 4. Visual Contact Sheets

Each primary window produces a contact sheet ordered from left to right and top
to bottom by shot timeline. Every tile contains:

```text
representative keyframe
shot_id
start_sec-end_sec
```

Example layout:

```text
+------------+------------+------------+------------+
| SH001      | SH002      | SH003      | SH004      |
| 00:00-03   | 00:03-07   | 00:07-11   | 00:11-15   |
+------------+------------+------------+------------+
| SH005      | SH006      | SH007      | SH008      |
| ...        | ...        | ...        | ...        |
+------------+------------+------------+------------+
```

Contact-sheet generation must be deterministic for the same ordered evidence:
same grid policy, image fit, dimensions, label format, and output encoding.
The visual exists only to help the judge associate image changes with ordered
shot IDs; it is not a canonical keyframe artifact.

## 5. Primary Window Judgement

Each request contains:

1. The context window contact sheet.
2. Ordered shot IDs and frame/time ranges.
3. The canonical Vietnamese and English captions for each shot.
4. The timeline-ordered transcript for each shot.
5. The exact focus gaps the provider must judge.

The prompt requires the judge to:

- mark a boundary when the principal event, setting, time, or topic changes to
  a new unit;
- keep shots together when only camera angle changes while the principal event
  continues;
- use visual evidence, captions, transcripts, and temporal order together;
- judge only the listed focus gaps; and
- return exactly one Boolean decision for every focus gap.

Canonical structured response:

```json
{
  "boundaries": [
    {
      "after_shot_id": "L21_V001_SH00005",
      "is_scene_boundary": false
    },
    {
      "after_shot_id": "L21_V001_SH00006",
      "is_scene_boundary": true
    }
  ]
}
```

The provider adapter rejects a response unless:

- it is valid JSON matching the versioned response schema;
- every `after_shot_id` exists and denotes a real adjacent-shot gap;
- every returned gap belongs to the requested focus set;
- every requested focus gap appears exactly once;
- no gap is duplicated; and
- `is_scene_boundary` is a Boolean, not free-form text or an inferred score.

Invalid responses may receive a bounded schema-repair retry. Raw responses,
validation failures, retry counts, provider, model, prompt version, and schema
version are recorded in diagnostics without exposing secrets.

## 6. Overlap Vote Aggregation

Overlapping focus windows can judge the same gap more than once. A vote near
the center of its focus range receives more weight than a vote near the edge.

For a focus range with `m` gaps and zero-based position `j`, the v1 deterministic
weight is:

```text
depth(j, m)  = min(j, m - 1 - j)
max_depth(m) = max(1, floor((m - 1) / 2))
weight(j, m) = 1 + depth(j, m) / max_depth(m)
```

This gives edge votes weight `1` and central votes up to `2` without allowing
window size to make one request dominate arbitrarily.

For each gap:

```text
true  = 1
false = 0

boundary_score(gap) =
  sum(vote * weight) / sum(weight)
```

Initial thresholds:

```yaml
scene_grouping:
  boundary_threshold: 0.67
  non_boundary_threshold: 0.33
```

Classification:

```text
score >= 0.67             -> boundary
score <= 0.33             -> non-boundary
0.33 < score < 0.67       -> ambiguous
```

Aggregation is package logic and must be deterministic. The provider cannot
override vote weights or thresholds in its response.

## 7. Ambiguous-Boundary Second Pass

Each ambiguous gap receives a focused request containing, when available:

```text
three shots before
shot_left
shot_right
three shots after
```

Visual evidence includes representative images for all neighboring shots plus
the late keyframe of `shot_left` and early keyframe of `shot_right` when those
optional roles exist. If early/late images are unavailable, the request remains
valid with representative images and records the reduced evidence.

Text evidence includes captions, transcripts, and timeline ranges.

Response:

```json
{
  "after_shot_id": "L21_V001_SH00015",
  "is_scene_boundary": true
}
```

The validated second-pass Boolean becomes the final local decision for that
gap, subject only to a later consistency review of a surrounding region.

## 8. Global Consistency Review

Once every gap has a provisional Boolean decision, package code scans the
complete sequence. It schedules a larger regional review when it detects:

- adjacent boundaries that create a one-shot scene;
- an unusually dense cluster of boundaries;
- strong disagreement among overlapping primary-window votes; or
- a missing/unresolved judgement after bounded provider retries.

A one-shot scene is not automatically invalid. It triggers review because it
may represent either a real short scene or an unstable local decision.

The regional request includes a larger ordered context and asks for every gap
in the flagged region:

```json
{
  "boundaries": [
    {
      "after_shot_id": "L21_V001_SH00020",
      "is_scene_boundary": false
    },
    {
      "after_shot_id": "L21_V001_SH00021",
      "is_scene_boundary": true
    },
    {
      "after_shot_id": "L21_V001_SH00022",
      "is_scene_boundary": false
    }
  ]
}
```

A valid regional result atomically replaces local decisions only for its
requested gaps. Package code then reruns consistency checks before partitioning.
The implementation must cap review rounds so provider instability cannot create
an infinite loop.

If provider calls remain unavailable or invalid after bounded retries, the
video fails scene grouping. Production must not convert unresolved gaps to
non-boundaries or silently emit one fallback scene. A successful all-false
judgement is different: it is valid evidence that the whole shot sequence is
one scene.

## 9. Deterministic Scene Partition

Package code scans ordered shots and splits after every final boundary:

```text
SH00000
SH00001
SH00002  <- boundary
SH00003
SH00004
SH00005  <- boundary
SH00006
```

```text
scene 0 = SH00000-SH00002
scene 1 = SH00003-SH00005
scene 2 = SH00006-...
```

Scene IDs follow the existing zero-based, five-digit contract:

```text
{video_id}_SC{scene_index:05d}

L21_V001_SC00000
L21_V001_SC00001
L21_V001_SC00002
```

The browser proposal's six-digit examples such as `SC000001` are not used.

Ranges are derived only from the first and last shot:

```text
scene.start_frame = first_shot.start_frame
scene.end_frame   = last_shot.end_frame
scene.start_sec   = first_shot.start_sec
scene.end_sec     = last_shot.end_sec
```

Frame ranges retain the repository convention `[start_frame, end_frame)`, so
`end_frame` is exclusive. The VLM never returns or calculates scene IDs,
frames, timestamps, counts, or ranges.

## 10. Canonical Outputs And Backfills

### `scenes.parquet`

The production target row contains:

```text
scene_id
video_id
scene_index
start_shot_id
end_shot_id
start_frame
end_frame
start_sec
end_sec
duration_sec
frame_count
shot_count
keyframe_count
scene_type
grouping_method
grouping_version
confidence
boundary_convention
status
```

For this implementation:

```text
grouping_method  = multimodal_context_focus
grouping_version = scene_grouping_v1
boundary_convention = [start_frame, end_frame)
```

`confidence` is a deterministic aggregate of final boundary evidence and must
be documented in the implementation; it is not a fabricated provider
probability.

### Mapping updates

After partitioning:

- backfill `shots.scene_id` so every shot belongs to exactly one scene;
- backfill `keyframes.scene_id` from each keyframe's `shot_id`;
- build `scene_transcript_links.parquet` from final scene ranges and canonical
  ASR links; and
- generate `scene_summaries.parquet` from the final scenes and their evidence.

Canonical `shot_captions.parquet` remains shot-owned and does not depend on
scene IDs for identity or rebuild behavior.

VLM requests, votes, contact sheets, and caches are intermediate diagnostics;
they are not new canonical runtime tables and do not belong in System 2's data
contract.

## 11. Package Interfaces And Layout

Provider interface:

```python
class SceneBoundaryJudge(Protocol):
    def judge(
        self,
        *,
        request_kind: str,
        focus_gap_ids: tuple[str, ...],
        context: Sequence[Mapping[str, Any]],
    ) -> Mapping[str, bool]:
        ...
```

Pure orchestration interface:

```python
def group_scenes(
    shots: list[Shot],
    shot_evidence: list[ShotEvidence],
    judge: SceneBoundaryJudge,
    config: SceneGroupingConfig,
) -> list[SceneRange]:
    ...
```

Implemented module layout:

```text
system1/src/system1/scenes/
|-- builder.py
|-- grouping.py
`-- gemini_judge.py
```

- `gemini_judge.py`: the compatibility-named generic structured
  `SceneBoundaryJudge`, deterministic contact sheets, strict response shape,
  and request evidence serialization. Qwen is primary and Gemini fallback;
  models, credentials, timeouts, and retry limits come from config/runtime and
  are not hardcoded in Notebook 01.
- `grouping.py`: window planning, contact-sheet request planning, vote
  aggregation, ambiguous second pass, consistency review, failure handling,
  partition,
  and pure validation logic.
- `phase01/production.py`: load canonical tables, resolve logical image refs to
  temporary local media, build evidence, invoke grouping, write tables, backfill
  mappings, and record diagnostics. `builder.py` is the legacy debug path.

Notebook 01 remains thin orchestration. It calls package/CLI behavior and does
not contain grouping algorithms, prompt text, JSON parsing, cache logic, or
table mutation.

## 12. Cache And Reproducibility

Every provider request has a deterministic cache key containing:

```text
request_kind
video_id
ordered shot_ids
representative/early/late image content hashes actually used
Vietnamese/English caption content hashes
transcript content hashes
focus gaps
scene grouping config hash
provider
model_name
prompt_version
schema_version
```

Logical namespaces are kept for:

```text
primary window judgement cache
ambiguous-boundary cache
consistency-review cache
```

These may share one physical content-addressed cache store. Cache entries are
disposable intermediate state under the run/checkpoint workspace, not canonical
per-video or runtime artifacts. A response is reusable only when the complete
key matches; provider/model/prompt/schema/config changes invalidate it
automatically.

Cache metadata and diagnostics must not store API keys or other secrets.

## 13. Validation

Scene grouping passes only when all of the following hold:

1. Every input shot belongs to exactly one scene.
2. No input shot is omitted.
3. No shot belongs to two scenes.
4. Shots inside each scene are consecutive in canonical shot order.
5. Scene ranges do not overlap.
6. Scenes create no gap over the ordered shot timeline.
7. Scene `start_frame`/`end_frame` equal the first/last shot range.
8. Scene `start_sec`/`end_sec` equal the first/last shot range.
9. Every frame range uses `[start_frame, end_frame)`.
10. `scene_id` values are deterministic and unique.
11. Every scene contains at least one shot.
12. Every `shots.scene_id` references the scene containing that shot.
13. Every `keyframes.scene_id` agrees with its linked shot's scene.
14. Every `scene_transcript_links` row references existing scene and ASR rows.
15. Provider/cache/prompt/schema/config provenance and final status are
    present in the per-video manifest or diagnostics.

Provider success does not substitute for partition validation. Provider
unavailability after bounded retry is a production video failure.

## 14. Required Tests

### Unit tests

- Context/focus/stride window planning is correct at normal, short-video, and
  end-of-video boundaries.
- Every real focus gap appears in at least one window.
- No non-existent gap after the final shot is requested.
- Contact-sheet tile ordering and labels are deterministic.
- Weighted overlap aggregation follows the v1 formula.
- Scores at both thresholds are classified correctly.
- Ambiguous gaps trigger the second pass.
- Invalid JSON, unknown gaps, duplicate gaps, extra gaps, and missing gaps are
  rejected.
- Regional consistency results replace only requested gaps.
- Review rounds and retries are bounded.
- Provider failure after bounded retry fails the production video explicitly.
- Scene partitioning covers every shot exactly once.
- Scene ranges and counts derive correctly from shot/keyframe ranges.
- Shot/keyframe scene backfills and scene-transcript links remain consistent.
- Cache keys change when any image, caption, transcript, focus gap, config,
  provider, model, prompt, or schema input changes.

### Behavioral fixtures

1. A -> B -> A camera sequence within one conversation remains one scene.
2. A move from a train station to a street creates a scene boundary.
3. Camera-angle changes without event change do not create a boundary.
4. Similar captions with a clear transcript topic change use both modalities.
5. Empty transcript with a strong visual setting change can still create a
   boundary.
6. Adjacent boundaries forming a one-shot scene trigger consistency review.
7. A genuinely short one-shot scene survives review when evidence supports it.
8. Provider outage fails the production video and cannot produce a misleading
   successful partition.

Tests use fake deterministic judges and fixtures. Live local-Qwen and Gemini
calls are a separate opt-in integration/rehearsal layer and are not required
for unit-test determinism.

## 15. Complete Execution Sequence

```text
load ordered shots
  -> load representative and optional early/late keyframes
  -> load canonical shot captions
  -> load ASR segments and shot-transcript links
  -> build ShotEvidence
  -> plan overlapping context/focus windows
  -> create deterministic contact sheets
  -> call SceneBoundaryJudge for primary windows
  -> validate and cache structured responses
  -> aggregate overlapping weighted votes
  -> second-pass ambiguous gaps
  -> consistency-review conflicting regions
  -> fail the video if any gap remains unresolved after bounded retry
  -> construct contiguous deterministic scene partition
  -> validate partition and ranges
  -> write scenes.parquet
  -> backfill shots.scene_id and keyframes.scene_id
  -> write scene_transcript_links.parquet
  -> generate scene_summaries.parquet
  -> write manifest provenance, diagnostics, errors, and final status
```

This is the canonical Phase01 scene-grouping design. Future changes may optimize
batching, contact-sheet rendering, or cache storage, but must preserve the
inputs, structured boundary semantics, deterministic partition authority,
canonical IDs/ranges, validation guarantees, and explicit failure behavior
defined here.
