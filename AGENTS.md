# Agent Instructions

Project-specific instructions for agents working in this repository.

<!-- HARNESS:BEGIN -->

## Harness

This repo uses Harness. Before work, read the stable entrypoints:

* This `AGENTS.md`
* `docs/harness/FEATURE_INTAKE.md`
* `docs/harness/CONTEXT_RULES.md`
* `scripts/bin/harness-cli query matrix` on macOS/Linux, or `.\scripts\bin\harness-cli.exe query matrix` on Windows

Repository layout:

* `system1/` is the data factory / preprocessing / dataset release builder.
* `system2/backend/` is the runtime retrieval backend.
* `system2/frontend/` is the runtime retrieval UI.
* `docs/` is canonical documentation.
* `docs/archived/` is historical reference only.
* `scripts/` is for repo-level utilities and Harness scripts.

After reading the stable entrypoints, use `docs/harness/CONTEXT_RULES.md` to decide which additional files to read by task phase, risk lane, and retrieval trigger. Do not bulk-read unrelated documentation when the lane, affected files, and validation path are already clear.

Before creating, normalizing, or syncing documentation, also read:

* `docs/harness/TEMPLATE_REGISTRY.md`

Use registered templates from `docs/harness/templates/`. Do not invent a documentation format when a registered template exists. Do not overwrite existing project docs during onboarding without a doc sync plan.

Use the Rust Harness CLI at `scripts/bin/harness-cli` on macOS/Linux or `scripts/bin/harness-cli.exe` on Windows as the main operational tool. If the CLI binary is unavailable in a checkout, read `docs/validation/test-matrix.md` directly and state that the durable matrix could not be queried.

If a Harness command fails, report the exact error. Do not invent results or bypass Harness with generic commands unless the user explicitly approves.

## Evidence Discipline

Do not claim that related files, docs, tests, validation files, or durable records were checked unless they were actually inspected or queried.

When reporting consistency closure, distinguish between:

* Checked and clean
* Checked and updated
* Checked and drift remains
* Not checked because unavailable
* Not applicable, with reason

Never mark something as “not applicable” without stating why.

Do not decide that a change is “small” or “isolated” without evidence. Every change starts with unknown related-file impact until checked.

If related impact cannot be confidently ruled out, treat the change as substantive and run the full consistency closure.

## Consistency Closure

For every change, assume related-file impact is unknown until checked. Do not stop at the requested file after implementation.

After implementation and required validation:

1. List changed files.
2. Classify the change impact with evidence across:

   * source code
   * tests
   * configs
   * docs
   * validation files
   * stories
   * decisions
   * backlog records
   * durable Harness records
3. Identify related files by checking:

   * imports
   * call sites
   * tests
   * configs
   * docs references
   * validation matrix entries
   * stories
   * decisions
   * backlog/friction records
   * durable Harness records
4. Re-check related files for:

   * code-to-code drift
   * code-to-doc drift
   * doc-to-durable-state drift
   * test-to-behavior drift
   * config-to-doc drift
5. Update affected docs and Harness durable records when required.
6. If creating, normalizing, or syncing documentation, use registered templates from `docs/harness/templates/` and follow `docs/harness/TEMPLATE_REGISTRY.md`.
7. If a code/doc mismatch remains, record it in `docs/onboarding/doc-conflicts.md` or Harness backlog/friction.
8. Record a trace with `scripts/bin/harness-cli trace` on macOS/Linux, or `.\scripts\bin\harness-cli.exe trace` on Windows, for any semantic source, config, docs, validation, or durable-record change. If unsure whether the change is semantic, treat it as semantic.
9. Review the score printed by `scripts/bin/harness-cli trace` when a trace is created. Use `scripts/bin/harness-cli score-trace --id <trace-id>` on macOS/Linux, or `.\scripts\bin\harness-cli.exe score-trace --id <trace-id>` on Windows, when re-checking a specific trace.
10. Run `scripts/bin/harness-cli score-context <trace-id>` on macOS/Linux, or `.\scripts\bin\harness-cli.exe score-context <trace-id>` on Windows, when trace/context scoring is relevant and supported by the current Harness CLI.
11. If trace or scoring commands fail, report the exact error and do not invent results.

The agent may skip full trace/scoring only for purely mechanical edits, such as whitespace-only formatting, typo-only changes in non-normative prose, or generated-file refreshes with no semantic change. When skipping, it must explicitly state why the change has no semantic impact.

## Final Response Requirements

Final response must include:

* Changed files
* Impact classification
* Evidence used to classify impact
* Related files checked
* Docs updated
* Durable records updated
* Trace ID, if created
* Trace/context score results, if run
* Remaining drift
* Any skipped checks and why they were safe to skip

## Detailed Final Report Format

Use `docs/harness/templates/report/report_format.md` only when the user explicitly asks for a detailed report, audit-style report, handoff report, or release-quality report.

For normal task completion, follow the Final Response Requirements above without expanding into the detailed report template unless requested.

<!-- HARNESS:END -->
