"""
Đọc kết quả caption đã chạy, chuẩn hoá về một dạng duy nhất cho bộ đo dùng.

Có hai định dạng đầu vào khả dĩ:
  - checkpoint_<model>.json  (từ benchmark_runner.py, dict {"da_xong": {...}})
  - sample_results.json     (list phẳng, mỗi phần tử một ảnh)

Không viết lại `load_checkpoint` — import thẳng từ scripts/checkpoint_utils.py
vì đó đã là chỗ đọc đúng định dạng checkpoint, thêm bản thứ hai chỉ tạo lệch.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# checkpoint_utils.py nằm ở scripts/, ngang hàng quality/ — thêm vào sys.path
# vì đây là script chạy độc lập, không phải package cài qua pip.
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from checkpoint_utils import load_checkpoint  # noqa: E402

# Không `from vlm.schema import _bo_nhan_thua` trực tiếp: import gói `vlm`
# (dot notation) luôn chạy `vlm/__init__.py` trước — file đó kéo theo
# model_loader/generate/adapters, những module có phụ thuộc GPU nặng mà
# quality/ phải chạy thuần CPU không có. Nạp thẳng module schema.py bằng
# importlib, bỏ qua __init__.py của gói vlm — cùng cách caption_defect_checks.py
# đã dùng để nạp prompts.py, giữ nhất quán trong cả package quality/.
_SCHEMA_PATH = Path(__file__).resolve().parent.parent / "vlm" / "schema.py"
_spec = importlib.util.spec_from_file_location("_vlm_schema_only", _SCHEMA_PATH)
_schema_module = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("_vlm_schema_only", _schema_module)
_spec.loader.exec_module(_schema_module)
_bo_nhan_thua = _schema_module._bo_nhan_thua


@dataclass
class CaptionRow:
    """Một dòng caption đã chuẩn hoá, sẵn sàng cho bộ đo recall / defect."""

    ten_anh: str
    caption: str
    doi_tuong: list[str]
    mau_sac: list[str]
    hanh_dong: str = ""
    boi_canh: str = ""


def _la_mock(ket_qua: dict[str, Any]) -> bool:
    """Mock adapter luôn trả doi_tuong/mau_sac = ["[mock]"] — xem vlm/adapters.py."""
    return ket_qua.get("doi_tuong") == ["[mock]"] or ket_qua.get("mau_sac") == ["[mock]"]


def _tu_ket_qua(ten_anh: str, ket_qua: dict[str, Any] | None) -> CaptionRow | None:
    """Chuyển một mục `ket_qua` thô thành CaptionRow, hoặc None nếu không dùng được."""
    if not ket_qua:
        return None
    if _la_mock(ket_qua):
        return None
    # Dùng lại _bo_nhan_thua của vlm/schema.py (đã xử lý đúng lúc sinh) thay vì
    # viết regex thứ hai — tránh hai bộ luật cắt nhãn lệch nhau theo thời gian.
    caption = _bo_nhan_thua(str(ket_qua.get("caption_chi_tiet", "")).strip())
    if not caption:
        return None
    return CaptionRow(
        ten_anh=ten_anh,
        caption=caption,
        doi_tuong=[str(x) for x in (ket_qua.get("doi_tuong") or [])],
        mau_sac=[str(x) for x in (ket_qua.get("mau_sac") or [])],
        hanh_dong=str(ket_qua.get("hanh_dong", "")),
        boi_canh=str(ket_qua.get("boi_canh", "")),
    )


def doc_checkpoint(duong_dan: Path) -> tuple[list[CaptionRow], int]:
    """
    Đọc file checkpoint_<model>.json, trả về (danh sách caption dùng được, số bị bỏ).

    Bỏ qua mục [mock] và mục thất bại — nhưng ĐẾM lại, không lặng lẽ bỏ, vì
    im lặng bỏ dữ liệu là cách dễ nhất để tưởng công cụ chạy đúng khi thực ra
    đang đo trên tập rỗng.
    """
    thu_muc = duong_dan.parent
    model_key = duong_dan.stem.removeprefix("checkpoint_")
    checkpoint = load_checkpoint(thu_muc, model_key)

    rows: list[CaptionRow] = []
    so_bo_qua = 0
    for ten_anh, muc in checkpoint.get("da_xong", {}).items():
        if not muc.get("thanh_cong"):
            so_bo_qua += 1
            continue
        row = _tu_ket_qua(ten_anh, muc.get("ket_qua"))
        if row is None:
            so_bo_qua += 1
            continue
        rows.append(row)
    return rows, so_bo_qua


def doc_sample_results(duong_dan: Path) -> tuple[list[CaptionRow], int]:
    """Đọc file sample_results.json (list phẳng, mỗi phần tử có 'image' + **ket_qua)."""
    try:
        du_lieu = json.loads(duong_dan.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return [], 0

    if not isinstance(du_lieu, list):
        return [], 0

    rows: list[CaptionRow] = []
    so_bo_qua = 0
    for muc in du_lieu:
        ten_anh = str(muc.get("image", ""))
        row = _tu_ket_qua(ten_anh, muc)
        if row is None:
            so_bo_qua += 1
            continue
        rows.append(row)
    return rows, so_bo_qua


def load_captions(duong_dan: Path) -> tuple[list[CaptionRow], int]:
    """
    Điểm vào duy nhất: tự nhận diện định dạng theo tên file, đọc và chuẩn hoá.

    Trả về (danh_sach_caption, so_muc_bi_bo_qua).
    """
    duong_dan = Path(duong_dan)
    if duong_dan.name.startswith("checkpoint_"):
        return doc_checkpoint(duong_dan)
    return doc_sample_results(duong_dan)
