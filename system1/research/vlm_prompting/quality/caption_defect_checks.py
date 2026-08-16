"""
Ba phép kiểm lỗi caption tự động — không cần LLM, không cần GPU.

Khác với `vlm/schema.py` (chặn LÚC SINH: một caption sai → ném lỗi ngay),
ba phép kiểm này chấm LÚC RÀ SOÁT HÀNG LOẠT: chạy trên N caption đã sinh
xong, thống kê bao nhiêu % dính lỗi nào. Hai vòng đời khác nhau nên tách
file riêng, không nhồi vào schema.py.

Mọi ngưỡng là tham số có giá trị mặc định — hiệu chỉnh sau khi có caption
thật (xem README, mục "Nhịp B"), không chép cứng vào logic.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from quality.caption_loader import CaptionRow
from quality.caption_ngon_ngu_la import kiem_ngon_ngu_la
from quality.caption_repetition import kiem_cum_lap
from quality.caption_ten_rieng import kiem_ten_rieng_trong_cac_truong

# Không `from vlm.prompts import _VI_DU_MAU` trực tiếp: import gói `vlm`
# chạy `vlm/__init__.py`, mà file đó kéo theo model_loader/adapters — hai
# module có phụ thuộc GPU nặng mà quality/ phải chạy thuần CPU không có.
# Nạp thẳng module prompts.py bằng importlib, bỏ qua __init__.py của gói vlm.
_PROMPTS_PATH = Path(__file__).resolve().parent.parent / "vlm" / "prompts.py"
_spec = importlib.util.spec_from_file_location("_vlm_prompts_only", _PROMPTS_PATH)
_prompts_module = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("_vlm_prompts_only", _prompts_module)
_spec.loader.exec_module(_prompts_module)
_VI_DU_MAU = _prompts_module._VI_DU_MAU

# Ví dụ mẫu của các phiên bản prompt ĐỜI TRƯỚC (trước prompt_version hiện tại).
# VÌ SAO phải giữ: caption đã sinh ra bằng prompt cũ (v1 dùng ví dụ "xe máy/áo
# mưa đỏ" lấy nguyên từ đề bài — xem git log vlm/prompts.py, commit trước
# b0125fa) vẫn còn nằm trong checkpoint cũ và vẫn cần chấm lại được. Nếu chỉ so
# với _VI_DU_MAU hiện tại (v2, cảnh bếp), caption chép ví dụ v1 sẽ lọt qua —
# đúng lỗi đã xảy ra thật với 001.jpg trong results/checkpoint_qwen2vl-2b-mau5.json.
# Thêm phiên bản mới vào đây khi prompts.py đổi _VI_DU_MAU lần nữa.
VI_DU_MAU_CU: tuple[str, ...] = (
    # v1 — ví dụ lấy nguyên từ đề bài (cảnh giao thông, xe máy/áo mưa đỏ).
    "Một người đàn ông mặc áo mưa đỏ đang chạy xe máy qua đoạn đường ngập "
    "nước dưới cơn mưa tầm tã.",
)

# Từ mượn phổ biến không có dấu tiếng Việt nhưng vẫn hợp lệ trong doi_tuong.
# Không đầy đủ — mở rộng dần khi gặp trường hợp thật báo nhầm (xem Rủi ro
# trong phase file: "Phép kiểm OCR báo nhầm từ mượn").
TU_MUON_MIEN_TRU = frozenset(
    {
        "laptop",
        "ti vi",
        "tivi",
        "radio",
        "internet",
        "wifi",
        "smartphone",
        "tablet",
        "video",
        "camera",
        "micro",
        "loa",
        "remote",
        "USB",
        "email",
        "web",
        "app",
        "bus",
        "taxi",
        "xe bus",
    }
)

_CO_DAU_TIENG_VIET = re.compile(
    r"[àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡ"
    r"ùúụủũưừứựửữỳýỵỷỹđ]",
    re.IGNORECASE,
)

# Phần tử doi_tuong đang MÔ TẢ CHUỖI CHỮ đọc từ ảnh (OCR) thay vì tên vật thể.
# Dấu hiệu 1: chuỗi trong dấu nháy đơn/kép — "chữ 'THANHNIEN' màu xanh lam".
_CHUOI_TRONG_NHAY = re.compile(r"['\"]([^'\"]{2,})['\"]")

# Dấu hiệu 2: cụm CHỮ IN HOA TOÀN BỘ dài >=4 ký tự — "THANHNIEN", "SAIGON".
# Ngưỡng 4 (không phải 3) để tránh bắt oan viết tắt phổ biến 3 ký tự (TV, PC...).
_CHU_HOA_TOAN_BO = re.compile(r"\b[A-ZÀ-Ỹ]{4,}\b")


def kiem_doi_tuong_la_chuoi_chu(doi_tuong: list[str]) -> bool:
    """
    True nếu có phần tử doi_tuong đang mô tả NỘI DUNG CHỮ đọc từ ảnh (OCR)
    thay vì tên vật thể — VD "chữ 'THANHNIEN' màu xanh lam". Bổ sung cho
    kiem_nhet_chu_ocr (bắt kiểu phần tử toàn từ tiếng Anh không dấu) — hai
    phép kiểm bắt hai dạng nhét OCR khác nhau, giữ cả hai vì đo thật cho thấy
    001.jpg lọt qua phép kiểm không dấu do phần tử có dấu tiếng Việt xen vào
    ("chữ", "màu", "xanh").

    ⚠️ Không bắt "biển hiệu đại học", "laptop Dell" — đó là tên VẬT MANG CHỮ /
    thương hiệu, không phải mô tả nội dung chữ.
    """
    for x in doi_tuong:
        if _CHUOI_TRONG_NHAY.search(x) or _CHU_HOA_TOAN_BO.search(x):
            return True
    return False


@dataclass
class KetQuaKiemLoi:
    """Kết quả 4 phép kiểm trên một caption."""

    ten_anh: str
    chep_few_shot: bool
    nhet_chu_ocr: bool
    vong_vo: bool
    ttr: float
    ngon_ngu_la: bool = False

    @property
    def co_loi(self) -> bool:
        return (
            self.chep_few_shot or self.nhet_chu_ocr or self.vong_vo or self.ngon_ngu_la
        )


def _n_gram(tu: list[str], n: int) -> set[tuple[str, ...]]:
    if len(tu) < n:
        return set()
    return {tuple(tu[i : i + n]) for i in range(len(tu) - n + 1)}


def kiem_chep_few_shot(caption: str, *, n: int = 8) -> bool:
    """
    So n-gram (theo từ, n=8 mặc định) giữa caption và mọi ví dụ mẫu từng dùng
    (`_VI_DU_MAU` hiện tại GỘP `VI_DU_MAU_CU`) — không chỉ bản hiện tại, vì
    caption đang chấm có thể đã được sinh bằng một phiên bản prompt cũ hơn.
    Model hay chép nguyên câu ví dụ khi gặp ảnh khó xử lý — đây là cách bắt
    cụ thể hơn "trông giống ví dụ", tránh cảm tính.

    n=5 (giá trị cũ) bắt oan cụm mở đầu thông dụng tiếng Việt (VD "Một người
    đàn ông mặc áo...") — đo thật trên 30 caption cho 10% dương tính giả.
    n=8 vẫn đủ dài để bắt chép nguyên câu, nhưng vượt quá độ dài cụm mở đầu
    thông dụng thường gặp.
    """
    tu_caption = caption.lower().split()
    ngram_caption = _n_gram(tu_caption, n)
    for mau in (_VI_DU_MAU, *VI_DU_MAU_CU):
        tu_mau = mau.lower().split()
        if ngram_caption & _n_gram(tu_mau, n):
            return True
    return False


def kiem_nhet_chu_ocr(
    doi_tuong: list[str], *, nguong_ty_le: float = 0.5, tu_mien_tru: frozenset[str] = TU_MUON_MIEN_TRU
) -> bool:
    """
    Đếm phần tử trong doi_tuong KHÔNG có dấu tiếng Việt và KHÔNG nằm trong
    danh sách từ mượn miễn trừ. Model đôi khi nhét chữ đọc được trong ảnh
    (OCR) vào doi_tuong thay vì mô tả vật thể — ví dụ ["enjoy","admit",...].

    ⚠️ Từ như "laptop", "ti vi" không dấu nhưng vẫn là từ tiếng Việt hợp lệ.
    Không có danh sách miễn trừ sẽ báo nhầm hàng loạt (xem TU_MUON_MIEN_TRU).
    """
    if not doi_tuong:
        return False
    khong_dau = [
        x for x in doi_tuong if not _CO_DAU_TIENG_VIET.search(x) and x.strip().lower() not in tu_mien_tru
    ]
    return (len(khong_dau) / len(doi_tuong)) > nguong_ty_le


_DAU_CAU_CUOI_TU = re.compile(r"[.,;:!?]+$")


def tinh_ttr(caption: str) -> float:
    """
    Type-token ratio = số từ khác nhau / tổng số từ. Thấp = lặp từ, vòng vo.

    Bỏ dấu câu dính ở cuối mỗi từ trước khi so — nếu không, "giảng dạy" và
    "giảng dạy." bị tính là hai từ khác nhau, làm TTR ảo cao hơn thực tế
    (dấu chấm cuối câu luôn dính đúng 1 lần nên chỉ lệch nhẹ, nhưng đủ để
    một caption lặp từ rõ ràng lọt qua ngưỡng).
    """
    tu = [_DAU_CAU_CUOI_TU.sub("", t) for t in caption.lower().split()]
    tu = [t for t in tu if t]
    if not tu:
        return 1.0
    return len(set(tu)) / len(tu)


# TTR ở trên chỉ thấy lặp CHUỖI (tổng số từ khác nhau / tổng số từ), không
# thấy lặp Ý NGHĨA — đo thật cho thấy "Người giảng dạy đang giảng dạy tại
# Trung tâm học tập." có TTR = 0.818 (> ngưỡng 0.6, KHÔNG bị bắt) dù cụm
# "giảng dạy" lặp lại nguyên văn, vì các từ khác xen vào giữa ("đang", "tại",
# "Trung", "tâm"...) kéo TTR ảo lên cao. kiem_cum_lap (caption_repetition.py)
# bắt bổ sung kiểu lặp này bằng cách đếm cụm 2-3 từ liền nhau xuất hiện >= 2
# lần, có lọc từ nối để tránh báo nhầm câu dài tự nhiên.
def kiem_vong_vo(caption: str, *, nguong_ttr: float = 0.6, n_gram_lap: int = 2) -> bool:
    """
    Vòng vo nếu TTR < ngưỡng (lặp CHUỖI, VD 'giảng dạy giảng dạy giảng dạy')
    HOẶC có cụm từ mang nghĩa lặp lại (lặp Ý, VD 'giảng dạy ... giảng dạy'
    xen từ khác ở giữa). Giữ nguyên TTR — không thay thế — vì hai phép kiểm
    bắt hai kiểu vòng vo khác nhau, bỏ cái nào cũng lọt lỗi.
    """
    return tinh_ttr(caption) < nguong_ttr or kiem_cum_lap(caption, n=n_gram_lap)


def kiem_mot_caption(
    row: CaptionRow,
    *,
    n_gram_few_shot: int = 8,
    nguong_ty_le_ocr: float = 0.5,
    nguong_ttr: float = 0.6,
    n_gram_lap: int = 2,
    tu_mien_tru: frozenset[str] = TU_MUON_MIEN_TRU,
) -> KetQuaKiemLoi:
    """
    Chạy cả 4 phép kiểm trên một CaptionRow, ngưỡng truyền qua tham số.

    ngon_ngu_la và nhet_chu_ocr soi CẢ row.caption LẪN row.doi_tuong (và
    mau_sac/hanh_dong/boi_canh cho ngon_ngu_la) — đo thật cho thấy bộ chấm cũ
    chỉ soi caption nên bỏ sót 047.jpg (chữ Hàn lẫn trong doi_tuong).

    kiem_ten_rieng_trong_cac_truong gộp vào nhet_chu_ocr thay vì thêm cờ mới:
    cùng bản chất "chép chữ đọc được từ ảnh" (tên người/tên trường đọc từ biển
    hiệu, giới thiệu trên màn hình) — không phải một dạng lỗi khác. Thêm cờ
    thứ 5 vào KetQuaKiemLoi sẽ phải sửa cả CLI danh_gia_chat_luong.py (in đúng
    4 dòng tỷ lệ) lẫn mọi báo cáo cũ đang giả định 4 cờ.
    """
    cac_truong_ngon_ngu = [row.caption, *row.doi_tuong, *row.mau_sac, row.hanh_dong, row.boi_canh]
    return KetQuaKiemLoi(
        ten_anh=row.ten_anh,
        chep_few_shot=kiem_chep_few_shot(row.caption, n=n_gram_few_shot),
        nhet_chu_ocr=(
            kiem_nhet_chu_ocr(row.doi_tuong, nguong_ty_le=nguong_ty_le_ocr, tu_mien_tru=tu_mien_tru)
            or kiem_doi_tuong_la_chuoi_chu(row.doi_tuong)
            or kiem_ten_rieng_trong_cac_truong(row)
        ),
        vong_vo=kiem_vong_vo(row.caption, nguong_ttr=nguong_ttr, n_gram_lap=n_gram_lap),
        ttr=round(tinh_ttr(row.caption), 4),
        ngon_ngu_la=any(kiem_ngon_ngu_la(truong) for truong in cac_truong_ngon_ngu if truong),
    )


def kiem_hang_loat(rows: list[CaptionRow], **kwargs) -> list[KetQuaKiemLoi]:
    """Chạy `kiem_mot_caption` trên toàn bộ danh sách, giữ nguyên thứ tự vào."""
    return [kiem_mot_caption(r, **kwargs) for r in rows]
