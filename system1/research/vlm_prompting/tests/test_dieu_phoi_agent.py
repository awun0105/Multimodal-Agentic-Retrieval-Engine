"""
Test bộ điều phối agent caption — thuần CPU, KHÔNG spawn agent thật.

Chỉ kiểm logic chia lô + gom kết quả JSON + ghi/đọc checkpoint. Việc spawn
agent thật (công cụ Agent) nằm ngoài phạm vi test được — do agent điều phối
làm thủ công, xem docstring scripts/dieu_phoi_agent_caption.py.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

GOC = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(GOC))

from quality.caption_loader import load_captions  # noqa: E402
from scripts.chon_anh_train import (  # noqa: E402
    chon_anh_rai_deu,
    ghi_danh_sach_anh,
    tach_train_holdout,
)
from scripts.dieu_phoi_agent_caption import (  # noqa: E402
    chia_lo,
    ghi_lo_vao_checkpoint,
    gom_ket_qua_agent,
)


def test_chia_lo_37_anh_lo_15() -> None:
    danh_sach = [f"anh_{i}.jpg" for i in range(37)]
    lo = chia_lo(danh_sach, 15)
    assert [len(x) for x in lo] == [15, 15, 7]


def test_chia_lo_500_anh_lo_15_ra_34_lo() -> None:
    danh_sach = list(range(500))
    lo = chia_lo(danh_sach, 15)
    assert len(lo) == 34


def test_gom_ket_qua_agent_json_hop_le() -> None:
    text = json.dumps(
        [
            {
                "ten_anh": "a.jpg",
                "doi_tuong": ["người", "xe máy"],
                "mau_sac": ["đỏ"],
                "hanh_dong": "đang chạy",
                "boi_canh": "đường phố",
                "caption_chi_tiet": "Một người đàn ông mặc áo đỏ đang chạy xe máy trên đường phố đông đúc.",
                "caption_en": "A man in a red shirt rides a motorbike on a busy street.",
            },
            {
                "ten_anh": "b.jpg",
                "doi_tuong": ["mèo"],
                "mau_sac": ["trắng"],
                "hanh_dong": "đang ngủ",
                "boi_canh": "trong nhà",
                "caption_chi_tiet": "Một con mèo trắng đang cuộn tròn ngủ trên ghế sofa trong phòng khách.",
                "caption_en": "A white cat curls up asleep on a sofa in the living room.",
            },
        ],
        ensure_ascii=False,
    )
    ket_qua, ten_anh_thua = gom_ket_qua_agent(text, ["a.jpg", "b.jpg"])
    assert ket_qua["a.jpg"]["thanh_cong"] is True
    assert ket_qua["b.jpg"]["thanh_cong"] is True
    assert ket_qua["a.jpg"]["ket_qua"]["caption_chi_tiet"].startswith("Một người đàn ông")
    assert ten_anh_thua == []


def test_gom_ket_qua_agent_boc_markdown() -> None:
    mang = [
        {
            "ten_anh": "c.jpg",
            "doi_tuong": ["bàn"],
            "mau_sac": ["nâu"],
            "hanh_dong": "đặt trong phòng",
            "boi_canh": "văn phòng",
            "caption_chi_tiet": "Một chiếc bàn gỗ màu nâu được đặt giữa phòng làm việc yên tĩnh.",
            "caption_en": "A brown wooden table sits in the middle of a quiet office.",
        }
    ]
    text = "Đây là kết quả:\n```json\n" + json.dumps(mang, ensure_ascii=False) + "\n```"
    ket_qua, ten_anh_thua = gom_ket_qua_agent(text, ["c.jpg"])
    assert ket_qua["c.jpg"]["thanh_cong"] is True
    assert ten_anh_thua == []


def test_gom_ket_qua_agent_thieu_anh() -> None:
    mang = [
        {
            "ten_anh": "d.jpg",
            "doi_tuong": ["cây"],
            "mau_sac": ["xanh"],
            "hanh_dong": "đứng yên",
            "boi_canh": "công viên",
            "caption_chi_tiet": "Một hàng cây xanh cao lớn đứng dọc theo lối đi trong công viên.",
            "caption_en": "A row of tall green trees lines the path in the park.",
        }
    ]
    text = json.dumps(mang, ensure_ascii=False)
    ket_qua, ten_anh_thua = gom_ket_qua_agent(text, ["d.jpg", "e.jpg"])
    assert ket_qua["d.jpg"]["thanh_cong"] is True
    assert ket_qua["e.jpg"]["thanh_cong"] is False
    assert ket_qua["e.jpg"]["loi"] == "agent bỏ sót"
    assert ten_anh_thua == []


def test_gom_ket_qua_agent_caption_qua_ngan_that_bai() -> None:
    mang = [
        {
            "ten_anh": "f.jpg",
            "doi_tuong": ["mèo"],
            "mau_sac": ["đen"],
            "hanh_dong": "ngồi",
            "boi_canh": "sân",
            "caption_chi_tiet": "một con mèo",
        }
    ]
    text = json.dumps(mang, ensure_ascii=False)
    ket_qua, ten_anh_thua = gom_ket_qua_agent(text, ["f.jpg"])
    assert ket_qua["f.jpg"]["thanh_cong"] is False
    assert ket_qua["f.jpg"]["ket_qua"] is None
    assert ten_anh_thua == []


def test_gom_ket_qua_agent_anh_thua_khong_lot_vao_ket_qua() -> None:
    mang = [
        {
            "ten_anh": "g.jpg",
            "doi_tuong": ["chó"],
            "mau_sac": ["nâu"],
            "hanh_dong": "chạy",
            "boi_canh": "công viên",
            "caption_chi_tiet": "Một chú chó nâu đang chạy nhảy vui vẻ trên bãi cỏ công viên.",
            "caption_en": "A brown dog runs joyfully on the park lawn.",
        },
        {
            "ten_anh": "h.jpg",
            "doi_tuong": ["xe"],
            "mau_sac": ["xanh"],
            "hanh_dong": "đỗ",
            "boi_canh": "bãi xe",
            "caption_chi_tiet": "Một chiếc xe hơi màu xanh đang đỗ ngay ngắn trong bãi đỗ xe.",
            "caption_en": "A blue car is neatly parked in the parking lot.",
        },
    ]
    text = json.dumps(mang, ensure_ascii=False)
    ket_qua, ten_anh_thua = gom_ket_qua_agent(text, ["g.jpg"])
    assert "g.jpg" in ket_qua
    assert "h.jpg" not in ket_qua
    assert ten_anh_thua == ["h.jpg"]


def test_checkpoint_ghi_ra_doc_lai_duoc_boi_quality(tmp_path: Path) -> None:
    ket_qua_lo = {
        "g.jpg": {
            "thanh_cong": True,
            "ket_qua": {
                "doi_tuong": ["xe đạp"],
                "mau_sac": ["vàng"],
                "hanh_dong": "đang dừng",
                "boi_canh": "vỉa hè",
                "caption_chi_tiet": "Một chiếc xe đạp màu vàng đang dựng bên vỉa hè trước cửa hàng.",
                "caption_en": "A yellow bicycle is parked on the sidewalk in front of a shop.",
            },
            "loi": None,
        }
    }
    ghi_lo_vao_checkpoint(tmp_path, "haiku-teacher", ket_qua_lo)

    duong_dan = tmp_path / "checkpoint_haiku-teacher.json"
    rows, so_bo_qua = load_captions(duong_dan)
    assert len(rows) > 0
    assert so_bo_qua == 0


def test_chon_anh_rai_deu_1000_chon_500() -> None:
    danh_sach = [Path(f"anh_{i:04d}.jpg") for i in range(1000)]
    da_chon = chon_anh_rai_deu(danh_sach, 500)
    assert len(da_chon) == 500
    assert len(set(da_chon)) == 500
    assert da_chon == sorted(da_chon)


def test_chon_anh_rai_deu_nhieu_hon_so_co_tra_toan_bo() -> None:
    danh_sach = [Path(f"anh_{i}.jpg") for i in range(10)]
    da_chon = chon_anh_rai_deu(danh_sach, 50)
    assert da_chon == danh_sach


def test_chon_anh_rai_deu_chon_0_ra_rong() -> None:
    danh_sach = [Path(f"anh_{i}.jpg") for i in range(10)]
    assert chon_anh_rai_deu(danh_sach, 0) == []


def test_tach_train_holdout_560_anh_holdout_60() -> None:
    danh_sach = [Path(f"anh_{i:04d}.jpg") for i in range(560)]
    train, holdout = tach_train_holdout(danh_sach, 60)
    assert len(train) == 500
    assert len(holdout) == 60
    assert set(train) & set(holdout) == set()
    assert len(train) + len(holdout) == len(danh_sach)


def test_tach_train_holdout_qua_so_luong_nem_loi() -> None:
    danh_sach = [Path(f"anh_{i}.jpg") for i in range(10)]
    try:
        tach_train_holdout(danh_sach, 10)
        assert False, "phai nem ValueError khi so_holdout >= tong so anh"
    except ValueError:
        pass


def test_ghi_danh_sach_anh_doc_lai_dung_so_dong(tmp_path: Path) -> None:
    danh_sach = [Path(f"/tuyet/doi/anh_{i}.jpg") for i in range(5)]
    duong_dan = tmp_path / "danh_sach.txt"
    ghi_danh_sach_anh(duong_dan, danh_sach)

    dong = duong_dan.read_text(encoding="utf-8").splitlines()
    assert len(dong) == 5
    assert dong == [f"anh_{i}.jpg" for i in range(5)]


def test_tach_train_holdout_holdout_rai_deu_khong_phai_cuoi_danh_sach() -> None:
    danh_sach = [Path(f"anh_{i:04d}.jpg") for i in range(560)]
    _, holdout = tach_train_holdout(danh_sach, 60)
    vi_tri_dau = danh_sach.index(holdout[0])
    assert vi_tri_dau < len(danh_sach) - 60
