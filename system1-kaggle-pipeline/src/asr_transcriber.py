"""
Phase 01: Audio ASR Transcription & Timestamping
Module nhận diện giọng nói tiếng Việt sử dụng faster-whisper large-v3 trên GPU/CPU.
Tối ưu hóa bóc tách lời thoại cho: Tin tức HTV/VTV, Phỏng vấn, Nấu ăn, Bài giảng trực tuyến.

Hợp đồng dữ liệu đầu vào (Input):
- audio_or_video_path: Đường dẫn tệp âm thanh WAV 16kHz hoặc video MP4 gốc.
- initial_prompt: Câu mồi định hướng ngữ cảnh tiếng Việt có dấu.

Hợp đồng dữ liệu đầu ra (Output):
- List[Dict]: [start_sec (float), end_sec (float), text (str), avg_logprob (float), no_speech_prob (float)].
"""

from __future__ import annotations
from pathlib import Path
from typing import Any


class VietnameseASRTranscriber:
    def __init__(
        self,
        model_size: str = "large-v3",
        device: str = "cuda",
        compute_type: str = "float16"
    ):
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.model = None

    def _load_model(self):
        if self.model is None:
            from faster_whisper import WhisperModel
            self.model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type=self.compute_type
            )

    def transcribe(
        self,
        audio_or_video_path: Path | str,
        initial_prompt: str = "Tin tức HTV, VTV, thời sự, phỏng vấn, bài giảng trực tuyến bằng tiếng Việt."
    ) -> list[dict[str, Any]]:
        """
        Nhận diện âm thanh và trả về danh sách các phân đoạn (segments) kèm timestamp.
        """
        self._load_model()
        segments, info = self.model.transcribe(
            str(audio_or_video_path),
            language="vi",
            initial_prompt=initial_prompt,
            beam_size=5,
            vad_filter=True, # Tự động lọc các khoảng lặng (Silence)
            vad_parameters=dict(min_silence_duration_ms=500)
        )

        results: list[dict[str, Any]] = []
        for seg in segments:
            results.append({
                "start_sec": round(seg.start, 3),
                "end_sec": round(seg.end, 3),
                "text": seg.text.strip(),
                "avg_logprob": round(seg.avg_logprob, 3),
                "no_speech_prob": round(seg.no_speech_prob, 3)
            })

        return results
