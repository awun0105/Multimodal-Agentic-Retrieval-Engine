"""
Thuật toán lõi khử trùng lặp: pHash + histogram màu, so ẢNH LIỀN KỀ (O(n)).

⚠️ GIẢI PHÁP TẠM — không phải shot boundary detection thật. Chỉ so 2 ảnh
LIỀN KỀ nhau theo thứ tự tên file (không so tất-cả-với-tất-cả), vì:
  - O(n^2) với 300k ảnh keyframe AIC = 45 tỷ phép so → bất khả thi.
  - Keyframe cùng cảnh vốn nằm cạnh nhau về thời gian (cùng tiền tố tên file
    dạng video_frame_0001, 0002, ...) → so liền kề là đủ để bắt trùng lặp.
Khi code lõi (`system1/src/system1/shots/builder.py`) có shot boundary thật,
module này nên nhường chỗ.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image

# Kích thước pHash chuẩn 8x8 → 64 bit. Đủ để phân biệt cảnh khác nhau,
# đủ nhỏ để tính nhanh trên CPU (yêu cầu < 60s / 1000 ảnh).
KICH_THUOC_PHASH = 8
# Số bin mỗi kênh màu cho histogram — 16 bin/kênh là đủ thô để chịu được
# nén/đổi kích thước nhẹ, đủ mịn để bắt đổi tông màu cảnh.
SO_BIN_HISTOGRAM = 16

# Ngưỡng mặc định (đơn vị: khoảng cách Hamming trên 64 bit pHash).
# Chọn CHẶT (giữ thừa còn hơn bỏ nhầm — xem phase spec mục Rủi ro):
# 2 ảnh cùng cảnh, chỉ khác nén/độ sáng nhẹ thường lệch < 6 bit trong 64 bit.
# 10 là điểm an toàn: đủ khoan dung nén/sáng, nhưng không gộp 2 cảnh khác hẳn.
NGUONG_PHASH_MAC_DINH = 10
# Ngưỡng histogram: khoảng cách Bhattacharyya trong [0, 1], càng nhỏ càng giống.
# 0.15 là điểm chặt tương ứng — 2 ảnh cùng cảnh thường < 0.05.
NGUONG_HISTOGRAM_MAC_DINH = 0.15


def phash(duong_dan_anh: Path) -> int:
    """
    Tính perceptual hash (pHash) đơn giản bằng DCT xấp xỉ qua trung bình khối.

    Không dùng thư viện ngoài (imagehash) — tự cài để tránh phụ thuộc mới
    (ràng buộc: không đụng requirements.txt, Phase 01 sở hữu file đó).
    Thuật toán: resize ảnh về 8x8 grayscale, so từng pixel với trung bình
    toàn ảnh → bit 1 nếu sáng hơn trung bình. Đây là biến thể aHash (average
    hash) — rẻ hơn DCT thật nhưng đủ tốt để bắt ảnh gần giống hệt nhau.
    """
    with Image.open(duong_dan_anh) as img:
        anh_xam = img.convert("L").resize(
            (KICH_THUOC_PHASH, KICH_THUOC_PHASH), Image.Resampling.LANCZOS
        )
        mang = np.asarray(anh_xam, dtype=np.float64)

    trung_binh = mang.mean()
    bits = (mang > trung_binh).flatten()

    gia_tri = 0
    for bit in bits:
        gia_tri = (gia_tri << 1) | int(bit)
    return gia_tri


def khoang_cach_hamming(hash_a: int, hash_b: int) -> int:
    """Số bit khác nhau giữa 2 hash — dùng bin(a^b).count('1'), nhanh và đúng."""
    return bin(hash_a ^ hash_b).count("1")


def histogram_mau(duong_dan_anh: Path) -> np.ndarray:
    """
    Histogram màu RGB gộp 3 kênh, chuẩn hoá tổng = 1 (để so được ảnh khác kích
    thước). Bắt được đổi cảnh theo tông màu mà pHash (dựa trên độ sáng) có
    thể bỏ lỡ — ví dụ cảnh đổi từ ánh sáng vàng sang xanh nhưng độ sáng tổng
    thể tương đương.
    """
    with Image.open(duong_dan_anh) as img:
        anh_rgb = img.convert("RGB")
        mang = np.asarray(anh_rgb)

    kenh_hist = []
    for kenh in range(3):
        hist, _ = np.histogram(
            mang[:, :, kenh], bins=SO_BIN_HISTOGRAM, range=(0, 256)
        )
        kenh_hist.append(hist.astype(np.float64))

    gop = np.concatenate(kenh_hist)
    tong = gop.sum()
    if tong == 0:
        return gop
    return gop / tong


def khoang_cach_bhattacharyya(hist_a: np.ndarray, hist_b: np.ndarray) -> float:
    """
    Khoảng cách Bhattacharyya giữa 2 histogram đã chuẩn hoá — 0 nghĩa là giống
    hệt, 1 nghĩa là không chồng lấn. Dùng công thức chuẩn: -ln(sum(sqrt(p*q))).
    """
    he_so = np.sqrt(hist_a * hist_b).sum()
    he_so = np.clip(he_so, 1e-12, 1.0)  # tránh log(0)
    return float(-np.log(he_so))


@dataclass
class NhomAnh:
    """Một nhóm ảnh gần giống nhau + ảnh đại diện được chọn (ảnh đầu nhóm)."""

    dai_dien: str  # tên file ảnh đại diện
    thanh_vien: list[str] = field(default_factory=list)  # toàn bộ tên file trong nhóm


def gom_nhom_lien_ke(
    danh_sach_anh: list[Path],
    *,
    phuong_phap: str = "phash",
    nguong: float | None = None,
) -> list[NhomAnh]:
    """
    Gom các ảnh LIỀN KỀ (theo thứ tự đã sắp trong `danh_sach_anh`) vào nhóm
    nếu ảnh sau giống ảnh TRƯỚC NÓ TRONG NHÓM quá ngưỡng. Đây là thuật toán
    O(n): mỗi ảnh chỉ so đúng 1 lần với ảnh liền trước, không so tất cả.

    `phuong_phap`: "phash" (mặc định, rẻ hơn) hoặc "histogram" (bắt đổi tông
    màu tốt hơn). Ngưỡng là THAM SỐ — không chép cứng trong hàm.

    Ca biên: danh sách rỗng → trả về []. Danh sách 1 ảnh → 1 nhóm 1 thành viên.
    """
    if not danh_sach_anh:
        return []

    if phuong_phap not in ("phash", "histogram"):
        raise ValueError(f"phuong_phap không hợp lệ: {phuong_phap!r}")

    if nguong is None:
        nguong = (
            NGUONG_PHASH_MAC_DINH
            if phuong_phap == "phash"
            else NGUONG_HISTOGRAM_MAC_DINH
        )

    tinh_dac_trung = phash if phuong_phap == "phash" else histogram_mau
    do_khoang_cach = (
        khoang_cach_hamming if phuong_phap == "phash" else khoang_cach_bhattacharyya
    )

    nhom: list[NhomAnh] = []
    dac_trung_dai_dien = None

    for duong_dan in danh_sach_anh:
        dac_trung_hien_tai = tinh_dac_trung(duong_dan)

        if dac_trung_dai_dien is None or do_khoang_cach(dac_trung_dai_dien, dac_trung_hien_tai) > nguong:
            # Khác quá ngưỡng (hoặc là ảnh đầu tiên) → mở nhóm mới, ảnh này
            # thành đại diện tạm thời của nhóm mới.
            nhom.append(NhomAnh(dai_dien=duong_dan.name, thanh_vien=[duong_dan.name]))
            dac_trung_dai_dien = dac_trung_hien_tai
        else:
            # Giống ảnh đại diện hiện tại trong ngưỡng → nhập nhóm, KHÔNG đổi
            # đại diện (đại diện luôn là ảnh đầu nhóm, ổn định và dễ tái lập).
            nhom[-1].thanh_vien.append(duong_dan.name)

    return nhom
