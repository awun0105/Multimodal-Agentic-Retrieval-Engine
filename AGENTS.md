# Agent Instructions

Add project-specific agent instructions here.

<!-- HARNESS:BEGIN -->
## Harness

This repo uses Harness. Before work, read:

- `README.md`
- `docs/README.md`
- `docs/harness/HARNESS.md`
- `docs/harness/FEATURE_INTAKE.md`
- `docs/architecture/overview.md`
- `docs/harness/CONTEXT_RULES.md`
- `scripts/bin/harness-cli query matrix` on macOS/Linux, or `.\scripts\bin\harness-cli.exe query matrix` on Windows

Before creating, normalizing, or syncing documentation, also read:

- `docs/harness/TEMPLATE_REGISTRY.md`

Use registered templates from `docs/harness/templates/`. Do not invent a
documentation format when a registered template exists. Do not overwrite
existing project docs during onboarding without a doc sync plan.

Use the Rust Harness CLI at `scripts/bin/harness-cli` on macOS/Linux or
`scripts/bin/harness-cli.exe` on Windows as the main operational tool. If the
CLI binary is unavailable in a checkout, read `docs/validation/test-matrix.md`
directly and state that the durable matrix could not be queried.
<!-- HARNESS:END -->
