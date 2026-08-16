"""
Chọn ảnh rải đều cho tập train + tách tập giữ lại (holdout) cho Phase 05.

Tách khỏi scripts/dieu_phoi_agent_caption.py (Phase 01, 255 dòng) để giữ file
đó dưới mốc 200 dòng của CLAUDE.md — trách nhiệm khác nhau: file kia điều phối
spawn/gom checkpoint, file này chỉ chọn ảnh trước khi vòng lặp bắt đầu.
dieu_phoi_agent_caption.py import lại các hàm này nên hành vi CLI không đổi.

Không import torch/transformers — chỉ dùng pathlib/stdlib.
"""

from __future__ import annotations

from pathlib import Path


def chon_anh_rai_deu(danh_sach: list[Path], so_luong: int) -> list[Path]:
    """
    Chọn so_luong ảnh rải đều trên danh_sach đã sắp xếp, dùng bước nhảy đều.

    Vì sao rải đều thay vì lấy N ảnh đầu: keyframe liền kề thường cùng một
    cảnh quay — lấy liền kề thì tập mẫu chỉ đại diện vài cảnh, không đại
    diện cả kho.
    """
    if so_luong <= 0:
        return []
    if so_luong >= len(danh_sach):
        return list(danh_sach)

    buoc_nhay = len(danh_sach) / so_luong
    chi_so = sorted({int(i * buoc_nhay) for i in range(so_luong)})
    # set() có thể làm rơi vài chỉ số trùng ở phần dư của phép chia — bù thêm
    # từ cuối danh sách (chưa được chọn) để giữ đúng so_luong.
    da_chon = set(chi_so)
    i = len(danh_sach) - 1
    while len(chi_so) < so_luong and i >= 0:
        if i not in da_chon:
            chi_so.append(i)
            da_chon.add(i)
        i -= 1
    chi_so = sorted(chi_so)
    return [danh_sach[i] for i in chi_so]


def tach_train_holdout(
    danh_sach: list[Path], so_holdout: int
) -> tuple[list[Path], list[Path]]:
    """
    Tách danh_sach thành (train, holdout) không giao nhau.

    Holdout cũng rải đều (không lấy N ảnh cuối) — cùng lý do với
    chon_anh_rai_deu: ảnh cuối liền kề nhau thường cùng một cảnh quay.
    """
    if so_holdout <= 0:
        return list(danh_sach), []
    if so_holdout >= len(danh_sach):
        raise ValueError(
            f"so_holdout ({so_holdout}) >= tong so anh ({len(danh_sach)}), "
            "tap train se rong — khong con gi de train."
        )

    holdout = chon_anh_rai_deu(danh_sach, so_holdout)
    tap_holdout = set(holdout)
    train = [anh for anh in danh_sach if anh not in tap_holdout]
    return train, holdout


def ghi_danh_sach_anh(duong_dan: Path, danh_sach: list[Path]) -> Path:
    """
    Ghi mỗi tên ảnh (không phải đường dẫn đầy đủ) một dòng.

    Ghi tên để so sánh được với khóa checkpoint (khóa checkpoint là tên ảnh,
    xem checkpoint_utils.py + gom_ket_qua_agent()).
    """
    duong_dan = Path(duong_dan)
    duong_dan.parent.mkdir(parents=True, exist_ok=True)
    noi_dung = "\n".join(Path(anh).name for anh in danh_sach)
    duong_dan.write_text(noi_dung + ("\n" if danh_sach else ""), encoding="utf-8")
    return duong_dan
