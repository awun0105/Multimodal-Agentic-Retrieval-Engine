"""Adapter cho họ InternVL (Vintern-1B).

Vì sao tách khỏi `adapters.py`: InternVL không dùng được đường chung của
transformers. `AutoProcessor.from_pretrained('5CD-AI/Vintern-1B-v3_5')` trả về
tokenizer thuần, nên `processor(text=..., images=...)` báo:

    TypeError: PreTrainedTokenizerFast._batch_encode_plus()
               got an unexpected keyword argument 'images'

Đo thật trên Kaggle T4 ngày 16/08/2026 — model NẠP được (`InternVLChatModel`),
chỉ hỏng ở tầng xử lý ảnh. Đường đúng của InternVL:

    anh PIL -> tensor (n_o, 3, 448, 448) -> model.chat(tokenizer, pixel_values, ...)

Tham khảo: OpenGVLab/InternVL `modeling_internvl_chat.py`, model card
`5CD-AI/Vintern-1B-v3_5`. Báo cáo:
`plans/reports/research-260816-1850-vintern-internvl-api.md`.
"""

from __future__ import annotations

from typing import Any

from .adapters import DUNG_LAY_MAU, MAX_NEW_TOKENS, BaseVlmAdapter
from .model_registry import ModelSpec
from .prompts import SYSTEM_PROMPT, USER_PROMPT

# Chuẩn ImageNet — InternVL huấn luyện với bộ số này, đổi là lệch phân phối đầu vào.
IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)

# InternVL cố định 448. Không phải tham số tự chọn: vision tower được huấn luyện
# ở đúng kích thước này.
KICH_THUOC_O = 448


def _tao_pixel_values(pil_image: Any, dtype: Any):
    """Ảnh PIL -> tensor (1, 3, 448, 448) đã chuẩn hóa.

    Dùng MỘT ô duy nhất thay vì cắt động nhiều ô như model card gợi ý.
    Lý do: mã `dynamic_preprocess()` chính xác của Vintern không tra được
    (xem mục "KHÔNG TÌM THẤY" trong báo cáo research), mà cắt ô sai còn hại hơn
    không cắt. Caption cảnh cũng không cần độ phân giải như đọc chữ.
    """
    import torch
    from torchvision import transforms as T

    bien_doi = T.Compose([
        T.Resize((KICH_THUOC_O, KICH_THUOC_O), interpolation=T.InterpolationMode.BICUBIC),
        T.ToTensor(),
        T.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD),
    ])
    anh = pil_image.convert("RGB") if hasattr(pil_image, "convert") else pil_image
    return torch.stack([bien_doi(anh)]).to(dtype)


class InternVlAdapter(BaseVlmAdapter):
    """Backend riêng cho InternVL: `model.chat()` thay vì `model.generate()`."""

    def __init__(self, spec: ModelSpec, *, dung_4bit: bool = True):
        super().__init__(spec, dung_4bit=dung_4bit)
        from .model_loader import load_model

        self.model, _processor, _ = load_model(spec.key, dung_4bit=dung_4bit)

        # Nạp tokenizer riêng với use_fast=False. Model card InternVL yêu cầu bản
        # chậm; bản fast tách token ảnh sai, model sinh ra rác mà không báo lỗi.
        # Không sửa model_loader chung vì Qwen đang chạy tốt với AutoProcessor.
        #
        # Nhưng InternVL3.5 CHỈ phát hành tokenizer.json (định dạng fast) — không
        # có file tokenizer chậm. Xin use_fast=False ở đó thì transformers vẫn trả
        # Qwen2TokenizerFast, rồi code InternVL đòi `start_image_token` mà bản fast
        # không có. Thử bản chậm trước, rơi về bản fast nếu model không phát hành.
        from transformers import AutoTokenizer

        try:
            self.tokenizer = AutoTokenizer.from_pretrained(
                spec.hf_id, trust_remote_code=True, use_fast=False
            )
        except Exception:
            self.tokenizer = AutoTokenizer.from_pretrained(
                spec.hf_id, trust_remote_code=True
            )

        # Bản fast của InternVL3.5 thiếu các token ảnh mà .chat() cần. Gắn thủ công
        # theo added_tokens.json của model thay vì để nó nổ giữa chừng lúc chạy.
        for ten, gia_tri in (
            ("start_image_token", "<img>"),
            ("end_image_token", "</img>"),
            ("context_image_token", "<IMG_CONTEXT>"),
        ):
            if not hasattr(self.tokenizer, ten):
                setattr(self.tokenizer, ten, gia_tri)

        if not hasattr(self.model, "chat"):
            from .model_loader import VlmKhongSanSang

            raise VlmKhongSanSang(
                f"{spec.hf_id} không có method .chat() — không phải model họ InternVL, "
                "đừng dùng adapter này."
            )

    @property
    def backend_name(self) -> str:
        return "internvl-4bit" if self.dung_4bit else "internvl-fp16"

    def infer(self, pil_image: Any) -> str:
        import torch

        # Ép pixel_values về đúng dtype của model. Ở 4-bit, trọng số đã nén nhưng
        # phép tính chạy ở compute_dtype (float16 trên T4) — đưa vào float32 sẽ
        # lỗi lệch kiểu ngay trong vision tower.
        dtype = next(self.model.parameters()).dtype
        pixel_values = _tao_pixel_values(pil_image, dtype).to(self.model.device)

        # InternVL không có kênh system riêng — ghép system vào câu hỏi.
        # Thẻ <image> để model biết chèn ảnh vào đâu; thiếu thì .chat() tự thêm
        # ở đầu, nhưng ghi tường minh để thứ tự không phụ thuộc phiên bản.
        cau_hoi = f"<image>\n{SYSTEM_PROMPT}\n\n{USER_PROMPT}"

        cau_hinh_sinh = {
            "max_new_tokens": MAX_NEW_TOKENS,
            "do_sample": DUNG_LAY_MAU,
            "repetition_penalty": 1.05,
        }

        with torch.no_grad():
            tra_loi = self.model.chat(
                self.tokenizer, pixel_values, cau_hoi, cau_hinh_sinh
            )

        return (tra_loi or "").strip()
