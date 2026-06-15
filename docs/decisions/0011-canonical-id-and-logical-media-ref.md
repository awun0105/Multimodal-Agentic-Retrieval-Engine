# ADR 0011: Canonical IDs And Logical Media Refs

## Status

Accepted

## Context

Older source material mixed `legacy video-name field` and `video_id`, used inconsistent keyframe identifiers, and sometimes implied physical repo paths for runtime media.

## Decision

Use `video_id` as the canonical DB/API identifier. Use `frame_id` as the canonical frame number. Use `keyframe_id = "{video_id}:{frame_id}"` as the canonical join key.

Persist logical media refs only; backend resolves them through `MediaStorePort`.

Canonical runtime refs:

- `video_ref`: canonical logical ref for the raw/source video, for example `raw_videos/{video_id}.mp4`.
- `keyframe_ref`: canonical logical ref for generated keyframe images, for example `keyframes/{video_id}/{video_id}_f{frame_id:07d}.jpg`.
- `thumbnail_ref`: canonical logical ref for generated thumbnails, for example `thumbnails/{video_id}/{video_id}_f{frame_id:07d}.webp`.

`media_ref` is only a generic adapter concept for tables or interfaces that need one abstract media column. It is not the preferred runtime column when the media type is known.

## Alternatives Considered

- Keep underscore-based keyframe IDs.
- Persist absolute filesystem paths in SQLite.
- Continue using `legacy video-name field` as canonical API vocabulary.

## Consequences

- API payloads and docs must use `video_id`, `frame_id`, and `keyframe_id` consistently.
- Runtime tables should prefer `video_ref`, `keyframe_ref`, and `thumbnail_ref` over generic `media_ref` fields.
- SQLite must not contain absolute machine-specific media paths.
- Media storage backend can change without changing UI or retrieval contracts.
