# Existing Project Onboarding

Use this workflow when Project Harness is added to a repository that already has
code, partial docs, tests, scripts, or production behavior.

The goal is to create a truthful baseline. Do not implement new product behavior
during onboarding.

## Rules

- Existing code and tests are evidence, not complete product intent.
- Generated template text is never source of truth.
- Missing docs are not permission to invent behavior.
- Mark uncertainty explicitly.
- If code and docs conflict, record the conflict with evidence.

## Evidence Labels

| Label | Meaning |
| --- | --- |
| confirmed | Found in code, tests, existing docs, or human-provided material |
| partial | Partly implemented, weakly proven, or missing an important path |
| unknown | Not enough evidence to make a claim |
| not implemented | No implementation evidence found. Use `not_implemented` in the durable matrix/CLI status field. |

## Recommended Outputs

- `docs/onboarding/source-inventory.md`
- `docs/onboarding/doc-sync-plan.md`
- `docs/onboarding/baseline-audit.md`
- `docs/onboarding/doc-conflicts.md`
- `docs/product/current-state.md`
- `docs/architecture/overview.md`
- `docs/validation/test-matrix.md`
- `docs/stories/backlog.md`
- Decision records for major existing choices when evidence is clear

## Audit Flow

1. Read `docs/harness/TEMPLATE_REGISTRY.md`.
2. Inventory existing docs, README files, package/build files, source
   entrypoints, routes, schemas, tests, deployment files, and existing docs.
3. Create `docs/onboarding/source-inventory.md` from
   `docs/harness/templates/onboarding/source-inventory.md`.
4. Map existing docs to registered templates.
5. Create `docs/onboarding/doc-sync-plan.md` from
   `docs/harness/templates/onboarding/doc-sync-plan.md`.
6. List confirmed, partial, unknown, and not implemented behavior.
7. Create or update current-state product docs from cited evidence.
8. Create or update architecture docs from code evidence.
9. Update validation expectations with real test/proof evidence.
10. Add backlog items or stories for gaps instead of fixing everything at once.
11. Record decision files only for meaningful choices that are visible or
   human-confirmed.
12. Do not overwrite or archive old docs unless the sync plan explains how
    useful source material is preserved.

## Stop Conditions

Pause for human confirmation when:

- Product intent cannot be inferred from code or docs.
- Auth, authorization, data loss, security, billing, or external providers are
  involved and evidence is incomplete.
- A generated doc conflicts with implemented behavior.
