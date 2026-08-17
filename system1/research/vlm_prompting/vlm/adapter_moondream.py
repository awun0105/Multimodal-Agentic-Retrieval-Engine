"""Backend riêng cho Moondream: `model.query()` thay vì `.generate()`.

Ba điểm khác mọi adapter hiện có, đều lấy từ model card `vikhyatk/moondream2`:

- API là `query(image, question)` trả `{"answer": ...}`, không phải `.generate()`
  hay `.chat()`. Cũng có `caption()` nhưng nó chỉ trả câu mô tả tự do — không
  ép được khuôn JSON, nên dùng `query()` với prompt hiện hành.
- Phải ghim `revision`: model card đánh phiên bản theo ngày, không ghim thì mỗi
  lần tải về một bản khác nhau và số đo không tái lập được.
- **Không nén 4-bit.** Model chỉ 1,93 tỷ tham số nên fp16 đã vừa T4 (~4 GB).
  Tài liệu không nói gì về bitsandbytes; ép 4-bit lên model không hỗ trợ chính
  là thứ làm MiniCPM-V-4 tràn bộ nhớ. Ở đây không cần mạo hiểm.
"""

from __future__ import annotations

from typing import Any

from .adapters import BaseVlmAdapter
from .model_registry import ModelSpec
from .prompts import SYSTEM_PROMPT, USER_PROMPT

# Model card đánh phiên bản theo ngày. Ghim để số đo tái lập được.
REVISION_MOONDREAM = "2025-06-21"


class MoondreamAdapter(BaseVlmAdapter):
    """Backend cho họ Moondream."""

    def __init__(self, spec: ModelSpec, *, dung_4bit: bool = True):
        super().__init__(spec, dung_4bit=dung_4bit)

        import torch
        from transformers import AutoModelForCausalLM

        from .model_loader import VlmKhongSanSang

        co_gpu = torch.cuda.is_available()
        kwargs: dict[str, Any] = {
            "trust_remote_code": True,
            "revision": REVISION_MOONDREAM,
        }
        if co_gpu:
            kwargs["device_map"] = {"": "cuda"}

        try:
            self.model = AutoModelForCausalLM.from_pretrained(spec.hf_id, **kwargs)
        except Exception as loi:
            raise VlmKhongSanSang(f"Không nạp được {spec.hf_id}: {loi}") from loi

        if not hasattr(self.model, "query"):
            raise VlmKhongSanSang(
                f"{spec.hf_id} không có method .query() — không phải model họ "
                "Moondream, đừng dùng adapter này."
            )

    @property
    def backend_name(self) -> str:
        # Luôn fp16: model đủ nhỏ để không cần nén, và 4-bit không được hỗ trợ.
        return "moondream-fp16"

    def infer(self, pil_image: Any) -> str:
        cau_hoi = f"{SYSTEM_PROMPT}\n\n{USER_PROMPT}"
        ket_qua = self.model.query(pil_image.convert("RGB"), cau_hoi)

        # query() trả dict {"answer": ...}; một số bản trả thẳng chuỗi.
        if isinstance(ket_qua, dict):
            ket_qua = ket_qua.get("answer", "")
        return (ket_qua or "").strip()
