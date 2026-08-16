"""
Phát hiện ảnh trắng/hỏng bằng số đo, không dựa vào agent tự đánh giá.

Vì sao cần: agent thầy khi thấy ảnh mờ/nhạt hay tự quyết "bỏ qua" dù ảnh vẫn
bình thường — đo thật trên kho 355 ảnh cho thấy agent bỏ nhầm nhiều ảnh có
biên độ sáng > 100. Ngược lại vài ảnh trắng thật (biên độ < 30) agent vẫn giữ.
Lọc bằng số trước khi đưa ảnh vào prompt loại bỏ hoàn toàn sự tùy tiện đó.

Đo bằng biên độ sáng (max - min của kênh xám) trên ảnh đã thu nhỏ 160x90 —
thu nhỏ trước khi tính nhanh hơn nhiều lần so với tính trên ảnh gốc và cho
kết quả gần như không đổi (đã đối chiếu trên toàn bộ 355 ảnh).

Không import torch — chỉ dùng Pillow (đã có sẵn trong repo).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image, UnidentifiedImageError

if sys.platform.startswith("win"):
    for _luong in (sys.stdout, sys.stderr):
        try:
            _luong.reconfigure(encoding="utf-8")
        except (AttributeError, OSError):
            pass

GOC = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(GOC))

NGUONG_BIEN_DO_MAC_DINH = 30
KICH_THUOC_THU_NHO = (160, 90)


def la_anh_hong(duong_dan: Path, *, nguong_bien_do: int = NGUONG_BIEN_DO_MAC_DINH) -> bool:
    """
    Trả True nếu ảnh trắng/phẳng/không mở được — dùng số đo, không đoán.

    getextrema() trên ảnh grayscale trả thẳng (min, max) — nhanh hơn và không
    bị cảnh báo deprecated như getdata(). File hỏng/không phải ảnh → True
    (coi là hỏng) để không làm sập cả mẻ đang chạy.
    """
    try:
        with Image.open(duong_dan) as anh:
            anh_xam = anh.convert("L").resize(KICH_THUOC_THU_NHO)
            gia_tri_nho_nhat, gia_tri_lon_nhat = anh_xam.getextrema()
    except (OSError, UnidentifiedImageError, ValueError):
        return True

    return (gia_tri_lon_nhat - gia_tri_nho_nhat) < nguong_bien_do


def loc_danh_sach_anh(
    danh_sach: list[Path], *, nguong_bien_do: int = NGUONG_BIEN_DO_MAC_DINH
) -> tuple[list[Path], list[Path]]:
    """Tách danh_sach thành (anh_tot, anh_hong), giữ nguyên thứ tự gốc."""
    anh_tot: list[Path] = []
    anh_hong: list[Path] = []
    for duong_dan in danh_sach:
        if la_anh_hong(duong_dan, nguong_bien_do=nguong_bien_do):
            anh_hong.append(duong_dan)
        else:
            anh_tot.append(duong_dan)
    return anh_tot, anh_hong


def main() -> None:
    from scripts.dieu_phoi_agent_caption import liet_ke_anh

    parser = argparse.ArgumentParser(
        description="Quet thu muc anh, bao anh trang/hong bang bien do sang."
    )
    parser.add_argument("--thu-muc-anh", type=Path, default=Path("data/keyframes_aic"))
    parser.add_argument("--nguong-bien-do", type=int, default=NGUONG_BIEN_DO_MAC_DINH)
    args = parser.parse_args()

    danh_sach_anh = liet_ke_anh(args.thu_muc_anh)
    anh_tot, anh_hong = loc_danh_sach_anh(danh_sach_anh, nguong_bien_do=args.nguong_bien_do)

    print(f"Tong so anh: {len(danh_sach_anh)}")
    print(f"Anh tot: {len(anh_tot)}")
    print(f"Anh hong: {len(anh_hong)}")
    for duong_dan in anh_hong:
        print(f"  - {duong_dan.name}")


if __name__ == "__main__":
    main()
