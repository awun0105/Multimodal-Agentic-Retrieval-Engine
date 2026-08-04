# Agent Instructions

Project-specific instructions for agents working in this repository.

Repository map:

- `system1/` is the data factory, preprocessing pipeline, and dataset release builder.
- `system2/backend/` is the runtime retrieval backend scaffold.
- `system2/frontend/` is the runtime retrieval UI scaffold.
- `docs/` is the canonical documentation surface; `docs/archived/` is historical only.

<!-- HARNESS:BEGIN -->
## Harness

Start with the requested outcome, then use the repository as the system of
record. Read `docs/WORKFLOW.md` and only relevant product, design, plan, code,
and validation material.

- Answers, explanations, reviews, diagnoses, plans, and status reports are
  read-only. Inspect only what is needed and do not mutate repository or Harness
  state.
- For a bounded change, use an ephemeral plan: inspect the affected behavior and
  proof, implement, and validate. No control-plane operation is required.
- Create or update one file under `docs/plans/active/` when work spans sessions,
  needs coordination, has meaningful dependencies, or requires recovery steps.
  Move it to `docs/plans/completed/` only after validation.
- Before editing, identify repository authority for each new externally
  observable policy. If materially different choices remain open, stop before
  edits; configurable defaults are not authority.
- Report reusable agent friction. Change guidance, tools, runbooks, or validation
  for that purpose only when explicitly asked to use `$improve-harness`.
- Also pause when product intent remains ambiguous, recovery is difficult,
  validation is weakened, or authority is insufficient.
- Claim completion only with relevant executable or observable evidence. Report
  the outcome, important changes, validation, and unresolved risks.

This repository uses Markdown plans, decisions, stories, validation documents,
code, tests, and Git history as durable state. The legacy SQLite Harness control
plane has been retired; do not recreate it unless a user explicitly requests a
separate compatibility migration.
<!-- HARNESS:END -->
