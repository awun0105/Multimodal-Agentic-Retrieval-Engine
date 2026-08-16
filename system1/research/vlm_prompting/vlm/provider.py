"""
Bọc generate_json() thành provider cắm được vào system1.

Repo đã định sẵn chỗ cho phần này:
  - `features/providers.py:26` định nghĩa Protocol `ImageCaptionProvider`
  - `config/loader.py:52,63` đã khai báo `shot_caption="vlm"` cho profile
    "real" và "vlm" — hệ thống đang CHỜ một provider tên "vlm"
  - `schemas/shot_captions.schema.json` quy định hình dạng hàng dữ liệu

File này lấp đúng chỗ trống đó. Đặt trong research/ thay vì src/system1/ vì
`pyproject.toml` của system1 chưa khai báo torch — import cứng sẽ làm vỡ CI của
cả nhóm. Khi nào chốt model và thêm dependency thì mới chuyển vào src/.

Cách dùng:
    from vlm.provider import VlmShotCaptionProvider

    provider = VlmShotCaptionProvider(model_key="qwen25vl-3b")
    caption = provider.caption_image(Path("keyframe.jpg"), fallback_text="")
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .model_registry import MODEL_MAC_DINH
from .prompts import PROMPT_VERSION
from .schema import SCHEMA_VERSION, KeyframeMetadata, to_shot_caption_row

logger = logging.getLogger(__name__)

PROVIDER_NAME = "vlm"


class VlmShotCaptionProvider:
    """
    Provider sinh caption bằng VLM, hợp với Protocol `ImageCaptionProvider`.

    Thỏa mãn cả 3 protocol của repo:
        caption_image(image_path, fallback_text) -> str    # ImageCaptionProvider
        caption_shot(shot_id, fallback_text) -> str        # ShotCaptionProvider
        summarize_scene(scene_id, fallback_text) -> str    # SceneSummaryProvider

    Kèm read_text / detect / transcribe trả rỗng, vì `features/builder.py` dùng
    MỘT text_provider duy nhất cho cả OCR lẫn caption. Xem chú thích tại chỗ.

    Nguyên tắc thiết kế: KHÔNG BAO GIỜ ném lỗi ra ngoài. Một ảnh lỗi không được
    làm hỏng cả mẻ ingest hàng nghìn keyframe — trả `fallback_text` và ghi log.
    Đây là cách `RealProviderUnavailable` (features/providers.py:64) đang làm.
    """

    def __init__(
        self,
        model_key: str = MODEL_MAC_DINH,
        *,
        backend: str = "auto",
        dung_4bit: bool = True,
        luu_metadata: bool = True,
    ):
        self.model_key = model_key
        self.backend = backend
        self.dung_4bit = dung_4bit
        self.luu_metadata = luu_metadata

        # Giữ metadata đầy đủ của lần chạy gần nhất, để caller lấy ra dựng hàng
        # shot_captions mà không phải chạy model lần hai.
        self._metadata_gan_nhat: dict[str, Any] | None = None

    @property
    def provider_name(self) -> str:
        return PROVIDER_NAME

    @property
    def metadata_gan_nhat(self) -> dict[str, Any] | None:
        """Kết quả đầy đủ của lần caption gần nhất (gồm doi_tuong, mau_sac...)."""
        return self._metadata_gan_nhat

    def caption_image(self, image_path: Path, fallback_text: str) -> str:
        """
        Sinh caption tiếng Việt cho một ảnh.

        Trả về `caption_chi_tiet`. Lỗi thì trả `fallback_text` — không ném.
        Metadata đầy đủ lấy qua thuộc tính `metadata_gan_nhat`.
        """
        from .generate import generate_json

        try:
            ket_qua = generate_json(
                image_path,
                model_key=self.model_key,
                backend=self.backend,
                dung_4bit=self.dung_4bit,
            )
        except Exception as loi:  # noqa: BLE001 - một ảnh lỗi không được dừng cả mẻ
            logger.warning("VLM caption failed for %s: %s", image_path, loi)
            self._metadata_gan_nhat = None
            return fallback_text

        if self.luu_metadata:
            self._metadata_gan_nhat = ket_qua
        return ket_qua.get("caption_chi_tiet") or fallback_text

    def caption_shot(self, shot_id: str, fallback_text: str) -> str:
        """
        Caption cho một shot.

        Provider này làm việc trên ẢNH, không tra được đường dẫn từ shot_id —
        việc đó thuộc về tầng gọi. Nên trả thẳng fallback, đúng tinh thần
        degrade thay vì giả vờ làm được.
        """
        return fallback_text

    def summarize_scene(self, scene_id: str, fallback_text: str) -> str:
        """Tóm tắt scene — cùng lý do như caption_shot."""
        return fallback_text

    # `features/builder.py:192-193` gọi read_text() và detect() trên CÙNG một
    # text_provider với caption. Thiếu hai hàm này thì pipeline ném AttributeError
    # ngay khi profile "vlm" chạy thật — provider phải phủ đủ bộ Protocol dù VLM
    # không đảm nhiệm OCR (Phần 2) hay nhận diện vật thể (ObjectDetectionProvider).
    def read_text(self, image_path: Path) -> str:
        return ""

    def detect(self, image_path: Path) -> list[str]:
        # KHÔNG trả list rỗng: `features/builder.py:197` lấy `objects[0]` mà
        # không kiểm tra rỗng → IndexError làm sập cả mẻ. Hai provider sẵn có
        # cũng luôn trả list khác rỗng vì cùng lý do đó.
        return ["unknown"]

    def transcribe(self, video_path: Path) -> str:
        return ""

    def build_shot_caption_row(
        self,
        *,
        shot_id: str,
        video_id: str,
        keyframe_id: str,
        timestamp_sec: float,
    ) -> dict[str, Any] | None:
        """
        Dựng hàng dữ liệu đúng `schemas/shot_captions.schema.json` từ kết quả
        caption gần nhất.

        Trả None nếu lần chạy gần nhất thất bại — caller tự quyết định bỏ qua
        hay ghi hàng status="failed".
        """
        if not self._metadata_gan_nhat:
            return None

        metadata = KeyframeMetadata(**{
            k: v for k, v in self._metadata_gan_nhat.items() if not k.startswith("_")
        })
        # Không chép cứng status="ok" ở đây — to_shot_caption_row() tự quyết
        # "ok"/"partial" dựa trên caption_en có rỗng hay không. Chép cứng sẽ
        # ghi đè quyết định đó, làm lộ lại chính lỗi mà schema.py vừa sửa.
        return to_shot_caption_row(
            metadata,
            shot_id=shot_id,
            video_id=video_id,
            keyframe_id=keyframe_id,
            timestamp_sec=timestamp_sec,
            provider=PROVIDER_NAME,
            model_name=self._metadata_gan_nhat.get("_model", self.model_key),
            model_version=self._metadata_gan_nhat.get("_backend", "unknown"),
            prompt_version=PROMPT_VERSION,
        )


def tao_provider(provider_ten: str, **kwargs: Any):
    """
    Tạo provider theo tên khai báo trong `configs/models.yaml`.

    Trả None nếu tên không phải "vlm" — để tầng gọi tự dùng provider khác.
    """
    if provider_ten != PROVIDER_NAME:
        return None
    return VlmShotCaptionProvider(**kwargs)


__all__ = [
    "VlmShotCaptionProvider",
    "tao_provider",
    "PROVIDER_NAME",
    "SCHEMA_VERSION",
]
