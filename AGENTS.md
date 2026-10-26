# Agent Instructions

Entrypoint for every coding agent in the Multimodal Agentic Retrieval Engine
(MARE), a multimedia retrieval system for the HCMC AI Challenge 2026.

## Always-On Rules

Read and follow both files on every task:

@docs/agents/GUIDE.md
@docs/agents/plain-prose.md

- `docs/agents/GUIDE.md`: coding rules, project boundaries, pre-flight gates,
  and the handoff report.
- `docs/agents/plain-prose.md`: how to write replies, docs, comments, and
  commit messages.

Hard rules:

1. Do only the requested outcome. Review, diagnosis, and questions change
   nothing.
2. Do not commit, push, open PRs, switch branches, or run destructive Git
   commands unless the user asks.
3. Do not rename, move, or delete files outside the task without permission.
4. Do not claim done or passing without executed evidence.
5. When sources conflict, stop, state the conflict, and ask.

## Repository Map

| Path | Content | State |
| --- | --- | --- |
| `system1/src/system1/` | Data factory package: ingest, Phase00/01/02, artifacts, release, validation | active |
| `system1/notebooks/` | Colab/Kaggle drivers that call the package | active |
| `system1/configs/`, `system1/schemas/`, `system1/prompts/` | Pipeline config, JSON schemas, model prompts | active |
| `mvp-app/` | Gradio retrieval app used for the preliminary round | active |
| `system2/backend/`, `system2/frontend/` | Runtime FastAPI + React/Vite app | scaffold only |
| `deploy/kaggle/` | Kaggle deployment notes | reference |
| `docs/` | Project documentation; map in `docs/README.md` | active |

## Authority Map

| Question | Authoritative source |
| --- | --- |
| Product scope, competition rules, acceptance | `docs/product/requirements-truth-set.md`, `docs/product/rules-2026.md`, `docs/product/acceptance-criteria.md`, `docs/product/official/` |
| What is implemented and verified | `docs/product/current-state.md`, `docs/validation/test-matrix.md` |
| IDs, schemas, artifact and storage layout | `docs/architecture/data-contracts.md`, `system1/schemas/` |
| System 1 pipeline behavior | `docs/architecture/system1-target.md`, ADRs 0021 to 0024, and `docs/plans/active/system1-pipeline-simplification.md` first; other `docs/architecture/system1-*.md` are partly outdated until the plan completes |
| System 2 runtime, API, UI | `docs/architecture/system2-retrieval.md`, `docs/product/api-contracts.md`, `docs/product/ui-implementation.md` |
| Lasting decisions | `docs/decisions/` |
| Work in progress | `docs/plans/active/` |
| Known doc/code drift | `docs/validation/doc-conflicts.md` |
| How to install and run | `system1/README.md`, `mvp-app/README.md` |
| Current executable behavior | code, tests, and runtime evidence |

## Verification

Run the tests for each component you change:

```bash
# system1 (base install; worker and release extras are not needed for tests)
cd system1 && uv run pytest -q
cd system1 && uv run pytest -q tests/<test_file>.py   # focused

# mvp-app (installs torch and model dependencies on first setup)
cd mvp-app && make setup && uv pip install --python .venv/bin/python -r requirements-dev.txt
cd mvp-app && .venv/bin/python -m pytest -q
```

Known failures on the base install (2026-10-26): none. Report new failures
separately.

No linter is configured for the repository yet. Do not reformat existing code.

<!-- HARNESS:BEGIN -->
## Harness

Start with the requested outcome and use the repository as the system of record.
Read `docs/WORKFLOW.md` and only relevant product, design, plan, code, and
validation material.

- Answers, explanations, reviews, diagnoses, plans, and status reports are
  read-only. Inspect only what is needed; change nothing.
- For a bounded change, inspect affected behavior and proof, implement, and
  validate. No control-plane operation is required.
- Use one `docs/plans/active/` file when work spans sessions, coordinates
  contributors, has dependencies, or needs recovery. Move it to
  `docs/plans/completed/` only after validation.
- Before editing, identify repository authority for each new externally
  observable policy. If materially different choices remain open, stop before
  edits; configurable defaults are not authority.
- For architecture, reliability, security, or quality invariant work, read
  `docs/patterns/encoding-invariants.md` and enforce only accepted rules.
- Report reusable agent friction. Change guidance, tools, runbooks, or validation
  for that purpose only when explicitly asked to use `$improve-harness`.
- Also pause when product intent remains ambiguous, recovery is difficult,
  validation is weakened, or authority is insufficient.
- Claim completion only with executable or observable evidence. Report outcome,
  changes, validation, and unresolved risks.

Harness has no task database or orchestration lifecycle. Use repository plans
and behavior-level proof; do not create parallel control-plane state.
<!-- HARNESS:END -->
