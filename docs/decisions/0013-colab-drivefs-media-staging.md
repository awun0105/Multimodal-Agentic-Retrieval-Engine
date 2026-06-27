# ADR 0013: Colab DriveFS Media Staging

Date: 2026-06-27

## Status

Accepted

## Context

Google Colab DriveFS/FUSE can be unreliable for large sequential media reads.
Direct `ffprobe` or provider upload reads from `/content/drive` can fail or
leave the runtime fighting DriveFS cache behavior. Hugging Face downloads can
also fill Colab disk if large videos are cached in the global user cache.

## Decision

When `upload-standardized-raw` needs to probe or upload a video whose source is
under `/content/drive`, it stages that video into local runtime temp storage
first. Direct DriveFS probing is reserved for explicit debug use through
`AIC_ALLOW_DRIVEFS_PROBE=1`.

HF canonical ingest continues to avoid raw video downloads by default through
`canonical_video_inventory.parquet`. If the explicit legacy fallback
`AIC_ALLOW_HF_VIDEO_DOWNLOAD_FOR_PROBE=1` is enabled, downloads use per-run
staging/cache directories and cleanup them in `finally` rather than deleting or
depending on the user's global Hugging Face cache.

## Alternatives Considered

1. Probe and upload directly from DriveFS. Rejected because large video reads
   through Colab DriveFS/FUSE are fragile.
2. Delete the global Hugging Face cache after ingest. Rejected because it can
   remove files not owned by the current run.
3. Remove HF video download fallback entirely. Rejected because it remains a
   useful controlled debug path for older raw repos without inventory.

## Consequences

Positive:

- Colab raw upload and inventory generation avoid direct DriveFS media probing.
- HF fallback downloads do not rely on the global Hugging Face cache for large
  videos.
- Temporary staged media is removed after each probe/upload batch or pair.

Tradeoffs:

- DriveFS video upload batches temporarily duplicate one upload batch in local
  runtime storage.
- Operators with very small runtime disks may need to reduce dataset batch size
  or run on a larger Colab runtime.

## Follow-Up

- Consider a future upload batch-size override if DriveFS staging needs finer
  runtime disk control for very large official datasets.
