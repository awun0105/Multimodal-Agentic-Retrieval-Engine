"""
Lưu tiến độ để không mất trắng khi phiên chạy bị ngắt.

Vì sao bắt buộc: Kaggle cắt phiên sau 12 giờ, Colab ngắt khi mất kết nối. Chạy
100 ảnh mất vài chục phút — đứt giữa chừng mà không lưu thì làm lại từ đầu.

Nguyên tắc: ghi ra file tạm rồi mới đổi tên. Nếu ghi thẳng vào file thật mà bị
ngắt giữa chừng, file checkpoint sẽ hỏng — mất luôn cả phần đã chạy được.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

CHU_KY_LUU_MAC_DINH = 25


def duong_dan_checkpoint(thu_muc: Path, model_key: str) -> Path:
    return Path(thu_muc) / f"checkpoint_{model_key}.json"


def load_checkpoint(thu_muc: Path, model_key: str) -> dict[str, Any]:
    """
    Đọc checkpoint đã lưu. Chưa có hoặc file hỏng thì trả về rỗng.

    Không ném lỗi khi file hỏng — thà chạy lại từ đầu còn hơn dừng hẳn.
    """
    duong_dan = duong_dan_checkpoint(thu_muc, model_key)
    if not duong_dan.exists():
        return {"model_key": model_key, "da_xong": {}}

    try:
        du_lieu = json.loads(duong_dan.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"model_key": model_key, "da_xong": {}}

    if not isinstance(du_lieu, dict) or "da_xong" not in du_lieu:
        return {"model_key": model_key, "da_xong": {}}
    return du_lieu


def save_checkpoint(thu_muc: Path, model_key: str, du_lieu: dict[str, Any]) -> Path:
    """Lưu checkpoint an toàn: ghi file tạm rồi đổi tên (atomic)."""
    thu_muc = Path(thu_muc)
    thu_muc.mkdir(parents=True, exist_ok=True)
    dich = duong_dan_checkpoint(thu_muc, model_key)
    tam = dich.with_suffix(".tmp")

    tam.write_text(json.dumps(du_lieu, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tam, dich)  # đổi tên là thao tác nguyên tử, không tạo file nửa vời
    return dich


def filter_pending(tat_ca_anh: list[str], checkpoint: dict[str, Any]) -> list[str]:
    """Bỏ những ảnh đã chạy xong, trả về danh sách còn phải làm."""
    da_xong = set(checkpoint.get("da_xong", {}))
    return [anh for anh in tat_ca_anh if anh not in da_xong]
