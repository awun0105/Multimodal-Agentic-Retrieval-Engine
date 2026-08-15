"""
Chuẩn bị bộ ảnh mẫu để benchmark.

Đề bài yêu cầu chạy thử trên ít nhất 100 ảnh. Script này lấy ảnh từ 3 nguồn,
theo thứ tự ưu tiên:

  1. Thư mục keyframe của bạn (--frames-dir) — TỐT NHẤT, vì là ảnh thật của
     cuộc thi, số đo mới sát thực tế
  2. File .blob / .zip chứa ảnh nén (--blob) — đọc thẳng không giải nén, tiết
     kiệm dung lượng đĩa (mẹo từ notebook của bạn Nhật)
  3. Tải ảnh công khai COCO val2017 — luôn chạy được, dùng khi chưa có ảnh thật

Cách chạy:
    python scripts/prepare_sample_images.py                    # tải 100 ảnh COCO
    python scripts/prepare_sample_images.py --n 200
    python scripts/prepare_sample_images.py --frames-dir /duong/dan/keyframes
    python scripts/prepare_sample_images.py --blob data/cached_keyframes.blob
"""

from __future__ import annotations

import argparse
import shutil
import sys
import zipfile
from pathlib import Path

if sys.platform.startswith("win"):
    for _luong in (sys.stdout, sys.stderr):
        try:
            _luong.reconfigure(encoding="utf-8")
        except (AttributeError, OSError):
            pass

DUOI_ANH = (".jpg", ".jpeg", ".png", ".webp", ".bmp")

# COCO val2017 — ảnh đời thường, đa dạng cảnh, dùng làm bộ thử tạm khi chưa có
# keyframe thật. Tên file theo dạng 12 chữ số.
COCO_BASE_URL = "http://images.cocodataset.org/val2017/"
COCO_IDS = [
    39769, 87038, 174482, 296649, 328757, 397133, 37777, 252219, 87470, 133418,
    120420, 189828, 285, 61471, 458054, 296231, 386912, 502136, 491497, 184791,
    348881, 289393, 522713, 181666, 17627, 143931, 303818, 463730, 460347, 322864,
    226111, 153299, 308394, 456496, 58636, 41888, 184321, 565778, 297343, 336587,
    122745, 219578, 555705, 443303, 500663, 418281, 25560, 403817, 85329, 329323,
    239274, 286994, 511321, 314294, 233771, 475779, 301867, 312421, 185250, 356427,
    572517, 270244, 516316, 125211, 562121, 360661, 16228, 382088, 266409, 430961,
    80671, 577539, 104612, 476258, 448365, 35197, 349860, 180135, 331352, 502136,
    91500, 196759, 137246, 481404, 44279, 96493, 176606, 22935, 191724, 251577,
    492937, 79969, 578545, 95022, 90108, 32901, 196141, 41888, 156976, 213255,
    277005, 532493, 91619, 224222, 236412, 34873, 130599, 581357, 41924, 4795,
]


def anh_trong_thu_muc(thu_muc: Path) -> list[Path]:
    """Liệt kê ảnh trong thư mục, đã sắp xếp để kết quả chạy lại giống nhau."""
    if not thu_muc.exists():
        return []
    return sorted(p for p in thu_muc.rglob("*") if p.suffix.lower() in DUOI_ANH)


def chep_tu_thu_muc(nguon: Path, dich: Path, so_luong: int) -> int:
    """Chép ảnh từ thư mục keyframe của bạn sang thư mục làm việc."""
    danh_sach = anh_trong_thu_muc(nguon)
    if not danh_sach:
        print(f"Không tìm thấy ảnh nào trong {nguon}")
        return 0

    # Rải đều thay vì lấy 100 ảnh đầu — 100 frame liên tiếp của cùng một video
    # thì gần như giống hệt nhau, benchmark ra số vô nghĩa.
    buoc = max(1, len(danh_sach) // so_luong)
    chon = danh_sach[::buoc][:so_luong]

    dich.mkdir(parents=True, exist_ok=True)
    dem = 0
    for duong_dan in chon:
        dich_file = dich / duong_dan.name
        if dich_file.exists():
            continue
        shutil.copy2(duong_dan, dich_file)
        dem += 1

    print(f"Đã chép {dem} ảnh mới (chọn {len(chon)}/{len(danh_sach)} ảnh có sẵn)")
    return dem


def trich_tu_blob(blob_path: Path, dich: Path, so_luong: int) -> int:
    """
    Lấy ảnh từ file nén mà KHÔNG giải nén cả kho.

    Kaggle giới hạn dung lượng đĩa. Giải nén hàng chục nghìn ảnh ra là hết chỗ.
    Đọc thẳng từng ảnh trong file zip thì không tốn đĩa.
    """
    if not blob_path.exists():
        print(f"Không tìm thấy file: {blob_path}")
        return 0

    try:
        zf = zipfile.ZipFile(blob_path)
    except zipfile.BadZipFile:
        print(f"{blob_path} không phải file zip hợp lệ")
        return 0

    with zf:
        ten_anh = sorted(
            n for n in zf.namelist() if Path(n).suffix.lower() in DUOI_ANH
        )
        if not ten_anh:
            print("File nén không chứa ảnh nào")
            return 0

        buoc = max(1, len(ten_anh) // so_luong)
        chon = ten_anh[::buoc][:so_luong]

        dich.mkdir(parents=True, exist_ok=True)
        dem = 0
        for ten in chon:
            dich_file = dich / Path(ten).name
            if dich_file.exists():
                continue
            dich_file.write_bytes(zf.read(ten))
            dem += 1

    print(f"Đã trích {dem} ảnh mới (chọn {len(chon)}/{len(ten_anh)} ảnh trong kho)")
    return dem


def tai_anh_coco(dich: Path, so_luong: int) -> int:
    """
    Tải ảnh mẫu công khai. Bỏ qua ảnh đã có nên chạy lại nhiều lần vẫn ổn.

    Danh sách ID cứng trong file này chỉ có hơn 100 mục và vài ID đã chết. Nên
    thử lấy danh sách ID thật từ trang liệt kê của COCO trước; hỏng thì mới
    quay về danh sách cứng.
    """
    import urllib.error
    import urllib.request

    dich.mkdir(parents=True, exist_ok=True)
    danh_sach_id = _lay_id_coco(so_luong)

    dem = 0
    that_bai = 0
    for image_id in danh_sach_id:
        if dem >= so_luong:
            break
        ten_file = f"{image_id:012d}.jpg"
        dich_file = dich / ten_file
        if dich_file.exists():
            continue

        try:
            urllib.request.urlretrieve(COCO_BASE_URL + ten_file, dich_file)
            dem += 1
            if dem % 20 == 0:
                print(f"  ... đã tải {dem} ảnh")
        except (urllib.error.URLError, OSError) as loi:
            that_bai += 1
            if that_bai <= 3:
                print(f"  Bỏ qua {ten_file}: {loi}")
            if that_bai > 30:
                print("  Quá nhiều lỗi mạng, dừng tải.")
                break

    print(f"Đã tải {dem} ảnh mới, {that_bai} lỗi")
    return dem


def _lay_id_coco(so_luong: int) -> list[int]:
    """
    Sinh danh sách ID ảnh COCO val2017.

    val2017 có 5000 ảnh, ID nằm rải rác trong khoảng 0-581929. Không có API
    liệt kê công khai nên ghép: ID đã biết chắc dùng được (đặt trước, tải là
    chắc chắn có), rồi thêm ID rải đều làm dự phòng khi cần nhiều ảnh hơn.
    Ảnh nào không tồn tại sẽ bị bỏ qua ở vòng tải.
    """
    danh_sach = list(dict.fromkeys(COCO_IDS))  # bỏ trùng, giữ thứ tự
    if so_luong <= len(danh_sach):
        return danh_sach

    # Cần nhiều hơn số ID đã biết -> rải thêm ứng viên, chấp nhận tỷ lệ trượt.
    can_them = (so_luong - len(danh_sach)) * 8
    buoc = max(1, 581929 // max(1, can_them))
    da_co = set(danh_sach)
    for ung_vien in range(1, 581929, buoc):
        if ung_vien not in da_co:
            danh_sach.append(ung_vien)
    return danh_sach


def main() -> int:
    parser = argparse.ArgumentParser(description="Chuẩn bị bộ ảnh mẫu để benchmark")
    parser.add_argument("--n", type=int, default=100, help="Số ảnh cần (mặc định 100)")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "data" / "frames",
        help="Thư mục đích",
    )
    parser.add_argument("--frames-dir", type=Path, help="Thư mục keyframe có sẵn của bạn")
    parser.add_argument("--blob", type=Path, help="File .blob/.zip chứa ảnh nén")
    args = parser.parse_args()

    print(f"Thư mục đích: {args.out}")
    print(f"Số ảnh cần  : {args.n}\n")

    if args.frames_dir:
        chep_tu_thu_muc(args.frames_dir, args.out, args.n)
    elif args.blob:
        trich_tu_blob(args.blob, args.out, args.n)
    else:
        print("Không có nguồn ảnh riêng -> tải ảnh mẫu COCO công khai.")
        print("(Có keyframe thật thì dùng --frames-dir để kết quả sát thực tế hơn)\n")
        tai_anh_coco(args.out, args.n)

    tong = len(anh_trong_thu_muc(args.out))
    print(f"\nTổng số ảnh hiện có: {tong}")
    if tong < args.n:
        print(f"CẢNH BÁO: mới có {tong}/{args.n} ảnh. Đề bài yêu cầu tối thiểu 100.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
