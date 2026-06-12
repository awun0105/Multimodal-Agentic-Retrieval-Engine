# 0007 Keyframe-first Workflow

Date: 2026-06-12

## Status

Accepted

## Context

Search speed, RAM protection, and fast evidence inspection matter more than
full-video playback during active competition use.

## Decision

Use a keyframe-first workflow.

## Alternatives Considered

1. Video-first result browsing.
2. Auto-loading preview/video on result click.
3. Dense-frame-first ingestion and UI by default.

## Consequences

Positive:

- Optimizes scanning speed and resource usage.
- Matches the competition workbench model.
- Keeps raw video playback secondary and optional.

Tradeoffs:

- Some edge cases may still require manual video inspection.
- Ingestion must produce strong keyframe/thumbnails contracts.

## Follow-Up

- Keep lazy loading and virtualized grids in MVP-2.
- Keep same-video nearby keyframe browsing in the UI baseline.
