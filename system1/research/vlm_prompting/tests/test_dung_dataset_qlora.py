"""Test dung_dataset_qlora.py — thuan CPU, khong torch."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.dung_dataset_qlora import THU_TU_KHOA, dung_dataset  # noqa: E402


def _ket_qua_mau(idx: int) -> dict:
    return {
        "doi_tuong": [f"vat_{idx}"],
        "mau_sac": ["do"],
        "hanh_dong": "dang di",
        "boi_canh": "duong pho",
        "caption_chi_tiet": f"Mot nguoi dang di bo tren duong pho so {idx} voi ao mau do noi bat.",
        "caption_en": f"A person walking on street {idx} wearing a bright red shirt.",
    }


def _tao_checkpoint(tmp_path: Path, so_mau: int, so_that_bai: int = 0) -> Path:
    da_xong = {}
    for i in range(so_mau):
        ten_anh = f"anh_{i:03d}.jpg"
        da_xong[ten_anh] = {"thanh_cong": True, "ket_qua": _ket_qua_mau(i), "loi": None}
    for i in range(so_that_bai):
        ten_anh = f"loi_{i:03d}.jpg"
        da_xong[ten_anh] = {"thanh_cong": False, "ket_qua": None, "loi": "timeout"}

    checkpoint = {"model_key": "haiku-teacher", "da_xong": da_xong}
    duong_dan = tmp_path / "checkpoint_haiku-teacher.json"
    duong_dan.write_text(json.dumps(checkpoint, ensure_ascii=False, indent=2), encoding="utf-8")
    return duong_dan


def _doc_jsonl(duong_dan: Path) -> list[dict]:
    return [json.loads(dong) for dong in duong_dan.read_text(encoding="utf-8").splitlines()]


def test_chia_train_eval_dung_ty_le(tmp_path):
    checkpoint = _tao_checkpoint(tmp_path, so_mau=10)
    out_dir = tmp_path / "out"

    thong_ke = dung_dataset(checkpoint, out_dir, ty_le_eval=0.1)

    assert thong_ke["so_train"] == 9
    assert thong_ke["so_eval"] == 1
    assert len(_doc_jsonl(out_dir / "train.jsonl")) == 9
    assert len(_doc_jsonl(out_dir / "eval.jsonl")) == 1


def test_loai_mau_that_bai_va_dem_dung(tmp_path):
    checkpoint = _tao_checkpoint(tmp_path, so_mau=10, so_that_bai=3)
    out_dir = tmp_path / "out"

    thong_ke = dung_dataset(checkpoint, out_dir, ty_le_eval=0.1)

    assert thong_ke["so_bo_qua"] == 3
    assert thong_ke["tong_mau"] == 10
    tat_ca = _doc_jsonl(out_dir / "train.jsonl") + _doc_jsonl(out_dir / "eval.jsonl")
    ten_anh_dataset = {m["image"] for m in tat_ca}
    assert all(not ten.startswith("loi_") for ten in ten_anh_dataset)


def test_moi_dong_jsonl_parse_duoc_va_dung_khoa(tmp_path):
    checkpoint = _tao_checkpoint(tmp_path, so_mau=5)
    out_dir = tmp_path / "out"

    dung_dataset(checkpoint, out_dir, ty_le_eval=0.2)

    tat_ca = _doc_jsonl(out_dir / "train.jsonl") + _doc_jsonl(out_dir / "eval.jsonl")
    assert len(tat_ca) == 5
    for muc in tat_ca:
        assert set(muc.keys()) == {"image", "messages"}
        assert len(muc["messages"]) == 2
        assert muc["messages"][0]["role"] == "user"
        assert muc["messages"][1]["role"] == "assistant"


def test_assistant_parse_ra_dung_6_truong(tmp_path):
    checkpoint = _tao_checkpoint(tmp_path, so_mau=5)
    out_dir = tmp_path / "out"

    dung_dataset(checkpoint, out_dir, ty_le_eval=0.2)

    tat_ca = _doc_jsonl(out_dir / "train.jsonl") + _doc_jsonl(out_dir / "eval.jsonl")
    for muc in tat_ca:
        chuoi_json = muc["messages"][1]["content"][0]["text"]
        du_lieu = json.loads(chuoi_json)
        assert list(du_lieu.keys()) == THU_TU_KHOA
        assert set(du_lieu.keys()) == {
            "doi_tuong", "mau_sac", "hanh_dong", "boi_canh",
            "caption_chi_tiet", "caption_en",
        }


def test_danh_sach_loai_tru_loai_ca_train_lan_eval(tmp_path):
    checkpoint = _tao_checkpoint(tmp_path, so_mau=10)
    out_dir = tmp_path / "out"
    file_loai_tru = tmp_path / "holdout.txt"
    anh_holdout = {"anh_001.jpg", "anh_005.jpg", "anh_009.jpg"}
    file_loai_tru.write_text("\n".join(sorted(anh_holdout)), encoding="utf-8")

    thong_ke = dung_dataset(checkpoint, out_dir, ty_le_eval=0.1, danh_sach_loai_tru=file_loai_tru)

    assert thong_ke["so_loai_tru"] == 3
    tat_ca = _doc_jsonl(out_dir / "train.jsonl") + _doc_jsonl(out_dir / "eval.jsonl")
    ten_anh_dataset = {m["image"] for m in tat_ca}
    assert ten_anh_dataset & anh_holdout == set()


def test_chay_lai_cung_dau_vao_ra_ket_qua_giong_het(tmp_path):
    checkpoint = _tao_checkpoint(tmp_path, so_mau=20)
    out_dir_1 = tmp_path / "out1"
    out_dir_2 = tmp_path / "out2"

    dung_dataset(checkpoint, out_dir_1, ty_le_eval=0.1)
    dung_dataset(checkpoint, out_dir_2, ty_le_eval=0.1)

    for ten_file in ("train.jsonl", "eval.jsonl"):
        noi_dung_1 = (out_dir_1 / ten_file).read_text(encoding="utf-8")
        noi_dung_2 = (out_dir_2 / ten_file).read_text(encoding="utf-8")
        assert noi_dung_1 == noi_dung_2
