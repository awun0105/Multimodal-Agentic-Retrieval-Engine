"""
Tự kiểm module khử trùng lặp bằng ảnh giả lập — chứng minh thuật toán đúng
khi chưa có keyframe AIC thật trên máy local (local chỉ có 37 ảnh COCO,
xem `data/README.md`, không đại diện cho keyframe video thật).

Không import torch/transformers — dedup/ phải chạy CPU thuần, Python 3.14.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

GOC = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(GOC))

from dedup.chon_anh_dai_dien import chay, xuat_dedup_map  # noqa: E402
from dedup.perceptual_dedup import gom_nhom_lien_ke  # noqa: E402


def _ve_anh_gradient(
    mau_goc: tuple[int, int, int], do_bien_thien: int = 0, *, doc: bool = True
) -> Image.Image:
    """Sinh ảnh 64x64 gradient từ 1 màu gốc — mô phỏng 1 'cảnh'. `do_bien_thien`
    thêm nhiễu nhẹ để mô phỏng đổi độ sáng/nén giữa các keyframe cùng cảnh.
    `doc=True` (mặc định): gradient theo hàng (dọc). `doc=False`: gradient
    theo cột (ngang) — dùng để tạo ảnh có CẤU TRÚC KHÔNG GIAN khác hẳn, vì
    aHash chỉ nhìn độ sáng theo pattern không gian (grayscale), đổi màu
    thuần không đủ để phân biệt nếu cấu trúc gradient giống hệt nhau."""
    mang = np.zeros((64, 64, 3), dtype=np.uint8)
    for i in range(64):
        for kenh in range(3):
            gia_tri = mau_goc[kenh] + (i - 32) // 4 + do_bien_thien
            gia_tri = np.clip(gia_tri, 0, 255)
            if doc:
                mang[i, :, kenh] = gia_tri
            else:
                mang[:, i, kenh] = gia_tri
    return Image.fromarray(mang, mode="RGB")


def _luu_anh(thu_muc: Path, ten_file: str, anh: Image.Image) -> Path:
    duong_dan = thu_muc / ten_file
    anh.save(duong_dan, format="JPEG", quality=90)
    return duong_dan


def test_anh_giong_het_gom_1_nhom(tmp_path: Path) -> None:
    """3 ảnh cùng gốc màu, chỉ lệch nhiễu nhẹ (mô phỏng đổi sáng/nén) → phải
    gom thành 1 nhóm, cùng 1 ảnh đại diện."""
    thu_muc = tmp_path / "frames"
    thu_muc.mkdir()
    _luu_anh(thu_muc, "001.jpg", _ve_anh_gradient((200, 50, 50), do_bien_thien=0))
    _luu_anh(thu_muc, "002.jpg", _ve_anh_gradient((200, 50, 50), do_bien_thien=3))
    _luu_anh(thu_muc, "003.jpg", _ve_anh_gradient((200, 50, 50), do_bien_thien=-3))

    danh_sach = sorted(thu_muc.glob("*.jpg"))
    nhom = gom_nhom_lien_ke(danh_sach, phuong_phap="phash")

    assert len(nhom) == 1
    assert set(nhom[0].thanh_vien) == {"001.jpg", "002.jpg", "003.jpg"}


def test_2_canh_khac_han_gom_2_nhom_chon_2_dai_dien(tmp_path: Path) -> None:
    """3 ảnh gần giống nhau (cảnh A) + 2 ảnh khác hẳn (cảnh B) → phải ra đúng
    2 nhóm, chọn đúng 2 đại diện — đây là ca kiểm chính theo yêu cầu phase."""
    thu_muc = tmp_path / "frames"
    thu_muc.mkdir()
    # Cảnh A: đỏ, 3 ảnh gần giống (đổi sáng nhẹ)
    _luu_anh(thu_muc, "a01.jpg", _ve_anh_gradient((220, 40, 40), do_bien_thien=0))
    _luu_anh(thu_muc, "a02.jpg", _ve_anh_gradient((220, 40, 40), do_bien_thien=4))
    _luu_anh(thu_muc, "a03.jpg", _ve_anh_gradient((220, 40, 40), do_bien_thien=-4))
    # Cảnh B: xanh dương, gradient NGANG (cấu trúc không gian khác hẳn cảnh A)
    _luu_anh(thu_muc, "b01.jpg", _ve_anh_gradient((30, 40, 220), do_bien_thien=0, doc=False))
    _luu_anh(thu_muc, "b02.jpg", _ve_anh_gradient((30, 40, 220), do_bien_thien=3, doc=False))

    danh_sach = sorted(thu_muc.glob("*.jpg"))
    nhom = gom_nhom_lien_ke(danh_sach, phuong_phap="phash")

    assert len(nhom) == 2
    assert nhom[0].thanh_vien == ["a01.jpg", "a02.jpg", "a03.jpg"]
    assert nhom[1].thanh_vien == ["b01.jpg", "b02.jpg"]
    assert nhom[0].dai_dien == "a01.jpg"
    assert nhom[1].dai_dien == "b01.jpg"


def test_ca_bien_1_anh_khong_sap(tmp_path: Path) -> None:
    """1 ảnh duy nhất → 1 nhóm, không sập, không lỗi chỉ số."""
    thu_muc = tmp_path / "frames"
    thu_muc.mkdir()
    _luu_anh(thu_muc, "chi_mot.jpg", _ve_anh_gradient((100, 100, 100)))

    danh_sach = sorted(thu_muc.glob("*.jpg"))
    nhom = gom_nhom_lien_ke(danh_sach, phuong_phap="phash")

    assert len(nhom) == 1
    assert nhom[0].thanh_vien == ["chi_mot.jpg"]
    assert nhom[0].dai_dien == "chi_mot.jpg"


def test_danh_sach_rong_khong_loi() -> None:
    """Ca biên: không có ảnh nào → trả về [] chứ không lỗi."""
    assert gom_nhom_lien_ke([], phuong_phap="phash") == []


def test_nguong_thap_moi_anh_thanh_1_nhom_rieng(tmp_path: Path) -> None:
    """Hạ ngưỡng xuống 0 (khắt khe tuyệt đối) → dù ảnh gần giống cũng không
    đạt ngưỡng → mỗi ảnh 1 nhóm riêng (trừ khi 2 ảnh hash giống hệt bit)."""
    thu_muc = tmp_path / "frames"
    thu_muc.mkdir()
    _luu_anh(thu_muc, "001.jpg", _ve_anh_gradient((200, 50, 50), do_bien_thien=0))
    _luu_anh(thu_muc, "002.jpg", _ve_anh_gradient((200, 50, 50), do_bien_thien=5))
    _luu_anh(thu_muc, "003.jpg", _ve_anh_gradient((200, 50, 50), do_bien_thien=-5))

    danh_sach = sorted(thu_muc.glob("*.jpg"))
    # Ngưỡng âm → do_khoang_cach > nguong luôn đúng (khoảng cách >= 0) → tách hết.
    nhom = gom_nhom_lien_ke(danh_sach, phuong_phap="phash", nguong=-1)

    assert len(nhom) == 3


def test_nguong_cao_gom_het_lam_1(tmp_path: Path) -> None:
    """Nâng ngưỡng lên rất cao (64 = tối đa bit khác nhau có thể) → mọi ảnh,
    dù khác cảnh hẳn, cũng gom vào 1 nhóm duy nhất."""
    thu_muc = tmp_path / "frames"
    thu_muc.mkdir()
    _luu_anh(thu_muc, "a.jpg", _ve_anh_gradient((220, 40, 40)))
    _luu_anh(thu_muc, "b.jpg", _ve_anh_gradient((30, 40, 220)))
    _luu_anh(thu_muc, "c.jpg", _ve_anh_gradient((40, 220, 40)))

    danh_sach = sorted(thu_muc.glob("*.jpg"))
    nhom = gom_nhom_lien_ke(danh_sach, phuong_phap="phash", nguong=64)

    assert len(nhom) == 1
    assert len(nhom[0].thanh_vien) == 3


def test_phuong_phap_khong_hop_le_bao_loi(tmp_path: Path) -> None:
    thu_muc = tmp_path / "frames"
    thu_muc.mkdir()
    _luu_anh(thu_muc, "a.jpg", _ve_anh_gradient((100, 100, 100)))
    danh_sach = sorted(thu_muc.glob("*.jpg"))

    try:
        gom_nhom_lien_ke(danh_sach, phuong_phap="khong_ton_tai")
        assert False, "phải raise ValueError"
    except ValueError:
        pass


def test_dedup_map_json_suy_nguoc_khep_kin(tmp_path: Path) -> None:
    """dedup_map.json phải khép kín: mọi ảnh vào nằm trong đúng 1 nhóm (không
    mất, không trùng), và tra ngược ảnh -> nhóm -> đại diện phải đúng."""
    thu_muc = tmp_path / "frames"
    thu_muc.mkdir()
    _luu_anh(thu_muc, "a01.jpg", _ve_anh_gradient((220, 40, 40), do_bien_thien=0))
    _luu_anh(thu_muc, "a02.jpg", _ve_anh_gradient((220, 40, 40), do_bien_thien=4))
    _luu_anh(thu_muc, "b01.jpg", _ve_anh_gradient((30, 40, 220), do_bien_thien=0))

    danh_sach = sorted(thu_muc.glob("*.jpg"))
    nhom = gom_nhom_lien_ke(danh_sach, phuong_phap="phash")

    duong_dan_out = tmp_path / "dedup_map.json"
    xuat_dedup_map(nhom, duong_dan_out)

    du_lieu = json.loads(duong_dan_out.read_text(encoding="utf-8"))

    # Khép kín: tổng ảnh trong mọi nhóm = tổng ảnh đầu vào.
    tong_trong_nhom = sum(len(n["thanh_vien"]) for n in du_lieu["nhom"])
    assert tong_trong_nhom == len(danh_sach)
    assert du_lieu["tong_anh"] == len(danh_sach)

    # Không trùng: mỗi tên ảnh chỉ xuất hiện trong đúng 1 nhóm.
    tat_ca_ten = [ten for n in du_lieu["nhom"] for ten in n["thanh_vien"]]
    assert len(tat_ca_ten) == len(set(tat_ca_ten))

    # Suy ngược: từ ảnh bất kỳ -> map ngược ra đúng chỉ số nhóm chứa nó.
    for idx, n in enumerate(du_lieu["nhom"]):
        for ten_anh in n["thanh_vien"]:
            assert du_lieu["anh_toi_nhom"][ten_anh] == idx
            # đại diện của nhóm đó phải nằm trong chính nhóm đó
            assert n["dai_dien"] in n["thanh_vien"]


def test_hieu_nang_1000_anh_duoi_60_giay(tmp_path: Path) -> None:
    """Yêu cầu phi chức năng: xử lý 1.000 ảnh nhỏ trên CPU < 60 giây."""
    thu_muc = tmp_path / "frames"
    thu_muc.mkdir()

    mau_lap = [(220, 40, 40), (30, 40, 220), (40, 220, 40)]
    for i in range(1000):
        mau = mau_lap[i % len(mau_lap)]
        bien_thien = (i % 5) - 2  # nhiễu nhẹ trong cùng cụm màu
        _luu_anh(thu_muc, f"{i:05d}.jpg", _ve_anh_gradient(mau, do_bien_thien=bien_thien))

    bat_dau = time.perf_counter()
    duong_dan_out = tmp_path / "dedup_map.json"
    nhom = chay(thu_muc, duong_dan_out, phuong_phap="phash")
    thoi_gian = time.perf_counter() - bat_dau

    assert thoi_gian < 60.0, f"Quá chậm: {thoi_gian:.2f}s cho 1000 ảnh"
    assert len(nhom) > 0
    assert duong_dan_out.exists()
