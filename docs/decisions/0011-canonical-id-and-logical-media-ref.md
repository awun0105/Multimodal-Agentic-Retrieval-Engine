# ADR 0011: Canonical IDs And Logical Media Refs

## Status

Accepted

## Context

Older source material mixed `legacy video-name field` and `video_id`, used inconsistent keyframe identifiers, and sometimes implied physical repo paths for runtime media.

## Decision

Use `video_id` as the canonical DB/API identifier. Use `frame_id` as the canonical frame number. Use `keyframe_id = "{video_id}:{frame_id}"` as the canonical join key. Persist logical media refs only; backend resolves them through `MediaStorePort`.

## Alternatives Considered

- Keep underscore-based keyframe IDs.
- Persist absolute filesystem paths in SQLite.
- Continue using `legacy video-name field` as canonical API vocabulary.

## Consequences

- API payloads and docs must use `video_id`, `frame_id`, and `keyframe_id` consistently.
- SQLite must not contain absolute machine-specific media paths.
- Media storage backend can change without changing UI or retrieval contracts.
