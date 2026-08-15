"""
Chạy thử generate_json() trên MỘT ảnh.

Đây là việc đầu tiên phải làm được trước khi nghĩ tới 100 ảnh. Một ảnh chạy
vài giây — prompt sai thì sửa rồi chạy lại ngay, không phải chờ cả mẻ.

Cách chạy:
    python scripts/smoke_one_image.py --image duong/dan/anh.jpg
    python scripts/smoke_one_image.py --image anh.jpg --model vintern-1b --debug
    python scripts/smoke_one_image.py --check          # chỉ xem máy có gì
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Console Windows mặc định dùng bảng mã cp1252 — in tiếng Việt sẽ crash.
if sys.platform.startswith("win"):
    for luong in (sys.stdout, sys.stderr):
        try:
            luong.reconfigure(encoding="utf-8")
        except (AttributeError, OSError):
            pass

# Cho phép chạy script trực tiếp mà không cần cài package.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from vlm.generate import (  # noqa: E402
    VlmKhongSanSang,
    generate_json,
    reset_vram_counter,
    thong_tin_moi_truong,
)
from vlm.json_utils import JsonParseError  # noqa: E402
from vlm.model_registry import MODEL_MAC_DINH, MODEL_REGISTRY, goi_y_theo_vram  # noqa: E402


def in_moi_truong() -> dict:
    thong_tin = thong_tin_moi_truong()
    print("=" * 60)
    print("MÔI TRƯỜNG")
    print("=" * 60)
    print(f"  Python      : {thong_tin['python']}")
    print(f"  PyTorch     : {thong_tin.get('torch_version', 'CHƯA CÀI')}")
    print(f"  GPU         : {thong_tin['ten_gpu'] or 'không có'}")
    print(f"  VRAM        : {thong_tin['vram_gb'] or '—'} GB")

    if thong_tin["vram_gb"]:
        goi_y = goi_y_theo_vram(thong_tin["vram_gb"])
        print(f"  Model chạy được: {', '.join(goi_y) if goi_y else 'KHÔNG CÓ (VRAM quá thấp)'}")
    elif not thong_tin["co_torch"]:
        print("  → Chưa cài PyTorch. Chạy: pip install -r requirements.txt")
    else:
        print("  → Không có GPU. Model sẽ chạy trên CPU (rất chậm, chỉ nên thử 1 ảnh).")
    print()
    return thong_tin


def main() -> int:
    parser = argparse.ArgumentParser(description="Chạy thử VLM trên một ảnh")
    parser.add_argument("--image", type=Path, help="Đường dẫn ảnh cần mô tả")
    parser.add_argument(
        "--model",
        default=MODEL_MAC_DINH,
        choices=sorted(MODEL_REGISTRY),
        help=f"Model dùng để chạy (mặc định: {MODEL_MAC_DINH})",
    )
    parser.add_argument("--debug", action="store_true", help="In prompt và output thô của model")
    parser.add_argument("--no-4bit", action="store_true", help="Tắt lượng tử hóa 4-bit")
    parser.add_argument("--check", action="store_true", help="Chỉ kiểm tra môi trường rồi thoát")
    parser.add_argument("--out", type=Path, help="Lưu kết quả JSON ra file")
    args = parser.parse_args()

    in_moi_truong()

    if args.check:
        return 0

    if not args.image:
        parser.error("thiếu --image (hoặc dùng --check để chỉ xem môi trường)")

    if not args.image.exists():
        print(f"LỖI: không tìm thấy ảnh {args.image}")
        return 1

    print(f"Ảnh   : {args.image}")
    print(f"Model : {MODEL_REGISTRY[args.model].ten_hien_thi}")
    print("Đang nạp model (lần đầu có thể mất vài phút để tải)...\n")

    reset_vram_counter()

    try:
        ket_qua = generate_json(
            args.image,
            model_key=args.model,
            dung_4bit=not args.no_4bit,
            debug=args.debug,
        )
    except VlmKhongSanSang as loi:
        print(f"LỖI: không nạp được model.\n  {loi}")
        print("\nGợi ý: chạy trên Kaggle (GPU 16GB miễn phí) thay vì máy cá nhân.")
        return 2
    except JsonParseError as loi:
        print(f"LỖI: model không trả về JSON hợp lệ.\n  {loi}")
        print(f"\nOutput thô của model:\n{loi.raw_text[:800]}")
        print("\nGợi ý: chạy lại với --debug, hoặc siết thêm prompt trong vlm/prompts.py")
        return 3

    print("=" * 60)
    print("KẾT QUẢ")
    print("=" * 60)
    print(json.dumps(ket_qua, ensure_ascii=False, indent=2))
    print()
    print(f"  Thời gian : {ket_qua['_latency_sec']} giây")
    print(f"  VRAM đỉnh : {ket_qua.get('_vram_peak_gb') or '—'} GB")

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(ket_qua, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  Đã lưu    : {args.out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
