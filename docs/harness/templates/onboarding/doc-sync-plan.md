# Documentation Sync Plan

## Goal

Normalize existing project documentation into the Project Harness documentation
structure without losing useful source material or treating stale docs as truth.

## Source Inventory

See: `docs/onboarding/source-inventory.md`

## Sync Table

| Source File | Current Role | Target Doc | Template | Action | Confidence | Needs Human Review | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `README.md` | setup/overview | `README.md` | `readme` | normalize | medium | yes | Preserve verified setup commands. |

## Actions

- `adopt`: keep as-is and register as canonical.
- `normalize`: rewrite into a registered template.
- `merge`: combine useful content into a canonical doc.
- `transform`: convert into a different artifact type.
- `conflict`: record mismatch; do not trust as truth.
- `archive`: preserve but remove from source-of-truth path after review.

## Conflicts

List source files whose claims conflict with code, tests, config, deployment, or
human-confirmed intent.

## Human Review Required

List the decisions or uncertain claims that require human review before docs can
be accepted as canonical.

## Apply Notes

Do not overwrite or archive source material until this plan explains how useful
content is preserved and the human has reviewed high-risk or conflicting items.
