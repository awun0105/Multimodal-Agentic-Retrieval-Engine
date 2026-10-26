# Execution Plan: System 1 Pipeline Simplification

Date: 2026-10-25

## Status

Active

## Outcome

System 1 produces a real, searchable release from Batch 1 videos: shots,
content-adaptive keyframes, real visual embeddings with an inner-product FAISS
index, ASR, OCR, and optional captions, packaged in one contract that System 2
can read. The pipeline runs end to end on Kaggle, records measured time per
video, and rejects the output defects observed in the 2026-08-27 run.

## Context

- Target design: `docs/architecture/system1-target.md`.
- Decisions: ADR 0021 (shot-level units, query-time window), ADR 0022
  (content-adaptive keyframes), ADR 0023 (model stack), ADR 0024 (validation
  policy), ADR 0025 (separate caption pass, bucket release storage, WebP at
  release time), ADR 0026 (deterministic scene grouping and text-only scene
  summary). ADR 0015
  keeps the self-generated evidence principle; ADR 0016 and ADR 0017 (Phase00
  metadata and timelines) are unchanged.
- Supersedes the active plans `notebook01-production-pipeline.md`,
  `phase01-semantic-correctness-remediation.md`, and `preliminary-ready-e2e.md`
  (moved to `docs/plans/completed/` with status Superseded).
- Evidence of the current state (2026-10-25 review):
  - Hugging Face `1thesudden/AIOU26_release`: Phase00 for 873 videos and 56
    Phase01 structure ZIPs. `1thesudden/AIOU26_checkpoints`: 77 per-video
    Phase01 checkpoints from 2026-08-25 to 2026-08-27. These artifacts predate
    the September code changes and are not reusable.
  - Phase02 (`features/builder.py`, `features/providers.py`) is mock only.
    `indexes/visual.py` writes `IndexFlatL2` or a JSON stub.
  - Notebook 01 writes Phase01 output to Hugging Face under the Phase00
    release ID. Notebooks 02 and 03 read a local `competition_dataset_v001`
    folder, default to mock providers, and never call
    `restore-structure-artifacts`.
  - Test baseline (base install): 562 passed, 4 known failures listed in
    `AGENTS.md`.

## Scope

In scope:

- Model trials on Kaggle and fixing model choices (ADR 0023).
- Removing scene stages (ADR 0021).
- Content-adaptive keyframes (ADR 0022).
- Real embedding providers and inner-product FAISS index.
- ASR and OCR replacement, single constrained caption call.
- Wiring Notebook 01 output into feature, merge, index, and validation steps.
- Validation consolidation and behavior tests (ADR 0024).
- A small runtime contract for System 2 (keyframes, image embeddings with
  vector map, video metadata, time-ranged text with evidence type, and text
  embeddings for captions and ASR chunks).
- Text embeddings for captions and ASR chunks, and FTS5 text with a
  diacritic-free column (ADR 0023, decision 5).

Out of scope:

- Phase00 ingest changes, except where the new runtime contract needs a field.
- System 2 implementation and the evaluation set (separate plans).
- Batch 2 processing.

## Approach

### Step 1: Documentation baseline (this change)

ADRs 0021 to 0024, this plan, superseded status on old plans and ADRs, and
status notes on architecture docs that will change.

### Step 2: Kaggle setup

1. Install the Kaggle CLI locally and authenticate with an API token in
   `~/.kaggle/kaggle.json` (the user creates the token; it never enters chat or
   the repository).
2. Trials read only public Hugging Face repos (`AIOU26_raw`,
   `AIOU26_release`, `AIOU26_checkpoints` are public), so no token is needed.
   Runs that write to Hugging Face add the token to Kaggle Secrets and read it
   with `kaggle_secrets.UserSecretsClient`; it is never printed or written to
   output. Kernels need internet, which requires a phone-verified Kaggle
   account.
3. Trial kernels are generated from the repository, pushed with
   `kaggle kernels push`, monitored with `kaggle kernels status`, and their
   outputs fetched with `kaggle kernels output`. GPU: T4 x2 or P100. Kaggle GPU
   time is limited per week, so trials stay small.
4. Trial outputs are written only to local kernel output or a separate test
   prefix on Hugging Face, never to `canonical_release_v001`.

### Step 3: Model trials

Videos: `L30_V030` (news, logo overlay) and one speech-heavy video. Each trial
records quality samples and GPU seconds per video.

1. Embeddings: SigLIP2, BEiT3, and CLIP on the trial keyframes. Check
   text-to-image results for 20 hand-written Vietnamese queries.
2. ASR: ChunkFormer-large-vie and PhoWhisper-large against the 2026-08-27
   Parakeet output.
3. OCR: PP-OCR with text detection gating against the 2026-08-27 Vintern
   output.
4. Captions: Qwen3-VL-4B and 2B with JSON-schema constrained decoding, one
   call per shot; measure valid-JSON rate, time per shot, and caption quality.
5. Text embeddings: BGE-M3, multilingual-e5-large, and Qwen3-Embedding-0.6B on
   trial captions and ASR chunks; check the same Vietnamese queries and query
   encoding latency on CPU and GPU.

Record results in this plan and fix model IDs in ADR 0023 and
`system1/configs/models.yaml`.

### Step 4: Behavior tests first

Write behavior tests for the simplified pipeline before removing old tests:
keyframes inside their shot and sub-shot, one-shot video density, OCR prompt
echo and repeated-logo rejection, ASR invalid-syllable gate, constrained
caption parsing, embedding normalization and vector map consistency, Notebook
01 to merge handoff.

### Step 5: Implementation, one stage per commit

1. Remove scene stages, scene schemas, scene prompts, review and quality guard.
2. Content-adaptive keyframes and sub-shots.
3. Embedding providers and inner-product FAISS index; drop duplicate OCR in
   Phase02.
4. ASR provider swap; remove Flashlight runtime artifact and Python 3.13 pin.
5. OCR provider swap with gating and repeated-text filtering.
6. Single constrained caption call (kept only if trials justify it).
6a. ASR chunking and text embeddings for captions and ASR chunks; FTS5 text
    with a diacritic-free column.
7. Failure policy: skip and log invalid items; fail on missing fallback
   credentials at preflight.
8. Notebook wiring: one release ID, restore from Hugging Face, production
   providers by default; collapse Notebook 00 variants to the documented ones.
9. One packaging-time output validator; remove scattered per-stage checks.

Each commit updates the docs for the stage it changes (architecture, data
contract, `docs/validation/test-matrix.md`).

### Step 5b: Caption pass, release publishing, scenes (ADR 0025, ADR 0026)

Added 2026-10-26 after the first end-to-end run (Progress, Step 5 item 11).

1. Remove captions from the worker: `worker/video.py` drops the `captions`
   stage and the caption and `visible_text` documents; `worker/models.py` no
   longer loads Qwen; `worker.yaml` moves `models.captions` under a `captions`
   section. Check: `test_worker_video.py` passes without a captioner; a Kaggle
   run of `batch_000` videos 1 to 5 stays under 10 GPU minutes per video.
2. Caption pass: `captions/video.py` (restore worker ZIP, caption the middle
   keyframe of each shot, build caption and `visible_text` documents with
   `text_unaccented` and E5 vectors, package with manifest and checksums),
   `captions/batch.py` (skip videos whose caption package exists, report), CLI
   `caption-batch`, notebook `caption_batch.ipynb`. Check: behavior tests with
   a fake captioner; Kaggle run on the same 5 videos; time per shot recorded.
3. Caption throughput trial: vLLM with structured outputs on Kaggle T4 against
   transformers `generate` at batch 16, same 5 videos. Keep the faster path
   that installs beside the other models. Check: valid-JSON rate and seconds
   per shot in this plan.
4. Release merge of caption packages: `release/build.py` accepts optional
   caption ZIPs, adds caption and `visible_text` documents and vectors, and
   records per-video caption presence in the manifest. Check:
   `test_release_build.py` covers a release with and without captions.
5. Scenes: `scenes/grouping.py` as a pure function over shot evidence with the
   ADR 0026 signals and parameters from `worker.yaml` section `scenes`;
   `release/build.py` writes `scenes` and `shots.scene_id`; `scenes.summary` is
   the distinct shot captions joined in time order, with no model call and no
   `scene` documents at release time (ADR 0026 amendment 2026-10-26). Check: behavior tests on synthetic shots (two angles of one
   situation join; silence plus visual change splits; `max_scene_sec` splits;
   short single-shot scene merges); hand-labelled boundaries on 3 videos with
   precision and recall recorded here.
6. Release media: `release/build.py` re-encodes keyframes to WebP quality 80
   and writes `.webp` refs; `data-contracts.md`, `schemas/`, and the package
   validator change together. Check: `test_release_build.py` asserts `.webp`
   refs and decodable files.
7. Release upload: `release/publish.py` uploads `db/`, `indexes/`,
   `manifest.json`, media, then `READY.json` to the bucket prefix
   `releases/{release_id}/` (test: `releases_test/`), batched and resumable,
   following `mvp-app/tools/upload_release.py`; CLI `publish-release`;
   `build_release.ipynb` calls build then publish. Check: upload of the 5-video
   release to `releases_test/`, `hf buckets sync` round trip, file count equals
   manifest counts.

### Step 5c: Algorithm improvements backlog

Added 2026-10-26. Each item names the stage, the current behavior, the change,
the expected effect, and the check that decides whether it stays. Items in
group A reduce worker time or fix observed output defects and run before the
full batch. Items in group B change retrieval quality and wait for the
evaluation set, because their effect cannot be measured without it. None of
these items changes a contract on its own; an item that does updates
`data-contracts.md`, `schemas/`, and the validator together.

**Group A: before the full run**

1. OCR per shot with region change detection (stage 5). Current: every
   keyframe runs detection and recognition (519 s for 500 keyframes in
   `L21_V014`, 24% of worker time). Change: run OCR on the first keyframe of
   each shot; for later keyframes in the same shot run OCR only when the
   difference hash of the lower third of the frame (ticker and subtitle band)
   or of the whole frame changes past `min_change`. Expected: about one third
   fewer OCR calls on news video. Check: OCR lines per video before and after on
   the 5 test videos; lines lost must be repeats of lines already found in the
   shot.
2. OCR crop cache (stage 5). Current: the same logo, ticker, and caption box is
   recognized hundreds of times per video. Change: hash each detected text box
   crop (difference hash at 16x16) and reuse the recognized string for a
   repeated hash inside the video. Expected: large cut in VietOCR calls on
   static overlays. Check: cache hit rate and recognition time per video.
3. OCR lexical filter (stage 5). Current: `clean_ocr_lines` filters by length
   and character class only; fragments such as "Vập", "Máp" reach FTS5.
   Change: score each line by the share of tokens that are valid Vietnamese
   syllables (syllable table or `pyvi`), keep lines above a threshold, keep
   digits, times, and all-caps acronyms. Expected: fewer noise documents.
   Check: sample of 200 dropped lines reviewed by hand; no real headline
   dropped.
4. Shot split by image vector instead of difference hash (stage 3). Current:
   `shot_drift 0.35` on a 64-bit difference hash; misses color changes and
   small changes inside text regions, and over-splits on camera motion.
   Change: compute SigLIP vectors for candidate frames first (the embedder
   runs at 0.087 s per image, the same frames are embedded anyway), then split
   when `cos(candidate, shot_start) < drift_threshold`; keep the difference
   hash only as the cheap candidate filter. Expected: fewer false splits on
   pans, more true splits on content change. Check: shot count and boundary
   agreement against hand-labelled shots on 3 videos; worker time unchanged
   within 10%.
5. Representative keyframe per shot (stage 3 and caption pass). Current: the
   middle keyframe. Change: the keyframe whose vector is closest to the mean
   vector of the shot's keyframes, after dropping frames with low variance of
   Laplacian (blur or transition). Expected: fewer captions of blurred or
   transitional frames. Check: rejected caption rate on the 5 test videos.
6. Blur and transition filter for keyframe candidates (stage 3). Current: only
   `edge_margin_frames` around cuts. Change: drop a candidate whose variance of
   Laplacian is below a fraction of the shot median. Expected: fewer unusable
   keyframes. Check: count of dropped candidates and visual sample.
7. ASR chunks on sentence and silence boundaries (stage 6). Current: 10 to 30
   s windows cut by time. Change: cut at ChunkFormer segment boundaries where
   the gap exceeds 0.6 s or the text ends with sentence punctuation, then pack
   to the 10 to 30 s range. Expected: chunks that do not cut sentences. Check:
   share of chunk boundaries that fall inside a segment.
8. Overlapping ASR windows (stage 6). Current: disjoint chunks. Change: add a
   second document set of 20 s windows stepped by 10 s, `evidence_type asr`,
   flagged `window = true` so System 2 can dedupe. Expected: queries that fall
   on a chunk boundary still match. Check: FTS and vector hits for 20 boundary
   queries on the 5 test videos.

**Group B: after the evaluation set**

9. BM25 ranking in FTS5 (release). Current: FTS5 default order. Change: order
   by `bm25(text_documents_fts)` with column weights for `text` over
   `text_unaccented`. Check: evaluation set MRR.
10. Generic keyframe flag (release). Current: intros, station logos, and
    weather maps repeat across videos and dominate image search. Change: cluster
    image vectors across the release (cosine above 0.97 across at least 5
    videos), set `keyframes.is_generic`, and let System 2 down-weight them.
    Check: evaluation set R@10; count of flagged keyframes.
11. Maximal Marginal Relevance at query time (System 2, noted here because it
    decides how many keyframes per shot the release must keep). Check:
    evaluation set with per-shot diversity.
12. Multi-frame captions for long shots (caption pass). Current: one keyframe
    per shot. Change: shots longer than 8 s send 2 to 4 keyframes in one call so
    the caption describes motion. Check: caption quality sample; seconds per
    shot.
13. Scene boundaries by local minima instead of a fixed threshold (release,
    ADR 0026). Change: TextTiling-style depth score on the continuity series;
    split where the depth exceeds `mean - k * std`. Check: boundary precision and
    recall against the same hand-labelled videos as ADR 0026.
14. Approximate image index (release). Current: `IndexFlatIP`, about 1.5 GB
    for 340,000 vectors of 1152 dimensions. Change only if the System 2 host
    lacks RAM: `IndexHNSWFlat` with a recall check against the flat index.
    Check: recall at 10 above 0.98 on 1,000 queries.

Order inside group A: 1 and 2 (worker time), then 4 and 5 (keyframe quality),
then 3, 7, 8 (text quality). Each item is one commit with its check recorded in
Progress.

### Step 5d: Data contract audit and alignment

Added 2026-10-26. Findings from comparing `docs/architecture/data-contracts.md`,
`system1/schemas/`, and the worker and release code at commit `93c7723`:

| Item | Contract today | Code today | Resolution |
| --- | --- | --- | --- |
| Runtime tables | 23 tables incl. `shot_captions`, `scene_summaries`, `shot_transcript_links`, `scene_transcript_links`, `objects`, `embeddings_meta`, `feature_availability`, `release_capabilities`, query and agent state tables | `cut_segments`, `shots`, `keyframes`, `text_documents`, `text_documents_fts` | Contract lists the release tables of `system1-target.md` plus `videos` and `scenes` (ADR 0026). Query and agent state tables move to `system2-retrieval.md`; they are runtime state, not release content. Removed tables are listed as superseded. |
| `videos` table | required | not written | `build-release` writes `videos` from Phase00 canonical metadata (`video_id`, duration, fps, frame count, width, height, organizer fields or null). System 2 needs duration and fps for the temporal window. |
| `shots.schema.json` | `scene_id`, `shot_index`, `detection_method: transnet_v2`, `status`, `boundary_convention` | `shot_id`, `video_id`, `cut_segment_id`, `start_frame`, `end_frame`, `start_sec`, `end_sec` | New `shots_v2` schema with the code columns plus `scene_id` (nullable until ADR 0026 lands). `boundary_convention` stays `[start_frame, end_frame)` as a documented rule, not a column. |
| `cut_segments` | no schema | written by the worker | New `cut_segments_v1` schema. |
| `keyframes.schema.json` | `keyframe_role`, `quality_score`, `is_representative`, `scene_id`, `status` | `keyframe_id`, `video_id`, `frame_id`, `timestamp_sec`, `shot_id`, `cut_segment_id`, `selection_reason`, `keyframe_ref`, `thumbnail_ref` | New `keyframes_v4` schema with the code columns; `selection_reason` enum `shot_start`, `visual_change`. Representative keyframe is a column `is_representative` once Step 5c item 5 lands. |
| `text_documents.schema.json` | `document_id`, `entity_id`, `normalized_text`, `language` | `doc_id`, `video_id`, `evidence_type`, `start_sec`, `end_sec`, `shot_ids`, `keyframe_id`, `text`, `text_unaccented` | New `text_documents_v2` schema; `evidence_type` enum `asr`, `ocr`, `caption`, `visible_text`, `scene`. |
| `asr_segments.schema.json` | `asr_segment_id`, words, confidence fields | `video_id`, `start_sec`, `end_sec`, `text` | New `asr_segments_v2` schema. |
| `vector_map` | mandatory SQLite table `(index_name, vector_id) -> keyframe_id` | `indexes/{name}_vector_map.parquet` per index | Keep Parquet beside each FAISS file (one index, one map, no join at load time) and add the same rows as SQLite table `vector_map(index_name, vector_id, item_id)` so the doc rule "FAISS resolves through SQLite" still holds. The release validator checks both agree. |
| Keyframe ref extension | `.jpg` | `.jpg` in packages | `.jpg` in worker packages, `.webp` in the release (ADR 0025; already written into the doc). |
| Package validation | schemas under `system1/schemas/` validate tables | `validate_package` checks columns and relations in code only | `validate_package` and `build_release` validate every Parquet table against its JSON schema (`jsonschema` is already a dependency). Schema version is recorded in the package manifest. |
| Hugging Face layout | `phase01_structure/artifacts/{batch}/{video}_structure.zip`, `releases/{release_id}/` in the dataset repo | `worker/artifacts/{batch}/{video}.zip`; release not uploaded | Doc follows ADR 0025 layout (already written into `system1-target.md`; `data-contracts.md` section "Hugging Face Storage Contract" is rewritten to match). |
| `pts_time`, `duration_time`, `frame_id_method` on keyframes | required | not written | Dropped. `frame_id` comes from the decoded timeline (ADR 0017) and `timestamp_sec` is its `pts_time`; one time column is enough. |

Done 2026-10-26 (docs only, no code): `system1/schemas/v2/` holds
`cut_segments`, `shots`, `keyframes`, `asr_segments`, `ocr`, `captions`,
`text_documents`, `scenes`, `videos`, `vector_map`; `data-contracts.md` is
rewritten for `release_v2`; `doc-conflicts.md` records the change. Checked the
new schemas against the real `L21_V014` worker package from Kaggle:
`cut_segments`, `asr_segments`, `ocr`, `captions` pass; `shots` lacks
`scene_id` and `keyframes` lacks `is_representative` (added by Step 5b item 5
and Step 5c item 5; until then the validator accepts their absence);
`text_documents.keyframe_id` holds `NaN` instead of null for `asr` rows (bug:
`_text_documents` must write `None` and Parquet must store a nullable string).

Work items for code:

1. Schema files are written (above). Delete the superseded ones (`shot_captions`,
   `scene_summaries`, `shot_transcript_links`, `scene_transcript_links`,
   `objects`, `embeddings_meta`, `feature_availability`, `text_sources`,
   `asr_words`, scene review schemas) in Step 6 with the code that reads them.
   Check: every table the worker and release write has exactly one schema file
   under `schemas/v2/`, and no `v2` schema lacks a writer.
2. `validate_package` validates each table against `schemas/v2/{table}.schema.json`
   (load with `jsonschema.Draft202012Validator`, convert numpy values to Python
   before validating, treat `NaN` as a violation); `build_release` validates
   merged tables, writes `videos` (from `phase00_ingestion/tables/videos.parquet`
   and the frame timelines) and `vector_map` (Parquet beside each index and the
   SQLite table), and records `schema_version: release_v2` plus schema sha256s
   in `manifest.json`. Worker manifest becomes `worker_package_v2`. Fix the
   `keyframe_id` NaN bug. Check: `test_worker_video.py`, `test_release_build.py`
   include a schema-violation case and a `videos` row check.
3. `data-contracts.md` rewritten (done). Remaining check after Step 5b code:
   every table and column named in the doc exists in a schema file and in the
   5-video test release. `system2-retrieval.md` already lists the query and
   agent state tables; confirm it needs no change.
4. Record the contract version in `release/manifest.json`
   (`schema_version: release_v2`) and in each package manifest.

Order: item 1 and 2 land with Step 5b item 4 (release merge), because that is
the last change to the table set before scenes; item 3 lands after Step 5b item
5 (scenes) so the doc is written once.

### Step 5e: Notebooks

Added 2026-10-26. Rule: notebooks hold settings and one CLI call each; every
decision lives in the package (`docs/agents/GUIDE.md` Rule 10).

Current state at commit `93c7723`:

| Notebook | State | Action |
| --- | --- | --- |
| `worker_batch.ipynb` | runs `worker-batch`; verified on Kaggle for 5 videos | keep; drop the `CAPTIONS` setting when Step 5b item 1 lands; rename to `01_worker_batch.ipynb` |
| `build_release.ipynb` | runs `build-release` into `/kaggle/temp`; no upload, so the release is lost when the session ends | add `publish-release` call and `BUCKET_ID`, `BUCKET_PREFIX` settings (Step 5b item 7); rename to `03_build_release.ipynb` |
| (missing) `caption_batch.ipynb` | - | new, same shape as `worker_batch.ipynb`, runs `caption-batch` (Step 5b item 2); `02_caption_batch.ipynb` |
| `00_master_ingestion_and_assignment.ipynb`, `00A_...` | Phase00 variants superseded by 00B and 00C | delete |
| `00B_master_ingestion_and_assignment.ipynb` (Colab, Drive) | Phase00 ingest, complete for Batch 1; needed for Batch 2 | keep; reduce to settings plus CLI calls if cells contain logic; verify on one archive in a test prefix before Batch 2 |
| `00C_master_ingestion_and_assignment (local).ipynb` | local Phase00 variant | keep as `00C_master_ingestion_local.ipynb` (no spaces in the name) after the same reduction |
| `01_worker_structure_pipeline.ipynb` | old Phase01 worker (scene stages, Vintern, Parakeet) | delete in Step 6 after the new worker has run one full batch |
| `02_worker_feature_enrichment.ipynb` | old Phase02 (mock providers) | delete in Step 6 |
| `03_merge_validate_index_release.ipynb` | old release flow against a local folder | delete in Step 6 |

Work items:

1. New `caption_batch.ipynb` and `publish-release` in `build_release.ipynb`
   (with Step 5b items 2 and 7).
2. Each kept notebook has a `test_notebooks.py` behavior test: cells are
   settings, setup, or one CLI call; no cell imports `system1.*` modules
   directly; secrets are read through `kaggle_secrets` or `google.colab.userdata`
   and never printed. Replaces
   `test_smoke.py::test_notebooks_are_operator_ready_thin_orchestration_shells`
   (known failure in `AGENTS.md`).
3. Operator runbook `system1/notebooks/README.md`: order of notebooks, Kaggle
   secrets required (`HF_TOKEN` write access to the output repo and bucket),
   settings per notebook, expected run time per batch, how to resume after a
   session ends (rerun; finished videos are skipped), where outputs land, and
   how to verify a batch (report JSON counts equal manifest counts).
4. End-to-end verification per notebook on Kaggle, recorded in Progress with
   kernel id and commit: `worker_batch` (5 videos, done at `93c7723`),
   `caption_batch` (same 5), `build_release` with publish (5-video release in
   `releases_test/`, `hf buckets sync` round trip, System 2 or `mvp-app`
   opens the SQLite and FAISS files).
5. Rename and delete per the table above in Step 6, together with
   `system1/README.md` and `docs/README.md` updates.

### Step 5f: Runtime efficiency and robustness on Kaggle, Colab, Hugging Face

Added 2026-10-26 from a review of `worker/video.py`, `worker/batch.py`,
`worker/stages.py`, `artifacts/hf_store.py`, `artifacts/package.py`,
`providers/*`, `release/build.py`. Constraints: Kaggle and Colab give tens of
GB of disk and a session limit (12 h Kaggle); a Kaggle GPU kernel has about 13
GB RAM, a CPU kernel about 30 GB; network to Hugging Face drops occasionally.

**Blocking for the full run**

1. `build-release` streams one package at a time. Current: downloads every
   ZIP to `packages/` (about 100 MB each, 87 GB for 873 videos), extracts all
   to `.staging/` (second copy), copies media to `release/media` (third copy).
   Change: for each ZIP: download, validate checksums, read tables and vectors
   into memory, re-encode keyframes to WebP straight into `release/media/`
   (Step 5b item 6), upload that video's media to the bucket (Step 5b item 7),
   delete the ZIP and its media. Tables and vectors are concatenated at the
   end; `db/`, `indexes/`, `manifest.json`, `READY.json` upload last. Peak
   disk: one package plus `db/` and `indexes/`. Resumable: a video whose media
   is already in the bucket (listed once at start) is not re-encoded or
   re-uploaded. Check: build of the 5-video release leaves no `packages/` or
   `.staging/` directory; disk high-water mark logged.
2. Memory budget for indexes. 873 videos give about 340,000 image vectors
   (1152 float32, 1.6 GB) and about 900,000 text vectors (1024 float32, 3.7
   GB); `IndexFlatIP` holds a second copy while building. Run `build-release`
   on a CPU kernel (about 30 GB RAM), not a GPU kernel. Record the measured
   peak RSS in the manifest. System 2 host needs the same RAM to load
   `text_e5.faiss`; Step 5c item 14 (HNSW or float16) is the fallback.

**Worker time**

3. One video decode instead of two. Current: TransNet decodes every frame
   (106 s on an 18-minute video) in a subprocess that reloads weights per
   video; `iter_decode_frame_groups` decodes every frame again (89 s). Change:
   one `cv2` pass yields each frame once; the 48x27 frame goes to a TransNet
   model loaded once per session (in-process, `providers/cuts.py`), the
   full-resolution frame is kept only when it is a keyframe candidate of the
   current segment. Because shot boundaries depend on cuts, the pass buffers
   candidate frames per 2-second candidate interval and finalizes segments as
   soon as TransNet predictions for that range exist (TransNet needs a 100-frame
   window, so the lag is 100 frames). Expected: about 90 s per 18-minute video,
   10 to 15% of the no-caption worker time. Check: cut segments and keyframes
   identical to the two-pass result on the 5 test videos; worker seconds
   recorded.
4. Video downloaded once. Current: `hf_hub_download` into `.hf_cache` then
   `shutil.copyfile` into `videos/` (two copies of about 150 MB, both deleted
   per video). Change: `hf_hub_download(local_dir=...)` or use the cached path
   directly; keep one copy. Check: `du` of `work_root` during one video.
5. `write_artifact_zip` uses `ZIP_STORED` for `.jpg`, `.webp`, `.npy`,
   `.parquet` (already compressed) and `ZIP_DEFLATED` only for JSON. Expected:
   seconds of CPU per video and no size change. Check: package size within 1%
   of the current size, zip time logged.
6. Keyframe JPEGs are opened from disk once per model stage (SigLIP, OCR; also
   captions until Step 5b item 1). Step 5c item 4 moves SigLIP into the
   keyframe pass and removes one decode; OCR keeps reading from disk because it
   runs after keyframes are final. No separate change.

**Robustness**

7. Retry on Hugging Face I/O. Current: a single failed `upload_file` or
   `download_file` marks the video `failed`, deletes `work/`, and loses the GPU
   time. Change: `HuggingFaceDatasetArtifactStore.upload_file` and
   `download_file` retry 3 times with exponential backoff (2, 4, 8 s) on
   `HfHubHTTPError` 5xx, 429, and connection errors; the batch runner retries
   the upload once more before recording a failure and keeps `work/{video_id}`
   when the failure is an upload, so a rerun in the same session finishes
   without recomputing. Check: unit test with a store that fails twice then
   succeeds.
8. Stage checkpoints are session-local by decision. `work/` is deleted after
   each video and `/kaggle/temp` disappears with the session, so
   `StageRunner` markers only help within one session. With captions out of
   the worker a video takes under 10 minutes, so a lost session costs at most
   one video. No cross-session checkpoint upload (the old
   `AIOU26_checkpoints` flow is not revived). Record in `system1-target.md`.
9. Batch report survives a dead session. Current: report uploaded once at the
   end. Change: after every video write `report.json` to the notebook's
   persisted output directory (`/kaggle/working` or the Colab working dir) in
   addition to `work_root`; upload to Hugging Face at the end as now. Check:
   the file exists after the first video.
10. One batch, one worker. Current: the uploaded set is listed once at start, so
    two sessions on the same batch would both process the same videos. Rule:
    one `batch_id` per session; the runbook (Step 5e item 3) states it. The
    runner re-checks `exists()` for the ZIP right before upload and skips the
    upload if another worker got there first (counts as `skipped`).
11. TransNet fallback is bounded. Current: `detect_shot_scenes` retries on CPU
    after a GPU failure, with no time limit; a 38-minute video on CPU can take
    20 minutes or more. Change: no CPU retry in the worker; a GPU failure goes
    straight to the one-segment fallback (status `fallback`, retried next run,
    ADR 0024). Check: fallback path test already exists; remove the CPU attempt
    for the worker code path only.
12. Commit volume is acceptable: one commit per worker ZIP, caption ZIP, and
    report gives under 2,000 commits for Batch 1 at about 6 per hour per
    worker. No batching of commits.

**Caption pass**

13. Read only what is needed from the worker ZIP. The caption pass needs
    `shots.parquet`, `keyframes.parquet`, and the representative keyframe of
    each shot (about 400 of 500 images). Change: open the ZIP with `zipfile`
    and read those members directly instead of extracting the whole package.
    Check: temp disk per video under 100 MB.

Order: 1, 2, 7, 9 before the 5-video release round trip (Step 5b item 7);
3, 4, 5, 11 before the full `batch_000` run; 10, 13 with their notebooks;
6, 8, 12 are decisions, no code.

### Step 6: End-to-end run and cleanup

1. Run the full pipeline on Kaggle for a 5 to 10 video batch; record time per
   video and output quality.
2. Remove constant tests, `phase01_qualification*.py`, `phase01/smoke.py`, and
   dead modules.
3. Rewrite `docs/product/current-state.md` and `docs/roadmap/`; reduce
   `docs/architecture/data-contracts.md` to the runtime contract plus System 1
   internals that still exist; remove superseded architecture docs.

## Risks And Recovery

- Kaggle GPU quota or session limits interrupt trials. Mitigation: small
  trials, per-video checkpoints, outputs fetched after each kernel.
- Selected OCR or ASR model handles Vietnamese diacritics poorly. Mitigation:
  trials compare against saved 2026-08-27 outputs before any switch.
- Removing tests reduces coverage. Mitigation: Step 4 precedes deletions.
- Caption pass throughput stays near 3.4 s per shot (about 500 GPU hours for
  873 videos). Mitigation: run on several Kaggle accounts in parallel; release
  ships without captions first; vLLM trial in Step 5b item 3; captions can be
  dropped after the evaluation set without changing the worker.
- vLLM pins a torch version that conflicts with ChunkFormer, EasyOCR, or
  SigLIP. Mitigation: the caption pass is its own notebook and environment, so
  the conflict cannot reach the worker.
- Scene grouping weights are wrong for interview or single-take videos.
  Mitigation: parameters are release-time configuration tuned on hand-labelled
  videos; System 2 keeps the query-time temporal window (ADR 0021).
- WebP re-encode of about 340,000 keyframes is slower than estimated.
  Mitigation: encode in a process pool at release time; measure on the 5-video
  release first.
- Recovery: every stage change is its own commit; revert the commit to restore
  the previous stage. Hugging Face canonical data is never overwritten during
  this plan.

## Progress

- [x] Step 1: Documentation baseline.
- [x] Step 2: Kaggle setup (CLI authenticated; trial kernels in `system1/research/phase01_trials/`).
- [x] Step 3: Model trials and fixed model choices (ADR 0023 status table).
- [ ] Step 4 and Step 5, built as new modules beside the old path; nothing is
  wired into Notebook 01 yet:
  - [x] `keyframes/adaptive.py` with `tests/test_adaptive_keyframes.py`.
  - [x] `text/evidence.py` (ASR chunks, shot mapping, unaccent, prompt echo,
    video-wide repeats) with `tests/test_text_evidence.py`.
  - [x] `indexes/vectors.py` (inner-product index, vector map, no stub) with
    `tests/test_vector_index.py`; `faiss-cpu` added to `system1` dependencies.
  - [x] `tests/test_smoke.py` no longer depends on host free disk
    (`ignore_host_free_disk` fixture).
  - [x] Embedding, ASR, OCR, and caption providers (`system1/providers/`,
    `configs/worker.yaml`, `worker` extra). Kaggle check at commit `007882b`
    (`research/phase01_trials/providers/`): all five run; SigLIP2 0.087 s/image,
    ChunkFormer on GPU 4.1 s (`L30_V030`) and 18.1 s (`L25_V085`), OCR 0.37
    s/image, captions 4.1 s/image with 32/32 valid JSON. Open: OCR logo variants
    ("tuổi trerv", "tucitrery") are not caught by exact-match repeat filtering.
  - [x] Per-video worker (`worker/video.py`, `stages.py`, `package.py`,
    `providers/cuts.py`). Kaggle run at commit `17a1891`
    (`research/phase01_trials/worker/results/v3_results.json`), all stages pass:
    `L30_V030` (5.7 min) in 5.7 min; `L25_V085` (38 min) in 29.6 min, of which
    captions 1032 s (3.3 s/shot, 315 shots) and OCR 427 s (text-heavy slides).
    Batch 16 at 512 px gained only about 1.4x over batch 8 at 768 px; per-token
    constrained decoding with transformers `generate` is the limit. Next
    optimization: vLLM structured outputs for captions.
  - [x] Cut-detection fallback: one whole-video cut segment, status `fallback`,
    retried on the next attempt; downstream stages rerun when an upstream
    outcome changes.
  - [x] Release step (`release/build.py`, `tests/test_release_build.py`):
    validates every package checksum and content, rejects duplicate videos,
    writes SQLite tables with FTS5 (`unicode61 remove_diacritics 0` over
    `text` and `text_unaccented`), image and text inner-product indexes with
    vector maps, copied media, and a manifest listing degraded stages.
  - [x] Batch runner (`worker/batch.py`, `tests/test_worker_batch.py`): reads
    Phase00 batch manifests and raw mapping, skips videos already uploaded,
    records failed videos and continues, uploads one package per video and a
    batch report, removes local files after each video. CLI `worker-batch` and
    `build-release` (`commands/worker.py`), model factory `worker/models.py`,
    `storage` section in `worker.yaml` (output defaults to
    `AIOU26_release_test`). New notebooks `notebooks/worker_batch.ipynb` and
    `notebooks/build_release.ipynb`; old notebooks remain until Step 6.
  - [x] Kaggle run of `worker_batch.ipynb` (`quanlam/mare-worker-batch`,
    commit `93c7723`, T4 x2) on the first 5 videos of `batch_000` into
    `AIOU26_release_test`: 5 completed, 0 failed, no degraded stage. 70.3 min
    of video in 130.7 min (about 1.9x video length): `L21_V014` (18.6 min)
    2141 s, `L22_V004` (21.7 min) 2726 s, `L22_V010` (18.2 min) 2175 s,
    `L23_V004` (6.6 min) 452 s, `L23_V010` (5.2 min) 346 s. In `L21_V014`,
    captions took 1358 s (401 shots, 10 rejected) and OCR 519 s (500
    keyframes); all other stages took about 4 min together. At this rate one
    batch of about 73 videos needs over 40 GPU hours, more than one 12-hour
    Kaggle session. Caption cost per video must drop before the full run.
  - [x] `build-release` from those 5 packages (local CPU, 53 s): 1076 cut
    segments, 1511 shots, 1932 keyframes, 5056 text documents (163 ASR, 1923
    OCR, 1485 caption, 1485 visible_text); release 410 MB, of which media 376
    MB. FTS5 matches with and without diacritics; image index self-search
    returns the query keyframe first.
  - Resolved 2026-10-26 (ADR 0025): captions leave the worker; the release is
    published to a Hugging Face Storage Bucket with WebP keyframes re-encoded
    at release time. Scenes return as a deterministic grouping (ADR 0026).
- [ ] Step 5b (ADR 0025, ADR 0026):
  - [x] 1. Worker without captions (code, 2026-10-26): `worker/video.py` has
    no caption stage, manifest `worker_package_v2`, `shots.scene_id` null,
    `keyframes.is_representative`, nullable `text_documents.keyframe_id`;
    `validate_package` checks every table against `schemas/v2`. Kaggle run at
    commit `46bf0c2` (`quanlam/mare-worker-batch` v7, same 5 videos, old v1
    packages removed first): 5 completed, 0 failed, 70.3 min of video in 43.4
    min (0.62x video length; was 1.9x with captions). Per video: `L21_V014`
    767 s, `L22_V004` 892 s, `L22_V010` 670 s, `L23_V004` 161 s, `L23_V010`
    117 s. `L21_V014` stages: OCR 505 s (66%), cuts 104 s, keyframes 89 s,
    SigLIP 33 s, ASR 16 s, text vectors 9 s. One batch of 73 videos now fits
    about 10.5 GPU hours, inside one Kaggle session. OCR is the next target.
  - [x] 2. Caption pass (code, 2026-10-26): `captions/{video,batch,models}.py`,
    CLI `caption-batch --persist-dir`, `notebooks/caption_batch.ipynb`,
    `tests/test_caption_pass.py`. Reads worker ZIP members in place (Step 5f
    item 13). Kaggle run at commit `2224257` (`quanlam/mare-caption-batch`,
    T4, transformers, same 5 videos): 5 completed, 0 failed, 1511 shots in
    5184 s (3.43 s/shot; 86.4 min for 70.3 min of video, 1.23x). Per video:
    `L21_V014` 401 shots 1381 s, `L22_V004` 503 shots 1813 s, `L22_V010` 407
    shots 1463 s, `L23_V004` 107 shots 297 s, `L23_V010` 93 shots 231 s.
    Valid JSON 1485/1511 (98.3%); all 26 rejects are `repetition_loop`.
    Captions still cost about 2x the worker; item 3 (vLLM) decides whether
    the pass stays on transformers.
  - [ ] 3. vLLM versus transformers caption throughput trial on T4.
    Trial kernel written, not run (2026-10-26):
    `system1/research/phase01_trials/caption_vllm/` (`quanlam/mare-caption-vllm`),
    vLLM 0.11.0, float16, `enforce_eager`, one T4, `L23_V010` and `L23_V004`.
  - [x] 4. Release merges optional caption packages (code, 2026-10-26):
    `release/build.py` streams one worker ZIP at a time, verifies the caption
    package `worker_package_sha256`, lists `videos_with_captions`.
  - [ ] 5. Scene grouping and text-only scene summaries; boundary precision
    and recall on 3 hand-labelled videos. Done 2026-10-26: pure grouping in
    `scenes/deterministic.py` (`ShotEvidence`, `SceneParams.from_config`,
    `continuity_score`, `group_scenes`, `scene_ids_for_shots`), `worker.yaml`
    section `scenes`, `tests/test_scene_deterministic.py` (7 tests). Wiring
    done 2026-10-26: `scenes/release_builder.py` is the default
    `scene_builder` of `build_release` and the `build-release` CLI; every shot
    gets a `scene_id`; `scenes.summary` joins shot captions, null without
    captions; no model call and no `scene` documents (ADR 0026 amendment).
    `tests/test_release_build.py` covers it. Not done: hand-labelled boundary
    precision and recall on 3 videos; a release run on real packages.
  - [x] 6. WebP keyframes in the release (code, 2026-10-26): quality 80,
    `.webp` refs, `videos` and `vector_map` tables, `release_v2` manifest with
    `schema_sha256` and `peak_rss_mb`, SQLite WAL and foreign_keys pragmas.
    `scene_builder` hook present, default null scenes.
  - [ ] 7. Bucket publish (code, 2026-10-26): `release/publish.py`
    (`publish_release`, `BucketClient`, `media_sink_for`), batched and resumable,
    `READY.json` last; CLI is `build-release --publish --bucket-id
    --bucket-prefix --persist-dir` (no separate `publish-release` command);
    `build_release.ipynb` installs `system1[release]` (huggingface_hub 1.x for
    the bucket API; `[tool.uv] conflicts` keeps it apart from
    `phase01-production`). Kaggle run at commit `200e013`
    (`quanlam/mare-build-release`, CPU kernel): 5 packages built and
    published to `1thesudden/aiou-app-storage` prefix
    `releases_test/canonical_release_v001` in 312 s end to end, peak RSS 560
    MB, 3870 files, 0 degraded stages. Tables: 1076 cut_segments, 1511 shots,
    1932 keyframes, 5047 text_documents (asr 163, ocr 1914, caption 1485,
    visible_text 1485), 0 scenes, 6979 vector_map rows. Round trip with `hf
    buckets sync` (control files 33 MB: app.sqlite 4.9 MB, image index 8.9
    MB, text index 20.7 MB): `READY.json` sha256 equals the downloaded
    `manifest.json`, FAISS ntotal equals the vector maps (1932, 5047), FTS5
    query works, keyframes are 1280x720 WebP. Media resume coded 2026-10-26:
    `media_sink_for` lists `{prefix}/media/keyframes/` once
    (`BucketClient.list_folders`, `list_bucket_tree` non-recursive) and skips
    videos whose keyframes folder exists; `sink.stats` counts uploaded and
    skipped; a failed listing uploads everything. A video whose upload died
    midway is also skipped. Not yet run on Kaggle.
- [ ] Step 5c (algorithm backlog, group A): items 1, 2, 3 coded 2026-10-26
  (`providers/ocr.py`: `frame_text_hashes`, `should_rerun_ocr`, `CropCache`,
  `EasyVietOcr.read(image, cache)`; `text/evidence.py`:
  `vietnamese_syllable_ratio`; `clean_ocr_lines(min_syllable_ratio)`; wired
  into `ocr_stage` per shot with one `CropCache` per video; config
  `models.ocr.rerun_min_change 0.15`, `text.ocr_min_syllable_ratio 0.6`).
  Decision: a single valid syllable is not penalized, so one-word headlines
  survive; fragments like "Vập" are left to the repeat and length filters.
  Measured at `46bf0c2` on the 5 test videos: `reused_from_shot` 0 on every
  video (news shots mostly have one keyframe, and extra keyframes exist only
  where the frame changed), `crop_cache_hits` 0 to 1 (detection boxes shift by
  a few pixels, so exact 16x16 hashes never match). 5c.2b done 2026-10-26:
  `CropCache` matches by Hamming distance (at most 24 of 256 bits; a 2-pixel
  box shift costs about 10 bits, unrelated crops about 127) within neighbouring
  size buckets; hit rate to be measured on the next Kaggle worker run. Item 5c.1 keeps its code but is not expected to save
  time on news video.
  Plan checks (OCR lines before/after, cache hit rate, 200 dropped lines
  reviewed) wait for the next Kaggle run; the stage report now records
  `reused_from_shot` and `crop_cache_hits`. Items 4, 5, 6 coded 2026-10-26:
  shot split by SigLIP cosine distance (`shot_drift 0.25`), one embed call per
  cut segment, `image_vectors` written from the keyframe pass without
  re-reading JPEGs; representative keyframe = nearest to the shot mean vector;
  blur filter `min_sharpness_ratio 0.3` with `blurred_dropped` in the stage
  report; keyframes checkpoint includes the image model config. Thresholds not
  tuned on real video.
  Items 7, 8 done 2026-10-26: `chunk_asr_segments(sentence_gap_sec)` cuts at
  the last segment ending in . ? ! or an ellipsis, or before a pause longer
  than `text.asr_sentence_gap_sec 0.6`, that leaves `min_sec`; falls back to
  the time cut. `asr_windows` adds `asr` documents of `text.asr_window_sec 20`
  stepped by `text.asr_window_step_sec 10` with `window` = true; all other
  documents (asr chunks, ocr, caption, visible_text) write `window` = false.
  `window` is required in `text_documents.schema.json` and
  `data-contracts.md`. Checks on Kaggle pending.
- [ ] Step 5d (data contract): audit, `schemas/v2/`, and `data-contracts.md`
  rewrite done 2026-10-26; validator and `videos`/`vector_map` code not
  started.
- [ ] Step 5f (efficiency): items 1 (streaming build), 2 (CPU kernel noted in
  the notebook), 6, 7 (HF retry with backoff, client-agnostic), 9 (report per
  video in worker and caption batch via `--persist-dir`, build report), 13
  (caption pass reads ZIP members) coded 2026-10-26. Items 4 (video
  downloaded once: `download_file(single_copy=True)` uses
  `hf_hub_download(local_dir=...)` and moves the file), 5 (`ZIP_STORED` for
  .jpg/.jpeg/.webp/.npy/.parquet), 10 (`exists()` re-check right before the
  worker and caption ZIP upload; counted as skipped) coded 2026-10-26, not
  yet run on Kaggle. Items 3 and 11 coded 2026-10-26: the cuts stage
  decodes once with `cv2` (`keyframes.adaptive.iter_cut_segment_frames`);
  TransNet runs in process, loaded once per session (`providers.cuts.
  TransNetStream`, same 100-frame windows as `transnet_worker`, input
  resized by `cv2` INTER_AREA instead of ffmpeg, so predictions may differ
  slightly from the subprocess); cut segments are finalized after the
  predictor lag and open positive runs; full-resolution frames are held only
  while their segment is unknown or while they can be candidates. Shots and
  keyframes pass to the keyframes stage in memory; a keyframes-only rerun
  decodes again from `cut_segments.parquet`. A TransNet failure goes straight
  to the one-segment fallback, no CPU retry. Test: single pass equals the
  two-pass result on a synthetic 300-frame video. Kaggle check pending: cut
  segments and keyframes identical on the 5 test videos, worker seconds.
  New known failure: `test_phase01_runtime_qualification.py::
  test_qualified_python313_production_tuple_is_pinned_in_project_and_lock`
  (lockfile now has two resolutions because of the `release` extra); the test
  belongs to the old qualification module removed in Step 6.
- [ ] Step 5e (notebooks): `worker_batch` verified at `93c7723`.
  Done 2026-10-26: items 2, 3, 5. Renamed to `01_worker_batch.ipynb`,
  `02_caption_batch.ipynb`, `03_build_release.ipynb`,
  `00C_master_ingestion_local.ipynb`; deleted `00_` and `00A_`; runbook
  `system1/notebooks/README.md`; `tests/test_notebooks.py` replaces the smoke
  notebook test, with an allowlist of 00B and 00C logic cells still to reduce.
- [ ] Step 6: End-to-end run and cleanup.
  - [x] Item 2 and deferred 5d/5e deletions (2026-10-26). Removed, each had
    no live importer from `cli.py`, notebooks, or `mvp-app`:
    - `asr/` (NeMo, faster-whisper, VAD, links): replaced by `providers/asr.py`.
    - `config/` (YAML loader for old phase configs): worker reads `worker.yaml`.
    - `db/sqlite_builder.py`, `indexes/builder.py`, `indexes/visual.py`: replaced by `release/build.py`, `indexes/vectors.py`.
    - `features/` (Phase02 mock providers): replaced by worker stages.
    - `gemini/client.py`, `vlm/`: replaced by `providers/captions.py`.
    - `phase01/` except `model_artifacts.py` (runner, production, smoke, preflight, qa, review, scheduler, checkpoint, validation, phase00); `phase01/__init__.py` reduced to a docstring.
    - `phase01_qualification.py`, `phase01_qualification_cli.py`, `phase01_qualification_worker.py`, script `system1-phase01-qualify`.
    - `release/merge.py`, `release/writer.py`, `release/smoke.py`, `release/phase_artifacts.py`: replaced by `release/build.py`, `release/publish.py`.
    - `scenes/builder.py`, `grouping.py`, `speech.py`, `summary.py`, `vlm_judge.py`: replaced by `scenes/deterministic.py`, `scenes/release_builder.py`.
    - `shots/builder.py`, `shots/understanding.py`; `shots/__init__.py` exports TransNet only.
    - `structure/`, `text/builder.py`, `validation/`: replaced by worker stages, `text/evidence.py`, `worker/package.validate_package`.
    - `release/types.py`: `BuildOptions`, `config_hash` (only used by removed modules).
    - CLI: `phase01-prepare-asr-runtime`, `phase01-smoke`, `process-batch`, `feature-batch`, `merge`, `build-db`, `build-index`, `validate`, `smoke-test`, `release`, `sync-release`, `restore-release`, `sync-structure-artifacts`, `restore-structure-artifacts`.
    - Notebooks `01_worker_structure_pipeline`, `02_worker_feature_enrichment`, `03_merge_validate_index_release`.
    - `system1/prompts/` (all read only by `vlm/`, `gemini/`, `phase01/`).
    - `configs/` except `worker.yaml` and `media.yaml`.
    - Schemas: shot_captions, scene_summaries, shot_transcript_links, scene_transcript_links, objects, embeddings_meta, feature_availability, text_sources, asr_words, scene_partition_manual_review, scene_partition_review_candidate.
    - `pyproject.toml` extra `phase01-production` and its `[tool.uv] conflicts`; `uv.lock` relocked.
    - 21 test files for removed modules (including `test_phase01_runtime_qualification.py`, `test_phase01_asr_alignment.py`, `test_phase01_vlm_client.py`); old-flow tests cut from `test_smoke.py`, `test_runtime_environment.py`, `test_phase_structure_artifacts.py`, `test_checkpoint_workflow_cli.py`.
    Check: `cd system1 && uv run pytest -q` 332 passed, 0 failed.

## Trial Results

Kaggle kernel `quanlam/mare-phase01-trial-perception`, Tesla T4 x2, videos
`L30_V030` (195 keyframes) and `L25_V085` (365 keyframes). 20 hand-written
Vietnamese queries with English translations; ground truth is a set of shots;
search runs over all 560 keyframes of both videos. Random baseline MRR is about
0.03. Small sample: differences of one or two queries are not significant.
Raw output: `system1/research/phase01_trials/perception/results/`.

Image embeddings (text-to-keyframe):

| Model | MRR vi | R@1 vi | R@10 vi | MRR en | Image s/keyframe |
| --- | --- | --- | --- | --- | --- |
| CLIP ViT-B/32 + multilingual text (current `mvp-app`) | 0.66 | 0.55 | 0.85 | 0.75 | 0.015 |
| SigLIP2 base patch16-256 | 0.71 | 0.60 | 0.95 | 0.74 | 0.011 |
| SigLIP2 so400m patch14-384 | 0.75 | 0.70 | 1.00 | 0.79 | 0.054 |

Text embeddings over the 2026-08-27 Vintern shot captions (`caption_vi`):

| Model | MRR | R@1 | R@10 | Query s |
| --- | --- | --- | --- | --- |
| multilingual-e5-large | 0.82 | 0.75 | 1.00 | 0.005 |
| BGE-M3 | 0.80 | 0.70 | 0.95 | 0.004 |
| Qwen3-Embedding-0.6B | 0.74 | 0.60 | 0.95 | 0.017 |

ASR: ChunkFormer-large-vie output has no broken syllables on both videos
(for example "tiểu học lý nhơn", "báo thanh niên" where Parakeet wrote
"Trừiểu học lý Dơn", "doáo Thanh niên"); output is lowercase without
punctuation. Decode time: 17 s for `L30_V030`, 129 s for `L25_V085`, on CPU:
`endless_decode` runs on the device of the model parameters and the trial did
not move the model to the GPU.
PhoWhisper-large ran out of GPU memory in both kernel versions (second version
on an otherwise unused T4, batch 8, 30 s chunks); not retried because
ChunkFormer already meets the need.

OCR: PaddleOCR 3.x `lang="vi"` (kernel version 2, CPU, `enable_mkldnn=False`)
drops Vietnamese letters and tone marks ("thương hiu", "bn đc d thi cuc thi",
"ÔN TÂP MÔN VÂT LÝ") and took 5.9 to 7.3 s per keyframe. Not usable. In the
caption trial, Qwen3-VL `visible_text` read Vietnamese correctly ("Thắp sáng
tương lai bằng con chữ", "THE SAIGON INTERNATIONAL UNIVERSITY").

OCR trial (kernel `quanlam/mare-phase01-trial-ocr` version 2, all 560
keyframes; results in `system1/research/phase01_trials/ocr/results/`):

| Variant | Detect s/kf | Recognize s/kf | Keyframes with text |
| --- | --- | --- | --- |
| A: PaddleOCR PP-OCRv5 det (CPU) + VietOCR | 0.62 | 0.35 | 437 |
| B: EasyOCR det (GPU) + VietOCR | 0.12 | 0.36 | 384 |
| C: EasyOCR det + EasyOCR `vi` recognition | - | 0.20 | 384 |

On the representative keyframes that have text: VietOCR (A, B) gives the most
literal Vietnamese text ("Thầy Lê Tấn Phát", "Giáo viên lớp học tình thương Ánh
Sáng Xanh") plus short noise fragments; C has more diacritic errors. Qwen3-VL-4B
`visible_text` reads full lines fluently but rewrites words ("Giáo viên" became
"Giảng viên") and adds content not in the frame ("764 + 146 = 910"). Qwen3-VL-2B
`visible_text` looped ("7 0 7 0 ...") on 2 of 9 keyframes with text.

Captions (kernel `quanlam/mare-phase01-trial-captions`, first 20 shots of each
video, one call per shot, middle keyframe resized to 768 px, transformers
`generate`, batch size 1, fp16):

| Model | Constrained JSON | Valid JSON | s/shot | GPU peak |
| --- | --- | --- | --- | --- |
| Qwen3-VL-4B-Instruct | xgrammar | 40/40 | 7.7 | 9.1 GB |
| Qwen3-VL-4B-Instruct | prompt only | 38/40 | 7.8 | 9.1 GB |
| Qwen3-VL-2B-Instruct | xgrammar | 40/40 | 7.6 | 4.4 GB |
| Qwen3-VL-2B-Instruct, batch 8 | xgrammar | 40/40 | 3.4 | 5.5 GB |
| Qwen3-VL-4B-Instruct, batch 8 | xgrammar | 40/40 | 3.7 | 10.8 GB |

Both models describe people, clothing, objects, and actions in more detail than
the 2026-08-27 Vintern captions; 4B also fills `visible_text` (for example
"THE SAIGON INTERNATIONAL UNIVERSITY"). Batch-1 generation took about 13
GPU-minutes per 100 shots; batch 8 reduces it to about 6. Remaining options:
one worker per T4 (two per Kaggle session) and vLLM structured outputs.

Adaptive keyframes (local CPU run of `system1.keyframes.adaptive` with
2026-08-27 shots, interval 2 s, min change 0.15, drift 0.35, max sub-shot
12 s): `L30_V030` 107 keyframes in 84 sub-shots (old pipeline 195);
`L25_V085` 333 keyframes in 315 sub-shots (old 365), one shot with no usable
frame. Decode time 10 s and 64 s.

Observations:

- SigLIP2 accepts Vietnamese queries with a small gap to English; BEiT3
  (English-only text) is not needed for language reasons.
- Caption text search scored higher than image search on these queries, which
  supports keeping captions, subject to the caption trial cost.

## Decisions

- 2026-10-25: Kaggle is the runtime for trials and batch runs.
- 2026-10-25: Models fixed in ADR 0023: SigLIP2 so400m, multilingual-e5-large,
  ChunkFormer-large-vie, EasyOCR detection + VietOCR (chosen by the user over
  PaddleOCR detection and Qwen-only OCR), Qwen3-VL-4B constrained captions.
- 2026-10-25: Documentation is updated per stage during implementation; only
  plans, ADRs, and status notes change before implementation.
- 2026-10-26: Captions are a separate pass over worker packages, not a worker
  stage (ADR 0025). Reason: 63% of worker time, one batch did not fit a Kaggle
  session, and captions cannot be thinned because every shot is a distinct run
  of frames.
- 2026-10-26: The runtime release is published to the Hugging Face Storage
  Bucket `1thesudden/aiou-app-storage` under `releases/{release_id}/`, with
  keyframes re-encoded to WebP quality 80 at release time (ADR 0025). Worker
  packages keep JPEG quality 90, so model inputs do not change.
- 2026-10-26: Scenes return as a deterministic grouping of consecutive shots
  from SigLIP, caption, ASR, and OCR evidence, with a text-only summary per
  multi-shot scene (ADR 0026). Every shot keeps its own caption; the user's
  example is one scene (a woman weaving a basket) made of two shots from
  different angles.

## Validation

- Focused proof: behavior tests per stage (Step 4).
- Integration proof: one Kaggle run from Phase00 restore to validated release
  for 5 to 10 videos.
- Repository-required checks: `cd system1 && uv run pytest -q` with no new
  failures beyond the known list in `AGENTS.md`.

## Result

Complete after implementation.
