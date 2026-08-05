# Decisions

Decision records preserve lasting product, architecture, data ownership,
security, compatibility, and validation choices that future work must inherit.

Use `docs/templates/decision.md`. Task-local implementation choices remain in
the active execution plan and do not require a separate decision.

An installed consumer begins with no fabricated decisions. Add local decision
documents here as real choices are accepted, then index them in this file.

## Recent Accepted Decisions

- `0014-multimodal-context-window-scene-grouping.md`: Phase01 scene boundaries
  are judged in overlapping multimodal context/focus windows while deterministic
  package code owns the final partition, IDs, ranges, validation, and explicit
  failure behavior.
- `0015-system1-self-generated-production-evidence.md`: System 1 consumes videos
  plus optional metadata, regenerates derived evidence, fixes the Notebook 01
  production pipeline, and builds separate SigLIP/BEiT3 indexes in Notebook 02.
