"""
Định nghĩa hình dạng JSON mà VLM phải trả về.

Đây là "hợp đồng" của toàn bộ Phần 3: mọi model, mọi prompt, mọi lần chạy
đều phải quy về đúng một hình dạng này. Nhờ vậy đổi model không làm vỡ code
phía sau.

Hai hợp đồng phải thỏa mãn cùng lúc:
  1. Đề bài AIC  → bắt buộc có caption_chi_tiet (tiếng Việt, mô tả dài)
  2. Repo system1 → schemas/shot_captions.schema.json bắt buộc caption_vi VÀ caption_en
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator

SCHEMA_VERSION = "v1"

CAPTION_MIN_LENGTH = 25

# Model hay lặp tên trường vào đầu giá trị: "Caption Chi tiết: Một người...".
# Đo thật trên 92 keyframe cho thấy lỗi này xảy ra ngay ở ảnh đầu tiên.
# Khớp mọi nhãn ngắn đứng trước dấu hai chấm ở đầu chuỗi. Không liệt kê từng
# biến thể ("Caption Chi tiết", "Mô tả"...) vì dấu tiếng Việt có nhiều cách mã
# hóa Unicode khác nhau — liệt kê kiểu đó sẽ sót.
_NHAN_THUA = re.compile(r"^\s*[\w\s_]{1,25}[:：]\s+(?=\S)")


def _bo_nhan_thua(v: str) -> str:
    """Cắt nhãn tên trường nếu model lỡ ghi vào đầu giá trị."""
    return _NHAN_THUA.sub("", v).strip()


class KeyframeMetadata(BaseModel):
    """
    Metadata sinh ra từ một khung hình.

    Tên trường giữ nguyên tiếng Việt không dấu theo đúng mẫu trong đề bài —
    đổi tên sẽ lệch yêu cầu bàn giao.
    """

    doi_tuong: list[str] = Field(default_factory=list)
    mau_sac: list[str] = Field(default_factory=list)
    hanh_dong: str = ""
    boi_canh: str = ""
    caption_chi_tiet: str
    caption_en: str = ""

    @field_validator("caption_chi_tiet")
    @classmethod
    def caption_phai_du_dai(cls, v: str) -> str:
        # Model nhỏ hay trả lời cụt kiểu "một con mèo" — vô dụng cho tìm kiếm.
        v = _bo_nhan_thua(v.strip())
        if len(v) < CAPTION_MIN_LENGTH:
            raise ValueError(
                f"caption_chi_tiet quá ngắn ({len(v)} ký tự, cần >= {CAPTION_MIN_LENGTH}): {v!r}"
            )
        return v

    @field_validator("doi_tuong", "mau_sac", mode="before")
    @classmethod
    def ep_ve_danh_sach(cls, v: object) -> list[str]:
        # Model đôi khi trả chuỗi "xe máy, người" thay vì list.
        if v is None:
            return []
        if isinstance(v, str):
            return [phan.strip() for phan in v.split(",") if phan.strip()]
        if isinstance(v, list):
            return [str(phan).strip() for phan in v if str(phan).strip()]
        return [str(v)]

    @field_validator("hanh_dong", "boi_canh", "caption_en", mode="before")
    @classmethod
    def ep_ve_chuoi(cls, v: object) -> str:
        if v is None:
            return ""
        if isinstance(v, list):
            return ", ".join(str(phan) for phan in v)
        return str(v)


def to_shot_caption_row(
    metadata: KeyframeMetadata,
    *,
    shot_id: str,
    video_id: str,
    keyframe_id: str,
    timestamp_sec: float,
    provider: str,
    model_name: str,
    model_version: str,
    prompt_version: str,
    status: str = "ok",
    confidence: float | None = None,
) -> dict:
    """
    Chuyển metadata sang đúng hàng của `system1/schemas/shot_captions.schema.json`.

    Tách riêng khỏi KeyframeMetadata vì hai thứ có vòng đời khác nhau: metadata
    là kết quả thuần của model, còn hàng shot_caption cần thêm thông tin định
    danh mà model không biết (shot_id, video_id, timestamp).
    """
    return {
        "shot_caption_id": f"{shot_id}:{prompt_version}",
        "shot_id": shot_id,
        "video_id": video_id,
        "representative_keyframe_id": keyframe_id,
        "representative_timestamp_sec": timestamp_sec,
        "caption_vi": metadata.caption_chi_tiet,
        "caption_en": metadata.caption_en or metadata.caption_chi_tiet,
        "provider": provider,
        "model_name": model_name,
        "model_version": model_version,
        "prompt_version": prompt_version,
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "confidence": confidence,
        "vlm_metadata": {
            "doi_tuong": metadata.doi_tuong,
            "mau_sac": metadata.mau_sac,
            "hanh_dong": metadata.hanh_dong,
            "boi_canh": metadata.boi_canh,
        },
    }
