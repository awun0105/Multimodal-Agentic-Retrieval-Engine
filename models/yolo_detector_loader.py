"""
AIC 2026 UNIFIED YOLO OBJECT DETECTOR LOADER.
Ho tro tai linh hoat tat ca cac phan cap YOLO:
- Local CPU Preview: YOLOv8n (3.2M params, <15ms)
- Balanced Mode: YOLOv8s / YOLOv8m
- Offline Preprocessing trên Kaggle GPU: YOLOv8x (68M params, 12ms) / YOLO11x (56M params)
- Open-Vocabulary Detection: YOLO-World v2 (ViT Vision-Language Prompting)
"""

from __future__ import annotations
import os
import sys
import torch
from pathlib import Path
from typing import Optional, Dict, Any, List

# Dam bao UTF-8
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

MODELS_CACHE_DIR = Path(__file__).resolve().parent / "weights"
MODELS_CACHE_DIR.mkdir(parents=True, exist_ok=True)


class YOLODetectorLoader:
    _instances: Dict[str, Any] = {}

    @classmethod
    def get_model(cls, model_name: str = "yolov8n", device: Optional[str] = None):
        """
        Tai va cache mo hinh YOLO theo cap do chi dinh.
        :param model_name: 'yolov8n', 'yolov8s', 'yolov8m', 'yolov8x', 'yolo11n', 'yolo11x', 'yolov8x-worldv2'
        :param device: 'cuda', 'cpu' hoac None (tu dong phat hien)
        """
        if device is None:
            device = "cuda" if torch.cuda.is_available() else "cpu"

        cache_key = f"{model_name}_{device}"
        if cache_key in cls._instances:
            return cls._instances[cache_key]

        try:
            from ultralytics import YOLO
            # Kiem tra file local truoc
            local_weight = MODELS_CACHE_DIR / f"{model_name}.pt"
            weight_path = str(local_weight) if local_weight.exists() else f"{model_name}.pt"

            print(f"[YOLO Loader] Dang khoi tao mo hinh {model_name} tren thiet bi {device}...")
            model = YOLO(weight_path)
            model.to(device)
            cls._instances[cache_key] = model
            print(f"[YOLO Loader] Khoi tao thanh cong {model_name} ({device})!")
            return model
        except Exception as e:
            print(f"[YOLO Loader] Khong the tai {model_name}: {e}. Su dung CPU fallback voi yolov8n...")
            from ultralytics import YOLO
            model = YOLO("yolov8n.pt")
            model.to("cpu")
            cls._instances[cache_key] = model
            return model

    @classmethod
    def list_supported_models(cls) -> List[str]:
        return [
            "yolov8n", "yolov8s", "yolov8m", "yolov8l", "yolov8x",
            "yolo11n", "yolo11s", "yolo11m", "yolo11l", "yolo11x",
            "yolov8s-worldv2", "yolov8m-worldv2", "yolov8x-worldv2"
        ]
