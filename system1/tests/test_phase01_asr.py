from __future__ import annotations

import hashlib
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType, SimpleNamespace

import numpy as np
import pytest

from system1.asr import AsrResult
from system1.asr import transcribe_video as transcribe_with_configured_provider
from system1.asr.faster_whisper import build_shot_transcript_links, transcribe_video
from system1.asr.vad import SpeechRange


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
        "compute_type": {
            "cuda_default": "float16",
            "cuda_oom_retry": "int8_float16",
            "cpu": "int8",
        },
        "total_attempts": 2,
    }


def nemo_config() -> dict:
    return {
        "provider": "nemo",
        "model_id": "nvidia/parakeet-ctc-0.6b-vi",
        "model_revision": "revision",
        "language": "vi",
        "total_attempts": 1,
        "segmentation": {
            "provider": "silero_vad_onnx",
            "max_speech_seconds": 30,
        },
        "decoder": {
            "strategy": "flashlight",
            "beam_size": 64,
            "beam_alpha": 0.3,
            "beam_beta": 0.5,
            "beam_size_token": 32,
            "beam_threshold": 20,
            "language_model_sha256": "a" * 64,
            "lexicon_sha256": "b" * 64,
        },
        "quality_gate": {
            "require_acoustic_metrics": True,
            "min_lexical_chars": 2,
            "min_characters_per_second": 0.01,
            "max_characters_per_second": 100,
            "max_blank_argmax_ratio": 0.99,
            "min_mean_nonblank_posterior": 0.01,
            "max_normalized_entropy": 0.99,
            "max_adjacent_low_information_repeats": 2,
            "low_information_max_chars": 12,
            "low_information_max_tokens": 3,
        },
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


def test_asr_dispatch_without_provider_uses_nemo(monkeypatch) -> None:
    from system1 import asr

    expected = AsrResult("no_audio", [], None, 0, None)
    monkeypatch.setattr(asr, "_transcribe_nemo", lambda *_args, **_kwargs: expected)
    monkeypatch.setattr(
        asr,
        "_transcribe_faster_whisper",
        lambda *_args, **_kwargs: pytest.fail("faster-whisper should not be default"),
    )
    result = asr.transcribe_video(
        "unused.mp4",
        video_id="L21_V001",
        frame_timeline=timeline(),
        config={},
        audio_present=False,
    )
    assert result is expected


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
        model_factory=lambda *_args, **_kwargs: FakeModel(
            [Segment(0.08, 0.20, " Xin chào ")]
        ),
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


class FakeHypothesis:
    def __init__(self, text: str) -> None:
        self.text = text
        self.alignments = np.asarray(
            [[6.0, 0.0, -4.0], [0.0, 6.0, -4.0], [5.0, 0.0, -3.0]]
        )


class FakeNemoModel:
    def __init__(self, texts: list[str], events: list[str] | None = None) -> None:
        self.texts = iter(texts)
        self.events = events if events is not None else []
        self.decoder = SimpleNamespace(vocabulary=["a", "b"])

    def to(self, _device: str):
        self.events.append("to")
        return self

    def eval(self) -> None:
        self.events.append("eval")

    def transcribe(self, paths, **kwargs):
        assert len(paths) == 1
        assert kwargs == {
            "batch_size": 1,
            "return_hypotheses": True,
            "verbose": False,
        }
        self.events.append("transcribe")
        return [FakeHypothesis(next(self.texts))]


def test_nemo_streams_one_speech_segment_and_emits_diagnostics(
    monkeypatch, tmp_path: Path
) -> None:
    from system1.asr import nemo

    monkeypatch.setattr(nemo, "_media_duration", lambda _path: 2.0)
    monkeypatch.setattr(
        nemo,
        "_extract_audio_segment",
        lambda _video, output, **_kwargs: output.write_bytes(b"wav"),
    )
    ranges = [SpeechRange(0.0, 1.0, 0), SpeechRange(1.0, 2.0, 1)]
    result = transcribe_with_configured_provider(
        tmp_path / "video.mp4",
        video_id="L21_V001",
        frame_timeline=timeline(),
        config=nemo_config(),
        audio_present=True,
        model_factory=lambda *_args, **_kwargs: FakeNemoModel(["Xin chào", ""]),
        speech_range_detector=lambda *_args, **_kwargs: ranges,
    )
    assert result.status == "pass"
    assert len(result.rows) == 1
    assert result.rows[0]["provider"] == "nemo"
    assert result.rows[0]["text"] == "Xin chào"
    assert [item["accepted"] for item in result.diagnostics] == [True, False]
    assert result.status_details["decoder"]["beam_size"] == 64


def test_nemo_marks_detected_speech_low_confidence_when_all_rows_are_rejected(
    monkeypatch, tmp_path: Path
) -> None:
    from system1.asr import nemo

    monkeypatch.setattr(nemo, "_media_duration", lambda _path: 1.0)
    monkeypatch.setattr(
        nemo,
        "_extract_audio_segment",
        lambda _video, output, **_kwargs: output.write_bytes(b"wav"),
    )
    result = transcribe_with_configured_provider(
        tmp_path / "video.mp4",
        video_id="L21_V001",
        frame_timeline=timeline(),
        config=nemo_config(),
        audio_present=True,
        model_factory=lambda *_args, **_kwargs: FakeNemoModel([""]),
        speech_range_detector=lambda *_args, **_kwargs: [
            SpeechRange(0.0, 1.0, 0)
        ],
    )

    assert result.status == "low_confidence"
    assert result.rows == []
    assert result.diagnostics[0]["reason_codes"] == [
        "empty_text",
        "insufficient_lexical_content",
        "character_rate_too_low",
    ]


def test_nemo_skips_model_load_when_vad_finds_no_speech(
    monkeypatch, tmp_path: Path
) -> None:
    from system1.asr import nemo

    monkeypatch.setattr(nemo, "_media_duration", lambda _path: 2.0)
    result = nemo.transcribe_video(
        tmp_path / "video.mp4",
        video_id="L21_V001",
        frame_timeline=timeline(),
        config=nemo_config(),
        audio_present=True,
        model_factory=lambda *_args, **_kwargs: pytest.fail("model must not load"),
        speech_range_detector=lambda *_args, **_kwargs: [],
    )
    assert result.status == "no_speech"
    assert result.attempts == 0


def test_nemo_runs_memory_guard_before_load_and_releases_after_use(
    monkeypatch, tmp_path: Path
) -> None:
    from system1.asr import nemo

    events: list[str] = []
    monkeypatch.setattr(nemo, "_media_duration", lambda _path: 1.0)
    monkeypatch.setattr(
        nemo,
        "_extract_audio_segment",
        lambda _video, output, **_kwargs: output.write_bytes(b"wav"),
    )
    monkeypatch.setattr(nemo, "_release_gpu_memory", lambda: events.append("release"))
    result = nemo.transcribe_video(
        tmp_path / "video.mp4",
        video_id="L21_V001",
        frame_timeline=timeline(),
        config=nemo_config(),
        model_factory=lambda *_args, **_kwargs: events.append("load")
        or FakeNemoModel(["Xin chào"], events),
        audio_present=True,
        pre_load_callback=lambda provider: events.append(f"guard:{provider}"),
        speech_range_detector=lambda *_args, **_kwargs: [SpeechRange(0, 1, 0)],
    )
    assert result.status == "pass"
    assert events == [
        "guard:nemo_flashlight_beam64",
        "load",
        "to",
        "eval",
        "transcribe",
        "release",
    ]


def test_nemo_snapshot_download_verifies_all_decoder_artifacts(
    monkeypatch, tmp_path: Path
) -> None:
    from system1.asr import nemo

    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    files = {
        "parakeet.nemo": b"model",
        "language.bin": b"language",
        "words.lexicon": b"lexicon",
    }
    for name, content in files.items():
        (snapshot / name).write_bytes(content)
    configured: list[tuple[Path, Path]] = []

    class FakeAsrModel:
        @staticmethod
        def restore_from(path):
            return path

    nemo_module = ModuleType("nemo")
    collections_module = ModuleType("nemo.collections")
    asr_module = ModuleType("nemo.collections.asr")
    asr_module.models = SimpleNamespace(ASRModel=FakeAsrModel)
    nemo_module.collections = collections_module
    collections_module.asr = asr_module
    monkeypatch.setitem(sys.modules, "nemo", nemo_module)
    monkeypatch.setitem(sys.modules, "nemo.collections", collections_module)
    monkeypatch.setitem(sys.modules, "nemo.collections.asr", asr_module)
    omegaconf_module = ModuleType("omegaconf")
    omegaconf_module.OmegaConf = SimpleNamespace(create=lambda value: value)
    monkeypatch.setitem(sys.modules, "omegaconf", omegaconf_module)
    monkeypatch.setattr(nemo, "snapshot_download", lambda **_kwargs: str(snapshot))
    monkeypatch.setattr(
        nemo,
        "_configure_flashlight_decoder",
        lambda _model, _decoder, *, lm_path, lexicon_path, omega_conf: configured.append(
            (lm_path, lexicon_path)
        ),
    )
    restored = nemo._load_pinned_nemo_model(
        "nvidia/parakeet-ctc-0.6b-vi",
        config={
            "model_revision": "revision",
            "model_file": "parakeet.nemo",
            "model_sha256": hashlib.sha256(files["parakeet.nemo"]).hexdigest(),
            "decoder": {
                "language_model_file": "language.bin",
                "language_model_sha256": hashlib.sha256(files["language.bin"]).hexdigest(),
                "lexicon_file": "words.lexicon",
                "lexicon_sha256": hashlib.sha256(files["words.lexicon"]).hexdigest(),
            },
        },
    )
    assert restored == str(snapshot / "parakeet.nemo")
    assert configured == [(snapshot / "language.bin", snapshot / "words.lexicon")]


def test_nemo_decoder_uses_model_card_flashlight_settings() -> None:
    from system1.asr.nemo import _configure_flashlight_decoder

    model = SimpleNamespace(change_decoding_strategy=lambda value: setattr(model, "cfg", value))
    decoder = nemo_config()["decoder"]
    _configure_flashlight_decoder(
        model,
        decoder,
        lm_path=Path("language.bin"),
        lexicon_path=Path("words.lexicon"),
        omega_conf=SimpleNamespace(create=lambda value: value),
    )
    assert model.cfg["strategy"] == "flashlight"
    assert model.cfg["preserve_alignments"] is True
    assert model.cfg["beam"]["beam_size"] == 64
    assert model.cfg["beam"]["ngram_lm_model"] == "language.bin"
    assert model.cfg["beam"]["ngram_lm_alpha"] == 0.3
    assert model.cfg["beam"]["flashlight_cfg"]["beam_size_token"] == 32


def test_deterministic_nemo_model_error_is_not_retried(tmp_path: Path) -> None:
    from system1.asr import nemo

    attempts = 0

    def factory(*_args, **_kwargs):
        nonlocal attempts
        attempts += 1
        raise ValueError("invalid model revision")

    with pytest.raises(ValueError, match="invalid model revision"):
        nemo.transcribe_video(
            tmp_path / "video.mp4",
            video_id="v",
            frame_timeline=timeline(),
            config=nemo_config(),
            audio_present=True,
            model_factory=factory,
            speech_range_detector=lambda *_args, **_kwargs: [SpeechRange(0, 1, 0)],
        )
    assert attempts == 1


def test_nemo_resource_failure_retries_without_greedy_fallback(
    monkeypatch, tmp_path: Path
) -> None:
    from system1.asr import nemo

    attempts = 0
    configured = nemo_config()
    configured["total_attempts"] = 2
    monkeypatch.setattr(nemo, "_release_gpu_memory", lambda: None)

    def factory(*_args, **_kwargs):
        nonlocal attempts
        attempts += 1
        raise RuntimeError("CUDA out of memory")

    with pytest.raises(nemo.AsrResourceError, match="greedy decoding is forbidden"):
        nemo.transcribe_video(
            tmp_path / "video.mp4",
            video_id="v",
            frame_timeline=timeline(),
            config=configured,
            audio_present=True,
            model_factory=factory,
            speech_range_detector=lambda *_args, **_kwargs: [SpeechRange(0, 1, 0)],
        )
    assert attempts == 2
