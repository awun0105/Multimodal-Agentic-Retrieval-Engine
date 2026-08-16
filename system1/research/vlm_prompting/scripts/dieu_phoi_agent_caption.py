"""
Điều phối spawn agent Haiku sinh caption, gom kết quả về checkpoint chuẩn.

RANH GIỚI QUAN TRỌNG: script Python này KHÔNG tự gọi được công cụ Agent —
đó là công cụ chỉ agent điều phối (Claude Code đang chạy phiên) mới gọi được.
Script chỉ làm hai việc:
  1. Chuẩn bị prompt cho từng lô ảnh (`--in-prompt`) để agent điều phối copy
     vào lời gọi Agent(subagent_type="general-purpose", model="haiku").
  2. Gom mảng JSON mà agent con trả về, validate, ghi vào checkpoint.
Việc spawn agent thật sự nằm ngoài script này — do agent điều phối thực hiện
thủ công giữa hai bước trên.

Không import torch/transformers, không import vlm.adapters/vlm.generate/
vlm.model_loader — máy chạy script này không có torch cho Python 3.14.
`liet_ke_anh` KHÔNG import từ scripts/benchmark_runner.py như audit ban đầu
đề xuất, vì benchmark_runner.py kéo theo vlm.adapters ở top-level (torch).
Bản sao tối giản dưới đây giữ nguyên logic gốc (cùng DUOI_ANH, cùng rglob).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

if sys.platform.startswith("win"):
    for _luong in (sys.stdout, sys.stderr):
        try:
            _luong.reconfigure(encoding="utf-8")
        except (AttributeError, OSError):
            pass

GOC = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(GOC))

from scripts.checkpoint_utils import (  # noqa: E402
    filter_pending,
    load_checkpoint,
    save_checkpoint,
)
from scripts.chon_anh_train import (  # noqa: E402
    chon_anh_rai_deu,
    ghi_danh_sach_anh,
    tach_train_holdout,
)
from scripts.loc_anh_hong import loc_danh_sach_anh  # noqa: E402
from scripts.prompt_agent_thay import KICH_THUOC_LO_MAC_DINH, PROMPT_THAY  # noqa: E402
from vlm.json_utils import JsonParseError, parse_json_safe  # noqa: E402
from vlm.schema import KeyframeMetadata  # noqa: E402

# Giữ đồng bộ với scripts/benchmark_runner.py:46 — không import trực tiếp vì
# benchmark_runner kéo theo vlm.adapters (torch), xem docstring đầu file.
DUOI_ANH = (".jpg", ".jpeg", ".png", ".webp", ".bmp")

MODEL_KEY_MAC_DINH = "haiku-teacher"


def liet_ke_anh(thu_muc: Path) -> list[Path]:
    if not thu_muc.exists():
        return []
    return sorted(p for p in thu_muc.rglob("*") if p.suffix.lower() in DUOI_ANH)


def chia_lo(danh_sach: list, kich_thuoc: int) -> list[list]:
    """Cắt list thành list các list, lô cuối được phép ngắn hơn kich_thuoc."""
    if kich_thuoc <= 0:
        raise ValueError(f"kich_thuoc phải > 0, nhận {kich_thuoc}")
    return [danh_sach[i : i + kich_thuoc] for i in range(0, len(danh_sach), kich_thuoc)]


def tao_prompt_cho_lo(danh_sach_anh: list[Path]) -> str:
    """Ghép PROMPT_THAY với đường dẫn tuyệt đối của từng ảnh trong lô."""
    duong_dan_tuyet_doi = "\n".join(str(Path(p).resolve()) for p in danh_sach_anh)
    return PROMPT_THAY + duong_dan_tuyet_doi


def _trich_mang_can_bang(text: str) -> str | None:
    """
    Tìm mảng JSON [...] cân bằng ngoặc đầu tiên trong text.

    vlm.json_utils._trich_ngoac_can_bang chỉ tìm cặp {} nên không dùng lại
    được — agent thầy trả về mảng ở ngoài cùng, không phải object đơn.
    """
    vi_tri_mo = text.find("[")
    if vi_tri_mo == -1:
        return None

    do_sau = 0
    trong_chuoi = False
    thoat_ky_tu = False

    for i in range(vi_tri_mo, len(text)):
        ky_tu = text[i]

        if thoat_ky_tu:
            thoat_ky_tu = False
            continue
        if ky_tu == "\\":
            thoat_ky_tu = True
            continue
        if ky_tu == '"':
            trong_chuoi = not trong_chuoi
            continue
        if trong_chuoi:
            continue

        if ky_tu == "[":
            do_sau += 1
        elif ky_tu == "]":
            do_sau -= 1
            if do_sau == 0:
                return text[vi_tri_mo : i + 1]

    return None


def _parse_mang_json(text_agent: str) -> list[dict]:
    """
    Bóc mảng JSON ra khỏi output thô của agent thầy.

    Agent trả về MẢNG, còn vlm.json_utils.parse_json_safe chỉ trả dict —
    không dùng thẳng được (xem docstring module). Thử json.loads trực tiếp
    trước, sau đó bóc rào ```json, cuối cùng quét ngoặc [] cân bằng thủ công.
    """
    import json
    import re

    text = text_agent.strip()

    try:
        gia_tri = json.loads(text)
        if isinstance(gia_tri, list):
            return gia_tri
        if isinstance(gia_tri, dict):
            return [gia_tri]
    except (json.JSONDecodeError, TypeError):
        pass

    fence_pattern = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)
    for khoi in fence_pattern.findall(text):
        try:
            gia_tri = json.loads(khoi.strip())
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(gia_tri, list):
            return gia_tri
        if isinstance(gia_tri, dict):
            return [gia_tri]

    doan_mang = _trich_mang_can_bang(text)
    if doan_mang:
        try:
            gia_tri = json.loads(doan_mang)
            if isinstance(gia_tri, list):
                return gia_tri
        except (json.JSONDecodeError, TypeError):
            pass

    raise JsonParseError(
        f"Không tìm thấy mảng JSON hợp lệ trong output agent (dài {len(text_agent)} ký tự)",
        text_agent,
    )


def gom_ket_qua_agent(
    text_agent: str, ten_anh_mong_doi: list[str]
) -> tuple[dict, list[str]]:
    """
    Parse mảng JSON agent trả về, validate từng phần tử, đối chiếu ảnh thiếu.

    Trả về (ket_qua, ten_anh_thua):
      - ket_qua: {ten_anh: {"thanh_cong": bool, "ket_qua": dict|None, "loi": str|None}}
        CHỈ chứa ảnh trong ten_anh_mong_doi — đúng hình checkpoint hiện có,
        không đổi (quality/caption_loader.py đọc thẳng hình này).
      - ten_anh_thua: tên ảnh agent trả về nhưng KHÔNG có trong ten_anh_mong_doi.
        Trước đây bị bỏ qua âm thầm — giờ trả ra ngoài để caller in cảnh báo,
        vì agent từng trả thêm ảnh không được giao (xem lỗi 2 trong yêu cầu).
    Lỗi validate một ảnh KHÔNG làm hỏng cả lô — chỉ đánh dấu ảnh đó thất bại.
    """
    ket_qua: dict[str, dict] = {}
    tap_mong_doi = set(ten_anh_mong_doi)

    try:
        danh_sach_muc = _parse_mang_json(text_agent)
    except JsonParseError as loi:
        for ten_anh in ten_anh_mong_doi:
            ket_qua[ten_anh] = {
                "thanh_cong": False,
                "ket_qua": None,
                "loi": f"không parse được JSON agent trả về: {loi}",
            }
        return ket_qua, []

    da_xu_ly: set[str] = set()
    ten_anh_thua: list[str] = []
    for muc in danh_sach_muc:
        if not isinstance(muc, dict):
            continue
        ten_anh = str(muc.get("ten_anh", "")).strip()
        if not ten_anh:
            continue

        if ten_anh not in tap_mong_doi:
            ten_anh_thua.append(ten_anh)
            continue

        da_xu_ly.add(ten_anh)

        try:
            metadata = KeyframeMetadata(**{k: v for k, v in muc.items() if k != "ten_anh"})
        except Exception as loi:  # pydantic.ValidationError + lỗi ép kiểu khác
            ket_qua[ten_anh] = {"thanh_cong": False, "ket_qua": None, "loi": str(loi)}
            continue

        ket_qua[ten_anh] = {
            "thanh_cong": True,
            "ket_qua": metadata.model_dump(),
            "loi": None,
        }

    for ten_anh in ten_anh_mong_doi:
        if ten_anh not in da_xu_ly:
            ket_qua[ten_anh] = {
                "thanh_cong": False,
                "ket_qua": None,
                "loi": "agent bỏ sót",
            }

    return ket_qua, ten_anh_thua


def ghi_lo_vao_checkpoint(thu_muc: Path, model_key: str, ket_qua_lo: dict) -> Path:
    """Merge kết quả một lô vào checkpoint cũ rồi ghi lại — gọi sau MỖI lô."""
    checkpoint = load_checkpoint(thu_muc, model_key)
    checkpoint["da_xong"].update(ket_qua_lo)
    return save_checkpoint(thu_muc, model_key, checkpoint)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Chuan bi prompt cho agent thay va gom ket qua caption vao checkpoint."
    )
    parser.add_argument("--thu-muc-anh", type=Path, default=Path("data/keyframes_aic"))
    parser.add_argument("--out-dir", type=Path, default=Path("results"))
    parser.add_argument("--model-key", type=str, default=MODEL_KEY_MAC_DINH)
    parser.add_argument("--kich-thuoc-lo", type=int, default=KICH_THUOC_LO_MAC_DINH)
    parser.add_argument(
        "--in-prompt",
        action="store_true",
        help="Chi in prompt cua tung lo roi thoat, khong spawn agent (script khong tu spawn duoc).",
    )
    parser.add_argument(
        "--so-luong",
        type=int,
        default=None,
        help="Chon N anh rai deu tu thu muc thay vi lay tat ca.",
    )
    parser.add_argument(
        "--so-holdout",
        type=int,
        default=0,
        help="Tach M anh rai deu giu lai (khong dua vao vong lap sinh caption).",
    )
    parser.add_argument(
        "--ghi-danh-sach",
        action="store_true",
        help="Xuat results/danh_sach_anh_train.txt + danh_sach_anh_holdout.txt.",
    )
    parser.add_argument(
        "--loc-anh-hong",
        dest="loc_anh_hong",
        action="store_true",
        default=True,
        help="Loc anh trang/hong bang bien do sang truoc khi chia lo (mac dinh BAT).",
    )
    parser.add_argument(
        "--khong-loc-anh-hong",
        dest="loc_anh_hong",
        action="store_false",
        help="Tat loc anh hong, dua het anh vao vong lap nhu cu.",
    )
    args = parser.parse_args()

    danh_sach_anh = liet_ke_anh(args.thu_muc_anh)

    if args.loc_anh_hong:
        danh_sach_anh, anh_hong = loc_danh_sach_anh(danh_sach_anh)
        if anh_hong:
            print(f"Da loai {len(anh_hong)} anh hong (bien do sang qua thap):")
            for duong_dan in anh_hong:
                print(f"  - {duong_dan.name}")

    if args.so_luong is not None:
        danh_sach_anh = chon_anh_rai_deu(danh_sach_anh, args.so_luong)

    danh_sach_anh, holdout = tach_train_holdout(danh_sach_anh, args.so_holdout)

    if args.ghi_danh_sach:
        ghi_danh_sach_anh(args.out_dir / "danh_sach_anh_train.txt", danh_sach_anh)
        ghi_danh_sach_anh(args.out_dir / "danh_sach_anh_holdout.txt", holdout)

    checkpoint = load_checkpoint(args.out_dir, args.model_key)
    ten_tat_ca = [p.name for p in danh_sach_anh]
    ten_con_lai = set(filter_pending(ten_tat_ca, checkpoint))
    anh_con_lai = [p for p in danh_sach_anh if p.name in ten_con_lai]

    cac_lo = chia_lo(anh_con_lai, args.kich_thuoc_lo)

    if args.in_prompt:
        for idx, lo in enumerate(cac_lo, start=1):
            print(f"=== LO {idx}/{len(cac_lo)} ({len(lo)} anh) ===")
            print(tao_prompt_cho_lo(lo))
            print()
        return

    print(
        f"{len(anh_con_lai)} anh con lai, chia thanh {len(cac_lo)} lo. "
        "Dung --in-prompt de lay prompt spawn agent."
    )


if __name__ == "__main__":
    main()
