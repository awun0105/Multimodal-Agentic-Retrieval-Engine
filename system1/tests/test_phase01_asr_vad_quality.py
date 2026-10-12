from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from system1.asr.nemo import _apply_adjacent_repetition_gate
from system1.asr.quality import alignment_metrics, evaluate_transcript
from system1.asr.vad import SAMPLE_RATE, _pack_speech_ranges, detect_speech_ranges


def test_vad_merges_short_gaps_but_preserves_natural_long_pause() -> None:
    ranges = _pack_speech_ranges(
        [(0.0, 5.0), (5.4, 10.0), (12.0, 16.0)],
        max_segment_seconds=30,
        merge_gap_seconds=0.7,
        forced_overlap_seconds=0.75,
        minimum_seconds=0.25,
    )
    assert [(item.start_sec, item.end_sec) for item in ranges] == [
        (0.0, 10.0),
        (12.0, 16.0),
    ]
    assert all(not item.forced_split for item in ranges)


def test_vad_uses_30_second_hard_cap_with_overlap_only_for_forced_splits() -> None:
    ranges = _pack_speech_ranges(
        [(0.0, 70.0)],
        max_segment_seconds=30,
        merge_gap_seconds=0.7,
        forced_overlap_seconds=0.75,
        minimum_seconds=0.25,
    )
    assert all(item.end_sec - item.start_sec <= 30 for item in ranges)
    assert [item.overlap_seconds for item in ranges] == [0.0, 0.75, 0.75]
    assert all(item.forced_split for item in ranges)


def test_vad_decodes_bounded_blocks_and_deduplicates_overlap() -> None:
    calls: list[tuple[float, float]] = []

    def decode(_path, start: float, duration: float) -> np.ndarray:
        calls.append((start, duration))
        return np.zeros(round(duration * SAMPLE_RATE), dtype=np.float32)

    def detect(audio: np.ndarray, _config) -> list[dict[str, int]]:
        return [{"start": 0, "end": len(audio)}]

    ranges = detect_speech_ranges(
        "video.mp4",
        duration_seconds=250,
        config={
            "provider": "silero_vad_onnx",
            "block_seconds": 120,
            "block_overlap_seconds": 2,
            "max_speech_seconds": 30,
            "forced_split_overlap_ms": 750,
            "merge_gap_ms": 700,
            "min_speech_duration_ms": 250,
        },
        audio_decoder=decode,
        speech_detector=detect,
    )
    assert calls == [(0.0, 120.0), (118.0, 120.0), (236.0, 14.0)]
    assert ranges[0].start_sec == 0
    assert ranges[-1].end_sec == 250
    assert all(item.end_sec - item.start_sec <= 30 for item in ranges)


def test_alignment_quality_accepts_clear_ctc_hypothesis() -> None:
    hypothesis = SimpleNamespace(
        alignments=np.asarray(
            [[7.0, 0.0, -5.0], [0.0, 7.0, -5.0], [6.0, 0.0, -4.0]]
        )
    )
    metrics = alignment_metrics(hypothesis, blank_index=2)
    decision = evaluate_transcript(
        "xin chào",
        duration_seconds=2,
        acoustic_metrics=metrics,
        config={"require_acoustic_metrics": True},
    )
    assert decision.accepted
    assert metrics["blank_argmax_ratio"] == 0.0


def test_quality_rejects_missing_alignment_and_repetitive_output() -> None:
    decision = evaluate_transcript(
        "aaaaaaaaaa",
        duration_seconds=10,
        acoustic_metrics=alignment_metrics("text"),
        config={
            "require_acoustic_metrics": True,
            "max_same_character_run_ratio": 0.75,
            "repeat_check_min_chars": 6,
        },
    )
    assert not decision.accepted
    assert "missing_acoustic_metrics" in decision.reason_codes
    assert "character_repetition" in decision.reason_codes


def test_adjacent_low_information_repetition_is_diagnostic_only() -> None:
    candidates = [
        {
            "text": "chào",
            "accepted": True,
            "diagnostic": {"accepted": True, "reason_codes": []},
        }
        for _ in range(3)
    ]
    _apply_adjacent_repetition_gate(
        candidates,
        {
            "max_adjacent_low_information_repeats": 2,
            "low_information_max_chars": 12,
            "low_information_max_tokens": 3,
        },
    )
    assert [item["accepted"] for item in candidates] == [False, False, False]
    assert all(
        "adjacent_low_information_repetition"
        in item["diagnostic"]["reason_codes"]
        for item in candidates
    )
