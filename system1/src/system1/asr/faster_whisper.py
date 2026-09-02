from __future__ import annotations

import math
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any

from .alignment import ALIGNMENT_VERSION, AsrAlignmentError
from .contracts import AsrResult
from .quality import normalize_for_comparison
from .runtime import has_audio_stream, is_retryable_local_error, release_gpu_memory
from .timing import index_frame_timeline, time_range_to_frames


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
        return AsrResult(
            status="no_audio",
            segment_rows=[],
            word_rows=[],
            compute_type=None,
            attempts=0,
            detected_language=None,
            status_details=_alignment_status_details([], []),
        )
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
                word_timestamps=True,
            )
            segment_rows, word_rows = _normalize_segments(
                segments,
                video_id=video_id,
                frame_timeline=frame_timeline,
                language=getattr(info, "language", None),
                model_config=config,
            )
            return AsrResult(
                status="pass" if segment_rows else "no_speech",
                segment_rows=segment_rows,
                word_rows=word_rows,
                compute_type=str(compute_type),
                attempts=attempt,
                detected_language=getattr(info, "language", None),
                status_details=_alignment_status_details(segment_rows, word_rows),
            )
        except AsrAlignmentError:
            raise
        except Exception as exc:
            last_error = exc
            if not is_retryable_local_error(exc):
                raise
            if device == "cuda" and _is_oom_error(exc):
                compute_type = config["compute_type"]["cuda_oom_retry"]
            if attempt >= total_attempts:
                break
        finally:
            del model
            release_gpu_memory()
    raise RuntimeError(
        f"faster-whisper failed after {total_attempts} attempt(s): "
        f"{last_error}"
    ) from last_error


def _normalize_segments(
    segments: Iterable[Any],
    *,
    video_id: str,
    frame_timeline: list[dict[str, Any]],
    language: str | None,
    model_config: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    word_rows: list[dict[str, Any]] = []
    timeline_index = index_frame_timeline(frame_timeline)
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
        start_frame, end_frame = time_range_to_frames(start, end, timeline_index)
        segment_id = f"{video_id}_ASR{segment_index:05d}"
        rows.append(
            {
                "asr_segment_id": segment_id,
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
        words = list(getattr(segment, "words", None) or [])
        canonical_words: list[dict[str, Any]] = []
        for word_index, word in enumerate(words):
            word_text = str(getattr(word, "word", "")).strip()
            word_start = float(getattr(word, "start", math.nan))
            word_end = float(getattr(word, "end", math.nan))
            if not word_text or not (
                math.isfinite(word_start)
                and math.isfinite(word_end)
                and start <= word_start < word_end <= end + 1e-6
            ):
                raise AsrAlignmentError(
                    f"faster-whisper returned invalid word timing for {segment_id}"
                )
            word_start_frame, word_end_frame = time_range_to_frames(
                word_start, min(word_end, end), timeline_index
            )
            canonical_words.append(
                {
                    "asr_word_id": f"{segment_id}_W{word_index:05d}",
                    "asr_segment_id": segment_id,
                    "video_id": video_id,
                    "word_index": word_index,
                    "text": word_text,
                    "start_sec": word_start,
                    "end_sec": min(word_end, end),
                    "start_frame": word_start_frame,
                    "end_frame": word_end_frame,
                    "confidence": _finite_or_none(getattr(word, "probability", None)),
                    "alignment_method": "provider_word_timestamps",
                    "alignment_version": ALIGNMENT_VERSION,
                    "provider": "faster_whisper",
                    "model_name": str(model_config["model_id"]),
                    "model_version": str(model_config["model_revision"]),
                    "status": "pass",
                }
            )
        if not canonical_words:
            raise AsrAlignmentError(
                f"Accepted faster-whisper segment has no aligned words: {segment_id}"
            )
        if normalize_for_comparison(text) != normalize_for_comparison(
            " ".join(row["text"] for row in canonical_words)
        ):
            raise AsrAlignmentError(
                f"faster-whisper words do not reconstruct segment text: {segment_id}"
            )
        word_rows.extend(canonical_words)
    return rows, word_rows


def _alignment_status_details(
    segment_rows: list[dict[str, Any]], word_rows: list[dict[str, Any]]
) -> dict[str, Any]:
    accepted = len(segment_rows)
    aligned = len({str(row["asr_segment_id"]) for row in word_rows})
    return {
        "accepted_segment_count": accepted,
        "rejected_segment_count": 0,
        "word_count": len(word_rows),
        "aligned_segment_count": aligned,
        "alignment_failed_segment_count": 0,
        "word_alignment_coverage": aligned / accepted if accepted else 1.0,
        "alignment_method": "provider_word_timestamps",
        "alignment_version": ALIGNMENT_VERSION,
    }


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


def _is_oom_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return "out of memory" in message or "cuda error" in message
