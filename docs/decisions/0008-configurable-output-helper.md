# 0008 Output Helper Configurable, No Hard-coded Final Submission API

Date: 2026-06-12

## Status

Accepted

## Context

Official 2026 submission details are not confirmed, so export behavior must stay
flexible.

## Decision

Treat submission support as configurable helpers, not a hard-coded final
submission API.

## Alternatives Considered

1. Hard-code prior-year CSV behavior as the final contract.
2. Build around a fixed remote submission API.
3. Delay all output helpers until official rules are published.

## Consequences

Positive:

- Preserves adaptability to official rules.
- Prioritizes fast copy helpers for competition use.
- Keeps export secondary to retrieval quality.

Tradeoffs:

- Some export automation remains deferred.
- Output validation must stay configurable.

## Follow-Up

- Model copy helpers in MVP-7.
- Keep CSV helper optional until needed.
