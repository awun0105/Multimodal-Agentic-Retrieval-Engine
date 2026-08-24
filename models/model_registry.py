"""
AIC 2026 UNIFIED MODEL REGISTRY & CONFIGURATION.
Trung tam dang ky, quan ly va phan bo tai nguyen phan cung cho toan bo mo hinh AI trong he thong.
"""

from __future__ import annotations
import os
import sys
from typing import Dict, Any, Optional
from dataclasses import dataclass
from pathlib import Path

# Dam bao UTF-8
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


@dataclass
class ModelInfo:
    model_id: str
    name: str
    category: str  # vision_embedding, object_detection, ocr, asr
    architecture: str
    parameters: str
    dimension: Optional[int]
    recommended_hardware: str  # CPU, GPU_T4, TPU_V3
    cpu_latency_ms: float
    gpu_latency_ms: float
    description: str


# ==============================================================================
# DANH MỤC TOÀN BỘ CÁC MÔ HÌNH TRONG HỆ THỐNG
# ==============================================================================
MODEL_CATALOG: Dict[str, ModelInfo] = {
    # 1. VISION EMBEDDING (DUAL-STREAM ViT)
    "siglip-so400m-384": ModelInfo(
        model_id="google/siglip-so400m-patch14-384",
        name="SigLIP SO400M (ViT Patch14-384)",
        category="vision_embedding",
        architecture="Vision Transformer (ViT-SO400M)",
        parameters="400M",
        dimension=1152,
        recommended_hardware="GPU_T4 / TPU_V3",
        cpu_latency_ms=180.0,
        gpu_latency_ms=12.0,
        description="Mô hình thị giác cao cấp nhất, độ phân giải 384x384, biểu diễn ngữ nghĩa visual chi tiết cao."
    ),
    "visiglip-ot-768": ModelInfo(
        model_id="bkai-foundation-models/vietnamese-bi-encoder",
        name="ViSigLIP-OT (Vietnamese ViT 768d)",
        category="vision_embedding",
        architecture="Vietnamese Adapted ViT",
        parameters="86M",
        dimension=768,
        recommended_hardware="GPU_T4 / CPU",
        cpu_latency_ms=45.0,
        gpu_latency_ms=4.5,
        description="Mô hình embedding thuần Việt, tối ưu bắt các khái niệm văn hóa, sự kiện và thực thể bản địa."
    ),
    "siglip-base-224": ModelInfo(
        model_id="google/siglip-base-patch16-224",
        name="SigLIP Base (ViT Patch16-224)",
        category="vision_embedding",
        architecture="Vision Transformer (ViT-Base)",
        parameters="86M",
        dimension=768,
        recommended_hardware="CPU / GPU",
        cpu_latency_ms=35.0,
        gpu_latency_ms=3.5,
        description="Mô hình chuẩn thi đấu cơ bản, tốc độ trích xuất nhanh và độ trễ cực thấp."
    ),
    "clip-vit-large": ModelInfo(
        model_id="openai/clip-vit-large-patch14",
        name="CLIP ViT-Large/14",
        category="vision_embedding",
        architecture="Vision Transformer (ViT-L/14)",
        parameters="304M",
        dimension=768,
        recommended_hardware="GPU_T4",
        cpu_latency_ms=120.0,
        gpu_latency_ms=8.0,
        description="Mô hình CLIP ViT-Large dự phòng, tương thích tốt với các prompt tiếng Anh mô tả chi tiết."
    ),

    # 2. OBJECT DETECTION (MULTI-TIER YOLO & OPEN-VOCABULARY)
    "yolov8n": ModelInfo(
        model_id="yolov8n.pt",
        name="YOLOv8 Nano (v8n)",
        category="object_detection",
        architecture="CNN Feature Pyramid",
        parameters="3.2M",
        dimension=None,
        recommended_hardware="CPU (Local UI Preview)",
        cpu_latency_ms=15.0,
        gpu_latency_ms=2.0,
        description="Bản siêu nhẹ dùng cho Live Interactive Cockpit Studio trên CPU Local, phản hồi tức thì <15ms."
    ),
    "yolov8s": ModelInfo(
        model_id="yolov8s.pt",
        name="YOLOv8 Small (v8s)",
        category="object_detection",
        architecture="CNN Feature Pyramid",
        parameters="11.2M",
        dimension=None,
        recommended_hardware="CPU / GPU",
        cpu_latency_ms=40.0,
        gpu_latency_ms=3.5,
        description="Cân bằng giữa tốc độ và độ chính xác bắt vật thể trung bình."
    ),
    "yolov8m": ModelInfo(
        model_id="yolov8m.pt",
        name="YOLOv8 Medium (v8m)",
        category="object_detection",
        architecture="CNN Feature Pyramid",
        parameters="25.9M",
        dimension=None,
        recommended_hardware="GPU_T4",
        cpu_latency_ms=90.0,
        gpu_latency_ms=6.0,
        description="Độ chính xác cao, nhận diện tốt vật thể bị che khuất một phần."
    ),
    "yolov8x": ModelInfo(
        model_id="yolov8x.pt",
        name="YOLOv8 Extra-Large (v8x)",
        category="object_detection",
        architecture="CNN Feature Pyramid (Deep)",
        parameters="68.2M",
        dimension=None,
        recommended_hardware="GPU_T4 (Offline Pre-processing)",
        cpu_latency_ms=350.0,
        gpu_latency_ms=12.0,
        description="Bản mạnh nhất dòng v8, dùng cho trích xuất Offline trên Kaggle GPU để bắt trọn vật thể nhỏ và đông người."
    ),
    "yolo11x": ModelInfo(
        model_id="yolo11x.pt",
        name="YOLO11 Extra-Large (11x)",
        category="object_detection",
        architecture="C3k2 & Spatial Attention",
        parameters="56.9M",
        dimension=None,
        recommended_hardware="GPU_T4",
        cpu_latency_ms=280.0,
        gpu_latency_ms=9.5,
        description="Kiến trúc YOLO mới nhất 2026, tối ưu cơ chế attention và giảm thiểu false-positives."
    ),
    "yolov8-world-v2": ModelInfo(
        model_id="yolov8x-worldv2.pt",
        name="YOLO-World v2 (Open-Vocabulary ViT)",
        category="object_detection",
        architecture="Vision-Language Cross-Attention",
        parameters="66.8M",
        dimension=None,
        recommended_hardware="GPU_T4",
        cpu_latency_ms=420.0,
        gpu_latency_ms=14.0,
        description="Nhận diện vật thể mở (Zero-Shot) theo text prompt văn hóa: múa lân, nón lá, áo dài, xe xích lô."
    ),

    # 3. OCR (TIER-1 & TIER-2 VIETNAMESE OCR)
    "vietocr-transformer": ModelInfo(
        model_id="vgg_transformer / vgg_seq2seq",
        name="VietOCR (ViT/Transformer Sequence)",
        category="ocr",
        architecture="CNN + Transformer Encoder-Decoder",
        parameters="35M",
        dimension=None,
        recommended_hardware="GPU / CPU",
        cpu_latency_ms=65.0,
        gpu_latency_ms=8.0,
        description="Mô hình OCR nhận diện tiếng Việt có dấu với độ chuẩn xác ký tự cao nhất."
    ),
    "paddleocr-v4": ModelInfo(
        model_id="ch_PP-OCRv4",
        name="PaddleOCR v4 (2-Tier Fast)",
        category="ocr",
        architecture="DBNet Text Detection + SVTR Text Recognition",
        parameters="15M",
        dimension=None,
        recommended_hardware="CPU / GPU",
        cpu_latency_ms=30.0,
        gpu_latency_ms=4.0,
        description="Bộ bóc tách OCR 2-Tier siêu nhanh, định vị và đọc chữ chân trang TV/Bản tin."
    ),

    # 4. ASR SPEECH-TO-TEXT
    "whisper-large-v3-turbo": ModelInfo(
        model_id="openai/whisper-large-v3-turbo",
        name="Whisper Large-v3 Turbo",
        category="asr",
        architecture="Encoder-Decoder Audio Transformer",
        parameters="809M",
        dimension=None,
        recommended_hardware="GPU_T4 / TPU_V3",
        cpu_latency_ms=1200.0,
        gpu_latency_ms=45.0,
        description="Mô hình nhận diện giọng nói tiếng Việt độ chính xác cao nhất, kèm timestamp từng từ phục vụ Video QA."
    ),
    "phowhisper-base": ModelInfo(
        model_id="vinai/PhoWhisper-base",
        name="PhoWhisper Base (Vietnamese ASR)",
        category="asr",
        architecture="Whisper Fine-tuned on Vietnamese",
        parameters="74M",
        dimension=None,
        recommended_hardware="CPU / GPU",
        cpu_latency_ms=180.0,
        gpu_latency_ms=15.0,
        description="Mô hình ASR chuyên biệt tiếng Việt, nhẹ và tối ưu cho xử lý phụ đề nhanh."
    )
}


def get_available_models(category: Optional[str] = None) -> Dict[str, ModelInfo]:
    """Lay danh sach mo hinh theo danh muc (vision_embedding, object_detection, ocr, asr)."""
    if category is None:
        return MODEL_CATALOG
    return {k: v for k, v in MODEL_CATALOG.items() if v.category == category}


def get_model_info(key: str) -> Optional[ModelInfo]:
    """Tra cuu thong tin chi tiet cua mot mo hinh theo key."""
    return MODEL_CATALOG.get(key)
