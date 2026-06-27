# Exec Plan

## Goal

Make Notebook 00 Drive shadow and archive standardization production-safe for
operator reruns before phase00 ingest.

## Scope

In scope:

- Fail CLI commands on partial Drive/archive errors by default.
- Add explicit opt-in flags for allowing partial results.
- Make archive standardization skip already-existing matching files by default.
- Preserve overwrite behavior when explicitly requested.
- Update Notebook 00 to use the safer defaults.
- Add unit/CLI tests for fail-fast and rerun behavior.
- Update docs and durable Harness records.

Out of scope:

- Live cloud provider execution.
- Provider-specific retries/backoff beyond existing API calls.
- Full release artifact validation beyond existing System 1 tests.

## Risk Classification

Risk flags:

- External systems.
- Existing behavior.
- Weak proof.

Hard gates:

- External provider behavior.

## Work Phases

1. Discovery.
2. Design.
3. Validation planning.
4. Implementation.
5. Verification.
6. Harness update.

## Stop Conditions

Pause for human confirmation if:

- The CLI would delete or overwrite user Drive data.
- Safety requires weakening existing validation.
- The implementation needs real credentials or live cloud mutation to proceed.
