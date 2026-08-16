"""
Smoke test chứng minh `providers_for_plan()` (system1/src) THỰC SỰ cố nạp
VLM khi `plan.shot_caption == "vlm"` — khác với hôm nay (trước Phase 03) là
âm thầm bỏ qua và luôn trả MockTextProvider/RealProviderUnavailable("mixed_real_unavailable").

Yêu cầu `pip install -e system1/` đã chạy (biên dịch package system1 cài đặt
được) — không tự thêm sys.path cho system1 ở đây.

Không import torch trực tiếp: import package `vlm` không cần torch ở mức
top-level (torch chỉ cần khi thực sự gọi `caption_image` -> `generate_json`).
Vì vậy trên máy hiện tại (không có torch), nạp `tao_provider("vlm")` THÀNH
CÔNG — ca "thiếu torch" được test bằng cách giả lập lỗi import thực sự
(monkeypatch builtins.__import__), tái tạo đúng tình huống máy nào đó thiếu
cả thư mục/torch/dependency bất kỳ.
"""

from __future__ import annotations

import builtins
import logging
from pathlib import Path

import pytest

from system1.config import ProviderPlan
from system1.features.builder import providers_for_plan
from system1.features.providers import MockTextProvider, RealProviderUnavailable


def _plan(shot_caption: str) -> ProviderPlan:
    return ProviderPlan(
        asr="mock",
        ocr="mock",
        embedding="mock",
        object_detection="mock",
        shot_caption=shot_caption,
        scene_summary="mock",
    )


def test_mock_khong_co_nap_vlm():
    """shot_caption != 'vlm' -> hành vi cũ, không đụng tới research/vlm_prompting."""
    _, text_provider = providers_for_plan(_plan("mock"))
    assert isinstance(text_provider, MockTextProvider)


def test_vlm_nap_that_thanh_cong_tren_may_khong_torch():
    """
    Ca kiểm quan trọng nhất: máy local không có torch nhưng import package
    `vlm` không cần torch ở top-level (thiết kế lười của Phase 02) -> nạp
    thành công, provider thật được trả về, không ném lỗi.
    """
    _, text_provider = providers_for_plan(_plan("vlm"))
    assert type(text_provider).__name__ == "VlmShotCaptionProvider"


def test_vlm_that_bai_roi_ve_real_provider_unavailable(monkeypatch, caplog):
    """
    Giả lập lỗi nạp thực sự (thiếu dependency/đường dẫn hỏng) bằng cách chặn
    mọi import bắt đầu bằng "vlm" -> phải rơi về RealProviderUnavailable,
    KHÔNG ném lỗi, và log phải chứa "vlm_unavailable".
    """
    import sys as sys_module

    real_import = builtins.__import__

    def _import_loi(name, *args, **kwargs):
        if name == "vlm" or name.startswith("vlm."):
            raise ImportError("gia lap thieu torch")
        return real_import(name, *args, **kwargs)

    for mod_name in list(sys_module.modules):
        if mod_name == "vlm" or mod_name.startswith("vlm."):
            monkeypatch.delitem(sys_module.modules, mod_name, raising=False)

    monkeypatch.setattr(builtins, "__import__", _import_loi)

    with caplog.at_level(logging.WARNING):
        _, text_provider = providers_for_plan(_plan("vlm"))

    assert isinstance(text_provider, RealProviderUnavailable)
    assert "vlm_unavailable" in text_provider.provider_name
    assert any("vlm_unavailable" in record.message for record in caplog.records)


def test_duong_dan_vlm_provider_ton_tai_that():
    """Ca chống hồi quy: bắt lỗi khi ai đó đổi tên/di chuyển research/vlm_prompting/vlm/."""
    duong_dan = Path(__file__).resolve().parents[1] / "vlm" / "provider.py"
    assert duong_dan.exists(), f"vlm/provider.py bien mat hoac doi cho: {duong_dan}"


def test_profile_real_khong_bi_cuop_mat_provider():
    """Profile "real" cũng khai shot_caption="vlm" nhưng dùng paddleocr/yolo THẬT.
    Nạp VLM provider ở đó sẽ cướp mất hai provider kia — regression thật đã xảy ra.
    Phân biệt bằng ocr/object_detection: chỉ profile "vlm" để cả hai ở "mock"."""
    real = ProviderPlan(
        asr="whisper",
        ocr="paddleocr",
        embedding="openclip",
        object_detection="yolo",
        shot_caption="vlm",
        scene_summary="llm",
    )
    _, text_provider = providers_for_plan(real)
    assert isinstance(text_provider, RealProviderUnavailable)


def test_detect_khong_tra_list_rong():
    """`features/builder.py:197` lấy `objects[0]` không kiểm tra rỗng → list rỗng
    gây IndexError làm sập cả mẻ."""
    _, text_provider = providers_for_plan(_plan("vlm"))
    objects = text_provider.detect(Path("bat_ky.jpg"))
    assert objects, "detect() tra list rong se gay IndexError o builder.py:197"
    assert objects[0]
