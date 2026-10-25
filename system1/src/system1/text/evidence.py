"""Text evidence helpers: ASR chunking, shot mapping, and content checks.

ASR chunks are the retrieval unit for speech (ADR 0023): 10 to 30 second
windows mapped to every overlapping shot. Content checks reject output defects
seen in the 2026-08-27 run (ADR 0024): prompt echoes and text repeated across
most of a video, such as channel logos.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

PLACEHOLDER = re.compile(r"^<[^<>]{1,80}>$")


@dataclass(frozen=True)
class AsrSegment:
    start_sec: float
    end_sec: float
    text: str


def parse_chunkformer_segments(raw: Iterable[Mapping[str, str]]) -> list[AsrSegment]:
    """Convert ChunkFormer `endless_decode(..., return_timestamps=True)` rows."""

    segments = []
    for row in raw:
        text = " ".join(str(row["decode"]).split())
        if text:
            segments.append(AsrSegment(_clock_seconds(row["start"]), _clock_seconds(row["end"]), text))
    return segments


def chunk_asr_segments(
    segments: Sequence[AsrSegment],
    *,
    min_sec: float,
    max_sec: float,
    max_gap_sec: float,
) -> list[AsrSegment]:
    """Group consecutive segments into chunks of at most `max_sec`.

    A chunk closes when adding the next segment would exceed `max_sec`, or
    when it has reached `min_sec` and the next segment starts after a pause
    longer than `max_gap_sec`. A pause longer than `max_sec` always closes it.
    """

    chunks: list[AsrSegment] = []
    current: list[AsrSegment] = []
    for segment in sorted(segments, key=lambda item: item.start_sec):
        if current:
            start = current[0].start_sec
            gap = segment.start_sec - current[-1].end_sec
            too_long = segment.end_sec - start > max_sec
            paused = gap > max_gap_sec and (current[-1].end_sec - start >= min_sec or gap > max_sec)
            if too_long or paused:
                chunks.append(_merge(current))
                current = []
        current.append(segment)
    if current:
        chunks.append(_merge(current))
    return chunks


def shots_for_interval(
    start_sec: float, end_sec: float, shots: Sequence[tuple[str, float, float]]
) -> list[str]:
    """Return IDs of shots `(shot_id, start_sec, end_sec)` overlapping the interval."""

    return [shot_id for shot_id, shot_start, shot_end in shots
            if shot_start < end_sec and start_sec < shot_end]


def unaccent(text: str) -> str:
    """Remove Vietnamese diacritics for accent-insensitive full-text search."""

    decomposed = unicodedata.normalize("NFD", text.replace("đ", "d").replace("Đ", "D"))
    return unicodedata.normalize(
        "NFC", "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
    )


def is_prompt_echo(text: str, prompt: str) -> bool:
    """True when model output is a placeholder or repeats a prompt line."""

    stripped = text.strip()
    if PLACEHOLDER.match(stripped):
        return True
    lines = {line.strip().lower() for line in prompt.splitlines() if len(line.strip()) >= 12}
    return stripped.lower() in lines


def strip_video_wide_repeats(texts: Mapping[str, str], *, min_fraction: float) -> dict[str, str]:
    """Remove lines that appear in at least `min_fraction` of a video's keyframes.

    `texts` maps keyframe ID to OCR text with one line per detected text line.
    """

    counts = Counter(line for text in texts.values() for line in _lines(text))
    limit = max(2, min_fraction * len(texts))
    repeated = {line for line, count in counts.items() if count >= limit}
    return {key: "\n".join(line for line in _lines(text) if line not in repeated)
            for key, text in texts.items()}


def _lines(text: str) -> list[str]:
    return list(dict.fromkeys(line.strip() for line in text.splitlines() if line.strip()))


def _merge(segments: Sequence[AsrSegment]) -> AsrSegment:
    return AsrSegment(segments[0].start_sec, segments[-1].end_sec,
                      " ".join(segment.text for segment in segments))


def _clock_seconds(value: str) -> float:
    hours, minutes, seconds, millis = (int(part) for part in str(value).split(":"))
    return hours * 3600 + minutes * 60 + seconds + millis / 1000
