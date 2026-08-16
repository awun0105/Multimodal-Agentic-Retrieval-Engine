"""Gom checkpoint + bang tong hop thanh dong bang dung dinh dang report.md muc 3.

Vi sao can: bang trong report co 7 cot, so lay tu 3 nguon khac nhau (checkpoint,
vlm_comparison_results.json, bo cham chat luong). Ghep tay de sai va de bo sot
model. Script nay doc het, in ra dong markdown chep thang vao report.

Chay:
    python scripts/gom-bang-benchmark-report.py --results results/
    python scripts/gom-bang-benchmark-report.py --results results/ --models qwen25vl-7b
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

GOC = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(GOC))

TEN_HIEN_THI = {
    "qwen25vl-7b": "Qwen2.5-VL-7B",
    "qwen25vl-3b": "Qwen2.5-VL-3B",
    "qwen2vl-2b": "Qwen2-VL-2B",
    "vintern-1b": "Vintern-1B-v3.5",
    "vintern-3b": "Vintern-3B-R-beta",
    "minicpm-v-4": "MiniCPM-V-4.0",
}


def _so(x, nd: int = 3) -> str:
    """Dinh dang so kieu Viet Nam (dau phay thap phan) nhu report dang dung."""
    if x is None:
        return "—"
    return f"{float(x):.{nd}f}".replace(".", ",")


def doc_checkpoint(duong_dan: Path) -> dict:
    d = json.loads(duong_dan.read_text(encoding="utf-8"))
    xong = d.get("da_xong") or {}
    tong = len(xong)
    ok = sum(1 for v in xong.values() if v.get("thanh_cong"))
    co_raw = sum(1 for v in xong.values() if v.get("raw_text"))
    co_en = sum(
        1
        for v in xong.values()
        if (v.get("ket_qua") or {}).get("caption_en")
    )
    return {
        "tong": tong,
        "ok": ok,
        "ty_le": ok / tong if tong else 0.0,
        "co_raw_text": co_raw,
        "caption_en": co_en / ok if ok else 0.0,
    }


def doc_chat_luong(model_key: str, checkpoint: Path) -> dict:
    """Chay bo cham chat luong co san. Tra dict rong neu khong cham duoc."""
    try:
        from quality.danh_gia_chat_luong import chay_danh_gia
    except ImportError:
        return {}
    try:
        kq = chay_danh_gia(checkpoint)
    except Exception as loi:  # noqa: BLE001 - thieu so cham van in duoc bang
        print(f"  (khong cham duoc {model_key}: {type(loi).__name__}: {loi})",
              file=sys.stderr)
        return {}
    return {
        **(kq.get("ty_le_loi") or {}),
        "recall_1": (kq.get("recall") or {}).get("recall_tai_1"),
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--results", type=Path, default=GOC / "results")
    p.add_argument("--models", help="Loc theo danh sach model, ngan bang dau phay")
    args = p.parse_args()

    bang = args.results / "vlm_comparison_results.json"
    tong_hop = {}
    if bang.exists():
        tong_hop = (json.loads(bang.read_text(encoding="utf-8")).get("ket_qua")) or {}

    loc = {m.strip() for m in args.models.split(",")} if args.models else None

    dong = []
    for ck in sorted(args.results.glob("checkpoint_*.json")):
        model_key = ck.stem.replace("checkpoint_", "")
        if loc and model_key not in loc:
            continue
        if model_key not in TEN_HIEN_THI:
            continue  # bo qua checkpoint thu nghiem (haiku-*, *-backup...)

        c = doc_checkpoint(ck)
        if c["tong"] < 100:
            print(f"  (bo qua {model_key}: chi {c['tong']} anh, duoi nguong de bai)",
                  file=sys.stderr)
            continue

        t = tong_hop.get(model_key) or {}
        lat = t.get("latency_trung_binh")
        p50, p95 = t.get("latency_p50"), t.get("latency_p95")
        vram = t.get("vram_dinh_gb")
        backend = t.get("backend") or "—"

        cot_lat = "—" if lat is None else f"{_so(lat)} s/ảnh"
        if p50 is not None and p95 is not None:
            cot_lat += f" (P50 {_so(p50)} · P95 {_so(p95)} s)"
        cot_vram = "—" if vram is None else f"{_so(vram)} GB"

        canh_bao = " ❌ **mock — số không dùng được**" if backend == "mock" else ""
        cot_diem = (f"JSON hợp lệ {_so(c['ty_le'] * 100, 2)}% "
                    f"({c['ok']}/**{c['tong']}**){canh_bao}")

        q = doc_chat_luong(model_key, ck)
        phu = []
        # recall la diem 0-1, khong phai ty le phan tram -> in nguyen, khong nhan 100.
        for nhan, khoa in (("nhét chữ OCR", "nhet_chu_ocr"),
                           ("vòng vo", "vong_vo"),
                           ("chép mẫu", "chep_few_shot")):
            if q.get(khoa) is not None:
                phu.append(f"{nhan} {_so(q[khoa] * 100, 2)}%")
        if q.get("recall_1") is not None:
            phu.append(f"recall@1 {_so(q['recall_1'], 4)}")
        if c["ok"]:
            phu.append(f"`caption_en` {_so(c['caption_en'] * 100, 1)}%")
        if c["co_raw_text"]:
            phu.append(f"{c['co_raw_text']} ca lỗi có raw_text")

        dong.append(
            f"| **{TEN_HIEN_THI[model_key]}** | {cot_lat} | {cot_vram} | "
            f"{cot_diem} | {' · '.join(phu) or '—'} | | |"
        )

    if not dong:
        print("Khong co model nao du dieu kien (>=100 anh).", file=sys.stderr)
        return 1

    print("| Mô hình | Latency | VRAM | Điểm benchmark | Chỉ số chất lượng | "
          "Nhược điểm | Kết luận |")
    print("|---|---|---|---|---|---|---|")
    for d in dong:
        print(d)
    print()
    print("(Cột Nhược điểm / Kết luận để trống — điền tay sau khi đọc số.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
