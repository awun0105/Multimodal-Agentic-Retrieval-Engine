# Coding Guide

Coding rules for agents changing this repository. `docs/WORKFLOW.md` decides
the work shape (read-only, bounded, planned) and when to stop for a decision.
This guide decides how code is written, checked, and reported.

## 1. Think before coding

State your assumptions. If a request has more than one reading, list them; do
not pick silently. Ask only when the answer changes what gets built and the
code, docs, and decisions do not settle it. Otherwise take the most reasonable
reading, state it, and continue.

## 2. Simplicity first

Write the minimum code that solves the problem. No speculative features,
single-use abstractions, unrequested configuration, or handling for impossible
cases. Never cut input validation, data-loss handling, or secret hygiene.

## 3. Surgical changes

Touch only what the request needs. Do not reformat, rename, or refactor nearby
code. Mention unrelated dead code instead of deleting it. Remove only what your
own change orphaned. Every changed line traces to the request.

## 4. Goal-driven execution

Turn each task into a verifiable goal: "fix the bug" becomes "a test reproduces
it, then passes". For multi-step work, state a short plan with one check per
step and loop until each check holds.

## 5. Read before you write

Before editing a file, read its public functions, its direct callers, and the
shared helpers it already uses. If the structure looks wrong, find out why
(callers, `git log -p`, the owning decision) before changing it.

## 6. Match the codebase

Follow the nearby pattern even if you would do it differently. If two patterns
conflict, follow the newer, better-tested one, say why, and flag the other.
If a convention looks harmful, raise it; do not fork it silently.

## 7. Tests verify intent

Each test protects a behavior someone depends on. A good test fails when that
behavior changes. Prefer the existing test file for the module over a new one.

## 8. Fail loud

If you cannot be sure something worked, say so. "Tests pass" is false if any
were skipped or not run. "Feature works" is false if the requested case was not
exercised.

## 9. Navigate with the code index first

When `.codegraph/` exists, use `codegraph_explore` (or `codegraph explore`)
before grep to read symbols, callers, and blast radius. When
`graphify-out/graph.json` exists, use `graphify query` for cross-file and
architecture questions. Use grep for strings, configs, YAML, JSON, Markdown,
and notebooks. If an index is missing or stale, say so once and continue with
search. After code changes, refresh with `codegraph sync .` and
`graphify update .` when those indexes exist.

## 10. Project boundaries

- **Package owns logic; notebooks drive it.** Notebooks in
  `system1/notebooks/` call package code in `system1/src/system1/`. Do not put
  pipeline logic, validation, IDs, or config values in notebook cells.
- **Contracts before code.** IDs, schemas, and artifact layouts follow
  `docs/architecture/data-contracts.md` and `system1/schemas/`. A change to a
  contract updates the doc, the schema, and the validating test together.
- **Never fabricate data.** Missing organizer metadata stays `null` or empty as
  the contract says. Do not invent values, captions, or evidence to make a
  pipeline pass.
- **Secrets stay out of the repository.** Tokens come from the environment,
  Colab Secrets, or Kaggle Secrets. Never print, log, commit, or persist them.
- **Generated data stays out of Git.** Do not commit videos, keyframes,
  indexes, databases, model weights, or `system1/output/`. Follow `.gitignore`.
- **Expensive runs need consent.** Do not start GPU jobs, model downloads,
  Hugging Face uploads, or full dataset runs unless the user asked for them.

## 11. Pre-flight gates

A task that changes code ends its summary with the gate report below. No code
change, no report. A gate that cannot run is reported as
`UNVERIFIED: <gate> - <reason>`, never skipped silently and never reported as
passing.

A small change (a few lines, no shared symbol, such as a typo or a log message)
needs one line: `Pre-flight: small change - <what you verified>`.

**Before coding**

1. **Read**: what you read with the code index or by hand (Rule 9).
2. **Impact**: callers of every shared symbol you change, or "no external
   callers".
3. **Minimal code**: stop at the first rung that holds: (1) does it need to
   exist? (2) is it already in this repository? (3) standard library? (4) an
   installed dependency? (5) only then, new code.

**After coding**

4. **Checks**: run the tests for each component you touched (see
   `AGENTS.md`, Verification). Report new failures you caused. Note existing
   failures; do not fix them unless asked.
5. **Runtime**: required when notebook, GPU, model, or Hugging Face behavior
   changes. State what ran and what was observed, or
   `UNVERIFIED: runtime - <reason>`.

**Gate report**

```text
Pre-flight (docs/agents/GUIDE.md Rule 11)
- read:         <files/symbols read>
- impact:       <affected callers, or "no external callers">
- minimal-code: <rung, e.g. "rung 2 - reused system1.artifacts.package">
- checks:       <command> -> <N passed / N failed>
- runtime:      <what ran and was observed | UNVERIFIED: reason | n/a>
```

## 12. Handoff report

End every task that changed files with:

1. **Outcome**: the result, or the blocker.
2. **Changed files**: files actually modified.
3. **Verification**: commands run and their real output.
4. **Open items**: risks, unverified parts, and decisions the user must make.
5. **Gate report**: when code changed (Rule 11).
