"""
Kiểm hành vi nạp LoRA của `TransformersAdapter` / `get_adapter`.

Máy local không có torch/transformers/peft thật. Chọn cách monkeypatch
`vlm.model_loader.load_model` (thay vì chèn module giả vào sys.modules cho cả
torch/transformers) vì `load_model` đã là đường lazy-import duy nhất mà
`TransformersAdapter.__init__` gọi tới — patch đúng một điểm nối là đủ, không
cần giả lập toàn bộ cây phụ thuộc torch. `peft` được giả lập bằng module thật
chèn vào `sys.modules["peft"]` vì đó là thư viện duy nhất `_gan_lora` tự import.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

from vlm.adapters import TransformersAdapter, get_adapter
from vlm.model_loader import VlmKhongSanSang

MODEL_KEY = "qwen25vl-3b"


class _ModelGia:
    pass


class _ProcessorGia:
    pass


def _load_model_gia(model_key: str, *, dung_4bit: bool = True):
    from vlm.model_registry import lay_spec

    return _ModelGia(), _ProcessorGia(), lay_spec(model_key)


@pytest.fixture(autouse=True)
def _mock_load_model(monkeypatch):
    monkeypatch.setattr("vlm.model_loader.load_model", _load_model_gia)


@pytest.fixture
def peft_gia(monkeypatch):
    """Chèn module peft giả với PeftModel.from_pretrained ghi lại lệnh gọi."""
    goi_lai = []

    class _PeftModelGia:
        @staticmethod
        def from_pretrained(model, lora_path):
            goi_lai.append((model, lora_path))
            return f"model_da_gan_lora({lora_path})"

    modun_gia = types.ModuleType("peft")
    modun_gia.PeftModel = _PeftModelGia
    monkeypatch.setitem(sys.modules, "peft", modun_gia)
    return goi_lai


@pytest.fixture
def lora_hop_le(tmp_path) -> str:
    thu_muc = tmp_path / "lora-adapter"
    thu_muc.mkdir()
    (thu_muc / "adapter_config.json").write_text("{}", encoding="utf-8")
    return str(thu_muc)


def test_khong_truyen_lora_khong_goi_peft(peft_gia):
    """Mặc định None -> PeftModel.from_pretrained 0 lần. Đây là bằng chứng rollback."""
    adapter = TransformersAdapter(_spec_that())
    assert peft_gia == []
    assert isinstance(adapter.model, _ModelGia)


def test_truyen_lora_hop_le_goi_peft_dung_1_lan(peft_gia, lora_hop_le):
    adapter = TransformersAdapter(_spec_that(), lora_model_path=lora_hop_le)

    assert len(peft_gia) == 1
    model_truyen_vao, duong_dan_truyen_vao = peft_gia[0]
    assert isinstance(model_truyen_vao, _ModelGia)
    assert duong_dan_truyen_vao == lora_hop_le
    assert adapter.model == f"model_da_gan_lora({lora_hop_le})"


def test_get_adapter_backend_transformers_truyen_dung_lora(peft_gia, lora_hop_le):
    adapter = get_adapter(MODEL_KEY, backend="transformers", lora_model_path=lora_hop_le)
    assert len(peft_gia) == 1
    assert peft_gia[0][1] == lora_hop_le
    assert adapter.backend_name.endswith("+lora")


def test_get_adapter_backend_mock_voi_lora_nem_loi():
    with pytest.raises(ValueError):
        get_adapter(MODEL_KEY, backend="mock", lora_model_path="bat_ky/duong/dan")


def test_get_adapter_backend_vllm_voi_lora_nem_loi():
    with pytest.raises(ValueError):
        get_adapter(MODEL_KEY, backend="vllm", lora_model_path="bat_ky/duong/dan")


def test_duong_dan_lora_khong_ton_tai_nem_vlm_khong_san_sang(peft_gia, tmp_path):
    duong_dan_sai = str(tmp_path / "khong-ton-tai")
    with pytest.raises(VlmKhongSanSang):
        TransformersAdapter(_spec_that(), lora_model_path=duong_dan_sai)
    assert peft_gia == []


def test_backend_name_phan_biet_co_khong_co_lora(peft_gia, lora_hop_le):
    khong_lora = TransformersAdapter(_spec_that())
    co_lora = TransformersAdapter(_spec_that(), lora_model_path=lora_hop_le)
    assert khong_lora.backend_name != co_lora.backend_name
    assert not khong_lora.backend_name.endswith("+lora")
    assert co_lora.backend_name.endswith("+lora")


def _spec_that():
    from vlm.model_registry import lay_spec

    return lay_spec(MODEL_KEY)
