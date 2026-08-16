"""
Bắt caption lẫn ký tự của ngôn ngữ khác (Hán/Nhật/Hàn/Cyrillic...).

Vì sao cần: Qwen2-VL huấn luyện phần lớn trên tiếng Trung. Khi gặp từ khó diễn
đạt, model rơi về tiếng mẹ đẻ giữa chừng câu tiếng Việt. Đo thật trên 79 caption
của Qwen2-VL-2B: 2 caption dính (027.jpg, 306.jpg) — VD "Một bức ảnh模糊 của một
tòa nhà trắng". Ba phép kiểm cũ (chép few-shot / nhét OCR / vòng vo) đều không
bắt được vì caption vẫn đúng ngữ pháp và đủ dài.

Tách file riêng thay vì nhồi vào caption_defect_checks.py: file đó đã 199 dòng,
sát ngưỡng 200 của repo.
"""

from __future__ import annotations

# Các dải Unicode KHÔNG bao giờ xuất hiện trong tiếng Việt viết đúng.
# Không liệt kê Latin mở rộng vì tiếng Việt dùng chung dải đó (ă, ơ, ế...).
_DAI_NGOAI_LAI: tuple[tuple[int, int, str], ...] = (
    (0x4E00, 0x9FFF, "Hán"),
    (0x3400, 0x4DBF, "Hán mở rộng"),
    (0x3040, 0x309F, "Hiragana"),
    (0x30A0, 0x30FF, "Katakana"),
    (0xAC00, 0xD7AF, "Hangul"),
    (0x0400, 0x04FF, "Cyrillic"),
    (0x0600, 0x06FF, "Ả Rập"),
    (0x0E00, 0x0E7F, "Thái"),
)


def tim_ky_tu_la(caption: str) -> list[tuple[str, str]]:
    """Trả về [(ký tự, tên hệ chữ)] cho mọi ký tự ngoài hệ chữ tiếng Việt."""
    thay: list[tuple[str, str]] = []
    for ky_tu in caption:
        ma = ord(ky_tu)
        for dau, cuoi, ten in _DAI_NGOAI_LAI:
            if dau <= ma <= cuoi:
                thay.append((ky_tu, ten))
                break
    return thay


def kiem_ngon_ngu_la(caption: str, *, so_ky_tu_toi_thieu: int = 1) -> bool:
    """
    True khi caption chứa từ `so_ky_tu_toi_thieu` ký tự ngoại lai trở lên.

    Mặc định 1 vì chỉ một chữ Hán lọt vào cũng đủ làm hỏng caption — tìm kiếm
    bằng tiếng Việt sẽ không bao giờ khớp phần đó.
    """
    return len(tim_ky_tu_la(caption)) >= so_ky_tu_toi_thieu
