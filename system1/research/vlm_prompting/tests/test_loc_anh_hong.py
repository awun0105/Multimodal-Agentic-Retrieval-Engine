"""Test bộ lọc ảnh trắng/hỏng — thuần Pillow, không phụ thuộc torch/agent."""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

GOC = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(GOC))

from scripts.loc_anh_hong import la_anh_hong, loc_danh_sach_anh  # noqa: E402


def test_anh_trang_tron_la_hong(tmp_path: Path) -> None:
    duong_dan = tmp_path / "trang.jpg"
    Image.new("RGB", (200, 100), color=(255, 255, 255)).save(duong_dan)
    assert la_anh_hong(duong_dan) is True


def test_anh_gradient_khong_hong(tmp_path: Path) -> None:
    duong_dan = tmp_path / "gradient.jpg"
    anh = Image.new("RGB", (200, 100))
    for x in range(200):
        for y in range(100):
            gia_tri = int(255 * x / 199)
            anh.putpixel((x, y), (gia_tri, gia_tri, gia_tri))
    anh.save(duong_dan)
    assert la_anh_hong(duong_dan) is False


def test_file_khong_ton_tai_la_hong(tmp_path: Path) -> None:
    assert la_anh_hong(tmp_path / "khong_co_that.jpg") is True


def test_file_khong_phai_anh_la_hong(tmp_path: Path) -> None:
    duong_dan = tmp_path / "khong_phai_anh.jpg"
    duong_dan.write_text("day khong phai la anh", encoding="utf-8")
    assert la_anh_hong(duong_dan) is True


def test_loc_danh_sach_anh_tach_dung_hai_nhom_giu_thu_tu(tmp_path: Path) -> None:
    duong_dan_trang = tmp_path / "a_trang.jpg"
    Image.new("RGB", (200, 100), color=(200, 200, 200)).save(duong_dan_trang)

    duong_dan_gradient = tmp_path / "b_gradient.jpg"
    anh = Image.new("RGB", (200, 100))
    for x in range(200):
        for y in range(100):
            gia_tri = int(255 * x / 199)
            anh.putpixel((x, y), (gia_tri, gia_tri, gia_tri))
    anh.save(duong_dan_gradient)

    duong_dan_trang_2 = tmp_path / "c_trang.jpg"
    Image.new("RGB", (200, 100), color=(50, 50, 50)).save(duong_dan_trang_2)

    danh_sach = [duong_dan_trang, duong_dan_gradient, duong_dan_trang_2]
    anh_tot, anh_hong = loc_danh_sach_anh(danh_sach)

    assert anh_tot == [duong_dan_gradient]
    assert anh_hong == [duong_dan_trang, duong_dan_trang_2]


def test_nguong_tham_so_hoa_anh_huong_ket_qua(tmp_path: Path) -> None:
    duong_dan = tmp_path / "bien_do_50.jpg"
    anh = Image.new("RGB", (200, 100))
    for x in range(200):
        for y in range(100):
            gia_tri = 100 + int(50 * x / 199)  # bien do khoang 50
            anh.putpixel((x, y), (gia_tri, gia_tri, gia_tri))
    anh.save(duong_dan)

    assert la_anh_hong(duong_dan, nguong_bien_do=30) is False
    assert la_anh_hong(duong_dan, nguong_bien_do=80) is True
