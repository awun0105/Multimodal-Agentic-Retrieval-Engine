from __future__ import annotations

import wave
from dataclasses import dataclass
from pathlib import Path

import pytest

from system1.asr import transcribe_video as transcribe_with_configured_provider
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


def test_nemo_provider_emits_canonical_chunk_rows(monkeypatch, tmp_path: Path) -> None:
    from system1.asr import nemo

    class FakeNemoModel:
        def to(self, _device):
            return self

        def eval(self) -> None:
            return None

        def transcribe(self, paths, *, batch_size):
            assert batch_size == 2
            assert len(paths) == 2
            return [" Xin chào ", ""]

    def fake_segment_audio(_video_path, output_pattern, ranges):
        assert ranges == [(0.0, 1.0, 0), (1.0, 2.0, 1)]
        for _start, _end, index in ranges:
            path = Path(str(output_pattern) % index)
            with wave.open(str(path), "wb") as handle:
                handle.setnchannels(1)
                handle.setsampwidth(2)
                handle.setframerate(16000)
                handle.writeframes(b"\0\0" * 16000)

    monkeypatch.setattr(nemo, "_segment_audio", fake_segment_audio)
    monkeypatch.setattr(
        nemo,
        "_segment_ranges",
        lambda _video_path, _frame_timeline, _config: [(0.0, 1.0, 0), (1.0, 2.0, 1)],
    )
    result = transcribe_with_configured_provider(
        tmp_path / "video.mp4",
        video_id="L21_V001",
        frame_timeline=timeline(),
        config={
            "provider": "nemo",
            "model_id": "nvidia/parakeet-ctc-0.6b-Vietnamese",
            "model_revision": "revision",
            "language": "vi",
            "max_segment_seconds": 1,
            "batch_size": 2,
            "total_attempts": 1,
        },
        audio_present=True,
        model_factory=lambda _model_id: FakeNemoModel(),
    )
    assert result.status == "pass"
    assert result.rows == [
        {
            "asr_segment_id": "L21_V001_ASR00000",
            "video_id": "L21_V001",
            "start_sec": 0.0,
            "end_sec": 1.0,
            "start_frame": 0,
            "end_frame": 25,
            "text": "Xin chào",
            "language": "vi",
            "confidence": None,
            "avg_logprob": None,
            "no_speech_prob": None,
            "provider": "nemo",
            "model_name": "nvidia/parakeet-ctc-0.6b-Vietnamese",
            "model_version": "revision",
            "status": "pass",
        }
    ]


def test_nemo_silencedetect_ranges_are_speech_segments(monkeypatch, tmp_path: Path) -> None:
    from system1.asr import nemo

    class Result:
        returncode = 0
        stderr = """
        [silencedetect @ 0x1] silence_start: 1.000
        [silencedetect @ 0x1] silence_end: 2.000 | silence_duration: 1.000
        [silencedetect @ 0x1] silence_start: 5.000
        [silencedetect @ 0x1] silence_end: 6.000 | silence_duration: 1.000
        """

    monkeypatch.setattr(nemo.subprocess, "run", lambda *_args, **_kwargs: Result())
    monkeypatch.setattr(nemo, "_media_duration", lambda _path: 8.0)

    ranges = nemo._segment_ranges(
        tmp_path / "video.mp4",
        frame_timeline=timeline(),
        config={
            "segmentation": "ffmpeg_silence",
            "max_segment_seconds": 4.0,
            "min_segment_seconds": 0.4,
            "speech_pad_seconds": 0.2,
            "silence_db": -35,
            "min_silence_duration": 0.6,
        },
    )

    assert ranges == [
        (0.0, 1.2, 0),
        (1.8, 5.2, 1),
        (5.8, 8.0, 2),
    ]


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
