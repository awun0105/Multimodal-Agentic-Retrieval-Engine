"""
Phép kiểm "vòng vo theo Ý" — bổ sung cho TTR (vòng vo theo CHUỖI).

TTR (type-token ratio, xem caption_defect_checks.tinh_ttr) chỉ thấy lặp
CHUỖI: tổng số từ khác nhau / tổng số từ. Đo thật cho thấy nó bỏ sót lặp Ý —
caption "Người giảng dạy đang giảng dạy tại Trung tâm học tập." có TTR = 0.818
(> ngưỡng 0.6, KHÔNG bị bắt) dù cụm "giảng dạy" lặp lại nguyên văn, vì các từ
khác ("đang", "tại", "Trung", "tâm"...) xen vào giữa kéo TTR ảo lên cao.

Tách file riêng (không nhồi vào caption_defect_checks.py) để giữ mỗi file
dưới 200 dòng — hai phép kiểm có cùng mục tiêu (bắt vòng vo) nhưng cơ chế
khác hẳn nhau, tách theo cơ chế cho dễ đọc/dễ chỉnh ngưỡng độc lập.
"""

from __future__ import annotations

import re

# Bỏ dấu câu dính cuối từ trước khi tách cụm — cùng lý do với tinh_ttr():
# nếu không, "giảng dạy." và "giảng dạy" (không dấu chấm) bị coi là khác cụm.
_DAU_CAU_CUOI_TU = re.compile(r"[.,;:!?]+$")

# Từ nối/hư từ phổ biến trong tiếng Việt — dùng để LỌC cụm trước khi đếm lặp.
# VÌ SAO cần lọc: nếu không, caption dài tự nhiên (lặp "của", "và", "trong"
# do câu nhiều mệnh đề) sẽ bị báo nhầm vòng vo dù nội dung không hề lặp ý.
# Chỉ cụm còn ít nhất MỘT từ có nghĩa (không phải toàn từ nối) mới tính là
# dấu hiệu vòng vo thật.
TU_NOI_PHO_BIEN = frozenset(
    {
        "của", "và", "trong", "với", "một", "các", "những", "là", "có",
        "được", "này", "đó", "cho", "tại", "trên", "dưới", "từ", "đến",
        "về", "khi", "đang", "sẽ", "đã", "rất", "cũng", "nhiều", "hơn",
    }
)

# Số cụm lặp / tổng số từ. Đếm TUYỆT ĐỐI số cụm lặp báo nhầm câu dài: một
# caption 40 từ nhắc lại "đại học" ở vế sau là hành văn bình thường, còn câu
# 11 từ lặp "giảng dạy" mới là vòng vo. Đo thật trên 8 caption có cụm lặp:
# 7 ca tự nhiên nằm trong 0.019-0.030, hai ca vòng vo thật ở 0.077 và 0.091 —
# khoảng trống giữa hai nhóm đủ rộng để 0.05 không phải con số chọn cho vừa.
NGUONG_MAT_DO_LAP = 0.05


def _tach_tu(caption: str) -> list[str]:
    tu = [_DAU_CAU_CUOI_TU.sub("", t) for t in caption.lower().split()]
    return [t for t in tu if t]


def cum_tu_lap(
    caption: str,
    *,
    n: int = 2,
    tu_noi: frozenset[str] = TU_NOI_PHO_BIEN,
) -> set[tuple[str, ...]]:
    """
    Tìm các cụm n-từ (mặc định bigram — cụm lặp ngắn nhất đã đủ để bắt kiểu
    "giảng dạy ... giảng dạy" mà không cần cụm dài hơn) xuất hiện >= 2 lần
    trong caption, sau khi loại cụm mà CẢ HAI từ đều là từ nối phổ biến.
    """
    tu = _tach_tu(caption)
    if len(tu) < n:
        return set()
    dem: dict[tuple[str, ...], int] = {}
    for i in range(len(tu) - n + 1):
        cum = tuple(tu[i : i + n])
        dem[cum] = dem.get(cum, 0) + 1
    return {c for c, so_lan in dem.items() if so_lan >= 2 and not all(t in tu_noi for t in c)}


def mat_do_lap(caption: str, *, n: int = 2) -> float:
    """Số cụm lặp trên mỗi từ của caption. Chuẩn hoá để câu dài không bị phạt oan."""
    tu = _tach_tu(caption)
    if not tu:
        return 0.0
    return len(cum_tu_lap(caption, n=n)) / len(tu)


def kiem_cum_lap(
    caption: str, *, n: int = 2, nguong_mat_do: float = NGUONG_MAT_DO_LAP
) -> bool:
    """True nếu mật độ cụm lặp vượt ngưỡng — bắt vòng vo mà TTR bỏ sót."""
    return mat_do_lap(caption, n=n) > nguong_mat_do
