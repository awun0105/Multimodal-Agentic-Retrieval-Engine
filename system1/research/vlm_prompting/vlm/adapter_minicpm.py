"""Backend riêng cho MiniCPM-V: `model.chat()` với ảnh PIL truyền thẳng.

Khác InternVL ở hai chỗ, đều lấy từ model card `openbmb/MiniCPM-V-4`:

- Không phải cắt ảnh thành ô 448×448 — `.chat()` nhận PIL Image trong `msgs`
  và tự lo phần tiền xử lý.
- Chữ ký là `chat(msgs=..., image=..., tokenizer=...)` với `msgs` dạng
  `[{'role': 'user', 'content': [image, question]}]`, không phải
  `chat(tokenizer, pixel_values, question, config)` như InternVL.

Registry ghi `loader="auto_causal"` cho model này là SAI — MiniCPM cần
`AutoModel`, không phải `AutoModelForCausalLM`. Adapter tự nạp lấy thay vì đi
qua `model_loader.load_model()` để không phải sửa nhánh nạp chung đang chạy tốt
cho Qwen và InternVL.
"""

from __future__ import annotations

from typing import Any

from .adapters import DUNG_LAY_MAU, MAX_NEW_TOKENS, BaseVlmAdapter
from .model_registry import ModelSpec
from .prompts import SYSTEM_PROMPT, USER_PROMPT


class MiniCpmAdapter(BaseVlmAdapter):
    """Backend cho họ MiniCPM-V."""

    def __init__(self, spec: ModelSpec, *, dung_4bit: bool = True):
        super().__init__(spec, dung_4bit=dung_4bit)

        import torch
        from transformers import AutoModel, AutoTokenizer

        from .model_loader import VlmKhongSanSang, _tao_quant_config

        co_gpu = torch.cuda.is_available()

        kwargs: dict[str, Any] = {"trust_remote_code": True}
        # Model card yêu cầu sdpa; 'eager' cho ra kết quả sai lệch trên bản này.
        kwargs["attn_implementation"] = "sdpa"

        if dung_4bit and co_gpu:
            kwargs["quantization_config"] = _tao_quant_config(spec)
        else:
            kwargs["torch_dtype"] = torch.float16 if co_gpu else torch.float32

        try:
            self.model = AutoModel.from_pretrained(spec.hf_id, **kwargs)
            self.tokenizer = AutoTokenizer.from_pretrained(
                spec.hf_id, trust_remote_code=True
            )
        except Exception as loi:
            raise VlmKhongSanSang(f"Không nạp được {spec.hf_id}: {loi}") from loi

        if not (dung_4bit and co_gpu) and co_gpu:
            self.model = self.model.to("cuda")

        self.model.eval()

        if not hasattr(self.model, "chat"):
            raise VlmKhongSanSang(
                f"{spec.hf_id} không có method .chat() — không phải model họ "
                "MiniCPM-V, đừng dùng adapter này."
            )

    @property
    def backend_name(self) -> str:
        return "minicpm-4bit" if self.dung_4bit else "minicpm-fp16"

    def infer(self, pil_image: Any) -> str:
        import torch

        # MiniCPM không có kênh system riêng — ghép system vào câu hỏi, giống
        # cách InternVlAdapter đang làm.
        cau_hoi = f"{SYSTEM_PROMPT}\n\n{USER_PROMPT}"
        msgs = [{"role": "user", "content": [pil_image.convert("RGB"), cau_hoi]}]

        with torch.no_grad():
            tra_loi = self.model.chat(
                msgs=msgs,
                image=None,
                tokenizer=self.tokenizer,
                max_new_tokens=MAX_NEW_TOKENS,
                sampling=DUNG_LAY_MAU,
            )

        # Bản mới trả str; một số bản trả tuple (text, context, ...).
        if isinstance(tra_loi, tuple):
            tra_loi = tra_loi[0]
        return (tra_loi or "").strip()
