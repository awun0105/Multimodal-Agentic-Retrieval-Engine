"""
AIC 2026 UNIFIED OCR & ASR LOADERS.
Quan ly cac mo hinh nhan dien chu (VietOCR / PaddleOCR) va am thanh giong noi (Whisper / PhoWhisper).
"""

from __future__ import annotations
import os
import sys
import torch
from pathlib import Path
from typing import Optional, Dict, Any

# Dam bao UTF-8
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


class OCRLoader:
    _instances: Dict[str, Any] = {}

    @classmethod
    def load_vietocr(cls, config_name: str = "vgg_transformer", device: Optional[str] = None):
        """Tai mo hinh VietOCR voi kien truc Transformer / ViT Sequence Encoder."""
        if device is None:
            device = "cuda" if torch.cuda.is_available() else "cpu"

        if "vietocr" in cls._instances:
            return cls._instances["vietocr"]

        try:
            from vietocr.tool.config import Cfg
            from vietocr.tool.predictor import Predictor
            print(f"[OCR Loader] Dang tai VietOCR ({config_name}) tren {device}...")
            config = Cfg.load_config_from_name(config_name)
            config["device"] = device
            config["predictor"]["beamsearch"] = False
            detector = Predictor(config)
            cls._instances["vietocr"] = detector
            print("[OCR Loader] Tai thanh cong VietOCR!")
            return detector
        except Exception as e:
            print(f"[OCR Loader] VietOCR khong kha dung ({e}).")
            return None


class ASRLoader:
    _instances: Dict[str, Any] = {}

    @classmethod
    def load_whisper(cls, model_size: str = "large-v3-turbo", device: Optional[str] = None):
        """Tai mo hinh Whisper Speech-to-Text voi Timestamp tung tu."""
        if device is None:
            device = "cuda" if torch.cuda.is_available() else "cpu"

        cache_key = f"whisper_{model_size}"
        if cache_key in cls._instances:
            return cls._instances[cache_key]

        try:
            import whisper
            print(f"[ASR Loader] Dang tai Whisper ({model_size}) tren {device}...")
            model = whisper.load_model(model_size, device=device)
            cls._instances[cache_key] = model
            print(f"[ASR Loader] Tai thanh cong Whisper ({model_size})!")
            return model
        except Exception as e:
            print(f"[ASR Loader] Whisper khong kha dung ({e}).")
            return None
