"""
Chạy benchmark VLM trên bộ ảnh, đo 6 chỉ số đề bài yêu cầu.

Hai chế độ chạy (theo gợi ý của nhóm — không phải cấu hình nào cũng phù hợp,
phải dò trước khi đốt giờ GPU):

    DEBUG — vài ảnh, in đầy đủ output thô, dùng để soi lỗi và chỉnh prompt
    MASS  — chạy hàng loạt, chỉ in tiến độ, tự lưu tiến độ mỗi 25 ảnh

Cách chạy:
    python scripts/benchmark_runner.py --mode debug --n 3
    python scripts/benchmark_runner.py --mode mass --models qwen25vl-3b,vintern-1b
    python scripts/benchmark_runner.py --mode mass --stability      # đo độ ổn định
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

if sys.platform.startswith("win"):
    for _luong in (sys.stdout, sys.stderr):
        try:
            _luong.reconfigure(encoding="utf-8")
        except (AttributeError, OSError):
            pass

GOC = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(GOC))

from checkpoint_utils import (  # noqa: E402
    CHU_KY_LUU_MAC_DINH,
    filter_pending,
    load_checkpoint,
    save_checkpoint,
)
from metrics import KetQuaMotAnh, danh_gia_mot_anh, do_on_dinh, tong_ket  # noqa: E402

from vlm.generate import generate_json, reset_vram_counter, thong_tin_moi_truong  # noqa: E402
from vlm.model_registry import MODEL_REGISTRY  # noqa: E402

DUOI_ANH = (".jpg", ".jpeg", ".png", ".webp", ".bmp")


def liet_ke_anh(thu_muc: Path) -> list[Path]:
    if not thu_muc.exists():
        return []
    return sorted(p for p in thu_muc.rglob("*") if p.suffix.lower() in DUOI_ANH)


def chay_mot_model(
    model_key: str,
    danh_sach_anh: list[Path],
    *,
    thu_muc_ket_qua: Path,
    backend: str = "auto",
    che_do_debug: bool = False,
    chu_ky_luu: int = CHU_KY_LUU_MAC_DINH,
    tiep_tuc: bool = True,
) -> tuple[list[KetQuaMotAnh], dict]:
    """
    Chạy một model trên toàn bộ danh sách ảnh.

    Trả về (danh sách kết quả từng ảnh, checkpoint). Tự bỏ qua ảnh đã chạy nếu
    có checkpoint cũ — nhờ vậy phiên Kaggle bị ngắt vẫn chạy tiếp được.
    """
    checkpoint = load_checkpoint(thu_muc_ket_qua, model_key) if tiep_tuc else {
        "model_key": model_key,
        "da_xong": {},
    }

    ten_tat_ca = [p.name for p in danh_sach_anh]
    con_lai = filter_pending(ten_tat_ca, checkpoint)
    da_co = len(ten_tat_ca) - len(con_lai)

    if da_co:
        print(f"  Đã có sẵn {da_co} ảnh từ lần chạy trước, còn {len(con_lai)} ảnh.")

    theo_ten = {p.name: p for p in danh_sach_anh}
    ket_qua_moi: list[KetQuaMotAnh] = []

    for i, ten in enumerate(con_lai, 1):
        duong_dan = theo_ten[ten]
        reset_vram_counter()

        text_tho = ""
        try:
            ket_qua = generate_json(
                duong_dan, model_key=model_key, backend=backend, debug=che_do_debug
            )
            danh_gia = danh_gia_mot_anh(ten, ket_qua, text_tho)
        except Exception as loi:  # noqa: BLE001 - một ảnh lỗi không được dừng cả mẻ
            danh_gia = danh_gia_mot_anh(ten, None, text_tho, loi=loi)
            raw = getattr(loi, "raw_text", "")
            if raw:
                danh_gia.co_rac_ngoai_json = True

        ket_qua_moi.append(danh_gia)
        checkpoint["da_xong"][ten] = {
            "thanh_cong": danh_gia.thanh_cong,
            "latency_sec": danh_gia.latency_sec,
            "ket_qua": danh_gia.ket_qua,
            "loi": danh_gia.loi,
        }

        if che_do_debug:
            _in_chi_tiet(i, len(con_lai), danh_gia)
        elif i % 10 == 0 or i == len(con_lai):
            so_ok = sum(1 for r in ket_qua_moi if r.thanh_cong)
            print(f"  [{i}/{len(con_lai)}] JSON hợp lệ: {so_ok}/{i}")

        # Lưu định kỳ: Kaggle cắt phiên sau 12h, không lưu là mất trắng.
        if i % chu_ky_luu == 0:
            save_checkpoint(thu_muc_ket_qua, model_key, checkpoint)

    save_checkpoint(thu_muc_ket_qua, model_key, checkpoint)

    # Gộp cả kết quả cũ trong checkpoint để tổng kết đủ bộ ảnh.
    tat_ca: list[KetQuaMotAnh] = []
    for ten in ten_tat_ca:
        muc = checkpoint["da_xong"].get(ten)
        if muc is None:
            continue
        if muc.get("thanh_cong"):
            tat_ca.append(danh_gia_mot_anh(ten, muc.get("ket_qua"), ""))
        else:
            tat_ca.append(
                KetQuaMotAnh(ten_anh=ten, thanh_cong=False, loi=muc.get("loi"))
            )

    return tat_ca, checkpoint


def _in_chi_tiet(i: int, tong: int, r: KetQuaMotAnh) -> None:
    print(f"\n--- [{i}/{tong}] {r.ten_anh} ---")
    if not r.thanh_cong:
        print(f"  LỖI: {r.loi}")
        return
    kq = r.ket_qua or {}
    print(f"  đối tượng : {kq.get('doi_tuong')}")
    print(f"  màu sắc   : {kq.get('mau_sac')}")
    print(f"  hành động : {kq.get('hanh_dong')}")
    print(f"  bối cảnh  : {kq.get('boi_canh')}")
    print(f"  caption   : {kq.get('caption_chi_tiet')}")
    print(f"  ({r.latency_sec}s, {r.so_tu_caption} từ)")


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark VLM trên bộ ảnh")
    parser.add_argument(
        "--mode",
        choices=["debug", "mass"],
        default="debug",
        help="debug = vài ảnh + in đầy đủ; mass = chạy hàng loạt",
    )
    parser.add_argument("--n", type=int, help="Giới hạn số ảnh (mặc định: tất cả)")
    parser.add_argument(
        "--models",
        default="qwen25vl-3b",
        help="Danh sách model, ngăn bằng dấu phẩy. Ví dụ: qwen25vl-3b,vintern-1b",
    )
    parser.add_argument(
        "--backend", default="auto", choices=["auto", "vllm", "transformers", "mock"]
    )
    parser.add_argument("--frames-dir", type=Path, default=GOC / "data" / "frames")
    parser.add_argument("--out-dir", type=Path, default=GOC / "results")
    parser.add_argument("--checkpoint-every", type=int, default=CHU_KY_LUU_MAC_DINH)
    parser.add_argument(
        "--restart", action="store_true", help="Bỏ checkpoint cũ, chạy lại từ đầu"
    )
    parser.add_argument(
        "--stability",
        action="store_true",
        help="Chạy 10 ảnh 3 lần để đo độ ổn định (yêu cầu của đề bài)",
    )
    args = parser.parse_args()

    moi_truong = thong_tin_moi_truong()
    print("=" * 62)
    print(f"BENCHMARK VLM — chế độ {args.mode.upper()}")
    print("=" * 62)
    print(f"  GPU  : {moi_truong['ten_gpu'] or 'không có'} "
          f"({moi_truong['vram_gb'] or '—'} GB)")

    danh_sach_anh = liet_ke_anh(args.frames_dir)
    if not danh_sach_anh:
        print(f"\nKhông có ảnh nào trong {args.frames_dir}")
        print("Chạy trước: python scripts/prepare_sample_images.py")
        return 1

    if args.mode == "debug":
        danh_sach_anh = danh_sach_anh[: (args.n or 3)]
    elif args.n:
        danh_sach_anh = danh_sach_anh[: args.n]

    print(f"  Ảnh  : {len(danh_sach_anh)}")

    model_keys = [m.strip() for m in args.models.split(",") if m.strip()]
    sai = [m for m in model_keys if m not in MODEL_REGISTRY]
    if sai:
        print(f"\nModel không tồn tại: {sai}")
        print(f"Các lựa chọn: {', '.join(sorted(MODEL_REGISTRY))}")
        return 1
    print(f"  Model: {', '.join(model_keys)}\n")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    tong_hop = {}

    for model_key in model_keys:
        spec = MODEL_REGISTRY[model_key]
        print(f"=== {spec.ten_hien_thi} ({model_key}) ===")
        bat_dau = time.perf_counter()

        try:
            ket_qua, _ = chay_mot_model(
                model_key,
                danh_sach_anh,
                thu_muc_ket_qua=args.out_dir,
                backend=args.backend,
                che_do_debug=(args.mode == "debug"),
                chu_ky_luu=args.checkpoint_every,
                tiep_tuc=not args.restart,
            )
        except KeyboardInterrupt:
            print("\n  Đã dừng theo yêu cầu. Tiến độ đã lưu, chạy lại sẽ tiếp tục.")
            return 130

        tk = tong_ket(model_key, ket_qua, model_name=spec.hf_id, backend=args.backend)
        tong_hop[model_key] = tk.to_dict()

        print(f"\n  JSON hợp lệ   : {tk.ty_le_json_hop_le:.1%} "
              f"({tk.so_anh_thanh_cong}/{tk.tong_so_anh})")
        print(f"  Tuân thủ prompt: {tk.ty_le_tuan_thu_prompt:.1%}")
        print(f"  Latency TB    : {tk.latency_trung_binh}s "
              f"(P50 {tk.latency_p50}s, P95 {tk.latency_p95}s)")
        print(f"  VRAM đỉnh     : {tk.vram_dinh_gb or '—'} GB")
        print(f"  Caption TB    : {tk.caption_tu_trung_binh} từ / "
              f"{tk.caption_ky_tu_trung_binh} ký tự")
        print(f"  Tổng thời gian: {time.perf_counter() - bat_dau:.1f}s\n")

        if args.stability:
            print("  Đang đo độ ổn định (10 ảnh × 3 lần)...")
            cac_lan = []
            for lan in range(3):
                kq_lan, _ = chay_mot_model(
                    model_key,
                    danh_sach_anh[:10],
                    thu_muc_ket_qua=args.out_dir / f"stability_{lan}",
                    backend=args.backend,
                    che_do_debug=False,
                    tiep_tuc=False,
                )
                cac_lan.append(kq_lan)
            tong_hop[model_key]["do_on_dinh"] = do_on_dinh(cac_lan)
            print(f"  {tong_hop[model_key]['do_on_dinh']}\n")

    dich = args.out_dir / "vlm_comparison_results.json"
    dich.write_text(
        json.dumps(
            {"moi_truong": moi_truong, "so_anh": len(danh_sach_anh), "ket_qua": tong_hop},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Đã lưu bảng số: {dich}")

    # sample_results.json — đề bài bắt buộc: JSON đầy đủ của từng ảnh, không
    # phải chỉ bảng tổng kết. Lấy từ checkpoint vì ở đó có nguyên kết quả.
    mau = _gom_sample_results(model_keys, args.out_dir)
    if mau:
        dich_mau = args.out_dir / "sample_results.json"
        dich_mau.write_text(json.dumps(mau, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Đã lưu {len(mau)} kết quả mẫu: {dich_mau}")

    return 0


def _gom_sample_results(model_keys: list[str], thu_muc: Path) -> list[dict]:
    """Gom kết quả từng ảnh của mọi model từ checkpoint thành một danh sách."""
    tat_ca: list[dict] = []
    for model_key in model_keys:
        checkpoint = load_checkpoint(thu_muc, model_key)
        for ten_anh, muc in checkpoint.get("da_xong", {}).items():
            ket_qua = muc.get("ket_qua")
            if not ket_qua:
                continue
            tat_ca.append({"image": ten_anh, "model": model_key, **ket_qua})
    return tat_ca


if __name__ == "__main__":
    raise SystemExit(main())
