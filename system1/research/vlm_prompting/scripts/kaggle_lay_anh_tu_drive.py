"""
Tải keyframe từ Google Drive vào Kaggle notebook.

Vì sao cần file này: Kaggle có tính năng "New Dataset -> Link -> Remote URL"
nhưng KHÔNG dùng được với Google Drive. Link Drive trả về một trang HTML cảnh
báo quét virus chứ không trả thẳng file, và trình tải của Kaggle không xử lý
được trang đó.

Thư viện `gdown` biết cách vượt trang cảnh báo — đây là cách duy nhất chạy ổn
định tính tới 8/2026.

ĐIỀU KIỆN: file trên Drive phải để chế độ "Bất kỳ ai có đường liên kết".
Nếu đang là "chỉ những người được chia sẻ", phải nhờ chủ sở hữu đổi lại, hoặc
tự sao chép file về Drive của mình rồi chia sẻ công khai.

Cách dùng trong Kaggle notebook (nhớ bật Internet ở Settings):

    !pip install -q gdown
    from kaggle_lay_anh_tu_drive import tai_va_giai_nen
    tai_va_giai_nen("1AbCdEfGhIjKlMnOpQrStUvWxYz", "/kaggle/working/data/frames")
"""

from __future__ import annotations

import re
import subprocess
import sys
import zipfile
from pathlib import Path

DUOI_ANH = (".jpg", ".jpeg", ".png", ".webp", ".bmp")


def lay_file_id(link_hoac_id: str) -> str:
    """
    Bóc FILE_ID ra khỏi link Google Drive.

    Nhận cả link đầy đủ lẫn ID trần, để bạn dán thẳng link từ trình duyệt
    mà không phải tự cắt.

    Các dạng link hỗ trợ:
        https://drive.google.com/file/d/FILE_ID/view?usp=sharing
        https://drive.google.com/open?id=FILE_ID
        https://drive.google.com/uc?id=FILE_ID
        FILE_ID
    """
    link = link_hoac_id.strip()

    mau = [
        r"/file/d/([a-zA-Z0-9_-]{20,})",
        r"[?&]id=([a-zA-Z0-9_-]{20,})",
        r"/folders/([a-zA-Z0-9_-]{20,})",
    ]
    for m in mau:
        khop = re.search(m, link)
        if khop:
            return khop.group(1)

    # Không khớp mẫu nào -> coi như người dùng đã đưa ID trần.
    if re.fullmatch(r"[a-zA-Z0-9_-]{20,}", link):
        return link

    raise ValueError(f"Không nhận ra FILE_ID trong: {link_hoac_id!r}")


def _dam_bao_co_gdown() -> None:
    try:
        import gdown  # noqa: F401
    except ImportError:
        print("Đang cài gdown...")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-q", "gdown"], check=True
        )


def tai_tu_drive(link_hoac_id: str, dich: Path | str) -> Path:
    """
    Tải một file từ Drive về. Trả về đường dẫn file đã tải.

    Bỏ qua nếu file đã có — chạy lại ô notebook nhiều lần không tải lại từ đầu.
    """
    _dam_bao_co_gdown()
    import gdown

    dich = Path(dich)
    dich.parent.mkdir(parents=True, exist_ok=True)

    if dich.exists() and dich.stat().st_size > 0:
        print(f"Đã có sẵn: {dich} ({dich.stat().st_size / 1e9:.2f} GB) — bỏ qua tải")
        return dich

    file_id = lay_file_id(link_hoac_id)
    print(f"Đang tải FILE_ID={file_id} ...")

    ket_qua = gdown.download(
        f"https://drive.google.com/uc?id={file_id}",
        str(dich),
        quiet=False,
    )

    if ket_qua is None or not dich.exists():
        raise RuntimeError(
            "Tải thất bại. Nguyên nhân thường gặp:\n"
            "  1. File chưa để chế độ 'Bất kỳ ai có đường liên kết'\n"
            "     -> nhờ chủ sở hữu đổi, hoặc tự sao chép về Drive của mình\n"
            "  2. Chưa bật Internet trong Kaggle (Settings -> Internet -> On)\n"
            "  3. Sai FILE_ID"
        )

    print(f"Xong: {dich} ({dich.stat().st_size / 1e9:.2f} GB)")
    return dich


def trich_anh_tu_zip(zip_path: Path | str, dich: Path | str, so_luong: int = 100) -> int:
    """
    Lấy `so_luong` ảnh từ file zip, rải đều thay vì lấy đoạn đầu.

    Rải đều vì 100 keyframe liên tiếp của cùng một video gần như giống hệt
    nhau — benchmark trên đó ra số vô nghĩa.

    Chỉ giải nén số ảnh cần, không giải nén cả kho: Kaggle giới hạn dung lượng
    đĩa, một file keyframe có thể chứa hàng chục nghìn ảnh.
    """
    zip_path = Path(zip_path)
    dich = Path(dich)
    dich.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_path) as zf:
        ten_anh = sorted(
            n for n in zf.namelist() if Path(n).suffix.lower() in DUOI_ANH
        )
        if not ten_anh:
            print(f"Không tìm thấy ảnh nào trong {zip_path}")
            return 0

        buoc = max(1, len(ten_anh) // so_luong)
        chon = ten_anh[::buoc][:so_luong]

        dem = 0
        for ten in chon:
            dich_file = dich / Path(ten).name
            if dich_file.exists():
                continue
            dich_file.write_bytes(zf.read(ten))
            dem += 1

    print(f"Đã trích {dem} ảnh mới (chọn {len(chon)}/{len(ten_anh)} ảnh trong kho)")
    return dem


def tai_va_giai_nen(
    link_hoac_id: str,
    thu_muc_anh: Path | str = "/kaggle/working/data/frames",
    *,
    so_luong: int = 100,
    zip_tam: Path | str = "/kaggle/working/keyframes.zip",
) -> int:
    """
    Làm cả hai bước: tải zip từ Drive rồi trích ảnh ra.

    Trả về số ảnh đã trích.
    """
    duong_dan_zip = tai_tu_drive(link_hoac_id, zip_tam)
    return trich_anh_tu_zip(duong_dan_zip, thu_muc_anh, so_luong)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Tải keyframe từ Google Drive")
    parser.add_argument("link", help="Link chia sẻ Google Drive hoặc FILE_ID")
    parser.add_argument("--out", default="/kaggle/working/data/frames")
    parser.add_argument("--n", type=int, default=100)
    args = parser.parse_args()

    tai_va_giai_nen(args.link, args.out, so_luong=args.n)
