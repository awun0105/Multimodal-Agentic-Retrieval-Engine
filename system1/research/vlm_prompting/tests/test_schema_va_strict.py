"""
Test cho hai lỗi sửa ở Phase 02:

1. `to_shot_caption_row()` không được nhét caption tiếng Việt vào ô caption_en
   khi model không sinh được tiếng Anh — trước đây bị vậy, làm nhiễm index
   tiếng Anh của cả nhóm (xem vlm/schema.py).
2. `get_adapter(strict=True)` phải NÉM LỖI khi không tải được model thật thay
   vì âm thầm rơi về MockAdapter — đây là nguồn gốc số liệu giả trong report
   benchmark cũ (xem vlm/adapters.py).

Chỉ dùng hàm thuần + backend="mock"/"auto" không GPU — không tải model thật,
chạy được trên Python 3.14 local không cần torch.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

GOC = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(GOC))

from vlm.adapters import MockAdapter, get_adapter  # noqa: E402
from vlm.schema import _THIEU_CAPTION_EN, KeyframeMetadata, to_shot_caption_row  # noqa: E402


def _metadata(*, caption_en: str = "") -> KeyframeMetadata:
    return KeyframeMetadata(
        doi_tuong=["người"],
        mau_sac=["xanh"],
        hanh_dong="đi bộ",
        boi_canh="đường phố",
        caption_chi_tiet="Một người đang đi bộ trên đường phố đông đúc buổi sáng.",
        caption_en=caption_en,
    )


def _row(**kwargs) -> dict:
    return to_shot_caption_row(
        _metadata(**kwargs),
        shot_id="shot_001",
        video_id="video_001",
        keyframe_id="kf_001",
        timestamp_sec=1.5,
        provider="vlm",
        model_name="test-model",
        model_version="test-backend",
        prompt_version="v1",
    )


class TestMapCaptionEn:
    """schema.py — to_shot_caption_row() quyết định caption_en + status."""

    def test_co_caption_en_thi_dung_va_status_ok(self):
        row = _row(caption_en="A person walking on a busy street in the morning.")
        assert row["caption_en"] == "A person walking on a busy street in the morning."
        assert row["status"] == "ok"

    def test_khong_co_caption_en_thi_rong_va_status_partial(self):
        row = _row(caption_en="")
        assert row["caption_en"] == _THIEU_CAPTION_EN
        assert row["status"] == "partial"

    def test_khong_co_caption_en_nhung_caller_truyen_failed_thi_giu_failed(self):
        metadata = _metadata(caption_en="")
        row = to_shot_caption_row(
            metadata,
            shot_id="shot_001",
            video_id="video_001",
            keyframe_id="kf_001",
            timestamp_sec=1.5,
            provider="vlm",
            model_name="test-model",
            model_version="test-backend",
            prompt_version="v1",
            status="failed",
        )
        assert row["status"] == "failed"
        assert row["caption_en"] == _THIEU_CAPTION_EN

    def test_caption_en_khong_bao_gio_trung_caption_vi_khi_model_khong_sinh_tieng_anh(self):
        """Ca kiểm ngược — chặn lỗi tái xuất hiện: caption tiếng Việt không được
        lọt vào ô caption_en dưới bất kỳ hình thức nào."""
        row = _row(caption_en="")
        assert row["caption_en"] != row["caption_vi"]
        assert row["caption_en"] == _THIEU_CAPTION_EN

    def test_caption_en_luon_du_dai_theo_schema_cua_nhom(self):
        """`shot_captions.schema.json` bắt caption_en minLength >= 1. Trả chuỗi
        rỗng làm validator chặn cả mẻ — đã xảy ra thật, test này chặn tái diễn."""
        for caption_en in ("", "A man walks down the street."):
            row = _row(caption_en=caption_en)
            assert len(row["caption_en"]) >= 1


class TestGetAdapterStrict:
    """adapters.py — get_adapter(strict=...) fail-loud khi benchmark, fail-soft khi production."""

    def test_strict_true_khong_co_gpu_thi_nem_loi(self):
        with pytest.raises(RuntimeError):
            get_adapter("qwen25vl-3b", backend="auto", strict=True)

    def test_strict_true_backend_mock_cung_nem_loi(self):
        with pytest.raises(RuntimeError):
            get_adapter("qwen25vl-3b", backend="mock", strict=True)

    def test_strict_false_khong_co_gpu_thi_van_tra_mock_adapter(self):
        """Hành vi production giữ nguyên 100% — không phá cách chạy cũ."""
        adapter = get_adapter("qwen25vl-3b", backend="auto", strict=False)
        assert isinstance(adapter, MockAdapter)

    def test_strict_mac_dinh_la_false(self):
        """Không truyền strict → hành vi y hệt trước khi có cờ này."""
        adapter = get_adapter("qwen25vl-3b", backend="mock")
        assert isinstance(adapter, MockAdapter)
