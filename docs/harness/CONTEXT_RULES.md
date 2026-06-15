# Context Engineering Rules

Context rules help agents decide what to read, when to read it, and when to
stop reading. They are additive to the stable `AGENTS.md` reading list.

These rules apply after the stable entrypoints in `AGENTS.md` have been read.
Do not re-read stable entrypoints unless the current task phase requires fresh
evidence.

The goal is not to maximize context. The goal is to put the right information
in the model for the current task phase and risk lane.

## Context Phases

### Intake Phase

Read to classify the request, find the affected surface, and choose a lane.

| Document Or Source | Tiny | Normal | High-Risk |
| --- | --- | --- | --- |
| `AGENTS.md` | Must | Must | Must |
| `docs/harness/FEATURE_INTAKE.md` | Must | Must | Must |
| `scripts/bin/harness-cli query matrix` | Must | Must | Must |
| `README.md` | Should | Must | Must |
| `docs/harness/HARNESS.md` | Should | Must | Must |
| `docs/harness/TEMPLATE_REGISTRY.md` | Must if creating or syncing docs | Must if creating or syncing docs | Must if creating or syncing docs |
| `docs/architecture/overview.md` | Skip | Should | Must |
| Relevant `docs/product/*` | Skip if unrelated | Must if product behavior changes | Must |
| Relevant `docs/stories/*` | Skip if unrelated | Must if a story exists | Must |
| `docs/decisions/*` | Skip | Should if architecture or durable rules are touched | Must |
| `docs/harness/HARNESS_COMPONENTS.md` | Skip | Should for Harness improvements | Must for observability or benchmark work |

### Planning Phase

Read to decide the smallest safe approach and expected proof.

| Document Or Source | Tiny | Normal | High-Risk |
| --- | --- | --- | --- |
| Current files to edit | Must | Must | Must |
| `docs/harness/TEMPLATE_REGISTRY.md` | Must if creating or syncing docs | Must if creating or syncing docs | Must if creating or syncing docs |
| `docs/harness/templates/stories/story.md` | Skip | Must when creating/updating a story | Should |
| `docs/harness/templates/stories/high-risk/*` | Skip | Skip unless risk escalates | Must |
| `docs/architecture/overview.md` | Skip | Should for code or boundary changes | Must |
| `docs/validation/test-matrix.md` or `scripts/bin/harness-cli query matrix` | Should | Must | Must |
| Relevant decisions | Skip | Should | Must |
| `docs/harness/HARNESS_MATURITY.md` | Skip | Should for Harness improvements | Must for maturity or process changes |
| `docs/harness/HARNESS_BACKLOG.md` and `scripts/bin/harness-cli query backlog` | Skip | Should if friction repeats | Must if changing Harness behavior |

### Implementation Phase

Read while making the change. Keep this phase scoped to files that directly
affect the selected story.

| Document Or Source | Tiny | Normal | High-Risk |
| --- | --- | --- | --- |
| Files being changed | Must | Must | Must |
| Adjacent files with same pattern | Should | Must | Must |
| Relevant product docs | Skip if copy-only | Must if behavior changes | Must |
| Relevant story packet | Skip if no story needed | Must | Must |
| Relevant registered templates | Skip | Should when adding docs | Must |
| `docs/architecture/overview.md` | Skip | Should for structural changes | Must |
| Provider/API/security docs | Skip | Should if touched | Must |
| Unrelated docs and historical traces | Skip | Skip | Should only if they affect decisions |

### Validation Phase

Read to prove the change and avoid claiming unsupported completion.

| Document Or Source | Tiny | Normal | High-Risk |
| --- | --- | --- | --- |
| Story acceptance criteria | Should | Must | Must |
| `docs/validation/test-matrix.md` or `scripts/bin/harness-cli query matrix` | Should | Must | Must |
| Validation section of story packet | Skip if no story | Must | Must |
| `docs/harness/templates/validation/validation-report.md` | Skip | Should for notable proof | Must for high-risk proof |
| Relevant commands from README/package docs | Should | Must | Must |
| Benchmark protocol or external benchmark repo | Skip | Skip unless requested | Must if the story depends on benchmark proof |
| `docs/harness/HARNESS_MATURITY.md` | Skip | Should for Harness improvements | Must for maturity claims |

### Trace Phase

Read to leave useful evidence for the next agent and for benchmark scoring.

| Document Or Source | Tiny | Normal | High-Risk |
| --- | --- | --- | --- |
| `docs/harness/TRACE_SPEC.md` | Should | Must | Must |
| `scripts/bin/harness-cli query matrix` | Should | Must | Must |
| `scripts/bin/harness-cli query backlog` | Skip | Should if friction occurred | Must |
| Changed-file list from `git status --short` | Must | Must | Must |
| Validation command output | Should | Must | Must |
| Story packet or progress log | Skip if no story | Must | Must |
| `docs/harness/HARNESS_COMPONENTS.md` | Skip | Should if attributing friction | Must if failure attribution is needed |

## Retrieval Triggers

| Trigger Condition | Action |
| --- | --- |
| Task touches database schema, durable records, or migrations | Read `docs/decisions/0004-sqlite-durable-layer.md`, `scripts/schema/`, and relevant CLI code before planning. |
| Task touches CLI command behavior or installer distribution | Read `docs/decisions/0005-prebuilt-rust-harness-cli.md`, `scripts/README.md`, relevant `crates/harness-cli/*` code, CLI help output, and installer docs. |
| Task touches auth, authorization, audit/security, data loss, or external providers | Treat as high-risk, read `docs/harness/templates/stories/high-risk/*`, and check prior decisions before implementation. |
| Task changes public API shape, product behavior, or user-visible workflow | Read relevant `docs/product/*`, story packets, and validation expectations before editing. |
| Task changes Harness policy, source hierarchy, risk classification, or validation requirements | Read `docs/harness/HARNESS.md`, `docs/harness/FEATURE_INTAKE.md`, `docs/architecture/overview.md`, and `docs/decisions/*`; pause if direction is ambiguous. |
| Task creates, normalizes, or syncs documentation | Read `docs/harness/TEMPLATE_REGISTRY.md`, then use registered templates from `docs/harness/templates/`; for existing-project onboarding, create a source inventory and doc sync plan before rewriting docs. |
| Task discovers repeated confusion, stale docs, or missing proof | Read `docs/harness/HARNESS_BACKLOG.md`, record `harness_friction`, and add a backlog item when the fix is out of scope. |
| Task makes a maturity, observability, trace quality, or benchmark claim | Read `docs/harness/HARNESS_COMPONENTS.md`, `docs/harness/HARNESS_MATURITY.md`, and `docs/harness/TRACE_SPEC.md`. |
| Task is normal or high-risk and spans multiple iterations | Create or update a story/progress file under `docs/stories/` and keep it current. |
| Final response is being prepared | Re-read the validation evidence, `git status --short`, and `docs/harness/TRACE_SPEC.md` before recording the final trace. |

## Token Budget Guidance

| Lane | Target Context Budget | Read Shape | Reasoning |
| --- | --- | --- | --- |
| Tiny | About 2K tokens of Harness context | `AGENTS.md`, `docs/harness/FEATURE_INTAKE.md`, matrix query, and the exact file being changed. | Tiny work should not spend more context on policy than on the edit. |
| Normal | About 5K tokens of Harness context | Intake docs, relevant product/story docs, architecture when structural, validation expectations, and trace spec at the end. | Normal work needs enough context to preserve contracts and record proof without reading every historical file. |
| High-risk | About 10K tokens of Harness context | Full intake, architecture, relevant decisions, high-risk templates, product docs, validation docs, trace spec, and component/maturity docs when Harness behavior changes. | High-risk work needs source hierarchy, prior decisions, and proof expectations in context before implementation. |

Budget rules:

- Prefer targeted `rg` searches over bulk reading.
- Read the smallest section that answers the current phase question.
- Escalate context when a retrieval trigger fires.
- Do not keep reading unrelated history after the lane, affected files, and
  validation path are clear.

## Additive Behavior

These rules do not replace `AGENTS.md`. Agents should still read the stable
entrypoint documents listed there before work. This document explains what to
retrieve after that initial context, based on lane, phase, and trigger.

## Review Checklist

Before implementation:

- Lane is chosen from `docs/harness/FEATURE_INTAKE.md`.
- Relevant product docs or story packets are identified.
- Any high-risk trigger has been handled.

Before final response:

- Validation evidence has been read.
- `docs/harness/TRACE_SPEC.md` has been read for normal/high-risk tasks.
- The final trace includes files read, files changed, outcome, and friction
  when applicable.

## Project Runtime And Coding Rules

These project-specific rules are canonicalized from historical coding standards.

### Architecture And Boundaries

- Keep System 1 (offline ingestion notebooks) and System 2 (runtime retrieval app) separate.
- System 1 produces artifacts for System 2; it is not part of live search runtime.
- Keep one shared Web UI codebase for System 2.
- Avoid microservices in MVP.
- Keep runtime SQLite as the source of truth; do not move app state into DuckDB.


### Engineering Principles
- **Loose coupling:** UI, API routes, services, storage, and agent logic depend on small interfaces.
- **Fail loudly:** Invalid data or bad submissions should throw clear errors, not fail silently.
- **Config-driven:** Paths, ports, limits, and feature flags belong in config/env.
- **Rebuildable:** Indexes, thumbnails, and generated evidence must be rebuildable from manifests.

### Architecture Patterns
- **Layered:** API (HTTP only) -> Service (logic) -> Repository (DB/Filesystem).
- **Repository:** DB queries live in repository functions. UI and agent code must not know SQL details.
- **Adapter:** Wrap FAISS, FTS5, and optional future object-stores in retriever/storage adapters.
- **Strategy:** Isolate query workflows (TKIS, Q&A, TRAKE, VKIS) into separate solver strategies using the same retrieval tools.
- **Command:** Automatic agent calls use structured inputs/outputs and are traceable.

### Python Standards
- **Format/Lint:** Use Ruff (`uv run ruff check`).
- **Validation:** Use pytest (`uv run pytest`).
- **Types:** Use type hints for public functions and service boundaries.
- **Data Models:** Prefer Pydantic for API input/output.
- **Safety:** Use `pathlib.Path` for paths. Use parameterized SQL only. Avoid global mutable state.

### TypeScript / React Standards
- **Strict Mode:** Use TypeScript strict mode.
- **State:** Prefer explicit props over global state until global state is strictly necessary. Do not mirror backend source-of-truth deeply in UI state.
- **API:** Keep API calls in a client module, not inline inside every component.
- **Validation:** Must pass `npm run build --prefix frontend`.

### Naming Conventions
- **Python files/modules/functions/variables:** `snake_case`
- **Python classes:** `PascalCase`
- **TypeScript files:** `PascalCase.tsx` (components), `camelCase.ts` (helpers)
- **TypeScript types/components:** `PascalCase`
- **API JSON / DB columns:** `snake_case`

### Performance Constraints
- Live search must read indexes/DB, never scan raw videos.
- Media responses stream files; JSON responses return URLs.

### Backend Rules

- Use FastAPI for the runtime backend.
- Use Pydantic models for public API input/output.
- Use parameterized SQL only.
- Use `pathlib.Path` for filesystem paths where possible.
- Do not swallow exceptions silently.

### Frontend Rules

- Use React + TypeScript + Vite.
- Keep one SPA, not multiple dashboards.
- Keep keyframe-first UX, lazy thumbnail loading, and virtualized grids.
- Persist Query Session state in SQLite through backend APIs.

### Ingestion Notebook Rules

- Keep notebooks task-specific so teammates can split work by dataset chunk or by task type.
- Do not hardcode personal machine paths.
- Add checkpoint/skip logic for already-processed outputs.
- Use explicit memory cleanup for long-running notebook loops.
- Produce deterministic artifact names and stable mappings.

### Search Rules

- Use FAISS for MVP vector search.
- Use SQLite FTS5 for MVP text search.
- Treat Tantivy/OpenSearch/BM25 JSON as non-MVP alternatives.
- Runtime search must read precomputed artifacts, never scan raw folders.

### Validation Rules

- Prefer executable proof tied to Harness stories.
- Do not mark behavior implemented without evidence.
- Keep MVP-0 to MVP-3 as the near-term proof target.
