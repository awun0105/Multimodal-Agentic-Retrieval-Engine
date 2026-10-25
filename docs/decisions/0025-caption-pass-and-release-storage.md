# ADR 0025: Separate Caption Pass And Bucket Release Storage

Date: 2026-10-26

## Status

Accepted

Amends ADR 0023 (captions run in a second pass, not inside the worker) and the
"Hugging Face Layout" and "Runtime Contract" sections of
`docs/architecture/system1-target.md`.

## Context

The first end-to-end Kaggle run of the new worker (`quanlam/mare-worker-batch`,
commit `93c7723`, T4 x2, first 5 videos of `batch_000`) processed 70.3 minutes
of video in 130.7 minutes, about 1.9x video length. For `L21_V014` (18.6 min,
401 shots, 500 keyframes) the stage times were:

| Stage | Seconds | Share |
| --- | --- | --- |
| captions (Qwen3-VL-4B, xgrammar, batch 16, 512 px) | 1358 | 63% |
| OCR (EasyOCR + VietOCR) | 519 | 24% |
| cuts (TransNetV2) | 106 | 5% |
| keyframes | 89 | 4% |
| ASR, image vectors, text vectors, documents | 59 | 3% |

News videos have a cut about every 2.4 seconds, so a shot count near 400 per
20-minute video is normal, not a detection error (only 56 of 1076 cut segments
were shorter than 1 s). Captions cost 3.4 s per shot and cannot be reduced by
captioning fewer shots: by the project definition (ADR 0022, amended) every
shot is a distinct run of frames and needs its own caption.

At this rate one batch of about 73 videos needs over 40 GPU hours, more than a
12-hour Kaggle session, and the full 873 videos need about 500 GPU hours.
Without captions the same batch needs about 12 GPU hours.

The release step has a second problem. The 5-video release holds 1932
keyframes and 1932 thumbnails (410 MB, media 376 MB). Scaled to 873 videos the
release holds roughly 340,000 keyframes and as many thumbnails, about 65 GB of
JPEG at quality 90. A Hugging Face dataset repo is a Git repository and is
recommended to stay under about 100,000 files; per-file commits of that many
small files are slow and rate limited. `mvp-app` already solved the same
problem in the preliminary round by uploading the release to a Hugging Face
Storage Bucket (`mvp-app/tools/upload_release.py`, bucket
`1thesudden/aiou-app-storage`, download with `hf buckets sync`).

## Decision

### 1. Captions move to a second pass

1. The worker (`worker-batch`) runs ASR, cuts, shots and keyframes, image
   vectors, OCR, text documents, and text vectors. It no longer loads the
   caption model. Target: under 10 GPU minutes per video, so one batch fits one
   Kaggle session.
2. A separate caption pass (`caption-batch`) reads finished worker packages
   from `AIOU26_release/{release_id}/worker/artifacts/{batch_id}/`, captions
   one keyframe per shot, and writes `captions.parquet` plus caption and
   `visible_text` text documents and their text vectors into a caption package
   `{release_id}/captions/artifacts/{batch_id}/{video_id}.zip`. The worker
   package is never rewritten.
3. The caption pass runs on as many Kaggle accounts as are available, one
   batch per session, and resumes by skipping videos whose caption package
   exists.
4. `build-release` merges worker packages and, when present, caption packages.
   A release can be built and published before captions finish; the manifest
   records for each video whether captions are included.
5. Caption throughput is the next optimization target. Order: (a) measure
   vLLM with structured outputs on Kaggle T4 (continuous batching, prefix
   caching of the fixed prompt; T4 has no bf16 or FlashAttention 2, and vLLM
   pins its own torch version, so the gain must be measured, not assumed);
   (b) keep transformers `generate` if vLLM does not install or is not faster.

### 2. Release storage

1. Raw videos and frame timelines stay in the dataset repo `AIOU26_raw`
   (write once).
2. Worker packages, caption packages, and batch reports stay in the dataset
   repo `AIOU26_release` (few files, immutable, Git history needed for reruns).
3. The runtime release for System 2 is uploaded to a Hugging Face Storage
   Bucket under `releases/{release_id}/`, not to the dataset repo. Upload order:
   `db/`, `indexes/`, `manifest.json`, then media, then `READY.json` last as
   the completion marker. Upload is batched and resumable, reusing the pattern
   of `mvp-app/tools/upload_release.py`. System 2 downloads with
   `hf buckets sync`.
4. Test runs write to a test prefix of the bucket (`releases_test/`) and to
   `AIOU26_release_test`, never to production paths.

### 3. Media format in the release

1. Workers keep writing keyframes as JPEG quality 90 at the video's native
   long side (1280 for Batch 1). All models read these files, so model inputs
   are unchanged.
2. `build-release` re-encodes keyframes to WebP quality 80, same resolution,
   and keeps thumbnails as WebP 320 px. Measured on one keyframe: 189 KB JPEG
   q90 becomes about 65 KB WebP q80; the full release drops from about 65 GB to
   about 22 GB. This affects display only; vectors and text were computed from
   the JPEG in the worker package.
3. `keyframe_ref` in the release tables therefore ends in `.webp`.
   `docs/architecture/data-contracts.md` changes the release keyframe path to
   `keyframes/{video_id}/{video_id}_f{frame_id:07d}.webp`; the worker package
   keeps `.jpg`.
4. Images are not bundled into tar files: the bucket has no small-file limit,
   and System 2 serves individual images by path.

## Alternatives Considered

1. Caption only one shot per cut segment. Rejected: shots inside one cut
   segment are visually different by definition and each needs a caption.
2. Skip very short shots (under 1 s). Rejected: only about 5% of shots; not
   worth the retrieval gap.
3. Keep captions inside the worker and use vLLM. Deferred: even a 4x gain
   leaves captions as the largest stage, and the full run would still not fit
   one session per batch. The caption pass stays separate regardless.
4. Publish the release into the dataset repo as in the current target doc.
   Rejected: hundreds of thousands of files in a Git repo; `mvp-app` already
   moved to a bucket for this reason.
5. Pack media into one tar per video. Rejected: the bucket does not need it
   and System 2 would have to unpack before serving.
6. Lower JPEG quality in the worker. Rejected: it changes model inputs and
   cannot be undone without rerunning the worker.

## Consequences

Positive:

- One batch fits one Kaggle session; the full worker run needs about 150 GPU
  hours instead of about 500.
- Releases can ship without captions and gain captions later without touching
  worker output.
- Worker output is immutable; every presentation choice (format, quality,
  layout) lives in the cheap release step.
- Release storage drops to about a third.

Tradeoffs:

- Two package types per video and two batch runners to operate.
- `build-release` runs longer: about 340,000 image re-encodes, estimated 1 to
  2 CPU hours for 873 videos (not yet measured).
- The bucket has no version history; each `release_id` is a separate prefix.

## Follow-Up

- Implement under `docs/plans/active/system1-pipeline-simplification.md`,
  Step 5 items 5 to 7.
- Record measured worker time per video without captions, caption-pass time
  per shot with transformers and with vLLM, and release build and upload time.
