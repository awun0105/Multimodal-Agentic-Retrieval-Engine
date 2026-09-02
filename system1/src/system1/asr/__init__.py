from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from .alignment import AsrAlignmentError
from .contracts import AsrResult
from .faster_whisper import transcribe_video as _transcribe_faster_whisper
from .links import (
    assign_words_to_intervals,
    build_interval_transcript,
    build_interval_transcripts,
    build_scene_transcript_links,
    build_shot_transcript_links,
)
from .nemo import AsrResourceError
from .nemo import transcribe_video as _transcribe_nemo
from .runtime import has_audio_stream


def transcribe_video(
    video_path: Path | str,
    *,
    video_id: str,
    frame_timeline: list[dict[str, Any]],
    config: Mapping[str, Any],
    model_factory: Callable[..., Any] | None = None,
    audio_present: bool | None = None,
    pre_load_callback: Callable[[str], None] | None = None,
    speech_range_detector: Callable[..., Any] | None = None,
) -> AsrResult:
    provider = str(config.get("provider", "nemo"))
    if provider == "faster_whisper":
        return _transcribe_faster_whisper(
            video_path,
            video_id=video_id,
            frame_timeline=frame_timeline,
            config=config,
            model_factory=model_factory,
            audio_present=audio_present,
            pre_load_callback=pre_load_callback,
        )
    if provider == "nemo":
        return _transcribe_nemo(
            video_path,
            video_id=video_id,
            frame_timeline=frame_timeline,
            config=config,
            model_factory=model_factory,
            audio_present=audio_present,
            pre_load_callback=pre_load_callback,
            speech_range_detector=speech_range_detector,
        )
    raise ValueError(f"Unsupported Phase01 ASR provider: {provider}")

__all__ = [
    "AsrAlignmentError",
    "AsrResourceError",
    "AsrResult",
    "assign_words_to_intervals",
    "build_interval_transcript",
    "build_interval_transcripts",
    "build_scene_transcript_links",
    "build_shot_transcript_links",
    "has_audio_stream",
    "transcribe_video",
]
