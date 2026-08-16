"""
Chuyển checkpoint caption (Phase 03) thành dataset huấn luyện QLoRA cho Qwen2-VL.

Chạy thuần CPU, KHÔNG import torch/transformers — script train thật sự sống
trong notebook Kaggle (Phase 04, xem scripts/kaggle_smoke.ipynb).

Mỗi mẫu là một hội thoại: người dùng gửi ảnh + USER_PROMPT (đúng câu hỏi dùng
lúc suy luận, xem vlm/prompts.py), trợ lý trả lời bằng chuỗi JSON đúng 6 trường
của KeyframeMetadata. Model học cả nội dung lẫn thứ tự khóa.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from quality.caption_loader import doc_checkpoint  # noqa: E402

# import vlm.prompts (dot notation) sẽ chạy vlm/__init__.py trước, kéo theo
# model_loader/generate/adapters — những module cần torch mà script CPU này
# không có. Nạp thẳng module prompts.py bằng importlib, bỏ qua __init__.py,
# giống cách quality/caption_defect_checks.py đã làm.
_PROMPTS_PATH = Path(__file__).resolve().parent.parent / "vlm" / "prompts.py"
_spec = importlib.util.spec_from_file_location("_vlm_prompts_only", _PROMPTS_PATH)
_prompts_module = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("_vlm_prompts_only", _prompts_module)
_spec.loader.exec_module(_prompts_module)
USER_PROMPT = _prompts_module.USER_PROMPT

# Thứ tự khóa cố định — model học cả thứ tự, để lộn xộn là dạy nó lộn xộn.
THU_TU_KHOA = ["doi_tuong", "mau_sac", "hanh_dong", "boi_canh", "caption_chi_tiet", "caption_en"]


def _doc_anh_loai_tru(duong_dan: Path | None) -> set[str]:
    """Đọc file .txt danh sách tên ảnh (mỗi dòng một tên) cần loại khỏi dataset."""
    if duong_dan is None:
        return set()
    if not duong_dan.exists():
        raise FileNotFoundError(f"Khong tim thay danh sach loai tru: {duong_dan}")
    dong = duong_dan.read_text(encoding="utf-8").splitlines()
    return {d.strip() for d in dong if d.strip()}


def _doc_ket_qua_goc(duong_dan_checkpoint: Path) -> dict[str, dict[str, Any]]:
    """Đọc lại checkpoint thô để lấy caption_en — CaptionRow không mang trường này."""
    du_lieu = json.loads(duong_dan_checkpoint.read_text(encoding="utf-8"))
    da_xong = du_lieu.get("da_xong", {})
    return {ten_anh: (muc.get("ket_qua") or {}) for ten_anh, muc in da_xong.items()}


def _tao_muc_hoi_thoai(ten_anh: str, caption_chi_tiet: str, doi_tuong: list[str],
                        mau_sac: list[str], hanh_dong: str, boi_canh: str,
                        caption_en: str) -> dict[str, Any]:
    """Dựng một dòng jsonl: {image, messages}. Assistant trả JSON 6 trường, thứ tự cố định."""
    dich_json = {
        "doi_tuong": doi_tuong,
        "mau_sac": mau_sac,
        "hanh_dong": hanh_dong,
        "boi_canh": boi_canh,
        "caption_chi_tiet": caption_chi_tiet,
        "caption_en": caption_en,
    }
    # dict trong Python 3.7+ giữ thứ tự chèn — khớp THU_TU_KHOA ở trên.
    assert list(dich_json.keys()) == THU_TU_KHOA
    chuoi_json_dich = json.dumps(dich_json, ensure_ascii=False, separators=(",", ":"))

    return {
        "image": ten_anh,
        "messages": [
            {
                "role": "user",
                "content": [{"type": "image"}, {"type": "text", "text": USER_PROMPT}],
            },
            {
                "role": "assistant",
                "content": [{"type": "text", "text": chuoi_json_dich}],
            },
        ],
    }


def dung_dataset(
    checkpoint: Path,
    out_dir: Path,
    ty_le_eval: float = 0.1,
    danh_sach_loai_tru: Path | None = None,
    thu_muc_anh_nguon: Path | None = None,
) -> dict[str, int]:
    """
    Đọc checkpoint, sinh train.jsonl + eval.jsonl (+ chép ảnh nếu có nguồn).

    Trả về thống kê: tong_mau, so_train, so_eval, so_loai_tru, so_bo_qua.
    """
    checkpoint = Path(checkpoint)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    rows, so_bo_qua = doc_checkpoint(checkpoint)
    ket_qua_goc = _doc_ket_qua_goc(checkpoint)
    anh_loai_tru = _doc_anh_loai_tru(danh_sach_loai_tru)

    so_loai_tru = 0
    muc_dung_duoc: list[dict[str, Any]] = []
    for row in rows:
        if row.ten_anh in anh_loai_tru:
            so_loai_tru += 1
            continue
        goc = ket_qua_goc.get(row.ten_anh, {})
        muc = _tao_muc_hoi_thoai(
            ten_anh=row.ten_anh,
            caption_chi_tiet=row.caption,
            doi_tuong=row.doi_tuong,
            mau_sac=row.mau_sac,
            hanh_dong=row.hanh_dong,
            boi_canh=row.boi_canh,
            caption_en=str(goc.get("caption_en", "")),
        )
        muc_dung_duoc.append(muc)

    # Chia train/eval theo thứ tự cố định (không random) — cùng đầu vào phải
    # ra cùng kết quả để chạy lại kiểm chứng được.
    tong_mau = len(muc_dung_duoc)
    so_eval = round(tong_mau * ty_le_eval)
    diem_cat = tong_mau - so_eval
    tap_train = muc_dung_duoc[:diem_cat]
    tap_eval = muc_dung_duoc[diem_cat:]

    _ghi_jsonl(out_dir / "train.jsonl", tap_train)
    _ghi_jsonl(out_dir / "eval.jsonl", tap_eval)

    if thu_muc_anh_nguon is not None:
        _chep_anh(muc_dung_duoc, Path(thu_muc_anh_nguon), out_dir / "images")

    thong_ke = {
        "tong_mau": tong_mau,
        "so_train": len(tap_train),
        "so_eval": len(tap_eval),
        "so_loai_tru": so_loai_tru,
        "so_bo_qua": so_bo_qua,
    }
    return thong_ke


def _ghi_jsonl(duong_dan: Path, muc_list: list[dict[str, Any]]) -> None:
    with duong_dan.open("w", encoding="utf-8") as f:
        for muc in muc_list:
            f.write(json.dumps(muc, ensure_ascii=False) + "\n")


def _chep_anh(muc_list: list[dict[str, Any]], nguon: Path, dich: Path) -> None:
    """Chép ảnh của các mẫu dùng được từ thư mục nguồn sang thư mục dataset."""
    dich.mkdir(parents=True, exist_ok=True)
    for muc in muc_list:
        ten_anh = muc["image"]
        duong_dan_nguon = nguon / ten_anh
        if duong_dan_nguon.exists():
            shutil.copy2(duong_dan_nguon, dich / ten_anh)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--checkpoint", type=Path, required=True,
                    help="Duong dan checkpoint_<model>.json")
    p.add_argument("--out-dir", type=Path, default=Path("data/dataset_qlora"),
                    help="Thu muc ghi train.jsonl + eval.jsonl")
    p.add_argument("--ty-le-eval", type=float, default=0.1,
                    help="Ty le mau danh cho eval (mac dinh 0.1 = 10%%)")
    p.add_argument("--danh-sach-loai-tru", type=Path, default=None,
                    help="File .txt ten anh moi dong, loai khoi dataset (vd: tap holdout Phase 05)")
    p.add_argument("--thu-muc-anh-nguon", type=Path, default=None,
                    help="Thu muc anh nguon de chep sang out-dir/images (vd: data/keyframes_aic)")
    return p.parse_args()


def main() -> None:
    if sys.stdout.encoding != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")

    args = _parse_args()
    thong_ke = dung_dataset(
        checkpoint=args.checkpoint,
        out_dir=args.out_dir,
        ty_le_eval=args.ty_le_eval,
        danh_sach_loai_tru=args.danh_sach_loai_tru,
        thu_muc_anh_nguon=args.thu_muc_anh_nguon,
    )

    print("=== Thong ke dataset QLoRA ===")
    print(f"Tong mau dung duoc : {thong_ke['tong_mau']}")
    print(f"So mau train       : {thong_ke['so_train']}")
    print(f"So mau eval        : {thong_ke['so_eval']}")
    print(f"So mau loai tru     : {thong_ke['so_loai_tru']} (tap holdout / danh sach loai tru)")
    print(f"So mau bo qua       : {thong_ke['so_bo_qua']} (thanh_cong=False hoac mock)")
    print(f"Ghi ra: {args.out_dir / 'train.jsonl'}")
    print(f"Ghi ra: {args.out_dir / 'eval.jsonl'}")


if __name__ == "__main__":
    main()
