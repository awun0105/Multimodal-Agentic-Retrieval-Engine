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

# Lay mau ngau nhien (do_sample) doc mot so tu phan phoi xac suat. O float16,
# phan phoi cua model 3B tran so thanh nan va PyTorch bao:
#   "probability tensor contains either inf, nan or element < 0"
# -> Qwen2.5-VL-3B sap sau 4 anh, 88/92 ca loi cung mot thong bao.
# Sinh JSON co cau truc thi lay chu xac suat cao nhat vua on dinh vua dung hon
# lay mau. TEMPERATURE chi dung khi DUNG_LAY_MAU bat. vLLM khong co tham so ten
# do_sample, nhung temperature > 0 chinh la lay mau -> phai theo cung cong tac.
DUNG_LAY_MAU = False
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

    def __init__(
        self,
        spec: ModelSpec,
        *,
        dung_4bit: bool = True,
        lora_model_path: str | None = None,
    ):
        super().__init__(spec, dung_4bit=dung_4bit)
        from .model_loader import load_model

        self.model, self.processor, _ = load_model(spec.key, dung_4bit=dung_4bit)

        self.lora_model_path = lora_model_path
        if lora_model_path is not None:
            self._gan_lora(lora_model_path)

    def _gan_lora(self, lora_model_path: str) -> None:
        """Gắn trọng số LoRA sau khi model gốc đã nạp xong.

        Kiểm đường dẫn sớm: im lặng chạy tiếp với model gốc khi đường dẫn sai
        sẽ tạo ra một bảng benchmark trông như đo model đã train nhưng thực ra
        không phải — đúng loại lỗi số giả mà strict=True được sinh ra để chặn.
        """
        from pathlib import Path

        thu_muc = Path(lora_model_path)
        if not (thu_muc / "adapter_config.json").exists():
            from .model_loader import VlmKhongSanSang

            raise VlmKhongSanSang(
                f"Không tìm thấy adapter_config.json trong lora_model_path={lora_model_path!r} "
                "- kiểm tra lại đường dẫn LoRA."
            )

        from peft import PeftModel

        self.model = PeftModel.from_pretrained(self.model, lora_model_path)

    @property
    def backend_name(self) -> str:
        ten = "transformers-4bit" if self.dung_4bit else "transformers-fp16"
        return f"{ten}+lora" if self.lora_model_path is not None else ten

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
            tham_so_sinh: dict[str, Any] = {
                "max_new_tokens": MAX_NEW_TOKENS,
                "do_sample": DUNG_LAY_MAU,
                "repetition_penalty": 1.05,
            }
            if DUNG_LAY_MAU:
                tham_so_sinh["temperature"] = TEMPERATURE
            output_ids = self.model.generate(**inputs, **tham_so_sinh)

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

        # CANH BAO: quantization="awq" can checkpoint da nen san (...-Instruct-AWQ).
        # Registry dang luu ten ban goc -> nap ban goc roi khai la AWQ se loi.
        # Muon bat duong nay phai doi hf_id sang ban AWQ VA kiem kernel co chay
        # tren card dich khong (kernel AWQ can sm_80+, T4 la sm_75).
        self.llm = LLM(
            model=self.spec.hf_id,
            quantization="awq" if self.dung_4bit else None,
            gpu_memory_utilization=0.85,
            max_model_len=2048,
            trust_remote_code=self.spec.trust_remote_code,
        )

        tham_so: dict[str, Any] = {
            "temperature": TEMPERATURE if DUNG_LAY_MAU else 0,
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


def _la_ho_internvl(spec) -> bool:
    """InternVL cần đường riêng: processor của nó là tokenizer thuần, không nhận ảnh.

    Nhận theo hf_id chứ không theo loader `auto_causal` — MiniCPM-V cũng dùng
    loader đó nhưng có processor bình thường, đẩy nó sang InternVlAdapter là sai.
    """
    ten = spec.hf_id.lower()
    return "internvl" in ten or "vintern" in ten


def _la_ho_moondream(spec) -> bool:
    """Moondream dùng .query(image, question) trả dict, không phải .generate().

    Nhận theo hf_id: registry ghi loader="auto_causal" nhưng adapter riêng tự nạp
    kèm revision ghim ngày — model card đánh phiên bản theo ngày phát hành.
    """
    return "moondream" in spec.hf_id.lower()


def _la_ho_minicpm(spec) -> bool:
    """MiniCPM-V cũng dùng .chat() nhưng chữ ký khác InternVL hoàn toàn.

    Nhận theo hf_id vì registry ghi `loader="auto_causal"` — loader đó trỏ tới
    AutoModelForCausalLM, còn MiniCPM cần AutoModel. Adapter riêng tự nạp lấy.
    """
    return "minicpm" in spec.hf_id.lower()


def _nap_nghiem_ngat(
    lop_adapter,
    spec,
    dung_4bit: bool,
    model_key: str,
    ten: str,
    strict: bool,
    **them,
):
    """Khởi tạo adapter được chỉ định thẳng; strict=True đổi lỗi thành RuntimeError có ngữ cảnh."""
    try:
        return lop_adapter(spec, dung_4bit=dung_4bit, **them)
    except Exception as loi:
        if strict:
            raise RuntimeError(
                f"strict=True: {ten} khởi tạo lỗi cho model={model_key}: {loi}"
            ) from loi
        raise


def get_adapter(
    model_key: str,
    *,
    backend: str = "auto",
    dung_4bit: bool = True,
    strict: bool = False,
    lora_model_path: str | None = None,
) -> BaseVlmAdapter:
    """
    Tạo adapter phù hợp.

    backend:
        "auto"          — tự dò: vllm → transformers → mock (mặc định)
        "vllm"          — ép dùng vLLM, lỗi thì báo luôn
        "transformers"  — ép dùng transformers, lỗi thì báo luôn
        "mock"          — ép dùng mock (để test luồng khi không có GPU)

    strict: mặc định False — production vẫn fail-soft như cũ, một model
        không tải được thì rơi về MockAdapter, không làm sập cả mẻ.
        True — chỉ dùng khi benchmark: NÉM LỖI thay vì âm thầm rơi về mock,
        kể cả khi backend="mock" (đo mock trong chế độ nghiêm ngặt là vô
        nghĩa). Đây là lý do report cũ có số giả "Vintern-1B 100% JSON hợp
        lệ, 0,0 giây" — model chưa từng chạy, mock trả JSON giả và benchmark
        chấm điểm cho mock. strict=True chặn việc đó tái diễn.

    lora_model_path: mặc định None — không đổi hành vi hiện có. Chỉ định thư
        mục adapter LoRA (đã train qua PEFT) để gắn vào model transformers
        SAU khi nạp xong. Chỉ backend="transformers" (hoặc auto rơi vào
        transformers) hỗ trợ; truyền cùng backend="vllm"/"mock" sẽ NÉM LỖI —
        im lặng bỏ qua sẽ khiến benchmark đo nhầm model gốc mà tưởng là model
        đã train.

    Chế độ "auto" không bao giờ ném lỗi khi strict=False — cùng lắm rơi về mock.
    """
    spec = lay_spec(model_key)

    if backend == "mock":
        if lora_model_path is not None:
            raise ValueError(
                f"lora_model_path={lora_model_path!r} không dùng được với backend=mock: "
                "mock không nạp model thật, gắn LoRA vô nghĩa."
            )
        if strict:
            raise RuntimeError(
                f"strict=True không cho phép backend=mock (model={model_key}): "
                "đo mock không phải kết quả model thật."
            )
        return MockAdapter(spec, ly_do="user selected backend=mock")

    # Hai backend chỉ định thẳng vốn đã tự ném lỗi khi không khởi tạo được, nên
    # strict=True hiện đúng ở đây. Bọc lại để bảo đảm đó là hợp đồng tường minh,
    # không phải may mắn — nếu sau này adapter nào đó im lặng degrade, strict vẫn chặn.
    if backend == "vllm":
        if lora_model_path is not None:
            raise ValueError(
                f"lora_model_path={lora_model_path!r} không dùng được với backend=vllm: "
                "VllmAdapter chưa hỗ trợ nạp LoRA."
            )
        return _nap_nghiem_ngat(VllmAdapter, spec, dung_4bit, model_key, "vLLM", strict)

    if backend == "transformers":
        if _la_ho_internvl(spec) and lora_model_path is None:
            from .adapter_internvl import InternVlAdapter

            return _nap_nghiem_ngat(
                InternVlAdapter, spec, dung_4bit, model_key, "internvl", strict
            )
        if _la_ho_minicpm(spec) and lora_model_path is None:
            from .adapter_minicpm import MiniCpmAdapter

            return _nap_nghiem_ngat(
                MiniCpmAdapter, spec, dung_4bit, model_key, "minicpm", strict
            )
        if _la_ho_moondream(spec) and lora_model_path is None:
            from .adapter_moondream import MoondreamAdapter

            return _nap_nghiem_ngat(
                MoondreamAdapter, spec, dung_4bit, model_key, "moondream", strict
            )
        return _nap_nghiem_ngat(
            TransformersAdapter,
            spec,
            dung_4bit,
            model_key,
            "transformers",
            strict,
            lora_model_path=lora_model_path,
        )

    if backend != "auto":
        raise ValueError(f"backend không hợp lệ: {backend!r}")

    if _co_the_dung_vllm():
        if lora_model_path is None:
            try:
                return VllmAdapter(spec, dung_4bit=dung_4bit)
            except Exception as loi:
                if strict:
                    raise RuntimeError(
                        f"strict=True: vLLM có mặt nhưng khởi tạo lỗi cho model={model_key}: {loi}"
                    ) from loi
                logger.warning(
                    "vLLM present but init failed (%s), falling back to transformers", loi
                )
        else:
            logger.warning(
                "lora_model_path duoc truyen, bo qua vLLM (chua ho tro LoRA), "
                "chuyen thang sang transformers"
            )

    if _co_the_dung_transformers():
        try:
            if _la_ho_internvl(spec) and lora_model_path is None:
                from .adapter_internvl import InternVlAdapter

                return InternVlAdapter(spec, dung_4bit=dung_4bit)
            if _la_ho_minicpm(spec) and lora_model_path is None:
                from .adapter_minicpm import MiniCpmAdapter

                return MiniCpmAdapter(spec, dung_4bit=dung_4bit)
            if _la_ho_moondream(spec) and lora_model_path is None:
                from .adapter_moondream import MoondreamAdapter

                return MoondreamAdapter(spec, dung_4bit=dung_4bit)
            return TransformersAdapter(spec, dung_4bit=dung_4bit, lora_model_path=lora_model_path)
        except Exception as loi:
            if strict:
                raise RuntimeError(
                    f"strict=True: transformers khởi tạo lỗi cho model={model_key}: {loi}"
                ) from loi
            logger.warning("transformers init failed (%s), falling back to mock", loi)
            return MockAdapter(spec, ly_do=f"transformers init failed: {loi}")

    if lora_model_path is not None:
        raise RuntimeError(
            f"lora_model_path={lora_model_path!r} được truyền nhưng không có backend nào "
            f"hỗ trợ LoRA khả dụng cho model={model_key} (transformers/torch chưa cài hoặc "
            "không có GPU). Rơi về mock sẽ đo nhầm model gốc, không phải model đã train."
        )

    if strict:
        raise RuntimeError(
            f"strict=True: không có GPU khả dụng, hoặc torch/transformers/vllm "
            f"chưa cài, cho model={model_key}. Không rơi về mock trong chế độ nghiêm ngặt."
        )

    return MockAdapter(spec, ly_do="no GPU available, or torch/transformers not installed")
