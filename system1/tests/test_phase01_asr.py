from __future__ import annotations

from dataclasses import dataclass

import pytest

from system1.asr.faster_whisper import build_shot_transcript_links, transcribe_video


@dataclass
class Segment:
    start: float
    end: float
    text: str
    avg_logprob: float = -0.2
    no_speech_prob: float = 0.01


@dataclass
class Info:
    language: str = "vi"


class FakeModel:
    def __init__(self, segments):
        self.segments = segments

    def transcribe(self, *_args, **_kwargs):
        return iter(self.segments), Info()


def config() -> dict:
    return {
        "model_id": "Systran/faster-whisper-large-v3",
        "model_revision": "revision",
        "language": "auto",
        "vad_enabled": True,
        "beam_size": 5,
        "word_timestamps": False,
        "vad_parameters": {"threshold": 0.5, "max_speech_duration_s": None},
        "compute_type": {"cuda_default": "float16", "cuda_oom_retry": "int8_float16", "cpu": "int8"},
        "total_attempts": 2,
    }


def timeline() -> list[dict]:
    return [
        {"frame_id": index, "pts_time": index * 0.04, "duration_time": 0.04}
        for index in range(100)
    ]


def test_no_audio_is_valid_empty_asr() -> None:
    result = transcribe_video(
        "unused.mp4",
        video_id="L21_V001",
        frame_timeline=timeline(),
        config=config(),
        audio_present=False,
    )
    assert result.status == "no_audio"
    assert result.rows == []


def test_no_speech_is_valid_empty_asr() -> None:
    result = transcribe_video(
        "unused.mp4",
        video_id="L21_V001",
        frame_timeline=timeline(),
        config=config(),
        audio_present=True,
        model_factory=lambda *_args, **_kwargs: FakeModel([]),
    )
    assert result.status == "no_speech"


def test_asr_rows_are_canonical_and_map_to_decoded_frames() -> None:
    result = transcribe_video(
        "unused.mp4",
        video_id="L21_V001",
        frame_timeline=timeline(),
        config=config(),
        audio_present=True,
        model_factory=lambda *_args, **_kwargs: FakeModel([Segment(0.08, 0.20, " Xin chào ")]),
    )
    assert result.status == "pass"
    assert result.rows[0]["text"] == "Xin chào"
    assert (result.rows[0]["start_frame"], result.rows[0]["end_frame"]) == (2, 5)
    assert result.rows[0]["confidence"] is None


def test_transcript_links_use_segment_coverage() -> None:
    shots = [
        {"video_id": "v", "shot_id": "s0", "start_sec": 0.0, "end_sec": 1.0},
        {"video_id": "v", "shot_id": "s1", "start_sec": 1.0, "end_sec": 2.0},
    ]
    segments = [{"asr_segment_id": "a0", "start_sec": 0.5, "end_sec": 1.5}]
    links = build_shot_transcript_links(shots, segments)
    assert [row["coverage"] for row in links] == [0.5, 0.5]


def test_deterministic_model_error_is_not_retried() -> None:
    attempts = 0

    def factory(*_args, **_kwargs):
        nonlocal attempts
        attempts += 1
        raise ValueError("invalid model revision")

    with pytest.raises(ValueError, match="invalid model revision"):
        transcribe_video(
            "unused.mp4",
            video_id="v",
            frame_timeline=timeline(),
            config=config(),
            audio_present=True,
            model_factory=factory,
        )
    assert attempts == 1
