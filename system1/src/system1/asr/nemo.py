from __future__ import annotations

import re
import subprocess
import tempfile
import wave
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from huggingface_hub import snapshot_download

from .faster_whisper import (
    AsrResult,
    _is_retryable_local_error,
    _release_gpu_memory,
    _time_range_to_frames,
    has_audio_stream,
)


def transcribe_video(
    video_path: Path | str,
    *,
    video_id: str,
    frame_timeline: list[dict[str, Any]],
    config: Mapping[str, Any],
    model_factory: Callable[..., Any] | None = None,
    audio_present: bool | None = None,
    pre_load_callback: Callable[[str], None] | None = None,
) -> AsrResult:
    present = has_audio_stream(video_path) if audio_present is None else audio_present
    if not present:
        return AsrResult("no_audio", [], None, 0, None)
    if model_factory is None:
        model_factory = _load_pinned_nemo_model

    total_attempts = int(config.get("total_attempts", 2))
    last_error: Exception | None = None
    for attempt in range(1, total_attempts + 1):
        model = None
        try:
            device = _device()
            if pre_load_callback is not None:
                pre_load_callback("nemo")
            if model_factory is _load_pinned_nemo_model:
                model = model_factory(str(config["model_id"]), config=config)
            else:
                model = model_factory(str(config["model_id"]))
            if hasattr(model, "to"):
                model = model.to(device)
            if hasattr(model, "eval"):
                model.eval()
            rows = _transcribe_chunked(
                model,
                Path(video_path),
                video_id=video_id,
                frame_timeline=frame_timeline,
                config=config,
            )
            return AsrResult("pass" if rows else "no_speech", rows, str(device), attempt, str(config.get("language", "vi")))
        except Exception as exc:
            last_error = exc
            if not _is_retryable_local_error(exc):
                raise
            if attempt >= total_attempts:
                break
        finally:
            del model
            _release_gpu_memory()
    raise RuntimeError(f"NeMo ASR failed after {total_attempts} attempt(s): {last_error}") from last_error


def _transcribe_chunked(
    model: Any,
    video_path: Path,
    *,
    video_id: str,
    frame_timeline: list[dict[str, Any]],
    config: Mapping[str, Any],
) -> list[dict[str, Any]]:
    batch_size = int(config.get("batch_size", 16))
    with tempfile.TemporaryDirectory(prefix="system1_nemo_asr_") as temporary:
        temp_dir = Path(temporary)
        ranges = _segment_ranges(video_path, frame_timeline, config)
        output_pattern = temp_dir / "chunk_%05d.wav"
        _segment_audio(video_path, output_pattern, ranges)
        chunk_paths = sorted(temp_dir.glob("chunk_*.wav"))
        if not chunk_paths:
            return []
        transcriptions = model.transcribe([str(path) for path in chunk_paths], batch_size=batch_size)
        return _normalize_transcriptions(
            transcriptions,
            ranges,
            video_id=video_id,
            frame_timeline=frame_timeline,
            model_config=config,
        )


def _load_pinned_nemo_model(model_id: str, *, config: Mapping[str, Any] | None = None) -> Any:
    try:
        import nemo.collections.asr as nemo_asr
    except ImportError as exc:  # pragma: no cover - production preflight
        raise RuntimeError("nemo_toolkit[asr] is required for NeMo Phase01 ASR") from exc

    model_config = config or {}
    revision = str(model_config.get("model_revision", "")).strip()
    model_file = str(model_config.get("model_file", "")).strip()
    if revision and model_file:
        snapshot_dir = Path(
            snapshot_download(
                repo_id=model_id,
                revision=revision,
                allow_patterns=[model_file],
            )
        )
        return nemo_asr.models.ASRModel.restore_from(str(snapshot_dir / model_file))
    return nemo_asr.models.ASRModel.from_pretrained(model_id)


def _segment_audio(
    video_path: Path,
    output_pattern: Path,
    ranges: list[tuple[float, float, int]],
) -> None:
    for start, end, segment_index in ranges:
        duration = max(0.0, end - start)
        if duration <= 0.0:
            continue
        output_path = Path(str(output_pattern) % segment_index)
        _extract_audio_segment(video_path, output_path, start_sec=start, duration_sec=duration)


def _extract_audio_segment(
    video_path: Path,
    output_path: Path,
    *,
    start_sec: float,
    duration_sec: float,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-ss",
            f"{start_sec:.3f}",
            "-i",
            str(video_path),
            "-t",
            f"{duration_sec:.3f}",
            "-vn",
            "-acodec",
            "pcm_s16le",
            "-ar",
            "16000",
            "-ac",
            "1",
            str(output_path),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
    )


def _segment_ranges(
    video_path: Path,
    frame_timeline: list[dict[str, Any]],
    config: Mapping[str, Any],
) -> list[tuple[float, float, int]]:
    total_duration = _media_duration(video_path) or _timeline_duration(frame_timeline)
    if total_duration <= 0.0:
        return []
    max_segment_seconds = float(config.get("max_segment_seconds", config.get("chunk_seconds", 12.0)))
    if str(config.get("segmentation", "ffmpeg_silence")) != "ffmpeg_silence":
        return _bounded_ranges(0.0, total_duration, max_segment_seconds)
    silences = _detect_silences(
        video_path,
        noise_db=float(config.get("silence_db", -35.0)),
        min_silence_duration=float(config.get("min_silence_duration", 0.6)),
    )
    if not silences:
        return _bounded_ranges(0.0, total_duration, max_segment_seconds)
    pad = float(config.get("speech_pad_seconds", 0.2))
    min_segment_seconds = float(config.get("min_segment_seconds", 0.4))
    speech_ranges: list[tuple[float, float, int]] = []
    cursor = 0.0
    for silence_start, silence_end in silences:
        speech_start = max(0.0, cursor - pad)
        speech_end = min(total_duration, silence_start + pad)
        if speech_end - speech_start >= min_segment_seconds:
            speech_ranges.extend(_bounded_ranges(speech_start, speech_end, max_segment_seconds))
        cursor = max(cursor, silence_end)
    speech_start = max(0.0, cursor - pad)
    if total_duration - speech_start >= min_segment_seconds:
        speech_ranges.extend(_bounded_ranges(speech_start, total_duration, max_segment_seconds))
    return [
        (start, end, index)
        for index, (start, end, _old_index) in enumerate(speech_ranges)
    ] or _bounded_ranges(0.0, total_duration, max_segment_seconds)


def _detect_silences(
    video_path: Path,
    *,
    noise_db: float,
    min_silence_duration: float,
) -> list[tuple[float, float]]:
    result = subprocess.run(
        [
            "ffmpeg",
            "-i",
            str(video_path),
            "-af",
            f"silencedetect=noise={noise_db}dB:d={min_silence_duration}",
            "-f",
            "null",
            "-",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return []
    return _parse_silencedetect(result.stderr)


def _parse_silencedetect(stderr: str) -> list[tuple[float, float]]:
    silences: list[tuple[float, float]] = []
    current_start: float | None = None
    start_pattern = re.compile(r"silence_start:\s*([0-9.]+)")
    end_pattern = re.compile(r"silence_end:\s*([0-9.]+)")
    for line in stderr.splitlines():
        start_match = start_pattern.search(line)
        if start_match:
            current_start = float(start_match.group(1))
            continue
        end_match = end_pattern.search(line)
        if end_match and current_start is not None:
            silence_end = float(end_match.group(1))
            if silence_end > current_start:
                silences.append((current_start, silence_end))
            current_start = None
    return silences


def _bounded_ranges(
    start: float,
    end: float,
    max_segment_seconds: float,
) -> list[tuple[float, float, int]]:
    if end <= start:
        return []
    max_duration = max(0.1, max_segment_seconds)
    ranges: list[tuple[float, float, int]] = []
    current = start
    while current < end:
        next_end = min(end, current + max_duration)
        ranges.append((current, next_end, len(ranges)))
        current = next_end
    return ranges


def _normalize_transcriptions(
    transcriptions: Any,
    ranges: list[tuple[float, float, int]],
    *,
    video_id: str,
    frame_timeline: list[dict[str, Any]],
    model_config: Mapping[str, Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for text_result, (start, end, chunk_index) in zip(list(transcriptions), ranges, strict=False):
        text = _transcription_text(text_result)
        if not text:
            continue
        start_frame, end_frame = _time_range_to_frames(start, end, frame_timeline)
        rows.append(
            {
                "asr_segment_id": f"{video_id}_ASR{chunk_index:05d}",
                "video_id": video_id,
                "start_sec": float(start),
                "end_sec": float(end),
                "start_frame": start_frame,
                "end_frame": end_frame,
                "text": text,
                "language": str(model_config.get("language", "vi")),
                "confidence": None,
                "avg_logprob": None,
                "no_speech_prob": None,
                "provider": "nemo",
                "model_name": str(model_config["model_id"]),
                "model_version": str(model_config["model_revision"]),
                "status": "pass",
            }
        )
    return rows


def _transcription_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    return str(getattr(value, "text", "")).strip()


def _wav_duration(wav_path: Path) -> float:
    with wave.open(str(wav_path), "rb") as handle:
        return handle.getnframes() / float(handle.getframerate())


def _media_duration(video_path: Path) -> float | None:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(video_path),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    try:
        return float(result.stdout.strip())
    except ValueError:
        return None


def _timeline_duration(frame_timeline: list[dict[str, Any]]) -> float:
    if not frame_timeline:
        return 0.0
    last = frame_timeline[-1]
    return float(last["pts_time"]) + float(last.get("duration_time") or 0.0)


def _device() -> str:
    try:
        import torch

        return "cuda:0" if torch.cuda.is_available() else "cpu"
    except ImportError:
        return "cpu"
