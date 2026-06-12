# Scripts

This directory contains harness automation tools.

## Harness CLI

The Rust Harness CLI is the primary interface for the durable layer. Installed
projects use the prebuilt binary at `scripts/bin/harness-cli` on macOS/Linux or
`scripts/bin/harness-cli.exe` on Windows for normal Harness work.

```bash
scripts/bin/harness-cli init          # Create the database
scripts/bin/harness-cli bootstrap     # Initialize, migrate, import brownfield markdown, and print stats
scripts/bin/harness-cli intake ...    # Record a feature intake classification
scripts/bin/harness-cli story ...     # Add or update a story (test matrix row)
scripts/bin/harness-cli story update --id US-001 --unit 1 --integration 1 --e2e 0 --platform 0
scripts/bin/harness-cli story verify US-001  # Run the story's verify_command
scripts/bin/harness-cli story verify-all     # Run all configured story verify commands
scripts/bin/harness-cli decision ...  # Add a decision or run its verification
scripts/bin/harness-cli backlog ...   # Add or close a backlog item
scripts/bin/harness-cli tool ...      # Register or remove external project tools
scripts/bin/harness-cli intervention ... # Record human, review, CI, or agent interventions
scripts/bin/harness-cli trace ...     # Record and auto-score an agent execution trace
scripts/bin/harness-cli score-trace   # Score a trace against TRACE_SPEC.md tiers
scripts/bin/harness-cli score-context <trace-id> # Score trace reads against context rules
scripts/bin/harness-cli audit         # Run drift checks and entropy scoring
scripts/bin/harness-cli propose       # Generate improvement proposals
scripts/bin/harness-cli query ...     # Query harness data, including backlog --open/--closed
scripts/bin/harness-cli query matrix --numeric  # Show proof flags as 1/0
scripts/bin/harness-cli migrate       # Apply pending schema migrations
scripts/bin/harness-cli --version     # Print the installed CLI version
```

Run `scripts/bin/harness-cli help` or `scripts/bin/harness-cli query help` for
full usage. On Windows, use the same commands through
`.\scripts\bin\harness-cli.exe`.

Proof flags on `story update` are numeric booleans: use `1` for yes and `0` for
no. `story verify <id>` runs the configured `verify_command`; it does not accept
proof flags. Configure the command with `story add/update --verify`, run
`story verify <id>`, then update proof flags with `story update`.

Backlog `--risk` uses Harness lanes, not severity words: use `tiny`, `normal`,
or `high-risk`. Use `tiny` instead of `low`. `query matrix` defaults to
human-readable `yes`/`no`; use `query matrix --numeric` when copying values into
`story update`.

The schema lives in `scripts/schema/` and is version-controlled. The database
file (`harness.db`) is `.gitignore`d.

Requires: the prebuilt Rust CLI at `scripts/bin/harness-cli` on macOS/Linux or
`scripts/bin/harness-cli.exe` on Windows.

Direct database inspection may still use SQLite tools, but normal Harness use
should go through the Rust CLI.

### Rust CLI Commands

Current migrated commands:

```bash
scripts/bin/harness-cli init
scripts/bin/harness-cli bootstrap
scripts/bin/harness-cli migrate
scripts/bin/harness-cli import brownfield
scripts/bin/harness-cli template list
scripts/bin/harness-cli scaffold source_inventory
scripts/bin/harness-cli scaffold product_domain --output docs/product/tasks.md
scripts/bin/harness-cli intake ...
scripts/bin/harness-cli story add ...
scripts/bin/harness-cli story update ...
scripts/bin/harness-cli story verify ...
scripts/bin/harness-cli story verify-all
scripts/bin/harness-cli decision add ...
scripts/bin/harness-cli decision verify ...
scripts/bin/harness-cli backlog add ...
scripts/bin/harness-cli backlog close ...
scripts/bin/harness-cli tool register ...
scripts/bin/harness-cli tool remove ...
scripts/bin/harness-cli intervention add ...
scripts/bin/harness-cli trace ...
scripts/bin/harness-cli score-trace
scripts/bin/harness-cli score-context ...
scripts/bin/harness-cli audit
scripts/bin/harness-cli propose
scripts/bin/harness-cli query matrix
scripts/bin/harness-cli query backlog
scripts/bin/harness-cli query decisions
scripts/bin/harness-cli query intakes
scripts/bin/harness-cli query traces
scripts/bin/harness-cli query friction
scripts/bin/harness-cli query tools
scripts/bin/harness-cli query interventions
scripts/bin/harness-cli query stats
scripts/bin/harness-cli query sql ...
```

`scripts/bin/harness-cli import brownfield` seeds or refreshes the durable database
from existing Harness v0 markdown in `docs/validation/test-matrix.md`,
`docs/decisions/`, and `docs/harness/HARNESS_BACKLOG.md`. This keeps already-installed
Harness repos on the Rust CLI path without losing their populated operating
docs.

`scripts/bin/harness-cli bootstrap` is the recommended post-install helper for
existing repositories. It runs `init`, `migrate`, `import brownfield`, and then
prints `query stats` so the durable layer is ready immediately after installation.

`scripts/bin/harness-cli template list` reads
`docs/harness/templates/manifest.yml` and shows the registered documentation
templates. `scripts/bin/harness-cli scaffold <template-id>` copies a registered
template to its default output path. Pass `--output <path>` for pattern-based
templates such as `product_domain`, and pass `--force` only when overwriting is
intentional. Scaffolded files are blank structure; agents and humans must fill
them from spec, code, tests, existing docs, or explicit human input.

## Installer

The installer applies Project Harness files and folder structure to a target
project directory. It defaults to the current directory,
accepts a target path, and asks interactive users whether to `1. Merge`,
`2. Override`, or `3. Stop` when the target already contains `AGENTS.md`,
`docs/`, or `scripts/`.
Non-interactive installs stop on those protected paths unless `--merge` or
`--override` is provided. Use `--merge` as the safe update path for repositories
that already have Harness: it keeps existing files in place and creates only
missing Harness files. Add `--refresh-agent-shim` when an older install has the
full generated Harness guide in `AGENTS.md` and should move to the small stable
shim. Use `--override` to back up and replace the entire `AGENTS.md`, `docs/`, and
`scripts/` surface into a timestamped backup directory. Use `--force` to perform
file-level backups and overwrites for specific manifest files.

Choose an installation layout:

| Layout | Use when | Installs |
| --- | --- | --- |
| `project` | New repos or repos intentionally adopting the full shared source-of-truth structure | Full docs map, product/requirements/architecture/planning/onboarding/stories/decisions/validation/harness areas |
| `harness-only` | Existing repos whose current docs must not be polluted before baseline audit | `AGENTS.md`, `docs/README.md`, `docs/harness/`, templates, `docs/validation/`, scripts, and `.gitignore` rules |

`project` is the default. Use `harness-only` with `--merge` for most existing
codebases, then run `docs/harness/ONBOARDING_EXISTING_PROJECT.md` as the first
task.

```bash
curl -fsSL "https://raw.githubusercontent.com/awun0105/repository-harness/refs/heads/custom/project-harness/scripts/install-harness.sh?$(date +%s)" | bash -s -- --yes
```

```powershell
& ([scriptblock]::Create((irm "https://raw.githubusercontent.com/awun0105/repository-harness/refs/heads/custom/project-harness/scripts/install-harness.ps1"))) -Yes
```

```bash
curl -fsSL "https://raw.githubusercontent.com/awun0105/repository-harness/refs/heads/custom/project-harness/scripts/install-harness.sh?$(date +%s)" | bash -s -- --merge --yes
```

```powershell
& ([scriptblock]::Create((irm "https://raw.githubusercontent.com/awun0105/repository-harness/refs/heads/custom/project-harness/scripts/install-harness.ps1"))) -Merge -Yes
```

```bash
curl -fsSL "https://raw.githubusercontent.com/awun0105/repository-harness/refs/heads/custom/project-harness/scripts/install-harness.sh?$(date +%s)" | bash -s -- --layout harness-only --merge --yes
```

```powershell
& ([scriptblock]::Create((irm "https://raw.githubusercontent.com/awun0105/repository-harness/refs/heads/custom/project-harness/scripts/install-harness.ps1"))) -Layout harness-only -Merge -Yes
```

```bash
curl -fsSL "https://raw.githubusercontent.com/awun0105/repository-harness/refs/heads/custom/project-harness/scripts/install-harness.sh?$(date +%s)" | bash -s -- --merge --refresh-agent-shim --yes
```

```powershell
& ([scriptblock]::Create((irm "https://raw.githubusercontent.com/awun0105/repository-harness/refs/heads/custom/project-harness/scripts/install-harness.ps1"))) -Merge -RefreshAgentShim -Yes
```

`--refresh-agent-shim` backs up `AGENTS.md` before changing it. If the existing
file is recognized as the old Harness-generated operating guide, the installer
replaces it with the current shim. Otherwise it appends or replaces only the
marked `<!-- HARNESS:BEGIN -->` block so project-specific instructions remain
in place.

The installer must stay limited to harness files. Do not use it to scaffold
application source folders, package scripts, CI, tests, platform shells, or fake
validation commands. The installer script is not part of the installed project
payload.

By default the installer also downloads the prebuilt Rust Harness CLI for the
current platform into `scripts/bin/harness-cli` on macOS/Linux or
`scripts/bin/harness-cli.exe` on Windows, verifies its `.sha256` checksum, and
automatically runs `harness-cli init` and `harness-cli migrate` to prepare `harness.db`.
A source branch can pin the release used by the installer through
`scripts/harness-cli-release-tag`; this fork currently pins the published
Project Harness CLI release for branch installs. Set `HARNESS_CLI_RELEASE_TAG`
to override that tag, or set `HARNESS_CLI_BASE_URL` to point at an alternate
artifact directory, such as a local `file:///.../dist` directory created by
`scripts/build-harness-cli-release.sh`.

This fork installs Project Harness source files and CLI release assets from
`awun0105/repository-harness`. Override `HARNESS_CLI_BASE_URL` when testing
locally built CLI assets before publishing a release.

## Schema Migrations

Migration files live under `scripts/schema/` and are named `NNN-description.sql`
where `NNN` is a zero-padded version number. Run `scripts/bin/harness-cli migrate` to
apply pending migrations.

## Future Command Contract

Expected future checks:

```text
validate:quick
  format, lint, typecheck, unit tests, architecture check

test:integration
  backend contract and integration checks

test:e2e
  user-visible end-to-end flows

test:platform
  platform shell smoke checks, if the project has a native shell

test:release
  full suite, log checks, and performance smoke
```

## Release Packaging

Build the current-platform Rust CLI release artifact from the source repo:

```bash
scripts/build-harness-cli-release.sh
```

The script writes `dist/harness-cli-<platform>` plus `.sha256` checksums. The
Windows artifact includes the `.exe` suffix. Supported labels are:

- `macos-arm64`
- `macos-x64`
- `linux-x64`
- `linux-arm64`
- `windows-x64`

For cross-compilation, pass a Cargo target triple:

```bash
scripts/build-harness-cli-release.sh --target x86_64-unknown-linux-gnu
```

GitHub releases are produced by
`.github/workflows/harness-cli-release.yml`. Push a tag matching `v*` or
`harness-cli-v*` to run the verification job, build all supported targets on
native hosted runners, and upload these release assets:

- `harness-cli-macos-arm64`
- `harness-cli-macos-arm64.sha256`
- `harness-cli-macos-x64`
- `harness-cli-macos-x64.sha256`
- `harness-cli-linux-x64`
- `harness-cli-linux-x64.sha256`
- `harness-cli-linux-arm64`
- `harness-cli-linux-arm64.sha256`
- `harness-cli-windows-x64.exe`
- `harness-cli-windows-x64.exe.sha256`
