"""
CLI gộp — một lệnh chạy ra recall@k + tỉ lệ dính từng lỗi + top caption tệ.

Cách dùng:
    python -m quality.danh_gia_chat_luong --input results/checkpoint_qwen25vl-3b.json
    python -m quality.danh_gia_chat_luong --input results/sample_results.json \\
        --out results/quality_report.json --top-worst 10

Không log nội dung caption ra màn hình mặc định (dữ liệu cuộc thi) — chỉ in
khi có cờ --top-worst, và người dùng phải chủ động bật.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if sys.platform.startswith("win"):
    for _luong in (sys.stdout, sys.stderr):
        try:
            _luong.reconfigure(encoding="utf-8")
        except (AttributeError, OSError):
            pass

from quality.caption_defect_checks import kiem_hang_loat
from quality.caption_loader import load_captions
from quality.self_retrieval_bm25 import do_self_retrieval


def _xep_hang_te_nhat(rows, ket_qua_loi, hang_tung_anh, top_n: int) -> list[dict]:
    """
    Xếp hạng caption tệ nhất để đọc tay: ưu tiên dính nhiều lỗi hơn, sau đó
    tới hạng self-retrieval thấp hơn (tụt hạng = ít riêng biệt = tệ hơn).
    """
    theo_ten = {r.ten_anh: r for r in rows}
    muc: list[dict] = []
    for kq in ket_qua_loi:
        so_loi = sum([kq.chep_few_shot, kq.nhet_chu_ocr, kq.vong_vo, kq.ngon_ngu_la])
        hang = hang_tung_anh.get(kq.ten_anh, 0)
        muc.append(
            {
                "ten_anh": kq.ten_anh,
                "so_loi": so_loi,
                "hang_self_retrieval": hang,
                "chep_few_shot": kq.chep_few_shot,
                "nhet_chu_ocr": kq.nhet_chu_ocr,
                "vong_vo": kq.vong_vo,
                "ngon_ngu_la": kq.ngon_ngu_la,
                "ttr": kq.ttr,
                "caption": theo_ten[kq.ten_anh].caption if kq.ten_anh in theo_ten else "",
            }
        )
    muc.sort(key=lambda m: (-m["so_loi"], -m["hang_self_retrieval"]))
    return muc[:top_n]


def chay_danh_gia(duong_dan_vao: Path, *, top_worst: int = 10) -> dict:
    """Logic lõi, tách khỏi main() để test import gọi thẳng được."""
    rows, so_bo_qua = load_captions(duong_dan_vao)

    recall = do_self_retrieval(rows)
    ket_qua_loi = kiem_hang_loat(rows)

    tong = len(ket_qua_loi)

    def _ty_le(ten_loi: str) -> float:
        if not tong:
            return 0.0
        return round(sum(getattr(k, ten_loi) for k in ket_qua_loi) / tong, 4)

    top_te = _xep_hang_te_nhat(rows, ket_qua_loi, recall.hang_tung_anh, top_worst)

    return {
        "nguon": str(duong_dan_vao),
        "so_caption_dung_duoc": len(rows),
        "so_bo_qua": so_bo_qua,
        "recall": {
            "recall_tai_1": recall.recall_tai_1,
            "recall_tai_5": recall.recall_tai_5,
            "recall_tai_10": recall.recall_tai_10,
            "mrr": recall.mrr,
        },
        "ty_le_loi": {
            ten: _ty_le(ten)
            for ten in ("chep_few_shot", "nhet_chu_ocr", "vong_vo", "ngon_ngu_la")
        },
        "top_te_nhat": top_te,
    }


def _in_bang(bao_cao: dict, *, hien_top_worst: bool) -> None:
    print("=" * 60)
    print("BÁO CÁO CHẤT LƯỢNG CAPTION (self-retrieval, không ground truth)")
    print("=" * 60)
    print(f"Nguồn           : {bao_cao['nguon']}")
    print(f"Caption dùng được: {bao_cao['so_caption_dung_duoc']} (bỏ qua {bao_cao['so_bo_qua']})")
    print()
    r = bao_cao["recall"]
    print(f"recall@1  : {r['recall_tai_1']:.4f}")
    print(f"recall@5  : {r['recall_tai_5']:.4f}")
    print(f"recall@10 : {r['recall_tai_10']:.4f}")
    print(f"MRR       : {r['mrr']:.4f}")
    print()
    tl = bao_cao["ty_le_loi"]
    print(f"Chép few-shot : {tl['chep_few_shot']:.2%}")
    print(f"Nhét chữ OCR  : {tl['nhet_chu_ocr']:.2%}")
    print(f"Vòng vo (TTR) : {tl['vong_vo']:.2%}")
    print(f"Ngôn ngữ lạ   : {tl['ngon_ngu_la']:.2%}")

    if hien_top_worst and bao_cao["top_te_nhat"]:
        print()
        print(f"--- Top {len(bao_cao['top_te_nhat'])} caption tệ nhất ---")
        for i, m in enumerate(bao_cao["top_te_nhat"], 1):
            co = []
            if m["chep_few_shot"]:
                co.append("chép few-shot")
            if m["nhet_chu_ocr"]:
                co.append("nhét OCR")
            if m["vong_vo"]:
                co.append("vòng vo")
            if m.get("ngon_ngu_la"):
                co.append("ngôn ngữ lạ")
            print(f"{i}. {m['ten_anh']} (hạng {m['hang_self_retrieval']}, {', '.join(co) or 'không lỗi rõ'})")
            print(f"   {m['caption']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Chấm chất lượng caption bằng self-retrieval + defect checks")
    parser.add_argument("--input", type=Path, required=True, help="checkpoint_*.json hoặc sample_results.json")
    parser.add_argument("--out", type=Path, default=None, help="Ghi báo cáo JSON ra file này")
    parser.add_argument(
        "--top-worst", type=int, default=0, help="In N caption tệ nhất ra màn hình (mặc định: không in)"
    )
    args = parser.parse_args()

    if not args.input.exists():
        print(f"Không tìm thấy file: {args.input}")
        return 1

    bao_cao = chay_danh_gia(args.input, top_worst=max(args.top_worst, 10))
    _in_bang(bao_cao, hien_top_worst=args.top_worst > 0)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(bao_cao, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nĐã ghi báo cáo: {args.out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
