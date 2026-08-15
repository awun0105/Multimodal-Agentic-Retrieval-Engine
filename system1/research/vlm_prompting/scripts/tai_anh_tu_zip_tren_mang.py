"""
Lấy N ảnh từ file zip lớn trên Google Drive mà KHÔNG tải cả file về.

Vì sao cần: file keyframe của cuộc thi nặng 5.7GB. Tải hết mất 10-20 phút và
gần cạn dung lượng đĩa Kaggle (~20GB), trong khi benchmark chỉ cần 100 ảnh.

Cách làm: định dạng zip đặt bảng mục lục ở CUỐI file. Dùng HTTP Range request
để đọc riêng phần mục lục, biết mỗi ảnh nằm ở byte nào, rồi chỉ tải đúng
những đoạn byte đó. Tải ~10MB thay vì 5.7GB.

Cách dùng:
    from tai_anh_tu_zip_tren_mang import tai_anh_tu_drive_zip
    tai_anh_tu_drive_zip("FILE_ID", "/kaggle/working/data/frames", so_luong=100)
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import Any

DUOI_ANH = (".jpg", ".jpeg", ".png", ".webp", ".bmp")


class _FileTrenMang(io.RawIOBase):
    """
    Giả lập một file cục bộ, nhưng thực chất đọc từng đoạn qua mạng.

    zipfile cần đối tượng biết seek() và read(). Lớp này đáp ứng bằng cách dịch
    mỗi lần đọc thành một HTTP Range request — chỉ tải đúng đoạn byte cần.
    """

    def __init__(self, session: Any, url: str):
        self.session = session
        self.url = url
        self.vi_tri = 0

        r = session.head(url, allow_redirects=True, timeout=60)
        if "content-length" not in r.headers:
            r = session.get(url, stream=True, allow_redirects=True, timeout=60)
            r.close()
        self.kich_thuoc = int(r.headers["content-length"])

        if r.headers.get("accept-ranges", "").lower() != "bytes":
            raise RuntimeError(
                "Máy chủ không hỗ trợ tải theo đoạn (Range). Phải tải cả file."
            )

    def seekable(self) -> bool:
        return True

    def readable(self) -> bool:
        return True

    def seek(self, offset: int, whence: int = 0) -> int:
        if whence == 0:
            self.vi_tri = offset
        elif whence == 1:
            self.vi_tri += offset
        else:
            self.vi_tri = self.kich_thuoc + offset
        return self.vi_tri

    def tell(self) -> int:
        return self.vi_tri

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            size = self.kich_thuoc - self.vi_tri
        if size <= 0 or self.vi_tri >= self.kich_thuoc:
            return b""

        cuoi = min(self.vi_tri + size, self.kich_thuoc) - 1
        r = self.session.get(
            self.url,
            headers={"Range": f"bytes={self.vi_tri}-{cuoi}"},
            timeout=120,
        )
        r.raise_for_status()
        du_lieu = r.content
        self.vi_tri += len(du_lieu)
        return du_lieu


def _tao_session_drive(file_id: str):
    """
    Tạo phiên đã vượt qua trang cảnh báo quét virus của Google.

    File trên 100MB bị Google chặn bằng một trang xác nhận. Phải lấy token
    trong trang đó rồi gửi kèm ở lần gọi sau.
    """
    import requests

    session = requests.Session()
    url = f"https://drive.google.com/uc?export=download&id={file_id}"

    r = session.get(url, stream=True, allow_redirects=True, timeout=60)

    # File nhỏ: trả thẳng nội dung, không qua trang cảnh báo.
    if "text/html" not in r.headers.get("content-type", ""):
        r.close()
        return session, r.url

    noi_dung = r.text
    r.close()

    token = None
    for ten, gia_tri in session.cookies.items():
        if ten.startswith("download_warning"):
            token = gia_tri
            break

    if token:
        return session, f"{url}&confirm={token}"

    # Bản mới của Google dùng form POST tới drive.usercontent.google.com.
    import re

    uuid = re.search(r'name="uuid" value="([^"]+)"', noi_dung)
    if uuid:
        return (
            session,
            "https://drive.usercontent.google.com/download"
            f"?id={file_id}&export=download&confirm=t&uuid={uuid.group(1)}",
        )

    return session, f"{url}&confirm=t"


def tai_anh_tu_drive_zip(
    file_id: str,
    thu_muc_dich: Path | str,
    *,
    so_luong: int = 100,
) -> int:
    """
    Trích `so_luong` ảnh từ file zip trên Drive, chỉ tải phần cần thiết.

    Rải đều thay vì lấy đoạn đầu — 100 keyframe liên tiếp của cùng một video
    gần như giống hệt nhau, benchmark trên đó ra số vô nghĩa.

    Trả về số ảnh đã lưu.
    """
    thu_muc_dich = Path(thu_muc_dich)
    thu_muc_dich.mkdir(parents=True, exist_ok=True)

    session, url = _tao_session_drive(file_id)
    nguon = _FileTrenMang(session, url)
    print(f"Kích thước file trên Drive: {nguon.kich_thuoc / 1e9:.2f} GB")
    print("Đang đọc mục lục zip (chỉ tải phần cuối file)...")

    dem = 0
    with zipfile.ZipFile(nguon) as zf:
        ten_anh = sorted(
            n for n in zf.namelist() if Path(n).suffix.lower() in DUOI_ANH
        )
        if not ten_anh:
            print("Không tìm thấy ảnh nào trong file zip")
            return 0

        buoc = max(1, len(ten_anh) // so_luong)
        chon = ten_anh[::buoc][:so_luong]
        print(f"Kho có {len(ten_anh)} ảnh -> lấy {len(chon)} ảnh rải đều")

        for i, ten in enumerate(chon, 1):
            dich = thu_muc_dich / Path(ten).name
            if dich.exists():
                continue
            dich.write_bytes(zf.read(ten))
            dem += 1
            if dem % 20 == 0:
                print(f"  ... đã lấy {dem}/{len(chon)} ảnh")

    print(f"Xong: {dem} ảnh mới trong {thu_muc_dich}")
    return dem


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Lấy ảnh từ zip lớn trên Drive")
    parser.add_argument("file_id", help="FILE_ID trên Google Drive")
    parser.add_argument("--out", default="/kaggle/working/data/frames")
    parser.add_argument("--n", type=int, default=100)
    args = parser.parse_args()

    tai_anh_tu_drive_zip(args.file_id, args.out, so_luong=args.n)
