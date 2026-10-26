# Current State

Date: 2026-10-26

What is implemented and verified today. Every row cites the Progress section of
`docs/plans/active/system1-pipeline-simplification.md` (plan) or a test. Design
is in `docs/architecture/system1-target.md`; tables and IDs in
`docs/architecture/data-contracts.md`; remaining work in `docs/roadmap/README.md`.

## System 1: Verified On Real Data

| Area | State | Evidence |
| --- | --- | --- |
| Phase00 ingest (`stream-standardize-upload-raw`, `ingest`, `assign-batches`, Notebook 00B/00C) | 873 videos in `canonical_raw_v001`; Phase00 complete for `canonical_release_v001` | `docs/architecture/system1-target.md` (Phase00) |
| Worker (`worker-batch`, `01_worker_batch.ipynb`): cuts, shots, keyframes, SigLIP2 vectors, ChunkFormer ASR, OCR, text vectors, package | Kaggle T4 x2 at commit `46bf0c2`, first 5 videos of `batch_000`: 5 completed, 0 failed, 70.3 min of video in 43.4 min (0.62x video length). OCR is 66% of worker time. | plan Step 5b item 1 |
| Caption pass (`caption-batch`, `02_caption_batch.ipynb`), Qwen3-VL-4B on transformers | Kaggle T4 at commit `2224257`, same 5 videos: 1511 shots in 5184 s (3.43 s/shot, 1.23x video length); valid JSON 1485/1511 (98.3%), all rejects `repetition_loop` | plan Step 5b item 2 |
| Release build and bucket publish (`build-release --publish`, `03_build_release.ipynb`) | Kaggle CPU kernel at commit `200e013`: 5 packages built and published to bucket `1thesudden/aiou-app-storage` prefix `releases_test/canonical_release_v001` in 312 s, peak RSS 560 MB, 0 degraded stages. Round trip with `hf buckets sync`: `READY.json` sha256 equals `manifest.json`, FAISS ntotal equals vector maps (1932, 5047), FTS5 query works, keyframes are WebP. | plan Step 5b item 7 |
| Test suite | `cd system1 && uv run pytest -q`: 332 passed, 0 failed after the Step 6 deletions | plan Step 6 item 2 |

## System 1: Coded, Not Verified On Real Data

| Area | State | Evidence |
| --- | --- | --- |
| Scenes in the release (`scenes/release_builder.py`, ADR 0026) | every shot gets a `scene_id`; `scenes.summary` joins shot captions, null without captions; no model call. The published 5-video release has 0 scenes (built before the wiring). Boundary precision and recall on hand-labelled videos not measured. | plan Step 5b item 5; `tests/test_release_build.py`, `tests/test_scene_deterministic.py` |
| One-pass decode with in-process TransNet (`providers.cuts.TransNetStream`) | single pass equals the two-pass result on a synthetic 300-frame video; not run on Kaggle | plan Step 5f items 3, 11 |
| OCR rerun skip, crop cache by Hamming distance, syllable filter | hit rate not measured since the Hamming change | plan Step 5c items 1 to 3 |
| Shot split by SigLIP drift, representative keyframe, blur filter | thresholds not tuned on real video | plan Step 5c items 4 to 6 |
| ASR sentence chunks and overlapping `window` documents | not run on Kaggle | plan Step 5c items 7, 8 |
| Bucket media resume, single video download, `ZIP_STORED`, upload re-check | not run on Kaggle | plan Step 5b item 7, Step 5f items 4, 5, 10 |
| vLLM caption trial | kernel written (`system1/research/phase01_trials/caption_vllm/`), not run | plan Step 5b item 3 |

## Removed

The previous Phase01/Phase02 pipeline was removed on 2026-10-26 (plan Step 6
item 2): Notebooks 01 to 03 of the old flow, the old Phase01 runner and
qualification modules, Phase02 mock providers, the old merge, SQLite, index,
and release writers, VLM scene grouping, `system1/prompts/`, old configs and
schemas, and their CLI commands. The plan lists every removed path.

## Pending

| Area | State |
| --- | --- |
| Full `batch_000` run (worker, caption pass, release) | not started |
| Remaining Phase00 batches | not started |
| Evaluation set | not started; separate plan |
| System 2 runtime (FastAPI + React) reading the release contract | scaffold only (`system2/backend/`, `system2/frontend/`) |
| `mvp-app/` | Gradio app used for the preliminary round; does not read `release_v2` |

## Interpretation Rule

A row is verified only when a Kaggle run or test recorded in the plan shows it.
Coded rows must not be described as working until their Kaggle check is
recorded in the plan Progress.
