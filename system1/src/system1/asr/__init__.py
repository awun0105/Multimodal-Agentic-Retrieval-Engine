from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from .faster_whisper import (
    AsrResult,
    build_shot_transcript_links,
    has_audio_stream,
)
from .faster_whisper import transcribe_video as _transcribe_faster_whisper
from .nemo import transcribe_video as _transcribe_nemo


def transcribe_video(
    video_path: Path | str,
    *,
    video_id: str,
    frame_timeline: list[dict[str, Any]],
    config: Mapping[str, Any],
    model_factory: Callable[..., Any] | None = None,
    audio_present: bool | None = None,
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
        )
    if provider == "nemo":
        return _transcribe_nemo(
            video_path,
            video_id=video_id,
            frame_timeline=frame_timeline,
            config=config,
            model_factory=model_factory,
            audio_present=audio_present,
        )
    raise ValueError(f"Unsupported Phase01 ASR provider: {provider}")

__all__ = [
    "AsrResult",
    "build_shot_transcript_links",
    "has_audio_stream",
    "transcribe_video",
]
