# Execution Plan: Remove System 1 Execution Modes

Date: 2026-08-13

## Status

Completed

## Outcome

System 1 exposes one workflow instead of legacy execution-quality tiers.
Package APIs, CLI commands, notebooks, tests, configuration, and current
documentation no longer depend on an execution-mode selector.

## Context

- `docs/architecture/system1-notebook01-production-pipeline.md` defines one
  production pipeline and keeps mocks only for tests and development.
- `docs/onboarding/throughput-plan.md` already says the legacy quality modes are
  not part of the production notebook contract.
- `system1/src/system1/commands/` still requires `--mode`, and mode values still
  affect reports and capability status in feature and release builders.

## Scope

In scope:

- Remove execution-mode CLI options and Python parameters from System 1.
- Replace mode-dependent status logic with provider/output-derived status.
- Remove mode fields from current generated manifests and reports where they
  represent the retired selector.
- Update Notebook 00A/00B/00C and downstream notebooks that would otherwise call
  removed CLI options.
- Update tests, active configuration, README, current design, onboarding, plan,
  and validation documentation.

Out of scope:

- Unrelated uses such as SQLite `journal_mode`, file open modes, archive source
  modes, and research CLI selection between OCR and ASR.
- Implementing the unfinished production TransNet, faster-whisper, or Gemini
  providers.

## Approach

1. Inventory execution-mode inputs, propagation, status branches, tests, and
   notebook calls.
2. Remove the selector from CLI and package APIs, then derive capability status
   only from provider availability and actual errors.
3. Update notebooks/configuration and rewrite current documentation around a
   single workflow.
4. Update tests and run focused plus complete System 1 validation.

## Risks And Recovery

- Removing a positional/keyword parameter can break direct callers; search all
  code and tests and prove public CLI help no longer advertises `--mode`.
- Existing checkpoints may contain a historical `mode` field. Readers must not
  require it; old artifacts remain readable while new artifacts stop writing it.
- Mode-dependent mock status could be accidentally upgraded to `pass`; status
  will instead remain derived from the selected provider and adapter
  availability.
- Recovery is a normal Git revert of this coherent change set; existing raw and
  release datasets are not modified.

## Progress

- [x] Inventory mode-dependent code, notebooks, tests, and documentation.
- [x] Refactor package and CLI to one workflow.
- [x] Update notebooks, configuration, and documentation.
- [x] Update and run tests.
- [x] Record validation and move this plan to completed.

## Decisions

- 2026-08-13: Remove the selector entirely instead of renaming it to
  `production_full`; provider selection remains explicit and test mocks remain
  available without implying a quality tier.
- 2026-08-13: Do not rewrite historical artifacts or unrelated meanings of the
  word `mode`.
- 2026-08-13: Provider selection is named `providers`/provider profile rather
  than another workflow mode. Mock and unavailable adapters remain degraded.
- 2026-08-13: New manifests omit the retired selector. Existing artifacts with
  the old extra field remain readable because consumers do not require or reject
  that field.

## Validation

- Focused proof: 94 CLI, notebook, checkpoint, and runtime tests passed.
- Integration or end-to-end proof: mock single-workflow release path passed as
  part of the complete suite.
- Repository-required checks: 188 tests passed; compileall passed; notebook JSON
  and Python syntax passed; all affected CLI help omitted the retired selector;
  Ruff `E9,F` passed; `git diff --check` passed.
- Existing limitation: the repository-wide default Ruff rule set reports 141
  pre-existing style findings outside this refactor's completion standard.

## Result

System 1 now has one workflow across package APIs, CLI commands, active configs,
Notebook 00A/00B/00C and downstream notebooks, tests, README, and current design
documentation. Capability status no longer changes according to a quality-tier
label: mock or unavailable providers remain degraded, enrichment uses provider
and availability evidence, and per-video reuse remains honestly degraded until
implemented. Old commands that still pass the removed selector must be updated;
old artifact JSON with the unused field remains readable.
