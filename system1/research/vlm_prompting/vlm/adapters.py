"""
Adapter cho từng backend chạy model.

Vì sao cần lớp này: đề bài bắt so sánh ít nhất 3 model. Cách ngây thơ là copy
generate.py thành 3 bản — hậu quả là sửa prompt phải sửa 3 chỗ, quên một chỗ thì
bảng benchmark so sánh nhầm (3 model chạy 3 prompt khác nhau = số liệu vô nghĩa).

Adapter chỉ chịu trách nhiệm DUY NHẤT một việc: cho ảnh + prompt, trả text thô.
Phần chung — prompt, parse, validate — nằm ngoài và dùng chung cho mọi model.
Nhờ vậy benchmark mới công bằng: cùng prompt, cùng parser, chỉ khác model.

Ba backend, tự dò theo thứ tự: vLLM → transformers → mock.
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from typing import Any

from .model_registry import ModelSpec, lay_spec
from .prompts import SYSTEM_PROMPT, USER_PROMPT, build_messages

logger = logging.getLogger(__name__)

MAX_NEW_TOKENS = 320
TEMPERATURE = 0.3


class BaseVlmAdapter(ABC):
    """Giao diện chung mọi backend phải tuân theo."""

    def __init__(self, spec: ModelSpec, *, dung_4bit: bool = True):
        self.spec = spec
        self.dung_4bit = dung_4bit

    @property
    def model_name(self) -> str:
        return self.spec.hf_id

    @property
    @abstractmethod
    def backend_name(self) -> str:
        """Tên backend, ghi vào báo cáo để biết số đo đến từ đâu."""

    @abstractmethod
    def infer(self, pil_image: Any) -> str:
        """Chạy model trên một ảnh, trả về text thô CHƯA parse."""


class TransformersAdapter(BaseVlmAdapter):
    """
    Backend mặc định: transformers + bitsandbytes 4-bit.

    Chạy được ở mọi nơi có GPU NVIDIA, kể cả Windows. Chậm hơn vLLM nhưng
    dễ cài hơn nhiều — đây là lý do nó là mặc định.
    """

    def __init__(self, spec: ModelSpec, *, dung_4bit: bool = True):
        super().__init__(spec, dung_4bit=dung_4bit)
        from .model_loader import load_model

        self.model, self.processor, _ = load_model(spec.key, dung_4bit=dung_4bit)

    @property
    def backend_name(self) -> str:
        return "transformers-4bit" if self.dung_4bit else "transformers-fp16"

    def infer(self, pil_image: Any) -> str:
        import torch

        messages = build_messages(pil_image)
        try:
            text_prompt = self.processor.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
        except Exception:
            text_prompt = f"{SYSTEM_PROMPT}\n\n{USER_PROMPT}"

        inputs = self.processor(text=[text_prompt], images=[pil_image], return_tensors="pt")
        inputs = {
            k: v.to(self.model.device) if hasattr(v, "to") else v for k, v in inputs.items()
        }

        with torch.no_grad():
            output_ids = self.model.generate(
                **inputs,
                max_new_tokens=MAX_NEW_TOKENS,
                do_sample=TEMPERATURE > 0,
                temperature=TEMPERATURE,
                repetition_penalty=1.05,
            )

        input_ids = inputs.get("input_ids")
        if input_ids is not None:
            output_ids = output_ids[:, input_ids.shape[1] :]

        return self.processor.batch_decode(output_ids, skip_special_tokens=True)[0].strip()


class VllmAdapter(BaseVlmAdapter):
    """
    Backend nhanh: vLLM + XGrammar ép JSON ở tầng giải mã.

    Khác biệt căn bản so với transformers: XGrammar chặn model sinh ra ký tự
    làm hỏng cấu trúc JSON — nên tỷ lệ JSON hợp lệ đạt ~99.9%, thay vì trông
    chờ model nghe lời prompt.

    Không cài được trên Windows. Chỉ dùng trên Linux/Kaggle/Colab.
    """

    def __init__(self, spec: ModelSpec, *, dung_4bit: bool = True, ep_json: bool = True):
        super().__init__(spec, dung_4bit=dung_4bit)
        self.ep_json = ep_json
        self._khoi_tao()

    def _khoi_tao(self) -> None:
        from vllm import LLM, SamplingParams

        from .schema import KeyframeMetadata

        self.llm = LLM(
            model=self.spec.hf_id,
            quantization="awq" if self.dung_4bit else None,
            gpu_memory_utilization=0.85,
            max_model_len=2048,
            trust_remote_code=self.spec.trust_remote_code,
        )

        tham_so: dict[str, Any] = {
            "temperature": TEMPERATURE,
            "max_tokens": MAX_NEW_TOKENS,
        }
        if self.ep_json:
            tham_so["guided_json"] = KeyframeMetadata.model_json_schema()

        self.sampling_params = SamplingParams(**tham_so)

    @property
    def backend_name(self) -> str:
        return "vllm-xgrammar" if self.ep_json else "vllm"

    def infer(self, pil_image: Any) -> str:
        prompt = f"{SYSTEM_PROMPT}\n\n{USER_PROMPT}"
        ket_qua = self.llm.generate(
            [{"prompt": prompt, "multi_modal_data": {"image": pil_image}}],
            self.sampling_params,
        )
        return ket_qua[0].outputs[0].text.strip()


class MockAdapter(BaseVlmAdapter):
    """
    Đường lui cuối: trả JSON giả hợp lệ thay vì crash.

    Vì sao cần: nếu code chỉ chạy khi có GPU thì đúng hôm demo mà máy trục trặc
    là mất trắng. Repo đã có sẵn triết lý này ở `RealProviderUnavailable`
    (features/providers.py:64) — degrade chứ không ném lỗi.

    Kết quả trả về CÓ ghi rõ là giả, để không ai nhầm là dữ liệu thật.
    """

    def __init__(self, spec: ModelSpec | None = None, *, ly_do: str = "unknown"):
        self.ly_do = ly_do
        self._spec = spec
        # Dùng ASCII trong log: console Windows mặc định cp1252 làm hỏng tiếng Việt.
        logger.warning(
            "MockAdapter active - returning FAKE JSON, not real model output. Reason: %s",
            ly_do,
        )

    @property
    def model_name(self) -> str:
        return f"mock({self._spec.hf_id})" if self._spec else "mock"

    @property
    def backend_name(self) -> str:
        return "mock"

    def infer(self, pil_image: Any) -> str:
        kich_thuoc = getattr(pil_image, "size", ("?", "?"))
        return json.dumps(
            {
                "doi_tuong": ["[mock]"],
                "mau_sac": ["[mock]"],
                "hanh_dong": "[mock]",
                "boi_canh": "[mock]",
                "caption_chi_tiet": (
                    f"[DỮ LIỆU GIẢ - không phải kết quả model] Ảnh kích thước "
                    f"{kich_thuoc}. Lý do dùng mock: {self.ly_do}"
                ),
                "caption_en": "[MOCK DATA - not a real model output]",
            },
            ensure_ascii=False,
        )


def _co_the_dung_vllm() -> bool:
    try:
        import vllm  # noqa: F401
        import torch

        return torch.cuda.is_available()
    except ImportError:
        return False


def _co_the_dung_transformers() -> bool:
    try:
        import torch
        import transformers  # noqa: F401

        return torch.cuda.is_available()
    except ImportError:
        return False


def get_adapter(
    model_key: str,
    *,
    backend: str = "auto",
    dung_4bit: bool = True,
) -> BaseVlmAdapter:
    """
    Tạo adapter phù hợp.

    backend:
        "auto"          — tự dò: vllm → transformers → mock (mặc định)
        "vllm"          — ép dùng vLLM, lỗi thì báo luôn
        "transformers"  — ép dùng transformers, lỗi thì báo luôn
        "mock"          — ép dùng mock (để test luồng khi không có GPU)

    Chế độ "auto" không bao giờ ném lỗi — cùng lắm rơi về mock.
    """
    spec = lay_spec(model_key)

    if backend == "mock":
        return MockAdapter(spec, ly_do="user selected backend=mock")

    if backend == "vllm":
        return VllmAdapter(spec, dung_4bit=dung_4bit)

    if backend == "transformers":
        return TransformersAdapter(spec, dung_4bit=dung_4bit)

    if backend != "auto":
        raise ValueError(f"backend không hợp lệ: {backend!r}")

    if _co_the_dung_vllm():
        try:
            return VllmAdapter(spec, dung_4bit=dung_4bit)
        except Exception as loi:
            logger.warning("vLLM present but init failed (%s), falling back to transformers", loi)

    if _co_the_dung_transformers():
        try:
            return TransformersAdapter(spec, dung_4bit=dung_4bit)
        except Exception as loi:
            logger.warning("transformers init failed (%s), falling back to mock", loi)
            return MockAdapter(spec, ly_do=f"transformers init failed: {loi}")

    return MockAdapter(spec, ly_do="no GPU available, or torch/transformers not installed")
