# ADR 0024: Pipeline Validation Policy

Date: 2026-10-25

## Status

Accepted

## Context

System 1 checks its environment strictly but missed real output defects:

- Preflight requires exact library versions, a Flashlight beam size of 64, a
  per-run Hugging Face write/read round trip, and fixed free-disk thresholds.
- `phase01/validation.py` has 119 raise sites spread across stages, and one
  invalid shot fails the whole video (`No valid keyframe candidate for shot`).
- Tests assert configuration constants (`test_phase01_production_contract.py`
  has 179 asserts, `test_smoke.py` has 613), so any configuration change breaks
  tests without any behavior change.
- The same pipeline accepted OCR rows that repeated the prompt placeholder and
  ASR text with broken syllables.

## Decision

1. **Fail fast on corrupted data:** wrong `video_id` or frame mapping, unreadable
   media, schema-invalid final outputs, checksum mismatch on upload or
   download, and secret leakage.
2. **Degrade and record on missing or weak evidence:** empty OCR, failed ASR, an
   invalid shot or keyframe candidate, or a failed caption. Mark the status,
   log the cause, and continue the video.
3. **Check output content, not environment exactness:** detect prompt echo,
   one string repeated across most keyframes, high invalid-syllable rates in
   ASR, and generic captions. Version pins live in `pyproject.toml`; preflight
   checks only credentials, write access, and required executables.
4. **One output validator** runs at packaging time, replacing per-stage
   validation scattered across modules.
5. **Tests assert behavior, not constants.** Example: "a keyframe lies inside
   its shot", "an OCR prompt echo is rejected". Configuration values are not
   asserted in tests.
6. New behavior tests are written before old constant tests are removed.

## Alternatives Considered

1. Keep current gates and add content checks. Rejected: constant tests and
   environment gates would still block every change.

## Consequences

Positive:

- Configuration and model changes no longer require editing large test files.
- Gates catch the defects that actually occurred.

Tradeoffs:

- Removing tests temporarily reduces coverage; mitigated by rule 6.

## Follow-Up

- Write behavior tests for the simplified pipeline, then remove constant tests,
  `phase01_qualification*.py`, and `phase01/smoke.py` under
  `docs/plans/active/system1-pipeline-simplification.md`.
