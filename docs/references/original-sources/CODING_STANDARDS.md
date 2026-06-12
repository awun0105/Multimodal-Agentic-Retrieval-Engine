# Coding Standards

This project should stay simple, readable, and easy to change under competition
pressure.

## Engineering Principles

- **Loose coupling:** UI, API routes, services, storage, search, and agent logic
  should depend on small interfaces, not concrete internals.
- **High cohesion:** each module should have one clear job.
- **Simple first:** use the smallest design that solves the current workflow.
- **Explicit data flow:** prefer plain request/response models and typed records.
- **Config-driven:** paths, ports, limits, and feature flags belong in config/env,
  not hardcoded in business logic.
- **Rebuildable artifacts:** indexes, thumbnails, and generated evidence must be
  rebuildable from raw data and manifests.
- **Fail loudly:** invalid data, broken paths, and bad submissions should produce
  clear errors before competition upload.
- **Readable over clever:** optimize after correctness and measurement.

## Architecture Patterns

Use these patterns consistently:

- **Layered architecture**
  - API layer: HTTP routes and request/response mapping only.
  - Service layer: workflow/business logic.
  - Repository/storage layer: SQLite/filesystem/index access.
  - UI layer: rendering and interaction only.

- **Repository pattern**
  - Database queries should live behind small repository functions/classes once
    they grow beyond trivial endpoints.
  - UI and agent code should not know SQL details.

- **Adapter pattern**
  - FAISS, FTS5, object search, OCR search, and future search engines should be
    accessed through retriever adapters.
  - This keeps SQLite FTS5 replaceable by Tantivy/OpenSearch later if needed.

- **Strategy pattern**
  - Query workflows such as TKIS, Q&A, TRAKE, and VKIS should be separate solver
    strategies using the same retrieval tools.

- **Command pattern for agent/tool calls**
  - Automatic mode should call named tools with structured inputs/outputs.
  - Every tool call should be traceable and replayable.

Avoid premature patterns:

- no microservices early;
- no abstract factory hierarchies without real variants;
- no separate agent-only retrieval path;
- no UI business logic hidden inside React components.

## Python Standards

- Follow PEP 8.
- Use Ruff as the formatter/linter gate.
- Use type hints for public functions and service boundaries.
- Prefer Pydantic models for API input/output.
- Keep functions small and named by intent.
- Use `pathlib.Path` for filesystem paths.
- Use parameterized SQL only.
- Do not swallow exceptions silently.
- Avoid global mutable state except cached settings/config.

Validation commands:

```bash
uv run ruff check backend tests
uv run pytest
```

## TypeScript / React Standards

- Use TypeScript strict mode.
- Keep API types in `src/types.ts` or feature-specific type files.
- Keep API calls in a client module, not directly inside every component.
- Components should be small and workflow-oriented.
- Prefer explicit props over global state until global state is necessary.
- Do not store backend source-of-truth data only in UI state.
- Use semantic HTML where practical.
- Keep CSS readable and scoped by clear class names.

Validation command:

```bash
npm run build --prefix frontend
```

## Naming

- Python files/modules: `snake_case.py`
- Python classes: `PascalCase`
- Python functions/variables: `snake_case`
- TypeScript files: `PascalCase.tsx` for components, `camelCase.ts` for helpers
- TypeScript types/components: `PascalCase`
- API JSON fields: `snake_case` to match backend models
- Database tables/columns: `snake_case`

## Testing Rules

- Add tests for API routes, parsing, validation, and export behavior.
- Add regression tests for competition-critical bugs.
- Do not commit code that fails available validation.
- If a test cannot be run, document why in the final status.

## Performance Rules

- Live search must read indexes/DB, not scan raw videos.
- Media responses should stream files; search JSON should return URLs.
- Grid thumbnails should be small and lazy-loaded.
- Heavy OCR/ASR/captioning belongs in preprocessing jobs.
- Measure before adding heavier infrastructure.

