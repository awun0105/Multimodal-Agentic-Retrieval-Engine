"""Phần 3 — VLM & Prompting: sinh JSON metadata từ keyframe."""

from .generate import generate_json, load_image, reset_vram_counter, thong_tin_moi_truong
from .json_utils import JsonParseError, parse_json_safe
from .model_loader import VlmKhongSanSang, load_model, xoa_cache_model
from .model_registry import MODEL_MAC_DINH, MODEL_REGISTRY, goi_y_theo_vram, lay_spec
from .prompts import PROMPT_VERSION
from .schema import SCHEMA_VERSION, KeyframeMetadata, to_shot_caption_row

__all__ = [
    "generate_json",
    "load_image",
    "load_model",
    "xoa_cache_model",
    "reset_vram_counter",
    "thong_tin_moi_truong",
    "VlmKhongSanSang",
    "KeyframeMetadata",
    "to_shot_caption_row",
    "parse_json_safe",
    "JsonParseError",
    "MODEL_REGISTRY",
    "MODEL_MAC_DINH",
    "lay_spec",
    "goi_y_theo_vram",
    "PROMPT_VERSION",
    "SCHEMA_VERSION",
]
