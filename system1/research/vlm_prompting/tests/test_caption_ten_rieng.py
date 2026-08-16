"""Test cho quality/caption_ten_rieng.py — dùng ca thật đo được trên checkpoint."""

from __future__ import annotations

from quality.caption_loader import CaptionRow
from quality.caption_ten_rieng import kiem_ten_rieng, kiem_ten_rieng_trong_cac_truong


def test_bat_danh_xung_thay_ten_ho_ten_dem_ten() -> None:
    text = "Một giáo viên tên Thầy Trần Ngọc Anh đang trình bày biểu đồ cơ cấu ngành công nghiệp."
    assert kiem_ten_rieng(text) is True


def test_bat_ten_nguoi_bon_tu_sau_danh_xung_giao_vien() -> None:
    text = "Giáo viên Nguyễn Việt Đăng Du đang giảng dạy sử dụng sơ đồ tư duy với vòng tròn."
    assert kiem_ten_rieng(text) is True


def test_bat_ten_truong_tieng_anh_nhieu_tu() -> None:
    text = "...biển tên đại học The Saigon International University trên một bức tường."
    assert kiem_ten_rieng(text) is True


def test_khong_bat_mo_ta_canh_khong_ten_rieng() -> None:
    text = "Một giáo viên nam mặc áo xanh đang giảng bài trước bảng trắng trong lớp học."
    assert kiem_ten_rieng(text) is False


def test_khong_bat_dia_danh_hai_tu_viet_nam() -> None:
    text = "Các quan chức ngồi quanh bàn với cờ Việt Nam và Đức trong phòng họp."
    assert kiem_ten_rieng(text) is False


def test_khong_bat_dia_danh_sai_gon() -> None:
    text = "Một tòa nhà cao tầng ở Sài Gòn với kiến trúc hiện đại và nhiều cửa kính."
    assert kiem_ten_rieng(text) is False


def test_khong_bat_cau_khong_co_cum_viet_hoa() -> None:
    text = "Nhiều học sinh nữ ngồi trên ghế xanh dương trong lớp học đại học."
    assert kiem_ten_rieng(text) is False


def test_khong_bat_doi_tuong_khong_co_ten_rieng() -> None:
    row = CaptionRow(
        ten_anh="x.jpg",
        caption="Một giáo viên đang giảng bài.",
        doi_tuong=["giáo viên nam", "laptop", "bảng trắng"],
        mau_sac=["trắng"],
    )
    assert kiem_ten_rieng_trong_cac_truong(row) is False


def test_bat_ten_rieng_lot_qua_truong_boi_canh() -> None:
    row = CaptionRow(
        ten_anh="y.jpg",
        caption="Một phòng máy tính hiện đại với nhiều màn hình.",
        doi_tuong=["máy tính", "bàn"],
        mau_sac=["xám"],
        boi_canh="phòng máy tính có tên gọi của Đại học Sài Gòn Quốc Tế xuất hiện trên tường",
    )
    assert kiem_ten_rieng_trong_cac_truong(row) is True
