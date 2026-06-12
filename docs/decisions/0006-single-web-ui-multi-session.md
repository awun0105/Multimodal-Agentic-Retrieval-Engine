# 0006 Single Web UI + Multi-session Workflow

Date: 2026-06-12

## Status

Accepted

## Context

The product is for a competition team. It needs one simple browser interface
without role-heavy complexity, but it must still support multiple teammates over
LAN working independently or together.

## Decision

Adopt this canonical phrase:

Single Web UI + Multi-session Workflow: one shared web app for the whole team,
no roles and no separate dashboards, but multiple teammates can work
independently or collaboratively through Query Sessions.

## Alternatives Considered

1. Separate human UI and agent UI.
2. Role-based dashboards.
3. Single-user only workflow.

## Consequences

Positive:

- Keeps the UI simple and shared.
- Supports independent and collaborative Query Session work.
- Keeps agent results in the same UI/result model.

Tradeoffs:

- Requires careful session-scoped state design.
- Needs clear distinction between lightweight client identity and real auth.

## Follow-Up

- Reflect Query Session scope in backlog and test matrix.
- Keep Candidate Basket and saved state scoped to Query Sessions.
