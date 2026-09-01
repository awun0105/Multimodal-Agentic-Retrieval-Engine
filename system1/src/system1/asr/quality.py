from __future__ import annotations

import math
import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass(frozen=True)
class QualityDecision:
    accepted: bool
    reason_codes: tuple[str, ...]
    metrics: dict[str, float | int | None]


def alignment_metrics(
    hypothesis: Any,
    *,
    blank_index: int | None = None,
) -> dict[str, float | int | None]:
    alignments = getattr(hypothesis, "alignments", None)
    if alignments is None:
        return {
            "alignment_frames": None,
            "blank_argmax_ratio": None,
            "mean_nonblank_posterior": None,
            "normalized_entropy": None,
        }
    value = alignments
    if hasattr(value, "detach"):
        value = value.detach()
    if hasattr(value, "float"):
        value = value.float()
    if hasattr(value, "cpu"):
        value = value.cpu()
    if hasattr(value, "numpy"):
        value = value.numpy()
    array = np.asarray(value, dtype=np.float64)
    array = np.squeeze(array)
    if array.ndim != 2 or not array.size or not np.isfinite(array).all():
        return {
            "alignment_frames": None,
            "blank_argmax_ratio": None,
            "mean_nonblank_posterior": None,
            "normalized_entropy": None,
        }
    resolved_blank = array.shape[1] - 1 if blank_index is None else int(blank_index)
    if not 0 <= resolved_blank < array.shape[1]:
        raise ValueError("CTC blank index is outside the alignment vocabulary")
    shifted = array - np.max(array, axis=1, keepdims=True)
    probabilities = np.exp(shifted)
    probabilities /= np.sum(probabilities, axis=1, keepdims=True)
    nonblank = np.delete(probabilities, resolved_blank, axis=1)
    entropy = -np.sum(
        probabilities * np.log(np.clip(probabilities, 1e-12, 1.0)), axis=1
    )
    normalizer = math.log(probabilities.shape[1])
    return {
        "alignment_frames": int(array.shape[0]),
        "blank_argmax_ratio": float(
            np.mean(np.argmax(probabilities, axis=1) == resolved_blank)
        ),
        "mean_nonblank_posterior": float(np.mean(np.max(nonblank, axis=1))),
        "normalized_entropy": float(np.mean(entropy) / normalizer),
    }


def evaluate_transcript(
    text: str,
    *,
    duration_seconds: float,
    acoustic_metrics: Mapping[str, float | int | None],
    config: Mapping[str, Any],
) -> QualityDecision:
    lexical = "".join(character for character in text if character.isalnum())
    lexical_count = len(lexical)
    metrics: dict[str, float | int | None] = dict(acoustic_metrics)
    metrics["lexical_char_count"] = lexical_count
    metrics["characters_per_second"] = (
        lexical_count / duration_seconds if duration_seconds > 0 else None
    )
    metrics["max_same_character_run_ratio"] = _max_same_character_run_ratio(
        lexical
    )
    reasons: list[str] = []
    if not text.strip():
        reasons.append("empty_text")
    if lexical_count < int(config.get("min_lexical_chars", 2)):
        reasons.append("insufficient_lexical_content")

    rate = metrics["characters_per_second"]
    if isinstance(rate, float):
        if rate < float(config.get("min_characters_per_second", 0.15)):
            reasons.append("character_rate_too_low")
        if rate > float(config.get("max_characters_per_second", 35.0)):
            reasons.append("character_rate_too_high")

    if bool(config.get("require_acoustic_metrics", True)) and any(
        acoustic_metrics.get(key) is None
        for key in (
            "blank_argmax_ratio",
            "mean_nonblank_posterior",
            "normalized_entropy",
        )
    ):
        reasons.append("missing_acoustic_metrics")
    blank_ratio = acoustic_metrics.get("blank_argmax_ratio")
    if isinstance(blank_ratio, (float, int)) and blank_ratio > float(
        config.get("max_blank_argmax_ratio", 0.985)
    ):
        reasons.append("blank_ratio_too_high")
    posterior = acoustic_metrics.get("mean_nonblank_posterior")
    if isinstance(posterior, (float, int)) and posterior < float(
        config.get("min_mean_nonblank_posterior", 0.02)
    ):
        reasons.append("nonblank_posterior_too_low")
    entropy = acoustic_metrics.get("normalized_entropy")
    if isinstance(entropy, (float, int)) and entropy > float(
        config.get("max_normalized_entropy", 0.98)
    ):
        reasons.append("entropy_too_high")
    repeat_ratio = metrics["max_same_character_run_ratio"]
    if (
        lexical_count >= int(config.get("repeat_check_min_chars", 6))
        and isinstance(repeat_ratio, float)
        and repeat_ratio > float(config.get("max_same_character_run_ratio", 0.75))
    ):
        reasons.append("character_repetition")
    return QualityDecision(not reasons, tuple(dict.fromkeys(reasons)), metrics)


def normalize_for_comparison(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return " ".join(re.findall(r"\w+", normalized, flags=re.UNICODE))


def low_information_text(text: str, *, max_chars: int, max_tokens: int) -> bool:
    normalized = normalize_for_comparison(text)
    return len(normalized.replace(" ", "")) <= max_chars or len(
        normalized.split()
    ) <= max_tokens


def _max_same_character_run_ratio(text: str) -> float | None:
    if not text:
        return None
    maximum = current = 1
    previous = text[0].casefold()
    for character in text[1:]:
        folded = character.casefold()
        if folded == previous:
            current += 1
            maximum = max(maximum, current)
        else:
            current = 1
            previous = folded
    return maximum / len(text)
