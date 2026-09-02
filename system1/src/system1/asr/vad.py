from __future__ import annotations

import math
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

SAMPLE_RATE = 16_000


@dataclass(frozen=True)
class SpeechRange:
    start_sec: float
    end_sec: float
    segment_index: int
    forced_split: bool = False
    overlap_seconds: float = 0.0


def detect_speech_ranges(
    video_path: Path | str,
    *,
    duration_seconds: float,
    config: Mapping[str, Any],
    audio_decoder: Callable[[Path, float, float], np.ndarray] | None = None,
    speech_detector: Callable[[np.ndarray, Mapping[str, Any]], list[dict[str, int]]]
    | None = None,
) -> list[SpeechRange]:
    """Run bounded-memory Silero VAD and return timeline-ordered speech ranges."""

    if not math.isfinite(duration_seconds) or duration_seconds <= 0:
        return []
    if str(config.get("provider", "silero_vad_onnx")) != "silero_vad_onnx":
        raise ValueError("NeMo ASR requires the silero_vad_onnx segmentation provider")

    block_seconds = float(config.get("block_seconds", 120.0))
    block_overlap_seconds = float(config.get("block_overlap_seconds", 2.0))
    if block_seconds <= 0 or not 0 <= block_overlap_seconds < block_seconds:
        raise ValueError("VAD block overlap must be non-negative and smaller than the block")

    decode = audio_decoder or _decode_audio_block
    detect = speech_detector or _silero_speech_timestamps
    raw_ranges: list[tuple[float, float]] = []
    block_start = 0.0
    block_step = block_seconds - block_overlap_seconds
    while block_start < duration_seconds:
        block_duration = min(block_seconds, duration_seconds - block_start)
        audio = decode(Path(video_path), block_start, block_duration)
        try:
            if audio.ndim != 1:
                raise ValueError("VAD audio decoder must return one-dimensional mono audio")
            for item in detect(audio, config):
                start_sample = int(item["start"])
                end_sample = int(item["end"])
                if not 0 <= start_sample < end_sample <= len(audio):
                    raise ValueError("Silero VAD returned an invalid sample range")
                start = block_start + start_sample / SAMPLE_RATE
                end = block_start + end_sample / SAMPLE_RATE
                raw_ranges.append(
                    (max(0.0, start), min(duration_seconds, end))
                )
        finally:
            del audio
        if block_start + block_duration >= duration_seconds:
            break
        block_start += block_step

    deduplicated = _merge_overlapping_ranges(raw_ranges)
    return _pack_speech_ranges(
        deduplicated,
        max_segment_seconds=float(config.get("max_speech_seconds", 30.0)),
        merge_gap_seconds=float(config.get("merge_gap_ms", 700)) / 1000.0,
        forced_overlap_seconds=float(config.get("forced_split_overlap_ms", 750))
        / 1000.0,
        minimum_seconds=float(config.get("min_speech_duration_ms", 250)) / 1000.0,
    )


def _decode_audio_block(
    video_path: Path,
    start_sec: float,
    duration_sec: float,
) -> np.ndarray:
    result = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-ss",
            f"{start_sec:.3f}",
            "-i",
            str(video_path),
            "-t",
            f"{duration_sec:.3f}",
            "-vn",
            "-acodec",
            "pcm_f32le",
            "-ar",
            str(SAMPLE_RATE),
            "-ac",
            "1",
            "-f",
            "f32le",
            "pipe:1",
        ],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        message = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"FFmpeg VAD block decode failed: {message[-1000:]}")
    return np.frombuffer(result.stdout, dtype="<f4").copy()


def _silero_speech_timestamps(
    audio: np.ndarray,
    config: Mapping[str, Any],
) -> list[dict[str, int]]:
    try:
        from faster_whisper.vad import VadOptions, get_speech_timestamps
    except ImportError as exc:  # pragma: no cover - production preflight
        raise RuntimeError(
            "faster-whisper with Silero VAD is required for NeMo Phase01 ASR"
        ) from exc

    threshold = float(config.get("threshold", 0.5))
    options = VadOptions(
        threshold=threshold,
        neg_threshold=float(config.get("neg_threshold", threshold - 0.15)),
        min_speech_duration_ms=int(config.get("min_speech_duration_ms", 250)),
        max_speech_duration_s=float("inf"),
        min_silence_duration_ms=int(config.get("min_silence_duration_ms", 700)),
        speech_pad_ms=int(config.get("speech_pad_ms", 350)),
    )
    return list(
        get_speech_timestamps(
            audio,
            vad_options=options,
            sampling_rate=SAMPLE_RATE,
        )
    )


def _merge_overlapping_ranges(
    ranges: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    merged: list[list[float]] = []
    for start, end in sorted(ranges):
        if end <= start:
            continue
        if merged and start <= merged[-1][1] + 0.05:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [(start, end) for start, end in merged]


def _pack_speech_ranges(
    ranges: list[tuple[float, float]],
    *,
    max_segment_seconds: float,
    merge_gap_seconds: float,
    forced_overlap_seconds: float,
    minimum_seconds: float,
) -> list[SpeechRange]:
    if max_segment_seconds <= 0:
        raise ValueError("VAD max speech duration must be positive")
    if not 0 <= forced_overlap_seconds < max_segment_seconds:
        raise ValueError("Forced split overlap must be smaller than max speech duration")

    packed: list[tuple[float, float, bool, float]] = []
    current: tuple[float, float] | None = None
    for start, end in ranges:
        if end - start < minimum_seconds:
            continue
        if current is None:
            current = (start, end)
            continue
        gap = start - current[1]
        if gap <= merge_gap_seconds and end - current[0] <= max_segment_seconds:
            current = (current[0], end)
        else:
            packed.extend(
                _split_continuous_range(
                    *current,
                    max_segment_seconds=max_segment_seconds,
                    overlap_seconds=forced_overlap_seconds,
                )
            )
            current = (start, end)
    if current is not None:
        packed.extend(
            _split_continuous_range(
                *current,
                max_segment_seconds=max_segment_seconds,
                overlap_seconds=forced_overlap_seconds,
            )
        )

    return [
        SpeechRange(
            start_sec=start,
            end_sec=end,
            segment_index=index,
            forced_split=forced,
            overlap_seconds=overlap,
        )
        for index, (start, end, forced, overlap) in enumerate(packed)
        if end - start >= minimum_seconds
    ]


def _split_continuous_range(
    start: float,
    end: float,
    *,
    max_segment_seconds: float,
    overlap_seconds: float,
) -> list[tuple[float, float, bool, float]]:
    if end - start <= max_segment_seconds:
        return [(start, end, False, 0.0)]
    output: list[tuple[float, float, bool, float]] = []
    cursor = start
    while cursor < end:
        segment_end = min(end, cursor + max_segment_seconds)
        output.append(
            (cursor, segment_end, True, overlap_seconds if output else 0.0)
        )
        if segment_end >= end:
            break
        cursor = segment_end - overlap_seconds
    return output
