# ADR 0026: Deterministic Scene Grouping From Shot Evidence

Date: 2026-10-26

## Status

Accepted

Amends ADR 0021 decision 3: scenes return, but only as the deterministic,
model-free step that ADR 0021 allowed. ADR 0021 decisions 1 and 2 (shots and
keyframes are the preprocessing units; System 2 keeps the query-time temporal
window) stand.

## Context

Terms:

- A **shot** is a run of near-identical frames. A new shot starts at a hard
  cut or when the content changes too much while the camera keeps rolling
  (ADR 0022). Every shot gets its own caption.
- A **scene** is a run of consecutive shots that show the same situation: for
  example a woman weaving a basket, filmed from two camera angles. Shot one
  shows her on a wooden bed, shot two shows a painting on the wall behind her;
  both belong to the scene "woman weaving a basket".

ADR 0021 removed VLM-judged scene boundaries and VLM scene summaries because
they were the most expensive Phase01 stages and their summaries repeated the
first shot caption. It left the door open for a cheap, deterministic grouping
if evaluation showed the need. The user wants scenes back for two reasons:
queries often describe a situation that spans several shots, and a scene-level
summary built from the shot captions gives System 2 a text document that
covers the whole situation.

After the worker and caption passes (ADR 0025) every shot already has a
SigLIP2 vector for its representative keyframe, a caption with an E5 vector,
OCR lines for its keyframes, and ASR segments with timestamps. No new model
run is needed to group shots.

## Decision

### 1. Grouping algorithm

Scenes are built in the release step (or a text-only pass after captions) from
existing shot evidence, in time order, one pass per video.

Inputs per shot `s`:

- `img(s)`: L2-normalized SigLIP2 vector of the shot's representative keyframe.
- `cap(s)`: L2-normalized E5 vector of the shot caption (absent when the
  caption pass has not run or the caption was rejected).
- `ocr(s)`: set of cleaned OCR lines of the shot's keyframes after video-wide
  repeat filtering (lower-cased, unaccented).
- ASR segments of the video with start and end seconds.

Algorithm:

1. Open a scene with the first shot. Keep the running mean of `img` and `cap`
   over the shots in the current scene.
2. For each following shot `s`, compute a continuity score against the current
   scene:

   | Signal | Value | Weight |
   | --- | --- | --- |
   | visual | `cos(img(s), mean_img(scene))` | `w_img` |
   | semantic | `cos(cap(s), mean_cap(scene))`, 0 when either side is absent | `w_cap` |
   | speech bridge | 1 when one ASR segment covers both the end of the previous shot and the start of `s`; 0 otherwise | `w_asr` |
   | silence | 1 when no ASR segment lies within the gap between the previous shot end and `s` start and the gap plus adjacent silence exceeds `silence_sec`; 0 otherwise | `-w_sil` |
   | shared text | Jaccard overlap of `ocr(s)` with the union of OCR lines in the scene | `w_ocr` |

   `score = w_img*visual + w_cap*semantic + w_asr*bridge - w_sil*silence + w_ocr*shared_text`.
3. If `score >= scene_threshold`, `s` joins the current scene; otherwise `s`
   opens a new scene.
4. After the pass, a scene with one shot shorter than `min_scene_sec` merges
   into the neighbouring scene whose `mean_img` is closer.
5. A scene longer than `max_scene_sec` is split at the shot boundary with the
   lowest continuity score inside it, repeated until every scene is under the
   cap.
6. Scenes tile the video: every shot belongs to exactly one scene, and scenes
   never cross a shot boundary.

Initial parameters, to be tuned on hand-labelled videos (Follow-Up):
`w_img 0.4`, `w_cap 0.3`, `w_asr 0.2`, `w_sil 0.2`, `w_ocr 0.1`,
`scene_threshold 0.55`, `silence_sec 2.0`, `min_scene_sec 2.0`,
`max_scene_sec 90`. These are configuration (`configs/worker.yaml`, section
`scenes`), not authority; this ADR fixes the signals and the procedure.

The algorithm runs without captions (`w_cap` term is 0) so a release built
before the caption pass still has scenes; scenes are rebuilt when captions
arrive.

### 2. Scene summary

For each scene, one text-only call to the caption model (Qwen3-VL-4B, no
image) with the shot captions in order, the `visible_text` of the shots, and
the ASR text inside the scene, constrained to a JSON object
`{"summary": str, "entities": [str]}` in Vietnamese. The summary becomes a text
document with `evidence_type = "scene"` spanning the scene's time range, with an
E5 vector and an FTS5 entry. Text-only calls are cheap compared with image
captions and run on CPU or GPU inside the caption pass.

A scene with one shot reuses the shot caption as its summary without a model
call.

Amendment (2026-10-26): the release runs on a CPU kernel, so it makes no model
call. `scenes.summary` is the scene's distinct shot captions joined in time
order, and null when no shot in the scene has a caption. The release writes no
`scene` text documents, because it cannot compute E5 vectors on CPU. The
text-only constrained call and `scene` documents are deferred to a later pass
that has a model. Grouping uses the mean SigLIP vector of a shot's keyframes,
the E5 vector of the shot's `caption` document, the spans of the video's `asr`
documents, and the lines of the shot's `ocr` documents
(`system1/src/system1/scenes/release_builder.py`).

### 3. Contract

Release tables gain `scenes` (`scene_id`, `video_id`, `start_shot_id`,
`end_shot_id`, `start_frame`, `end_frame`, `start_sec`, `end_sec`,
`shot_count`) and `shots.scene_id`. `scene_id` is `{video_id}_SC{n:05d}`.
`text_documents.evidence_type` adds `scene`. The scene summary document
carries `shot_ids` of the whole scene.

System 2 keeps the query-time temporal window (ADR 0021 decision 2). Scenes
add a coarser retrieval unit and a summary document; they do not replace
keyframe and shot retrieval.

## Alternatives Considered

1. No scenes, temporal window only (ADR 0021). Superseded: the user wants a
   scene-level summary document and a unit that covers multi-angle situations.
2. VLM boundary judgement (ADR 0014). Rejected again: cost and permanent
   boundary errors.
3. Visual similarity only. Rejected: interviews cut between two speakers whose
   frames look different; speech and caption signals are needed to keep them
   in one scene.
4. Clustering (for example agglomerative over all shots). Rejected: scenes are
   contiguous in time; a sequential pass is simpler and keeps that constraint.

## Consequences

Positive:

- No extra GPU for grouping; only a cheap text-only call per multi-shot scene.
- Thresholds are tuned in the release step without rerunning the worker.
- Scene summaries aggregate per-shot captions instead of re-describing the
  first shot.

Tradeoffs:

- Weights and threshold need hand-labelled scenes on a few videos; until then
  the grouping is unvalidated.
- Boundary errors are still fixed in the release; System 2's temporal window
  remains the correction for them.
- One more table and one more document type in the runtime contract.

## Follow-Up

- Implement `system1/src/system1/scenes/grouping.py` (pure function over
  shot evidence, with behavior tests on synthetic shots) after the caption
  pass exists, under `docs/plans/active/system1-pipeline-simplification.md`.
- Hand-label scene boundaries on 3 videos (one news, one interview, one
  single-take) and tune parameters; record precision and recall of boundaries
  in the plan.
- Update `docs/architecture/data-contracts.md` and `system1/schemas/` for the
  `scenes` table and the `scene` evidence type together with the code.
