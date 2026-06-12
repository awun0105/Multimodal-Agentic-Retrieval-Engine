# Template Registry

This registry tells humans and agents which templates to use when creating,
normalizing, or syncing Project Harness documentation.

## Rules

- Read this registry before creating, normalizing, or syncing project docs.
- Do not invent a new documentation format when a registered template exists.
- Do not create placeholder product domains just to fill the folder structure.
- Treat existing docs as source material until they are audited and reconciled.
- During existing-project onboarding, create a doc sync plan before replacing
  or rewriting existing project docs.
- Mark assumptions, conflicts, and unknowns explicitly.
- Use `docs/harness/templates/manifest.yml` for machine-readable template
  metadata and CLI scaffold commands.
- `harness-cli scaffold` copies registered templates only; it does not generate
  accepted project truth.

## Template Map

| Document Type | Template | Default Output | Use When | Review |
| --- | --- | --- | --- | --- |
| Project README | `docs/harness/templates/readme/README_TEMPLATE.md` | `README.md` | Creating or normalizing a project README | human |
| Project README VN | `docs/harness/templates/readme/README_VN_TEMPLATE.md` | `README_VN.md` | Creating a Vietnamese README variant | human |
| Docs suite index | `docs/harness/templates/docs-suite/README.md` | `docs/README.md` | Creating a detailed docs map | human |
| Docs suite EN overview | `docs/harness/templates/docs-suite/EN/overview.md` | `docs/EN/overview.md` | Creating English overview docs | human |
| Docs suite VN overview | `docs/harness/templates/docs-suite/VN/overview.md` | `docs/VN/overview.md` | Creating Vietnamese overview docs | human |
| SRDS | `docs/harness/templates/requirements/srds.md` | `docs/requirements/SRDS.md` | Creating combined requirements and design docs | human |
| Product domain | `docs/harness/templates/product/domain.md` | `docs/product/<domain>.md` | Creating an evidence-backed product domain contract | human |
| Spec intake | `docs/harness/templates/intake/spec-intake.md` | `docs/stories/spec-intake.md` | Turning a supplied spec into candidate work | human |
| Source inventory | `docs/harness/templates/onboarding/source-inventory.md` | `docs/onboarding/source-inventory.md` | Inventorying existing docs/code/tests/config before onboarding | human |
| Doc sync plan | `docs/harness/templates/onboarding/doc-sync-plan.md` | `docs/onboarding/doc-sync-plan.md` | Planning how old docs map into canonical docs | human |
| Baseline audit | `docs/harness/templates/onboarding/baseline-audit.md` | `docs/onboarding/baseline-audit.md` | Auditing an existing project | human |
| Doc conflict | `docs/harness/templates/onboarding/doc-conflict.md` | `docs/onboarding/doc-conflicts.md` | Recording code/docs/spec conflicts | human |
| Story | `docs/harness/templates/stories/story.md` | `docs/stories/<id>-<slug>.md` | Normal story-sized work | reviewer |
| High-risk story overview | `docs/harness/templates/stories/high-risk/overview.md` | `docs/stories/<epic>/<story>/overview.md` | High-risk story packet | reviewer |
| High-risk execution plan | `docs/harness/templates/stories/high-risk/execplan.md` | `docs/stories/<epic>/<story>/execplan.md` | High-risk implementation plan | reviewer |
| High-risk design | `docs/harness/templates/stories/high-risk/design.md` | `docs/stories/<epic>/<story>/design.md` | High-risk design notes | reviewer |
| High-risk validation | `docs/harness/templates/stories/high-risk/validation.md` | `docs/stories/<epic>/<story>/validation.md` | High-risk proof plan | reviewer |
| Decision | `docs/harness/templates/decisions/decision.md` | `docs/decisions/NNNN-<slug>.md` | Durable product or architecture decision | reviewer |
| Validation report | `docs/harness/templates/validation/validation-report.md` | `docs/validation/reports/<date>-<slug>.md` | Capturing notable proof | reviewer |

## Existing Project Sync

When a repository already has docs, agents must use this sequence:

1. Create a source inventory.
2. Map existing docs to registered templates.
3. Create a doc sync plan.
4. Generate normalized docs only from cited evidence.
5. Preserve conflicts and unknowns instead of guessing.
6. Ask for human review before replacing or archiving existing docs.

## New Project Docs

For a new project spec, agents may create draft docs directly from registered
templates, but the drafts are not accepted source of truth until reviewed or
confirmed by the human.

## CLI Support

Use the CLI to inspect and copy registered templates:

```bash
scripts/bin/harness-cli template list
scripts/bin/harness-cli scaffold source_inventory
scripts/bin/harness-cli scaffold product_domain --output docs/product/tasks.md
```

`scaffold` refuses to overwrite existing files unless `--force` is passed.
Pattern-only templates require `--output`.
