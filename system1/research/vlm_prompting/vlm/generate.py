"""
Hàm generate_json(image) — điểm vào chính của Phần 3 (VLM & Prompting).

Đưa vào một ảnh, nhận về dict JSON mô tả nội dung ảnh theo cấu trúc cố định.

Cách dùng ngắn nhất:
    from vlm import generate_json
    ket_qua = generate_json("anh.jpg")
    print(ket_qua["caption_chi_tiet"])

Việc nạp model nằm ở model_loader.py — file này chỉ lo luồng xử lý.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

from .json_utils import parse_json_safe
from .model_loader import VlmKhongSanSang, load_model, xoa_cache_model
from .model_registry import MODEL_MAC_DINH, ModelSpec
from .prompts import PROMPT_VERSION, SYSTEM_PROMPT, USER_PROMPT, build_messages
from .schema import SCHEMA_VERSION, KeyframeMetadata

MAX_NEW_TOKENS = 320
TEMPERATURE = 0.3

__all__ = [
    "generate_json",
    "load_image",
    "load_model",
    "xoa_cache_model",
    "reset_vram_counter",
    "thong_tin_moi_truong",
    "VlmKhongSanSang",
]


def load_image(image: Any):
    """Chuẩn hóa đầu vào (đường dẫn / bytes / PIL.Image) về PIL.Image RGB."""
    from PIL import Image

    if isinstance(image, Image.Image):
        return image.convert("RGB")
    if isinstance(image, (str, Path)):
        duong_dan = Path(image)
        if not duong_dan.exists():
            raise FileNotFoundError(f"Không tìm thấy ảnh: {duong_dan}")
        return Image.open(duong_dan).convert("RGB")
    if isinstance(image, (bytes, bytearray)):
        import io

        return Image.open(io.BytesIO(image)).convert("RGB")
    raise TypeError(f"Kiểu ảnh không hỗ trợ: {type(image)!r}")


def _sinh_text_tho(model, processor, spec: ModelSpec, pil_image) -> str:
    """Chạy model, trả về chuỗi text thô chưa parse."""
    import torch

    messages = build_messages(pil_image)

    try:
        text_prompt = processor.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
    except Exception:
        # Model không có chat template (thường gặp ở loader auto_causal).
        text_prompt = f"{SYSTEM_PROMPT}\n\n{USER_PROMPT}"

    inputs = processor(text=[text_prompt], images=[pil_image], return_tensors="pt")
    inputs = {k: v.to(model.device) if hasattr(v, "to") else v for k, v in inputs.items()}

    with torch.no_grad():
        output_ids = model.generate(
            **inputs,
            max_new_tokens=MAX_NEW_TOKENS,
            do_sample=TEMPERATURE > 0,
            temperature=TEMPERATURE,
            repetition_penalty=1.05,
        )

    # Cắt bỏ phần prompt, chỉ giữ phần model sinh mới.
    input_ids = inputs.get("input_ids")
    if input_ids is not None:
        output_ids = output_ids[:, input_ids.shape[1] :]

    return processor.batch_decode(output_ids, skip_special_tokens=True)[0].strip()


def generate_json(
    image: Any,
    model_key: str = MODEL_MAC_DINH,
    *,
    dung_4bit: bool = True,
    debug: bool = False,
) -> dict:
    """
    Nhận đầu vào là ảnh. Trả về JSON mô tả nội dung ảnh theo cấu trúc cố định.

    Tham số:
        image: đường dẫn ảnh, bytes, hoặc PIL.Image.
        model_key: khóa model trong MODEL_REGISTRY.
        dung_4bit: bật lượng tử hóa 4-bit (tự tắt khi máy không có GPU).
        debug: in output thô của model để soi lỗi.

    Trả về dict gồm các trường của KeyframeMetadata, cộng metadata kỹ thuật
    (`_model`, `_latency_sec`, `_vram_peak_gb`...). Các trường bắt đầu bằng "_"
    là thông tin phụ trợ cho benchmark, không thuộc hợp đồng JSON của đề bài.

    Ném VlmKhongSanSang nếu không nạp được model, JsonParseError nếu model trả
    về thứ không cứu được thành JSON.
    """
    pil_image = load_image(image)
    model, processor, spec = load_model(model_key, dung_4bit=dung_4bit)

    bat_dau = time.perf_counter()
    text_tho = _sinh_text_tho(model, processor, spec, pil_image)
    latency = time.perf_counter() - bat_dau

    if debug:
        print(f"[DEBUG] model={spec.hf_id}")
        print(f"[DEBUG] output thô ({len(text_tho)} ký tự):\n{text_tho}\n")

    du_lieu = parse_json_safe(text_tho)
    metadata = KeyframeMetadata(**du_lieu)

    ket_qua = metadata.model_dump()
    ket_qua["_model"] = spec.hf_id
    ket_qua["_model_key"] = spec.key
    ket_qua["_latency_sec"] = round(latency, 3)
    ket_qua["_prompt_version"] = PROMPT_VERSION
    ket_qua["_schema_version"] = SCHEMA_VERSION
    ket_qua["_vram_peak_gb"] = _doc_vram_dinh()
    return ket_qua


def _doc_vram_dinh() -> float | None:
    try:
        import torch

        if not torch.cuda.is_available():
            return None
        return round(torch.cuda.max_memory_allocated() / (1024**3), 3)
    except Exception:
        return None


def reset_vram_counter() -> None:
    """Xóa mốc VRAM đỉnh. Gọi TRƯỚC mỗi lần đo, nếu không số sẽ dính từ lần trước."""
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.reset_peak_memory_stats()
    except Exception:
        pass


def thong_tin_moi_truong() -> dict:
    """Dò phần cứng hiện có — dùng để chọn model phù hợp và ghi vào báo cáo."""
    thong_tin: dict[str, Any] = {
        "python": sys.version.split()[0],
        "co_torch": False,
        "co_gpu": False,
        "ten_gpu": None,
        "vram_gb": None,
    }
    try:
        import torch

        thong_tin["co_torch"] = True
        thong_tin["torch_version"] = torch.__version__
        if torch.cuda.is_available():
            thong_tin["co_gpu"] = True
            thong_tin["ten_gpu"] = torch.cuda.get_device_name(0)
            thong_tin["vram_gb"] = round(
                torch.cuda.get_device_properties(0).total_memory / (1024**3), 2
            )
    except ImportError:
        pass
    return thong_tin
