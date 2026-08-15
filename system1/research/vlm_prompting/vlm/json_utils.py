"""
Cứu JSON méo do model trả về.

Model là thứ xác suất: cùng một prompt, hôm nay trả JSON sạch, mai lại thêm
"Đây là kết quả:" phía trước hoặc bọc trong ```json. Không bao giờ được tin
json.loads() chạy được ngay lần đầu.

Ba tầng cứu hộ, thử lần lượt từ rẻ tới đắt.
"""

from __future__ import annotations

import json
import re

_FENCE_PATTERN = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


class JsonParseError(ValueError):
    """Không cứu được JSON. Giữ nguyên text thô để còn debug."""

    def __init__(self, message: str, raw_text: str):
        super().__init__(message)
        self.raw_text = raw_text


def parse_json_safe(raw: str) -> dict:
    """
    Bóc dict JSON ra khỏi output thô của model.

    Thứ tự thử:
        1. json.loads thẳng — trường hợp model ngoan
        2. Bóc khỏi khối ```json ... ```
        3. Quét thủ công cặp ngoặc {} cân bằng đầu tiên

    Raise JsonParseError kèm text gốc nếu cả ba đều thất bại.
    """
    if not raw or not raw.strip():
        raise JsonParseError("Model trả về chuỗi rỗng", raw or "")

    text = raw.strip()

    ket_qua = _thu_json_truc_tiep(text)
    if ket_qua is not None:
        return ket_qua

    for khoi in _FENCE_PATTERN.findall(text):
        ket_qua = _thu_json_truc_tiep(khoi.strip())
        if ket_qua is not None:
            return ket_qua

    doan_ngoac = _trich_ngoac_can_bang(text)
    if doan_ngoac:
        ket_qua = _thu_json_truc_tiep(doan_ngoac)
        if ket_qua is not None:
            return ket_qua

    raise JsonParseError(
        f"Không tìm thấy JSON hợp lệ trong output (dài {len(raw)} ký tự)", raw
    )


def _thu_json_truc_tiep(text: str) -> dict | None:
    try:
        gia_tri = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None
    return gia_tri if isinstance(gia_tri, dict) else None


def _trich_ngoac_can_bang(text: str) -> str | None:
    """
    Tìm cặp {} cân bằng đầu tiên.

    Không dùng regex đơn giản vì JSON có ngoặc lồng nhau — regex sẽ cắt nhầm
    ở ngoặc đóng đầu tiên gặp phải.
    """
    vi_tri_mo = text.find("{")
    if vi_tri_mo == -1:
        return None

    do_sau = 0
    trong_chuoi = False
    thoat_ky_tu = False

    for i in range(vi_tri_mo, len(text)):
        ky_tu = text[i]

        if thoat_ky_tu:
            thoat_ky_tu = False
            continue
        if ky_tu == "\\":
            thoat_ky_tu = True
            continue
        if ky_tu == '"':
            trong_chuoi = not trong_chuoi
            continue
        if trong_chuoi:
            continue

        if ky_tu == "{":
            do_sau += 1
        elif ky_tu == "}":
            do_sau -= 1
            if do_sau == 0:
                return text[vi_tri_mo : i + 1]

    return None
