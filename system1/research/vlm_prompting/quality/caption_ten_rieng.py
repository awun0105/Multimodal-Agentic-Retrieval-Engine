"""
Bắt caption chép TÊN RIÊNG người/tổ chức đọc được trong ảnh (biển tên, chữ trên
màn hình...) — biến thể của lỗi "nhét chữ OCR": model đọc chữ thay vì mô tả cảnh.

Vì sao cần: caption sinh ra dùng để huấn luyện + phục vụ tìm kiếm cảnh, không
phải để nhận dạng danh tính. Đo thật gặp "Thầy Trần Ngọc Anh", "Nguyễn Việt
Đăng Du" (tên giáo viên chép từ giới thiệu trên video) và "Đại học Sài Gòn",
"The Saigon International University" (tên trường chép từ biển hiệu) lọt vào
caption — vừa lộ dữ liệu cá nhân, vừa dạy model học sai việc (đọc chữ thay vì
tả cảnh: "một giáo viên nam", "một trường đại học quốc tế").

Tiếng Việt không có quy tắc viết hoa chặt như tiếng Anh (không viết hoa danh
từ chung), nên dùng ĐA TÍN HIỆU thay vì một heuristic mơ hồ duy nhất — mỗi
luật bắt một dạng câu cụ thể đã thấy trong dữ liệu thật.
"""

from __future__ import annotations

import re

from quality.caption_loader import CaptionRow

# Từ viết hoa xuất hiện tự nhiên trong mô tả CẢNH — không phải tên riêng người/
# tổ chức cần chặn. Địa danh phổ biến hợp lệ để tả bối cảnh ("một toà nhà ở Sài
# Gòn"). Không đầy đủ — mở rộng dần theo tiền lệ TU_MUON_MIEN_TRU trong
# caption_defect_checks.py khi gặp báo nhầm thật.
TU_VIET_HOA_HOP_LE: frozenset[str] = frozenset(
    {
        "Việt Nam",
        "Sài Gòn",
        "Hà Nội",
        "Đà Nẵng",
        "Huế",
        "Cần Thơ",
        "Hải Phòng",
    }
)

# Danh xưng thường đi trước tên riêng người. Không đầy đủ — mở rộng khi gặp
# danh xưng mới báo nhầm hoặc bỏ sót trong dữ liệu thật.
_DANH_XUNG = (
    "thầy",
    "cô",
    "giáo viên",
    "giảng viên",
    "ông",
    "bà",
    "anh",
    "chị",
    "bác sĩ",
    "tiến sĩ",
)

# Chữ hoa tiếng Việt phải LIỆT KÊ, không dùng dải [À-Ỹ]: trong bảng mã Unicode
# chữ hoa và thường có dấu nằm xen kẽ nhau, nên dải đó nuốt luôn chữ thường
# ("ệ", "ứ", "ọ"...). Đo thật: dải khiến "ệu ứng ánh" bị coi là 3 từ viết hoa,
# gây báo nhầm 26,67% trên 30 caption.
_CHU_HOA = (
    "A-Z"
    "ÀÁÂÃÈÉÊÌÍÒÓÔÕÙÚĂĐĨŨƠƯ"
    "ẠẢẤẦẨẪẬẮẰẲẴẶẸẺẼỀỀỂỄỆỈỊỌỎỐỒỔỖỘỚỜỞỠỢỤỦỨỪỬỮỰỲỴÝỶỸ"
)
_CHU_THUONG = (
    "a-z"
    "àáâãèéêìíòóôõùúăđĩũơư"
    "ạảấầẩẫậắằẳẵặẹẻẽềềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỵýỷỹ"
)
_TU_VIET_HOA = rf"[{_CHU_HOA}][{_CHU_THUONG}{_CHU_HOA}]*"

# Tín hiệu (a): cụm >=3 từ viết hoa chữ đầu liên tiếp, không nằm ở đầu câu.
# Ngưỡng 3 (không phải 2) để KHÔNG bắt oan địa danh 2 từ hợp lệ như "Việt Nam",
# "Sài Gòn" — tên người tiếng Việt thường có 3+ từ (họ, tên đệm, tên), tên tổ
# chức dài ("The Saigon International University") càng chắc chắn >=3 từ.
_CUM_VIET_HOA_LIEN_TIEP = re.compile(rf"(?:{_TU_VIET_HOA}\s+){{2,}}{_TU_VIET_HOA}")

# Tín hiệu (b): danh xưng + tên viết hoa (>=2 từ liên tiếp) ngay sau — bắt cả
# tên 2 từ ("cô Nguyễn Lan") mà tín hiệu (a) một mình có thể bỏ sót nếu tên chỉ
# vỏn vẹn 2 từ.
#
# KHÔNG dùng re.IGNORECASE: cờ đó làm [A-ZÀ-Ỹ] khớp luôn chữ thường, biến mọi
# câu tả cảnh bình thường ("giáo viên nam mặc áo xanh") thành danh xưng + tên
# riêng. Danh xưng viết hoa đầu câu ("Thầy", "Cô") xử lý riêng bằng nhóm chữ
# hoa/thường ở phần tử đầu, không cần cờ toàn cục.
_DANH_XUNG_HOA_THUONG = "|".join(
    f"[{d[0].upper()}{d[0]}]{re.escape(d[1:])}" for d in _DANH_XUNG
)
_DANH_XUNG_PATTERN = re.compile(
    rf"\b(?:{_DANH_XUNG_HOA_THUONG})\s+"
    rf"(?:{_TU_VIET_HOA}\s+){{1,}}{_TU_VIET_HOA}"
)


def _bo_cum_hop_le(text: str) -> str:
    """
    Xoá các cụm trong TU_VIET_HOA_HOP_LE khỏi text trước khi soi — tránh cụm
    hợp lệ ghép với từ viết hoa liền kề tạo thành chuỗi >=3 từ giả.

    Chỉ xoá khi cụm ĐỨNG RIÊNG: hai bên không có từ viết hoa nào khác. Xoá vô
    điều kiện sẽ cắt đứt tên tổ chức chứa địa danh ("Đại học Sài Gòn Quốc Tế"
    thành "Đại học  Quốc Tế"), làm lọt đúng loại tên cần bắt.
    """
    ket_qua = text
    for cum in TU_VIET_HOA_HOP_LE:
        # Bắt luôn từ viết hoa liền trước/sau (nếu có) rồi mới quyết định: có
        # từ nào kèm theo nghĩa là cụm nằm trong tên dài hơn, giữ nguyên.
        mau = re.compile(rf"({_TU_VIET_HOA}\s+)?{re.escape(cum)}(\s+{_TU_VIET_HOA})?")
        ket_qua = mau.sub(
            lambda m: m.group(0) if (m.group(1) or m.group(2)) else "", ket_qua
        )
    return ket_qua


def kiem_ten_rieng(text: str) -> bool:
    """
    True nếu phát hiện tên riêng người/tổ chức trong text.

    Tín hiệu (b) kiểm trước trên text gốc (danh xưng là bằng chứng mạnh, giữ
    nguyên cụm hợp lệ không ảnh hưởng). Tín hiệu (a) kiểm trên text đã bỏ cụm
    hợp lệ, và bỏ qua khớp ở đầu câu/đầu text (chữ hoa đầu câu không phải dấu
    hiệu tên riêng).
    """
    if _DANH_XUNG_PATTERN.search(text):
        return True

    da_loc = _bo_cum_hop_le(text)
    for match in _CUM_VIET_HOA_LIEN_TIEP.finditer(da_loc):
        if match.start() == 0:
            continue
        # Ký tự ngay trước cụm phải không phải đầu câu (sau dấu chấm/than/hỏi
        # hoặc chỉ là khoảng trắng nối từ đầu chuỗi) mới tính là giữa câu.
        truoc = da_loc[: match.start()].rstrip()
        if truoc and not truoc.endswith((".", "!", "?")):
            return True
    return False


def kiem_ten_rieng_trong_cac_truong(row: CaptionRow) -> bool:
    """Soi caption, doi_tuong, boi_canh, hanh_dong của một CaptionRow."""
    cac_truong = [row.caption, *row.doi_tuong, row.boi_canh, row.hanh_dong]
    return any(kiem_ten_rieng(truong) for truong in cac_truong if truong)
