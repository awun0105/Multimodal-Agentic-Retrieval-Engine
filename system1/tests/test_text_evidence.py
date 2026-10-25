"""Behavior tests for ASR chunking and text content checks (ADR 0023, ADR 0024)."""

from __future__ import annotations

import pytest

from system1.text.evidence import (
    AsrSegment,
    chunk_asr_segments,
    is_prompt_echo,
    parse_chunkformer_segments,
    shots_for_interval,
    strip_video_wide_repeats,
    unaccent,
)


def test_chunkformer_timestamps_are_parsed_to_seconds() -> None:
    raw = [{"decode": "xin chào các em", "start": "00:00:08:160", "end": "00:01:09:360"}]

    assert parse_chunkformer_segments(raw) == [AsrSegment(8.16, 69.36, "xin chào các em")]


def test_empty_decodes_are_dropped() -> None:
    raw = [{"decode": "  ", "start": "00:00:01:000", "end": "00:00:02:000"}]

    assert parse_chunkformer_segments(raw) == []


def _segments(spans: list[tuple[float, float]]) -> list[AsrSegment]:
    return [AsrSegment(start, end, f"w{index}") for index, (start, end) in enumerate(spans)]


def test_chunks_stay_within_the_maximum_length() -> None:
    segments = _segments([(i * 3.0, i * 3.0 + 2.5) for i in range(40)])

    chunks = chunk_asr_segments(segments, min_sec=10.0, max_sec=30.0, max_gap_sec=2.0)

    assert all(chunk.end_sec - chunk.start_sec <= 30.0 for chunk in chunks)
    assert " ".join(chunk.text for chunk in chunks) == " ".join(s.text for s in segments)


def test_a_long_silence_closes_the_chunk() -> None:
    segments = _segments([(0.0, 4.0), (4.5, 8.0), (40.0, 44.0)])

    chunks = chunk_asr_segments(segments, min_sec=10.0, max_sec=30.0, max_gap_sec=2.0)

    assert [chunk.text for chunk in chunks] == ["w0 w1", "w2"]


def test_chunk_maps_to_every_overlapping_shot() -> None:
    shots = [("S0", 0.0, 5.0), ("S1", 5.0, 12.0), ("S2", 12.0, 20.0)]

    assert shots_for_interval(4.0, 13.0, shots) == ["S0", "S1", "S2"]
    assert shots_for_interval(6.0, 11.0, shots) == ["S1"]


def test_unaccent_removes_vietnamese_diacritics() -> None:
    assert unaccent("Đường Trường Sơn, thành phố Hồ Chí Minh") == "Duong Truong Son, thanh pho Ho Chi Minh"


@pytest.mark.parametrize(
    "text",
    [
        "<every visible line, joined by spaces>",
        "<NO_TEXT>",
        "Return only the transcribed visible text.",
    ],
)
def test_prompt_echo_is_detected(text: str) -> None:
    prompt = "Read all text that is visibly present in this image.\nReturn only the transcribed visible text."

    assert is_prompt_echo(text, prompt)


def test_real_text_is_not_a_prompt_echo() -> None:
    prompt = "Read all text that is visibly present in this image."

    assert not is_prompt_echo("Clip bạn đọc dự thi: Lan tỏa năng lượng tích cực 2024", prompt)


def test_text_repeated_across_most_keyframes_is_removed() -> None:
    texts = {f"k{i}": "Tuổi trẻTV tv.tuoitre.vn" for i in range(8)}
    texts["k8"] = "Tuổi trẻTV tv.tuoitre.vn\nThầy LÊ TẤN PHÁT"
    texts["k9"] = ""

    cleaned = strip_video_wide_repeats(texts, min_fraction=0.5)

    assert cleaned["k0"] == ""
    assert cleaned["k8"] == "Thầy LÊ TẤN PHÁT"
    assert cleaned["k9"] == ""
