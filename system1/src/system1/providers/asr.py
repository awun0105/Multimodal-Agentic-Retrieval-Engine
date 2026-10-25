"""Speech recognition with ChunkFormer-large-vie (ADR 0023)."""

from __future__ import annotations

import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from system1.text.evidence import AsrSegment, parse_chunkformer_segments


def audio_extract_command(video_path: Path, wav_path: Path) -> list[str]:
    """ffmpeg command for the 16 kHz mono WAV that ChunkFormer expects."""

    return ["ffmpeg", "-y", "-loglevel", "error", "-i", str(video_path),
            "-vn", "-ac", "1", "-ar", "16000", str(wav_path)]


class ChunkFormerAsr:
    def __init__(self, config: Mapping[str, Any], device: str = "cuda") -> None:
        import torch
        from chunkformer import ChunkFormerModel

        self._torch = torch
        self.config = config
        # endless_decode runs on the device of the model parameters (CPU by default).
        self.model = ChunkFormerModel.from_pretrained(
            config["model_id"], revision=config["revision"]).to(device)

    def transcribe(self, video_path: Path, wav_path: Path) -> list[AsrSegment]:
        subprocess.run(audio_extract_command(video_path, wav_path), check=True)
        if self._torch.cuda.is_available():
            self._torch.cuda.empty_cache()
        raw = self.model.endless_decode(
            audio_path=str(wav_path),
            chunk_size=int(self.config["chunk_size"]),
            left_context_size=int(self.config["left_context_size"]),
            right_context_size=int(self.config["right_context_size"]),
            total_batch_duration=int(self.config["total_batch_duration_sec"]),
            return_timestamps=True,
        )
        return parse_chunkformer_segments(raw)
