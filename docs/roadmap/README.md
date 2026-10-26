# Roadmap

Date: 2026-10-26

Remaining work after the System 1 pipeline simplification. Detail and measured
results are in `docs/plans/active/system1-pipeline-simplification.md`;
implemented state is in `docs/product/current-state.md`. The roadmap before
2026-10-26 is in `docs/archive/roadmap/`.

| # | Step | Done when | Source |
| --- | --- | --- | --- |
| 1 | Kaggle verification runs of code not yet run on Kaggle: one-pass decode with in-process TransNet, OCR crop cache, ASR sentence chunks and windows, shot drift split, blur filter, bucket media resume | worker run on the 5 test videos matches the previous cut segments and keyframes; stage timings and cache hit rate recorded | plan Step 5c, 5f |
| 2 | vLLM caption trial on T4 | s/shot and valid-JSON rate compared with transformers (3.43 s/shot, 98.3%) | plan Step 5b item 3 |
| 3 | Scene grouping check | release built from real packages contains scenes; boundary precision and recall measured on 3 hand-labelled videos | plan Step 5b item 5, ADR 0026 |
| 4 | Full Batch 1 | worker and caption pass run on all of `batch_000`, then on the remaining Phase00 batches (873 videos in `canonical_release_v001`); `build-release` publishes to `releases/{release_id}/`; time per video recorded | plan Step 6 item 1, `docs/architecture/system1-target.md` |
| 5 | Evaluation set (separate plan, not started) | set exists and is used to decide whether captions stay and whether the query-time temporal window is enough | ADR 0021, `docs/architecture/system1-target.md` Open Items |
| 6 | System 2 integration | System 2 downloads the release from the bucket and searches image vectors, text vectors, and FTS5 with the query-time temporal window | `docs/architecture/data-contracts.md` (runtime contract), `docs/architecture/system2-retrieval.md` |
