from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from typing import Any


def assign_words_to_intervals(
    intervals: Iterable[Mapping[str, Any]],
    words: Iterable[Mapping[str, Any]],
    *,
    entity_id_field: str,
) -> dict[str, list[dict[str, Any]]]:
    ordered_intervals = _ordered_intervals(intervals, entity_id_field)
    assignments = {str(row[entity_id_field]): [] for row in ordered_intervals}
    for word in sorted(words, key=_word_sort_key):
        start, end = _range(word, "ASR word")
        overlaps: list[tuple[float, int, Mapping[str, Any]]] = []
        for index, interval in enumerate(ordered_intervals):
            interval_start, interval_end = _range(interval, entity_id_field)
            overlap = min(end, interval_end) - max(start, interval_start)
            if overlap > 0:
                overlaps.append((overlap, index, interval))
        if not overlaps:
            continue
        maximum = max(value[0] for value in overlaps)
        tied = [value for value in overlaps if math.isclose(value[0], maximum, abs_tol=1e-12)]
        selected = tied[0]
        if len(tied) > 1:
            midpoint = (start + end) / 2.0
            containing = [
                value
                for value in tied
                if float(value[2]["start_sec"]) <= midpoint < float(value[2]["end_sec"])
            ]
            if containing:
                selected = containing[0]
            else:
                selected = min(tied, key=lambda value: value[1])
        assignments[str(selected[2][entity_id_field])].append(dict(word))
    return assignments


def build_interval_transcript(words: Sequence[Mapping[str, Any]]) -> str:
    ordered = sorted(words, key=_word_sort_key)
    seen: set[str] = set()
    surface: list[str] = []
    for row in ordered:
        word_id = str(row["asr_word_id"])
        if word_id in seen:
            raise ValueError(f"Duplicate ASR word in interval transcript: {word_id}")
        seen.add(word_id)
        text = str(row["text"]).strip()
        if text:
            surface.append(text)
    return " ".join(surface)


def build_interval_transcripts(
    intervals: Iterable[Mapping[str, Any]],
    words: Iterable[Mapping[str, Any]],
    *,
    entity_id_field: str,
) -> dict[str, str]:
    assignments = assign_words_to_intervals(
        intervals, words, entity_id_field=entity_id_field
    )
    return {
        entity_id: build_interval_transcript(assigned)
        for entity_id, assigned in assignments.items()
    }


def build_shot_transcript_links(
    shots: Iterable[Mapping[str, Any]],
    segments: Iterable[Mapping[str, Any]],
    words: Iterable[Mapping[str, Any]] = (),
) -> list[dict[str, Any]]:
    return _build_links(
        shots,
        segments,
        words,
        entity_id_field="shot_id",
    )


def build_scene_transcript_links(
    scenes: Iterable[Mapping[str, Any]],
    segments: Iterable[Mapping[str, Any]],
    words: Iterable[Mapping[str, Any]] = (),
) -> list[dict[str, Any]]:
    return _build_links(
        scenes,
        segments,
        words,
        entity_id_field="scene_id",
    )


def _build_links(
    intervals: Iterable[Mapping[str, Any]],
    segments: Iterable[Mapping[str, Any]],
    words: Iterable[Mapping[str, Any]],
    *,
    entity_id_field: str,
) -> list[dict[str, Any]]:
    interval_rows = _ordered_intervals(intervals, entity_id_field)
    segment_rows = sorted(segments, key=lambda row: (float(row["start_sec"]), str(row["asr_segment_id"])))
    assignments = assign_words_to_intervals(
        interval_rows, words, entity_id_field=entity_id_field
    )
    assigned_counts: dict[tuple[str, str], int] = {}
    for entity_id, assigned in assignments.items():
        for word in assigned:
            key = (entity_id, str(word["asr_segment_id"]))
            assigned_counts[key] = assigned_counts.get(key, 0) + 1
    rows: list[dict[str, Any]] = []
    for interval in interval_rows:
        entity_start, entity_end = _range(interval, entity_id_field)
        entity_duration = entity_end - entity_start
        entity_id = str(interval[entity_id_field])
        for segment in segment_rows:
            segment_start, segment_end = _range(segment, "ASR segment")
            overlap_start = max(entity_start, segment_start)
            overlap_end = min(entity_end, segment_end)
            overlap = overlap_end - overlap_start
            if overlap <= 0:
                continue
            segment_duration = segment_end - segment_start
            segment_coverage = _bounded_ratio(overlap, segment_duration)
            entity_coverage = _bounded_ratio(overlap, entity_duration)
            segment_id = str(segment["asr_segment_id"])
            rows.append(
                {
                    "video_id": str(interval["video_id"]),
                    entity_id_field: entity_id,
                    "asr_segment_id": segment_id,
                    "overlap_start_sec": overlap_start,
                    "overlap_end_sec": overlap_end,
                    "overlap_sec": overlap,
                    "segment_coverage": segment_coverage,
                    "entity_coverage": entity_coverage,
                    "coverage": segment_coverage,
                    "assigned_word_count": assigned_counts.get((entity_id, segment_id), 0),
                }
            )
    return rows


def _ordered_intervals(
    intervals: Iterable[Mapping[str, Any]], entity_id_field: str
) -> list[Mapping[str, Any]]:
    ordered = sorted(
        intervals,
        key=lambda row: (
            float(row["start_sec"]),
            float(row["end_sec"]),
            str(row[entity_id_field]),
        ),
    )
    previous_end: float | None = None
    for row in ordered:
        start, end = _range(row, entity_id_field)
        if previous_end is not None and start < previous_end - 1e-9:
            raise ValueError(f"{entity_id_field} intervals must not overlap")
        previous_end = end
    return ordered


def _range(row: Mapping[str, Any], label: str) -> tuple[float, float]:
    start = float(row["start_sec"])
    end = float(row["end_sec"])
    if not (math.isfinite(start) and math.isfinite(end) and 0 <= start < end):
        raise ValueError(f"{label} duration must be finite and positive")
    return start, end


def _bounded_ratio(numerator: float, denominator: float) -> float:
    ratio = numerator / denominator
    if ratio < -1e-9 or ratio > 1 + 1e-9:
        raise ValueError("Transcript overlap coverage is outside [0, 1]")
    return min(1.0, max(0.0, ratio))


def _word_sort_key(row: Mapping[str, Any]) -> tuple[float, float, str, int]:
    return (
        float(row["start_sec"]),
        float(row["end_sec"]),
        str(row["asr_segment_id"]),
        int(row["word_index"]),
    )
