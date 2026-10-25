"""Behavior tests for the model-independent parts of worker providers (ADR 0023, ADR 0024)."""

from __future__ import annotations

import json

from system1.providers.asr import audio_extract_command
from system1.providers.captions import CAPTION_PROMPT, has_repetition_loop, parse_caption
from system1.providers.ocr import (
    CropCache,
    clean_ocr_lines,
    frame_text_hashes,
    reading_order_rects,
    should_rerun_ocr,
)
from system1.providers.text_embedding import e5_passages, e5_queries

GOOD = {
    "caption": "Một thầy giáo áo xanh đậm chỉ vào phép cộng trên bảng xanh.",
    "objects": ["bảng xanh", "phấn"],
    "actions": ["chỉ vào bảng"],
    "visible_text": "Thắp sáng tương lai bằng con chữ",
}


def test_valid_caption_json_is_accepted() -> None:
    result = parse_caption(json.dumps(GOOD, ensure_ascii=False))

    assert result.payload == GOOD
    assert result.problems == ()


def test_invalid_json_is_rejected() -> None:
    result = parse_caption('{"caption": "cut off')

    assert result.payload is None
    assert result.problems == ("invalid_json",)


def test_missing_field_is_rejected() -> None:
    payload = {key: value for key, value in GOOD.items() if key != "actions"}

    assert parse_caption(json.dumps(payload)).payload is None


def test_repetition_loop_in_any_field_is_rejected() -> None:
    looped = {**GOOD, "visible_text": "764 + 146 " + "7 0 " * 40}

    result = parse_caption(json.dumps(looped))

    assert result.payload is None
    assert "repetition_loop" in result.problems


def test_prompt_echo_caption_is_rejected() -> None:
    echoed = {**GOOD, "caption": "<one or two sentences>"}

    assert "prompt_echo" in parse_caption(json.dumps(echoed)).problems


def test_ordinary_text_is_not_a_loop() -> None:
    assert not has_repetition_loop("Clip bạn đọc dự thi cuộc thi: Lan tỏa năng lượng tích cực 2024")
    assert has_repetition_loop("a b " * 20)


def test_caption_prompt_has_no_placeholder_text() -> None:
    assert "<" not in CAPTION_PROMPT


def test_ocr_rects_follow_reading_order_and_drop_tiny_boxes() -> None:
    boxes = [
        [[100, 60], [190, 60], [190, 80], [100, 80]],
        [[10, 10], [90, 10], [90, 30], [10, 30]],
        [[10, 60], [90, 60], [90, 80], [10, 80]],
        [[5, 5], [8, 5], [8, 8], [5, 8]],
    ]

    rects = reading_order_rects(boxes, width=200, height=100, padding=4, min_size=8)

    assert [rect[:2] for rect in rects] == [(6, 6), (6, 56), (96, 56)]


def test_ocr_noise_lines_are_dropped_but_numbers_and_words_kept() -> None:
    lines = ["1", "8", "ĐÀM", "764", "Thầy Lê Tấn Phát", "  ", "#"]

    assert clean_ocr_lines(lines, min_chars=3) == ["ĐÀM", "764", "Thầy Lê Tấn Phát"]


def test_e5_inputs_carry_the_required_prefixes() -> None:
    assert e5_passages(["xin chào"]) == ["passage: xin chào"]
    assert e5_queries(["xin chào"]) == ["query: xin chào"]


def test_audio_is_extracted_as_16k_mono_wav(tmp_path) -> None:
    command = audio_extract_command(tmp_path / "v.mp4", tmp_path / "v.wav")

    assert command[0] == "ffmpeg"
    assert ["-ac", "1"] == command[command.index("-ac"):command.index("-ac") + 2]
    assert ["-ar", "16000"] == command[command.index("-ar"):command.index("-ar") + 2]
    assert command[-1] == str(tmp_path / "v.wav")


def _frame(band_seed: int | None = None):
    import numpy as np
    from PIL import Image

    pixels = np.random.default_rng(0).integers(0, 255, (240, 320, 3), dtype=np.uint8)
    if band_seed is not None:
        pixels[160:] = np.random.default_rng(band_seed).integers(0, 255, (80, 320, 3), dtype=np.uint8)
    return Image.fromarray(pixels)


def test_frame_text_hashes_detect_a_changed_lower_band() -> None:
    first, again, changed = frame_text_hashes(_frame()), frame_text_hashes(_frame()), frame_text_hashes(_frame(7))
    assert first == again
    assert bin(first[1] ^ changed[1]).count("1") / 64 >= 0.3


def test_ocr_reruns_on_first_keyframe_and_band_change_only() -> None:
    first, changed = frame_text_hashes(_frame()), frame_text_hashes(_frame(7))
    assert should_rerun_ocr(None, first, min_change=0.15)
    assert should_rerun_ocr(first, changed, min_change=0.15)
    assert not should_rerun_ocr(first, first, min_change=0.15)


def test_crop_cache_reuses_text_for_a_slightly_shifted_crop() -> None:
    from PIL import Image, ImageDraw

    canvas = Image.new("RGB", (320, 240), "white")
    ImageDraw.Draw(canvas).text((20, 100), "THOI SU", fill="black")
    cache = CropCache()
    crop = canvas.crop((10, 90, 130, 120))
    shifted = canvas.crop((12, 91, 132, 121))  # detection box moved by two pixels
    other = _frame(7).crop((0, 200, 120, 230))
    assert cache.get(crop) is None
    cache.put(crop, "THỜI SỰ")
    assert cache.get(crop.copy()) == "THỜI SỰ"
    assert cache.get(shifted) == "THỜI SỰ"
    assert cache.get(other) is None
    assert (cache.hits, cache.misses) == (2, 2)


def test_ocr_lines_with_few_vietnamese_syllables_are_dropped() -> None:
    lines = ["tucitrery", "lorem ipsum dolor", "Nhiều điểm sáng trong phát triển kinh tế xã hội",
             "06:32:58", "VTV1", "Hà Nội 25°C", "Thời sự"]
    assert clean_ocr_lines(lines, min_chars=3, min_syllable_ratio=0.6) == lines[2:]
    assert clean_ocr_lines(lines, min_chars=3) == lines
