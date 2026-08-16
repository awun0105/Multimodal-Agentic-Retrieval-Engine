"""
Đo self-retrieval recall bằng BM25 — thước không cần đáp án chuẩn.

Ý tưởng: coi mỗi caption là một "tài liệu". Lấy chính caption của ảnh X làm
câu truy vấn, tìm trong kho xem caption nào khớp nhất. Caption tốt (mô tả
riêng biệt cho ảnh đó) thì tự nó phải xếp hạng 1. Caption chung chung
("người đang giảng dạy") thì hàng chục caption khác cũng khớp ngang → tụt hạng.

Không cần nhãn đúng/sai từ con người — đây là lý do chọn cách này khi
chưa có ground truth. Đổi lại: chỉ so sánh được TƯƠNG ĐỐI giữa hai bộ
caption, không có mốc "bao nhiêu là đủ tốt" tuyệt đối (xem README).
"""

from __future__ import annotations

from dataclasses import dataclass

from rank_bm25 import BM25Okapi

from quality.caption_loader import CaptionRow


def _tach_tu(text: str) -> list[str]:
    """
    Tách từ tiếng Việt thô: hạ chữ thường + tách theo khoảng trắng.

    Không dùng thư viện tách từ nặng (underthesea, pyvi...) — bộ đo này chỉ
    so sánh TƯƠNG ĐỐI giữa hai phiên bản prompt trên cùng một cách tách từ,
    sai số hệ thống do tách thô sẽ triệt tiêu khi so sánh. Kéo thư viện nặng
    vào là over-engineering (YAGNI) cho mục đích này.
    """
    return text.lower().split()


@dataclass
class KetQuaRecall:
    """Kết quả đo self-retrieval trên một bộ caption."""

    so_caption: int
    recall_tai_1: float
    recall_tai_5: float
    recall_tai_10: float
    mrr: float
    hang_tung_anh: dict[str, int]  # ten_anh -> hạng của chính nó (1 = tốt nhất)


def do_self_retrieval(rows: list[CaptionRow]) -> KetQuaRecall:
    """
    Dựng chỉ mục BM25 từ toàn bộ caption, rồi lần lượt lấy mỗi caption làm
    truy vấn tìm trong chính chỉ mục đó. Hạng của tài liệu trùng ten_anh với
    câu truy vấn là con số cần đo.

    Cần >= 2 caption để so sánh có ý nghĩa (1 caption thì luôn recall@1 = 1.0
    một cách vô nghĩa vì không có gì để phân biệt).
    """
    if len(rows) < 2:
        return KetQuaRecall(
            so_caption=len(rows),
            recall_tai_1=0.0,
            recall_tai_5=0.0,
            recall_tai_10=0.0,
            mrr=0.0,
            hang_tung_anh={},
        )

    kho_tu = [_tach_tu(r.caption) for r in rows]
    bm25 = BM25Okapi(kho_tu)

    dung_hang_1 = 0
    dung_hang_5 = 0
    dung_hang_10 = 0
    tong_nghich_dao_hang = 0.0
    hang_tung_anh: dict[str, int] = {}

    for i, row in enumerate(rows):
        diem = bm25.get_scores(kho_tu[i])
        # Sắp giảm dần theo điểm; ổn định để bằng điểm thì giữ thứ tự gốc.
        thu_tu = sorted(range(len(rows)), key=lambda j: -diem[j])
        hang = thu_tu.index(i) + 1  # hạng 1-based

        hang_tung_anh[row.ten_anh] = hang
        tong_nghich_dao_hang += 1.0 / hang
        if hang <= 1:
            dung_hang_1 += 1
        if hang <= 5:
            dung_hang_5 += 1
        if hang <= 10:
            dung_hang_10 += 1

    n = len(rows)
    return KetQuaRecall(
        so_caption=n,
        recall_tai_1=round(dung_hang_1 / n, 4),
        recall_tai_5=round(dung_hang_5 / n, 4),
        recall_tai_10=round(dung_hang_10 / n, 4),
        mrr=round(tong_nghich_dao_hang / n, 4),
        hang_tung_anh=hang_tung_anh,
    )
