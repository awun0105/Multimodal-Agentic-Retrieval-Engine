from __future__ import annotations

import math

import pandas as pd
import pytest

from system1.asr import (
    assign_words_to_intervals,
    build_interval_transcripts,
    build_scene_transcript_links,
    build_shot_transcript_links,
)
from system1.phase01.validation import _validate_asr_words, _validate_links


def _word(index: int, text: str, start: float, end: float) -> dict:
    return {
        "asr_word_id": f"v_ASR00000_W{index:05d}",
        "asr_segment_id": "v_ASR00000",
        "word_index": index,
        "text": text,
        "start_sec": start,
        "end_sec": end,
    }


def test_cross_shot_words_are_attributed_once_without_segment_leakage() -> None:
    shots = [
        {"video_id": "v", "shot_id": "s0", "start_sec": 0.0, "end_sec": 1.0},
        {"video_id": "v", "shot_id": "s1", "start_sec": 1.0, "end_sec": 2.0},
    ]
    segment = {
        "video_id": "v",
        "asr_segment_id": "v_ASR00000",
        "start_sec": 0.5,
        "end_sec": 1.5,
    }
    words = [
        _word(0, "xin", 0.55, 0.72),
        _word(1, "chào", 0.74, 0.95),
        _word(2, "mọi", 1.07, 1.20),
        _word(3, "người", 1.22, 1.42),
    ]
    assert build_interval_transcripts(shots, words, entity_id_field="shot_id") == {
        "s0": "xin chào",
        "s1": "mọi người",
    }
    links = build_shot_transcript_links(shots, [segment], words)
    assert [row["assigned_word_count"] for row in links] == [2, 2]
    assert [row["coverage"] for row in links] == [0.5, 0.5]


def test_cross_scene_words_are_attributed_once() -> None:
    scenes = [
        {"video_id": "v", "scene_id": "c0", "start_sec": 0.0, "end_sec": 10.0},
        {"video_id": "v", "scene_id": "c1", "start_sec": 10.0, "end_sec": 20.0},
    ]
    segment = {
        "video_id": "v",
        "asr_segment_id": "v_ASR00000",
        "start_sec": 8.0,
        "end_sec": 13.0,
    }
    words = [
        _word(0, "chúng", 8.2, 8.5),
        _word(1, "ta", 8.6, 8.8),
        _word(2, "sang", 9.6, 9.9),
        _word(3, "phần", 10.2, 10.5),
        _word(4, "tiếp", 10.6, 10.9),
        _word(5, "theo", 11.0, 11.4),
    ]
    transcripts = build_interval_transcripts(scenes, words, entity_id_field="scene_id")
    assert transcripts == {"c0": "chúng ta sang", "c1": "phần tiếp theo"}
    links = build_scene_transcript_links(scenes, [segment], words)
    assert [row["assigned_word_count"] for row in links] == [3, 3]
    assert math.isclose(links[0]["segment_coverage"], 0.4)
    assert math.isclose(links[1]["segment_coverage"], 0.6)
    assert links[0]["coverage"] == links[0]["segment_coverage"]


def test_exact_boundary_tie_is_owned_by_right_half_open_interval() -> None:
    intervals = [
        {"entity_id": "left", "start_sec": 0.0, "end_sec": 1.0},
        {"entity_id": "right", "start_sec": 1.0, "end_sec": 2.0},
    ]
    assignments = assign_words_to_intervals(
        intervals,
        [_word(0, "giữa", 0.9, 1.1)],
        entity_id_field="entity_id",
    )
    assert assignments["left"] == []
    assert [row["text"] for row in assignments["right"]] == ["giữa"]


def test_one_utterance_crosses_shots_but_appears_once_in_scene() -> None:
    shots = [
        {"shot_id": "s0", "start_sec": 0.0, "end_sec": 1.0},
        {"shot_id": "s1", "start_sec": 1.0, "end_sec": 2.0},
    ]
    scenes = [{"scene_id": "c0", "start_sec": 0.0, "end_sec": 2.0}]
    words = [_word(0, "xin", 0.6, 0.8), _word(1, "chào", 1.2, 1.4)]
    assert build_interval_transcripts(shots, words, entity_id_field="shot_id") == {
        "s0": "xin",
        "s1": "chào",
    }
    assert build_interval_transcripts(scenes, words, entity_id_field="scene_id") == {
        "c0": "xin chào"
    }


def _canonical_segment() -> dict:
    return {
        "asr_segment_id": "v_ASR00000",
        "video_id": "v",
        "start_sec": 0.0,
        "end_sec": 2.0,
        "start_frame": 0,
        "end_frame": 2,
        "text": "xin chào",
        "provider": "nemo",
        "model_name": "fixture",
        "model_version": "revision",
    }


def _canonical_word(index: int, text: str, start: float, end: float) -> dict:
    return {
        **_word(index, text, start, end),
        "video_id": "v",
        "start_frame": index,
        "end_frame": index + 1,
        "provider": "nemo",
        "model_name": "fixture",
        "model_version": "revision",
    }


def test_package_word_validation_rejects_missing_or_mismatched_alignment() -> None:
    segments = pd.DataFrame([_canonical_segment()])
    valid_words = pd.DataFrame(
        [
            _canonical_word(0, "xin", 0.2, 0.6),
            _canonical_word(1, "chào", 1.0, 1.4),
        ]
    )
    _validate_asr_words(segments, valid_words, video_id="v")

    with pytest.raises(ValueError, match="no canonical word"):
        _validate_asr_words(segments, valid_words.iloc[0:0], video_id="v")
    mismatched = valid_words.copy()
    mismatched.loc[1, "text"] = "khác"
    with pytest.raises(ValueError, match="do not reconstruct"):
        _validate_asr_words(segments, mismatched, video_id="v")
    orphan = valid_words.copy()
    orphan.loc[0, "asr_segment_id"] = "missing"
    with pytest.raises(ValueError, match="unknown segment"):
        _validate_asr_words(segments, orphan, video_id="v")

    duplicate = pd.concat([valid_words, valid_words.iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="must be unique"):
        _validate_asr_words(segments, duplicate, video_id="v")

    bad_frames = valid_words.copy()
    bad_frames.loc[0, "end_frame"] = 3
    with pytest.raises(ValueError, match="frame range lies outside"):
        _validate_asr_words(segments, bad_frames, video_id="v")

    reversed_time = valid_words.copy()
    reversed_time.loc[0, ["start_sec", "end_sec"]] = [1.5, 1.8]
    with pytest.raises(ValueError, match="not timeline ordered"):
        _validate_asr_words(segments, reversed_time, video_id="v")


def test_package_link_validation_recomputes_assigned_word_count() -> None:
    entities = pd.DataFrame(
        [{"video_id": "v", "shot_id": "s0", "start_sec": 0.0, "end_sec": 2.0}]
    )
    segments = pd.DataFrame([_canonical_segment()])
    words = pd.DataFrame(
        [
            _canonical_word(0, "xin", 0.2, 0.6),
            _canonical_word(1, "chào", 1.0, 1.4),
        ]
    )
    links = pd.DataFrame(
        build_shot_transcript_links(
            entities.to_dict("records"),
            segments.to_dict("records"),
            words.to_dict("records"),
        )
    )
    _validate_links(links, "shot_id", {"s0"}, segments, entities, words)
    links.loc[0, "assigned_word_count"] = 1
    with pytest.raises(ValueError, match="assigned_word_count is inconsistent"):
        _validate_links(links, "shot_id", {"s0"}, segments, entities, words)
