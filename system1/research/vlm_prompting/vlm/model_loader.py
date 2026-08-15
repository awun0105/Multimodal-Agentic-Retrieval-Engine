"""
Nạp model VLM và cấu hình lượng tử hóa 4-bit.

Tách khỏi generate.py vì đây là phần phụ thuộc nặng vào phần cứng và thư viện —
generate.py chỉ lo luồng xử lý, file này lo chuyện nạp model.

Mọi import torch/transformers đều đặt TRONG hàm (lazy import) để máy chưa cài
torch vẫn import được module mà chạy phần schema/prompt.
"""

from __future__ import annotations

from typing import Any

from .model_registry import MODEL_MAC_DINH, ModelSpec, lay_spec

_CACHE_MODEL: dict[str, tuple[Any, Any, ModelSpec]] = {}


class VlmKhongSanSang(RuntimeError):
    """Không nạp được model — thiếu thư viện, thiếu GPU, hoặc tải model lỗi."""


def _tao_quant_config(spec: ModelSpec):
    """
    Cấu hình lượng tử hóa 4-bit (yêu cầu bắt buộc của đề bài, mục 17).

    Vision tower giữ nguyên FP16 — nén cả phần "mắt" xuống 4-bit làm chất lượng
    mô tả rơi rõ rệt trong khi tiết kiệm rất ít bộ nhớ.
    """
    import torch
    from transformers import BitsAndBytesConfig

    return BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.float16,
        bnb_4bit_use_double_quant=True,
        llm_int8_skip_modules=list(spec.skip_quant_modules),
    )


def _nap_theo_loader(spec: ModelSpec, kwargs: dict[str, Any]):
    """Mỗi họ model có lớp nạp riêng — tách ra cho dễ thêm model mới."""
    if spec.loader == "qwen25vl":
        from transformers import Qwen2_5_VLForConditionalGeneration

        return Qwen2_5_VLForConditionalGeneration.from_pretrained(spec.hf_id, **kwargs)
    if spec.loader == "qwen2vl":
        from transformers import Qwen2VLForConditionalGeneration

        return Qwen2VLForConditionalGeneration.from_pretrained(spec.hf_id, **kwargs)

    from transformers import AutoModelForCausalLM

    return AutoModelForCausalLM.from_pretrained(spec.hf_id, **kwargs)


def load_model(model_key: str = MODEL_MAC_DINH, *, dung_4bit: bool = True):
    """
    Nạp model và processor, có cache.

    Trả về (model, processor, spec). Gọi lại cùng model_key sẽ lấy từ cache —
    nạp model mất 30-60 giây, không cache thì chạy 100 ảnh mất cả tiếng chờ.
    """
    khoa_cache = f"{model_key}:{'4bit' if dung_4bit else 'fp16'}"
    if khoa_cache in _CACHE_MODEL:
        return _CACHE_MODEL[khoa_cache]

    spec = lay_spec(model_key)

    try:
        import torch
        from transformers import AutoProcessor
    except ImportError as loi:
        raise VlmKhongSanSang(
            f"Thiếu thư viện: {loi}. Cài bằng: pip install -r requirements.txt"
        ) from loi

    co_gpu = torch.cuda.is_available()
    quant_config = _tao_quant_config(spec) if (dung_4bit and co_gpu) else None

    kwargs: dict[str, Any] = {
        "torch_dtype": torch.float16 if co_gpu else torch.float32,
        "low_cpu_mem_usage": True,
    }
    if spec.trust_remote_code:
        kwargs["trust_remote_code"] = True
    if quant_config is not None:
        kwargs["quantization_config"] = quant_config
        kwargs["device_map"] = "auto"
    elif co_gpu:
        kwargs["device_map"] = "auto"

    try:
        model = _nap_theo_loader(spec, kwargs)
        processor = AutoProcessor.from_pretrained(
            spec.hf_id, trust_remote_code=spec.trust_remote_code
        )
    except Exception as loi:
        raise VlmKhongSanSang(f"Không nạp được {spec.hf_id}: {loi}") from loi

    model.eval()
    _CACHE_MODEL[khoa_cache] = (model, processor, spec)
    return model, processor, spec


def xoa_cache_model() -> None:
    """Giải phóng model khỏi VRAM. Gọi khi cần đổi sang model khác trên GPU nhỏ."""
    _CACHE_MODEL.clear()
    try:
        import gc

        import torch

        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except ImportError:
        pass
