from __future__ import annotations

import bisect
import gc
import json
import math
import subprocess
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AsrResult:
    status: str
    rows: list[dict[str, Any]]
    compute_type: str | None
    attempts: int
    detected_language: str | None


def has_audio_stream(video_path: Path | str) -> bool:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a",
            "-show_entries",
            "stream=index",
            "-of",
            "json",
            str(video_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout or "{}")
    return bool(payload.get("streams"))


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
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:  # pragma: no cover - production preflight
            raise RuntimeError("faster-whisper is required for Phase01 ASR") from exc
        model_factory = WhisperModel

    device = "cuda" if _cuda_available() else "cpu"
    total_attempts = int(config.get("total_attempts", 2))
    compute_type = (
        config["compute_type"]["cuda_default"]
        if device == "cuda"
        else config["compute_type"]["cpu"]
    )
    last_error: Exception | None = None
    for attempt in range(1, total_attempts + 1):
        model = None
        try:
            if pre_load_callback is not None:
                pre_load_callback("faster_whisper")
            model = model_factory(
                config["model_id"],
                device=device,
                compute_type=compute_type,
                revision=config["model_revision"],
            )
            segments, info = model.transcribe(
                str(video_path),
                language=None if config.get("language") == "auto" else config.get("language"),
                beam_size=int(config.get("beam_size", 5)),
                vad_filter=bool(config.get("vad_enabled", True)),
                vad_parameters=_normalized_vad_parameters(config.get("vad_parameters", {})),
                word_timestamps=bool(config.get("word_timestamps", False)),
            )
            rows = _normalize_segments(
                segments,
                video_id=video_id,
                frame_timeline=frame_timeline,
                language=getattr(info, "language", None),
                model_config=config,
            )
            return AsrResult(
                "pass" if rows else "no_speech",
                rows,
                str(compute_type),
                attempt,
                getattr(info, "language", None),
            )
        except Exception as exc:
            last_error = exc
            if not _is_retryable_local_error(exc):
                raise
            if device == "cuda" and _is_oom_error(exc):
                compute_type = config["compute_type"]["cuda_oom_retry"]
            if attempt >= total_attempts:
                break
        finally:
            del model
            _release_gpu_memory()
    raise RuntimeError(
        f"faster-whisper failed after {total_attempts} attempt(s): "
        f"{last_error}"
    ) from last_error


def build_shot_transcript_links(
    shots: Iterable[Mapping[str, Any]], segments: Iterable[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for shot in shots:
        shot_start = float(shot["start_sec"])
        shot_end = float(shot["end_sec"])
        for segment in segments:
            segment_start = float(segment["start_sec"])
            segment_end = float(segment["end_sec"])
            overlap = min(shot_end, segment_end) - max(shot_start, segment_start)
            if overlap <= 0:
                continue
            duration = segment_end - segment_start
            if duration <= 0:
                raise ValueError("ASR segment duration must be positive")
            rows.append(
                {
                    "video_id": str(shot["video_id"]),
                    "shot_id": str(shot["shot_id"]),
                    "asr_segment_id": str(segment["asr_segment_id"]),
                    "coverage": min(1.0, max(0.0, overlap / duration)),
                }
            )
    return rows


def _normalize_segments(
    segments: Iterable[Any],
    *,
    video_id: str,
    frame_timeline: list[dict[str, Any]],
    language: str | None,
    model_config: Mapping[str, Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    previous_start = -1.0
    for segment_index, segment in enumerate(segments):
        start = float(segment.start)
        end = float(segment.end)
        text = str(segment.text).strip()
        if not text:
            continue
        if not (math.isfinite(start) and math.isfinite(end) and 0 <= start < end):
            raise ValueError("faster-whisper returned an invalid timestamp range")
        if start < previous_start:
            raise ValueError("faster-whisper segments are not timeline ordered")
        previous_start = start
        start_frame, end_frame = _time_range_to_frames(start, end, frame_timeline)
        rows.append(
            {
                "asr_segment_id": f"{video_id}_ASR{segment_index:05d}",
                "video_id": video_id,
                "start_sec": start,
                "end_sec": end,
                "start_frame": start_frame,
                "end_frame": end_frame,
                "text": text,
                "language": language,
                "confidence": None,
                "avg_logprob": _finite_or_none(getattr(segment, "avg_logprob", None)),
                "no_speech_prob": _finite_or_none(getattr(segment, "no_speech_prob", None)),
                "provider": "faster_whisper",
                "model_name": str(model_config["model_id"]),
                "model_version": str(model_config["model_revision"]),
                "status": "pass",
            }
        )
    return rows


def _time_range_to_frames(
    start: float, end: float, timeline: list[dict[str, Any]]
) -> tuple[int | None, int | None]:
    if not timeline:
        return None, None
    ordered = sorted(timeline, key=lambda row: int(row["frame_id"]))
    timestamps = [float(row["pts_time"]) for row in ordered]
    start_position = max(0, bisect.bisect_right(timestamps, start) - 1)
    end_position = bisect.bisect_left(timestamps, end)
    end_position = min(len(ordered), max(start_position + 1, end_position))
    exclusive_end = (
        int(ordered[end_position]["frame_id"])
        if end_position < len(ordered)
        else int(ordered[-1]["frame_id"]) + 1
    )
    return int(ordered[start_position]["frame_id"]), exclusive_end


def _normalized_vad_parameters(parameters: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in parameters.items() if value is not None}


def _finite_or_none(value: Any) -> float | None:
    if value is None:
        return None
    converted = float(value)
    return converted if math.isfinite(converted) else None


def _cuda_available() -> bool:
    try:
        import torch

        return bool(torch.cuda.is_available())
    except ImportError:
        return False


def _is_retryable_local_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return any(
        marker in message
        for marker in (
            "out of memory",
            "cuda error",
            "temporarily unavailable",
            "resource temporarily unavailable",
            "decode",
            "i/o",
            "input/output",
        )
    )


def _is_oom_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return "out of memory" in message or "cuda error" in message


def _release_gpu_memory() -> None:
    gc.collect()
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except ImportError:
        return
