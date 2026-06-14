# 0008 Submission Helper Configurable, No Hard-coded Final Payload

Date: 2026-06-12

## Status

Accepted

## Context

Official 2026 submission details are not confirmed. Current project requirement expects final-round submission through an organizer API, but endpoint, auth/session mechanism, payload, response semantics, and scoring feedback remain unknown. Submit responsibility is a team process outside the app, not an MVP auth/role feature.

## Decision

Treat submission support as configurable answer-draft, review, history, and provider-adapter helpers, not a hard-coded final organizer payload.

## Alternatives Considered

1. Hard-code prior-year CSV behavior as the final contract.
2. Build around a fixed organizer submission API before official docs exist.
3. Delay all submission helpers until official rules are published.

## Consequences

Positive:

- Preserves adaptability to official rules.
- Supports human review before risky submit attempts.
- Preserves per-question/session submission history for team awareness.
- Keeps submission secondary to retrieval quality while still modeling final-round needs.

Tradeoffs:

- Organizer API integration remains deferred until official details exist.
- Submission validation must stay configurable.

## Follow-Up

- Model answer drafts, edit/review, and submission history in `MVP-8`.
- Keep copy/CSV helpers as optional fallback support until official submission API details exist.
