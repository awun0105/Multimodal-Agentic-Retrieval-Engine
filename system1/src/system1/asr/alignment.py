from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from .quality import normalize_for_comparison
from .timing import FrameTimelineIndex, time_range_to_frames

ALIGNMENT_METHOD = "ctc_forced_alignment"
ALIGNMENT_VERSION = "ctc_word_alignment_v1"


class AsrAlignmentError(RuntimeError):
    """A deterministic ASR alignment contract failed."""


@dataclass(frozen=True)
class TokenAlignment:
    token_index: int
    token_id: int
    start_timestep: int
    end_timestep: int


def extract_ctc_log_probs(hypothesis: Any) -> np.ndarray:
    """Extract the T x V matrix retained by NeMo 2.7.3 CTC transcribe."""

    value = getattr(hypothesis, "alignments", None)
    if value is None:
        candidate = getattr(hypothesis, "y_sequence", None)
        if getattr(candidate, "ndim", None) == 2:
            value = candidate
    if value is None:
        raise AsrAlignmentError("NeMo hypothesis has no preserved CTC log probabilities")
    for method in ("detach", "float", "cpu"):
        operation = getattr(value, method, None)
        if callable(operation):
            value = operation()
    to_numpy = getattr(value, "numpy", None)
    if callable(to_numpy):
        value = to_numpy()
    array = np.asarray(value, dtype=np.float64)
    array = np.squeeze(array)
    if array.ndim != 2 or array.shape[0] < 1 or array.shape[1] < 2:
        raise AsrAlignmentError("CTC log probabilities must have shape T x V")
    if not np.isfinite(array).all():
        raise AsrAlignmentError("CTC log probabilities contain non-finite values")
    return array


def ctc_viterbi_align(
    log_probs: Any,
    target_token_ids: Sequence[int],
    *,
    blank_id: int,
) -> tuple[TokenAlignment, ...]:
    """Align target tokens to a CTC matrix with exact repeated-token semantics."""

    matrix = np.asarray(log_probs, dtype=np.float64)
    if matrix.ndim != 2 or not matrix.size or not np.isfinite(matrix).all():
        raise AsrAlignmentError("CTC log probabilities must be a finite T x V matrix")
    if not 0 <= blank_id < matrix.shape[1]:
        raise AsrAlignmentError("CTC blank ID is outside the acoustic vocabulary")
    targets = [int(value) for value in target_token_ids]
    if not targets:
        raise AsrAlignmentError("Cannot align an empty target token sequence")
    if any(value == blank_id or not 0 <= value < matrix.shape[1] for value in targets):
        raise AsrAlignmentError("Target token IDs must be valid non-blank symbols")
    extended: list[int] = [blank_id]
    for token_id in targets:
        extended.extend((token_id, blank_id))
    path = _viterbi_state_path(matrix, extended, blank_id=blank_id)
    spans: list[TokenAlignment] = []
    for token_index, token_id in enumerate(targets):
        state = 2 * token_index + 1
        frames = np.flatnonzero(path == state)
        if not len(frames):
            raise AsrAlignmentError("CTC path omitted a required target token")
        spans.append(
            TokenAlignment(
                token_index=token_index,
                token_id=token_id,
                start_timestep=int(frames[0]),
                end_timestep=int(frames[-1]) + 1,
            )
        )
    return tuple(spans)


def align_nemo_hypothesis_words(
    hypothesis: Any,
    model: Any,
    *,
    text: str,
    segment_id: str,
    video_id: str,
    segment_start_sec: float,
    segment_end_sec: float,
    frame_timeline: Sequence[Mapping[str, Any]] | FrameTimelineIndex,
    provider: str,
    model_name: str,
    model_version: str,
) -> list[dict[str, Any]]:
    """Align canonical Flashlight text without running the acoustic model again."""

    canonical_text = " ".join(str(text).split())
    if not canonical_text:
        raise AsrAlignmentError("Accepted ASR text cannot be empty")
    matrix = extract_ctc_log_probs(hypothesis)
    try:
        from nemo.collections.asr.parts.utils.aligner_utils import Word, get_utt_obj
    except ImportError as exc:  # pragma: no cover - production preflight owns NeMo
        raise AsrAlignmentError("NeMo tokenizer alignment utilities are unavailable") from exc

    try:
        utterance = get_utt_obj(
            text=canonical_text,
            T=int(matrix.shape[0]),
            model=model,
            segment_separators=[],
            word_separator=" ",
            audio_filepath=segment_id,
            utt_id=segment_id,
        )
    except Exception as exc:
        raise AsrAlignmentError(f"NeMo could not tokenize canonical ASR text: {exc}") from exc
    extended = [int(value) for value in utterance.token_ids_with_blanks]
    if len(extended) <= 1:
        raise AsrAlignmentError("Canonical ASR text produced no alignable model tokens")
    blank_id = int(extended[0])
    if any(not 0 <= value < matrix.shape[1] for value in extended):
        raise AsrAlignmentError("Tokenizer IDs do not match the CTC acoustic vocabulary")
    path = _viterbi_state_path(matrix, extended, blank_id=blank_id)
    timestep_seconds = _nemo_output_timestep_seconds(model)

    words: list[tuple[str, int, int]] = []
    for segment_or_token in utterance.segments_and_tokens:
        for word_or_token in getattr(segment_or_token, "words_and_tokens", []):
            if not isinstance(word_or_token, Word):
                continue
            states = range(int(word_or_token.s_start), int(word_or_token.s_end) + 1)
            frames = np.flatnonzero(np.isin(path, list(states)))
            if not len(frames):
                raise AsrAlignmentError(
                    f"CTC path omitted canonical word {word_or_token.text!r}"
                )
            words.append((str(word_or_token.text), int(frames[0]), int(frames[-1]) + 1))
    if not words:
        raise AsrAlignmentError("Canonical ASR text produced no aligned words")
    if normalize_for_comparison(canonical_text) != normalize_for_comparison(
        " ".join(word for word, _, _ in words)
    ):
        raise AsrAlignmentError("Aligned words do not reconstruct canonical segment text")

    result: list[dict[str, Any]] = []
    previous_start = segment_start_sec
    for word_index, (surface, first_frame, exclusive_last_frame) in enumerate(words):
        start_sec = max(
            segment_start_sec,
            segment_start_sec + first_frame * timestep_seconds,
        )
        end_sec = min(
            segment_end_sec,
            segment_start_sec + exclusive_last_frame * timestep_seconds,
        )
        start_sec = max(start_sec, previous_start)
        if not (math.isfinite(start_sec) and math.isfinite(end_sec) and start_sec < end_sec):
            raise AsrAlignmentError(f"Aligned word {surface!r} has an invalid time range")
        start_frame, end_frame = time_range_to_frames(
            start_sec, end_sec, frame_timeline
        )
        result.append(
            {
                "asr_word_id": f"{segment_id}_W{word_index:05d}",
                "asr_segment_id": segment_id,
                "video_id": video_id,
                "word_index": word_index,
                "text": surface,
                "start_sec": start_sec,
                "end_sec": end_sec,
                "start_frame": start_frame,
                "end_frame": end_frame,
                "confidence": None,
                "alignment_method": ALIGNMENT_METHOD,
                "alignment_version": ALIGNMENT_VERSION,
                "provider": provider,
                "model_name": model_name,
                "model_version": model_version,
                "status": "pass",
            }
        )
        previous_start = start_sec
    return result


def _viterbi_state_path(
    matrix: np.ndarray,
    extended_target: Sequence[int],
    *,
    blank_id: int,
) -> np.ndarray:
    time_steps, _ = matrix.shape
    state_count = len(extended_target)
    minimum_frames = sum(
        2 if index and value == extended_target[index - 2] else 1
        for index, value in enumerate(extended_target)
        if index % 2 == 1
    )
    if time_steps < minimum_frames:
        raise AsrAlignmentError("CTC target has no possible path through the acoustic frames")
    negative_infinity = -np.inf
    scores = np.full((time_steps, state_count), negative_infinity, dtype=np.float64)
    backpointers = np.full((time_steps, state_count), -1, dtype=np.int32)
    scores[0, 0] = matrix[0, int(extended_target[0])]
    if state_count > 1:
        scores[0, 1] = matrix[0, int(extended_target[1])]
    for timestep in range(1, time_steps):
        for state, symbol in enumerate(extended_target):
            candidates = [(scores[timestep - 1, state], state)]
            if state > 0:
                candidates.append((scores[timestep - 1, state - 1], state - 1))
            if (
                state > 1
                and symbol != blank_id
                and symbol != extended_target[state - 2]
            ):
                candidates.append((scores[timestep - 1, state - 2], state - 2))
            best_score, best_state = max(candidates, key=lambda item: item[0])
            if np.isneginf(best_score):
                continue
            scores[timestep, state] = best_score + matrix[timestep, int(symbol)]
            backpointers[timestep, state] = best_state
    final_states = [state_count - 1]
    if state_count > 1:
        final_states.append(state_count - 2)
    final_state = max(final_states, key=lambda state: scores[-1, state])
    if np.isneginf(scores[-1, final_state]):
        raise AsrAlignmentError("CTC target has no valid terminal path")
    path = np.empty(time_steps, dtype=np.int32)
    state = final_state
    for timestep in range(time_steps - 1, -1, -1):
        path[timestep] = state
        if timestep:
            state = int(backpointers[timestep, state])
            if state < 0:
                raise AsrAlignmentError("CTC alignment backtrace is incomplete")
    return path


def _nemo_output_timestep_seconds(model: Any) -> float:
    try:
        config = model.cfg
        preprocessor = config["preprocessor"]
        window_stride = float(preprocessor["window_stride"])
        subsampling_factor = int(model.encoder.subsampling_factor)
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        raise AsrAlignmentError(
            "Cannot derive NeMo output timestep from model runtime metadata"
        ) from exc
    duration = window_stride * subsampling_factor
    if not math.isfinite(duration) or duration <= 0:
        raise AsrAlignmentError("NeMo output timestep duration is invalid")
    return duration
