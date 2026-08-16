"""
CLI: nhận thư mục keyframe → chọn ảnh đại diện, xuất `results/dedup_map.json`.

⚠️ GIẢI PHÁP TẠM cho khử trùng lặp — KHÔNG phải shot boundary detection thật.
Xem docstring `dedup/perceptual_dedup.py` và `dedup/README.md`.

Cách chạy:
    python -m dedup.chon_anh_dai_dien --frames-dir data/frames --out results/dedup_map.json
    python -m dedup.chon_anh_dai_dien --frames-dir data/frames --nguong 15 --phuong-phap histogram
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

if sys.platform.startswith("win"):
    for _luong in (sys.stdout, sys.stderr):
        try:
            _luong.reconfigure(encoding="utf-8")
        except (AttributeError, OSError):
            pass

GOC = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(GOC))
# benchmark_runner.py tự import "checkpoint_utils" (không phải "scripts.checkpoint_utils"),
# giả định scripts/ đã nằm trong sys.path — phải thêm thủ công khi import module này
# từ ngoài (thay vì chạy trực tiếp `python scripts/benchmark_runner.py`).
sys.path.insert(0, str(GOC / "scripts"))

from scripts.benchmark_runner import liet_ke_anh  # noqa: E402 — REUSE-AS-IS, đã có sẵn

from dedup.perceptual_dedup import NhomAnh, gom_nhom_lien_ke  # noqa: E402


def xuat_dedup_map(nhom_list: list[NhomAnh], duong_dan_out: Path) -> None:
    """
    Ghi `dedup_map.json`. Cấu trúc cho phép suy ngược 2 chiều:
    - `nhom`: mỗi nhóm gồm đại diện + toàn bộ thành viên (đại diện -> cả nhóm).
    - `anh_toi_nhom`: map ngược tên_ảnh -> chỉ số nhóm (ảnh bất kỳ -> nhóm chứa nó).
    Có cả 2 chiều thì tra cứu đằng nào cũng O(1), không phải quét toàn bộ.
    """
    anh_toi_nhom: dict[str, int] = {}
    for idx, nhom in enumerate(nhom_list):
        for ten_anh in nhom.thanh_vien:
            anh_toi_nhom[ten_anh] = idx

    du_lieu = {
        "so_nhom": len(nhom_list),
        "tong_anh": sum(len(n.thanh_vien) for n in nhom_list),
        "nhom": [
            {"dai_dien": n.dai_dien, "thanh_vien": n.thanh_vien} for n in nhom_list
        ],
        "anh_toi_nhom": anh_toi_nhom,
    }

    duong_dan_out.parent.mkdir(parents=True, exist_ok=True)
    duong_dan_out.write_text(
        json.dumps(du_lieu, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def chay(
    thu_muc_anh: Path,
    duong_dan_out: Path,
    *,
    phuong_phap: str = "phash",
    nguong: float | None = None,
) -> list[NhomAnh]:
    """Chạy toàn bộ pipeline, in tiến độ + tỉ lệ giảm, trả về danh sách nhóm."""
    danh_sach_anh = liet_ke_anh(thu_muc_anh)
    tong_anh = len(danh_sach_anh)
    if tong_anh == 0:
        print(f"Không tìm thấy ảnh nào trong {thu_muc_anh}")
        return []

    bat_dau = time.perf_counter()
    nhom_list = gom_nhom_lien_ke(danh_sach_anh, phuong_phap=phuong_phap, nguong=nguong)
    thoi_gian = time.perf_counter() - bat_dau

    xuat_dedup_map(nhom_list, duong_dan_out)

    so_nhom = len(nhom_list)
    ti_le_giam = tong_anh / so_nhom if so_nhom else 0.0
    print(f"Tổng ảnh vào: {tong_anh}")
    print(f"Số nhóm (= số ảnh đại diện): {so_nhom}")
    print(f"Tỉ lệ giảm: {ti_le_giam:.2f}x")
    print(f"Thời gian xử lý: {thoi_gian:.2f}s")
    print(f"Đã ghi: {duong_dan_out}")
    return nhom_list


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frames-dir", type=Path, required=True, help="Thư mục chứa keyframe")
    parser.add_argument(
        "--out", type=Path, default=Path("results/dedup_map.json"), help="Đường dẫn file JSON kết quả"
    )
    parser.add_argument(
        "--phuong-phap", choices=["phash", "histogram"], default="phash", help="Cách so ảnh"
    )
    parser.add_argument(
        "--nguong", type=float, default=None, help="Ngưỡng giống nhau (mặc định theo phương pháp)"
    )
    args = parser.parse_args()

    chay(args.frames_dir, args.out, phuong_phap=args.phuong_phap, nguong=args.nguong)


if __name__ == "__main__":
    main()
