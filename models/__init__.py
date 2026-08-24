"""
AIC 2026 UNIFIED MODEL REGISTRY & LOADERS.
Quan ly tap trung tat ca cac mo hinh:
1. Vision Embedding: SigLIP SO400M (1152d), ViSigLIP-OT (768d), SigLIP Base (768d), CLIP ViT.
2. Object Detection: YOLO Multi-Tier (v8n, v8s, v8m, v8l, v8x, yolo11x, YOLO-World Open-Vocabulary).
3. OCR: VietOCR (Transformer/ViT), PaddleOCR, EasyOCR.
4. ASR: Whisper Large-v3 Turbo, PhoWhisper, Wav2Vec2 Vietnamese.
"""

from pathlib import Path

MODELS_DIR = Path(__file__).resolve().parent
