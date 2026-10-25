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
TONE_MARKS = {"\u0300", "\u0301", "\u0303", "\u0309", "\u0323"}
SYLLABLE = re.compile(
    r"^(ngh|ng|nh|kh|th|tr|ch|ph|gi|qu|gh|[bcdđghklmnprstvx])?"
    r"[aăâeêioôơuưy]{1,3}"
    r"(ch|ng|nh|[cmnpt])?$"
)


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


def is_vietnamese_syllable(token: str) -> bool:
    """Rule check: optional onset, 1 to 3 Vietnamese vowels, optional coda, at most one tone mark."""

    decomposed = unicodedata.normalize("NFD", token.lower())
    if sum(char in TONE_MARKS for char in decomposed) > 1:
        return False
    base = unicodedata.normalize("NFC", "".join(char for char in decomposed if char not in TONE_MARKS))
    return bool(SYLLABLE.match(base))


def _is_acceptable_token(token: str) -> bool:
    """Digits, times, dates, percentages (all contain a digit) and 2 to 6 letter uppercase acronyms."""

    if any(char.isdigit() for char in token):
        return True
    return 2 <= len(token) <= 6 and token.isalpha() and token.isupper()


def vietnamese_syllable_ratio(line: str) -> float:
    """Share of whitespace tokens that are Vietnamese syllables or acceptable tokens.

    Punctuation at token edges is ignored; tokens of punctuation only are not
    counted. A single valid syllable ("Vập", "Máp") scores 1.0: it is
    phonotactically valid and one-word headlines ("Thời sự") must survive, so
    such fragments are left to the repeat and length filters.
    """

    tokens = [_strip_edges(token) for token in line.split()]
    tokens = [token for token in tokens if token]
    if not tokens:
        return 0.0
    valid = sum(_is_acceptable_token(token) or is_vietnamese_syllable(token) for token in tokens)
    return valid / len(tokens)


def _strip_edges(token: str) -> str:
    start, end = 0, len(token)
    while start < end and not token[start].isalnum():
        start += 1
    while end > start and not token[end - 1].isalnum():
        end -= 1
    return token[start:end]


def _lines(text: str) -> list[str]:
    return list(dict.fromkeys(line.strip() for line in text.splitlines() if line.strip()))


def _merge(segments: Sequence[AsrSegment]) -> AsrSegment:
    return AsrSegment(segments[0].start_sec, segments[-1].end_sec,
                      " ".join(segment.text for segment in segments))


def _clock_seconds(value: str) -> float:
    hours, minutes, seconds, millis = (int(part) for part in str(value).split(":"))
    return hours * 3600 + minutes * 60 + seconds + millis / 1000
