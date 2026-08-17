"""Sinh phiếu chấm tay 30 ảnh × 4 model, giấu tên model.

Vì sao cần chấm tay: bộ chấm tự động cho tín hiệu mâu thuẫn. Vintern-3B thắng 5/6
chỉ số nhưng thua "vòng vo 37,28%", mà con số đó phạt oan danh từ ghép tiếng Việt
(`người đàn`, `máy tính`). Khi thước đo hỏng ở một chiều, mắt người là trọng tài.

Hai biện pháp chống thiên vị:

1. Chỉ lấy ảnh mà CẢ 4 model đều sinh được caption. Không thì model nào bỏ qua ảnh
   khó sẽ được lợi — nó chỉ bị chấm trên phần dễ.
2. Thứ tự A/B/C/D xáo LẠI Ở MỖI ẢNH. Xáo một lần cho cả phiếu thì người chấm nhận
   ra giọng văn của một model rồi suy ra ba model kia.

Chạy:
    python quality/tao-phieu-cham-tay.py
    python quality/tao-phieu-cham-tay.py --so-anh 30 --seed 42
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

GOC = Path(__file__).resolve().parent.parent

# Tên hiển thị chỉ dùng cho file đáp án, KHÔNG lọt vào phiếu chấm.
NGUON = {
    "qwen25vl-7b": "results/checkpoint_qwen25vl-7b.json",
    "vintern-3b": "results/checkpoint_vintern-3b.json",
    "qwen25vl-3b": "results/checkpoint_qwen25vl-3b-promptmoi.json",
    "qwen2vl-2b": "results/checkpoint_qwen2vl-2b-promptmoi.json",
}

NHAN = ["A", "B", "C", "D"]


def doc_caption(duong_dan: Path) -> dict[str, dict]:
    d = json.loads(duong_dan.read_text(encoding="utf-8"))
    return {
        ten: muc["ket_qua"]
        for ten, muc in (d.get("da_xong") or {}).items()
        if muc.get("thanh_cong") and muc.get("ket_qua")
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--so-anh", type=int, default=30)
    p.add_argument("--seed", type=int, default=42, help="cố định để tái lập được")
    p.add_argument("--out-dir", type=Path, default=GOC / "results")
    args = p.parse_args()

    kho = {k: doc_caption(GOC / v) for k, v in NGUON.items()}
    for k, v in kho.items():
        if not v:
            print(f"Không đọc được caption của {k}")
            return 1

    # Chỉ ảnh CẢ 4 model đều có — xem docstring.
    chung = sorted(set.intersection(*(set(v) for v in kho.values())))
    if len(chung) < args.so_anh:
        print(f"Chỉ có {len(chung)} ảnh chung, cần {args.so_anh}")
        return 1

    rng = random.Random(args.seed)
    chon = sorted(rng.sample(chung, args.so_anh))

    dong: list[str] = [
        "# Phiếu chấm tay — 30 ảnh × 4 model",
        "",
        f"Chọn ngẫu nhiên {args.so_anh} ảnh trong {len(chung)} ảnh mà **cả 4 model đều "
        "sinh được caption** (seed cố định, tái lập được).",
        "",
        "**Tên model được giấu, và thứ tự A/B/C/D xáo lại ở mỗi ảnh** — nhãn A ở ảnh 1 "
        "không phải model của nhãn A ở ảnh 2.",
        "",
        "## Cách chấm",
        "",
        "Mỗi caption cho điểm 0-2 ở ba tiêu chí, điền vào cột `Điểm`:",
        "",
        "| Tiêu chí | 0 | 1 | 2 |",
        "|---|---|---|---|",
        "| **Đúng** — khớp nội dung ảnh | sai/bịa | đúng phần chính, sai chi tiết | đúng hết |",
        "| **Tiếng Việt** — tự nhiên | lủng củng, sai ngữ pháp | đọc được nhưng gượng | trôi chảy |",
        "| **Đủ** — đủ chi tiết để tìm lại cảnh | chung chung | thiếu một vài chi tiết | đủ dùng |",
        "",
        "Ghi theo dạng `2/1/2` (Đúng/Tiếng Việt/Đủ). Tối đa 6 điểm mỗi caption.",
        "",
        "Mở ảnh tại `data/keyframes_aic/<tên ảnh>`.",
        "",
        "---",
        "",
    ]

    dap_an: dict[str, dict[str, str]] = {}

    for i, ten_anh in enumerate(chon, 1):
        thu_tu = list(kho)
        rng.shuffle(thu_tu)  # xáo lại mỗi ảnh
        dap_an[ten_anh] = {NHAN[j]: mk for j, mk in enumerate(thu_tu)}

        dong += [f"## {i}. `{ten_anh}`", ""]
        for j, model_key in enumerate(thu_tu):
            kq = kho[model_key][ten_anh]
            cap = str(kq.get("caption_chi_tiet") or "").strip()
            dt = kq.get("doi_tuong") or []
            dong += [
                f"**{NHAN[j]}.** {cap}",
                "",
                f"> đối tượng: `{dt}` · bối cảnh: *{kq.get('boi_canh')}*",
                "",
                f"> Điểm {NHAN[j]}: `___/___/___`",
                "",
            ]
        dong += ["---", ""]

    phieu = args.out_dir / "phieu-cham-tay-30-anh.md"
    phieu.write_text("\n".join(dong), encoding="utf-8")

    # Đáp án để riêng: mở nhầm lúc đang chấm là hỏng cả phép đo.
    dich_dap_an = args.out_dir / "phieu-cham-DAP-AN.json"
    dich_dap_an.write_text(
        json.dumps(
            {"seed": args.seed, "so_anh": args.so_anh, "anh": dap_an},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"Phiếu chấm : {phieu}")
    print(f"Đáp án     : {dich_dap_an}  (ĐỪNG mở trước khi chấm xong)")
    print(f"{args.so_anh} ảnh × 4 model = {args.so_anh * 4} caption cần chấm")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
