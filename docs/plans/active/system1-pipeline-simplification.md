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
- Decisions: ADR 0021 (no scene grouping), ADR 0022 (content-adaptive
  keyframes), ADR 0023 (model stack), ADR 0024 (validation policy). ADR 0015
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
  - [ ] Embedding, ASR, OCR, and caption providers.
  - [ ] Per-video worker wiring, packaging validator, release step.
- [ ] Step 6: End-to-end run and cleanup.

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
punctuation. Decode time: 17 s for `L30_V030`, 129 s for `L25_V085`.
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

## Validation

- Focused proof: behavior tests per stage (Step 4).
- Integration proof: one Kaggle run from Phase00 restore to validated release
  for 5 to 10 videos.
- Repository-required checks: `cd system1 && uv run pytest -q
  --ignore=tests/test_phase01_vlm_client.py` with no new failures beyond the
  known list in `AGENTS.md`.

## Result

Complete after implementation.
