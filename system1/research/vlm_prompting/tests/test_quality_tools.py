"""
Tự kiểm bộ đo chất lượng caption bằng dữ liệu giả lập — chứng minh công cụ
đúng khi chưa có 92 caption thật (đang chờ Phase 05 kéo về từ Kaggle).

Dựng thẳng CaptionRow trong test, không đọc file — vì mục tiêu là kiểm logic
đo (BM25 recall, 3 phép kiểm lỗi), không phải kiểm caption_loader (loader có
lối vào riêng qua load_checkpoint, không cần giả lập ở đây).

Không import torch/transformers — file này lẫn toàn bộ quality/ phải chạy
được trên Python 3.14 CPU thuần (máy local chưa có torch cho 3.14).
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

GOC = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(GOC))

from quality.caption_defect_checks import kiem_mot_caption  # noqa: E402
from quality.caption_loader import CaptionRow, _tu_ket_qua  # noqa: E402
from quality.caption_ngon_ngu_la import kiem_ngon_ngu_la  # noqa: E402
from quality.caption_repetition import NGUONG_MAT_DO_LAP, mat_do_lap  # noqa: E402
from quality.self_retrieval_bm25 import do_self_retrieval  # noqa: E402


def _row(ten_anh: str, caption: str, *, doi_tuong: list[str] | None = None) -> CaptionRow:
    return CaptionRow(
        ten_anh=ten_anh,
        caption=caption,
        doi_tuong=doi_tuong or [],
        mau_sac=[],
    )


def test_bo_caption_hoan_hao_recall_cao() -> None:
    """Mỗi caption tả một cảnh hoàn toàn khác nhau → recall@1 phải cao (>=0.95)."""
    rows = [
        _row("001.jpg", "Một người đàn ông mặc áo mưa đỏ chạy xe máy qua đường ngập nước."),
        _row("002.jpg", "Con mèo tam thể nằm ngủ trên ghế sofa màu xám trong phòng khách."),
        _row("003.jpg", "Đầu bếp đang thái rau củ trên thớt gỗ trong nhà bếp công nghiệp."),
        _row("004.jpg", "Hai đứa trẻ chơi thả diều trên bãi biển lúc hoàng hôn."),
        _row("005.jpg", "Chiếc xe buýt màu vàng dừng đón khách tại trạm xe buýt thành phố."),
        _row("006.jpg", "Nhân viên văn phòng gõ bàn phím laptop cạnh cửa sổ tòa nhà cao tầng."),
        _row("007.jpg", "Đàn cá vàng bơi lội trong bể kính đặt giữa phòng khách sang trọng."),
        _row("008.jpg", "Người nông dân gặt lúa trên cánh đồng vàng óng buổi sáng sớm."),
        _row("009.jpg", "Vận động viên chạy marathon vượt qua vạch đích trong tiếng reo hò."),
        _row("010.jpg", "Cụ già ngồi đọc báo trên ghế đá công viên dưới bóng cây cổ thụ."),
    ]
    ket_qua = do_self_retrieval(rows)
    assert ket_qua.recall_tai_1 >= 0.95, f"recall@1 quá thấp: {ket_qua.recall_tai_1}"


def test_bo_caption_giong_het_recall_thap() -> None:
    """Toàn bộ caption giống hệt nhau → không phân biệt được → recall@1 phải thấp."""
    rows = [_row(f"{i:03d}.jpg", "Người giảng dạy đang giảng dạy.") for i in range(1, 11)]
    ket_qua = do_self_retrieval(rows)
    assert ket_qua.recall_tai_1 <= 0.20, f"recall@1 lẽ ra phải thấp, đo được: {ket_qua.recall_tai_1}"


def test_bat_duoc_chep_few_shot() -> None:
    """Caption chép nguyên ví dụ mẫu _VI_DU_MAU phải bị phép kiểm bắt được."""
    row = _row(
        "011.jpg",
        "Một chiếc nồi kim loại màu bạc đang đun sôi trên bếp gas với ngọn lửa xanh trong gian bếp gia đình.",
    )
    ket_qua = kiem_mot_caption(row)
    assert ket_qua.chep_few_shot is True


def test_bat_duoc_caption_vong_vo() -> None:
    """Caption lặp từ ('giảng dạy' x3) phải có TTR thấp và bị đánh dấu vòng vo."""
    row = _row("012.jpg", "Người giảng dạy đang giảng dạy giảng dạy.")
    ket_qua = kiem_mot_caption(row)
    assert ket_qua.vong_vo is True
    assert ket_qua.ttr < 0.6


def test_bat_duoc_nhet_chu_ocr() -> None:
    """doi_tuong toàn từ tiếng Anh (chữ đọc từ ảnh, không phải vật thể) phải bị bắt."""
    row = _row(
        "014.jpg",
        "Trung tâm giáo dục đang tổ chức một buổi học trực tuyến với nhiều hoạt động thú vị.",
        doi_tuong=["enjoy", "admit", "avoid", "deny", "fancy"],
    )
    ket_qua = kiem_mot_caption(row)
    assert ket_qua.nhet_chu_ocr is True


def test_loader_cat_nhan_thua() -> None:
    """caption_loader phải dùng lại _bo_nhan_thua của vlm/schema.py — không
    còn tiền tố kiểu 'Caption Chi tiết:' trong caption đọc ra (ca thật 001.jpg,
    xem results/checkpoint_qwen2vl-2b-mau5.json)."""
    row = _tu_ket_qua(
        "001.jpg",
        {
            "caption_chi_tiet": (
                "Caption Chi tiết: Một người đàn ông mặc áo mưa đỏ đang chạy "
                "xe máy qua đoạn đường ngập nước dưới cơn mưa tầm tã."
            ),
            "doi_tuong": [],
            "mau_sac": [],
        },
    )
    assert row is not None
    assert not row.caption.lower().startswith("caption chi tiết")
    assert row.caption.startswith("Một người đàn ông")


def test_bat_duoc_chep_few_shot_ban_cu_v1() -> None:
    """Caption chép ví dụ mẫu của PROMPT V1 (đã bỏ dùng, thay bằng v2) vẫn
    phải bị bắt — vì dữ liệu sinh bằng prompt cũ vẫn cần chấm được (ca thật
    001.jpg, xem git log vlm/prompts.py trước commit b0125fa)."""
    row = _row(
        "001.jpg",
        "Một người đàn ông mặc áo mưa đỏ đang chạy xe máy qua đoạn đường "
        "ngập nước dưới cơn mưa tầm tã.",
    )
    ket_qua = kiem_mot_caption(row)
    assert ket_qua.chep_few_shot is True


def test_bat_duoc_vong_vo_theo_y_ttr_khong_thay() -> None:
    """Caption lặp cụm 'giảng dạy' xen từ khác ở giữa có TTR cao (0.818,
    trên ngưỡng 0.6) nên riêng TTR bỏ sót — nhưng phép kiểm cụm lặp phải
    bắt được (ca thật 009.jpg)."""
    row = _row("009.jpg", "Người giảng dạy đang giảng dạy tại Trung tâm học tập.")
    ket_qua = kiem_mot_caption(row)
    assert ket_qua.ttr > 0.6, f"TTR lẽ ra phải cao (đúng hiện tượng bỏ sót), đo được: {ket_qua.ttr}"
    assert ket_qua.vong_vo is True


def test_caption_tot_khong_bi_bao_nham_vong_vo() -> None:
    """Caption dài tự nhiên, không lặp ý, KHÔNG được báo vòng vo (ca thật
    010.jpg) — chống báo nhầm của phép kiểm cụm lặp mới thêm."""
    row = _row(
        "010.jpg",
        "Người giới thiệu đang trình bày trong phòng học với một màn hình "
        "hiển thị hình ảnh khoa học kỹ thuật.",
    )
    ket_qua = kiem_mot_caption(row)
    assert ket_qua.vong_vo is False
    assert ket_qua.co_loi is False


def test_tu_muon_khong_bi_bao_nham() -> None:
    """doi_tuong = ["laptop","ti vi"] không dấu nhưng hợp lệ — KHÔNG được báo nhầm.

    Gộp luôn kiểm tra hiệu năng (100 caption < 5s, cổng kiểm bắt buộc của
    phase) vào ca cuối để giữ đúng 6 hàm test theo đặc tả — không phải vì
    hai việc liên quan, chỉ để không lệch số lượng ca kiểm yêu cầu.
    """
    row = _row(
        "015.jpg",
        "Nhân viên văn phòng đang sử dụng laptop cạnh chiếc ti vi treo tường trong phòng họp.",
        doi_tuong=["laptop", "ti vi"],
    )
    ket_qua = kiem_mot_caption(row)
    assert ket_qua.nhet_chu_ocr is False

    rows_100 = [
        _row(f"{i:03d}.jpg", f"Ảnh số {i} chụp cảnh khác nhau với chi tiết riêng biệt số {i}.")
        for i in range(100)
    ]
    bat_dau = time.perf_counter()
    do_self_retrieval(rows_100)
    for r in rows_100:
        kiem_mot_caption(r)
    thoi_gian = time.perf_counter() - bat_dau
    assert thoi_gian < 5.0, f"Chạy quá lâu: {thoi_gian:.2f}s"


def test_bat_ky_tu_han_lan_trong_caption():
    # Lỗi thật đo được trên 027.jpg: Qwen2-VL rơi về tiếng Trung giữa câu tiếng Việt.
    assert kiem_ngon_ngu_la("Một bức ảnh模糊 của một tòa nhà trắng.")
    assert kiem_ngon_ngu_la("Cảnh đường phố ハイウェイ đông đúc.")


def test_khong_bao_nham_caption_tieng_viet_thuan():
    assert not kiem_ngon_ngu_la(
        "Một người đang giảng dạy trên màn hình máy tính với một laptop ở trước mặt."
    )
    # Số, dấu câu, chữ Latin không dấu đều hợp lệ trong caption tiếng Việt.
    assert not kiem_ngon_ngu_la("Có 3 người mặc áo T-shirt màu xanh, đứng cạnh laptop.")


# --- Hiệu chỉnh sau đo thật 30 caption (checkpoint_haiku-thu30.json) ---
# Ca 1-4, 5-6: bắt oan cũ, sau hiệu chỉnh KHÔNG được bắt.
# Ca 7-11: lỗi thật, sau hiệu chỉnh VẪN phải bắt.


def test_khong_bao_nham_cum_mo_dau_thong_dung_few_shot():
    """Ca 1 — cụm mở đầu thông dụng ('Một người đàn ông mặc áo...') trùng
    5 từ đầu với ví dụ mẫu đời cũ nhưng KHÔNG phải chép nội dung — n=8 không
    được bắt."""
    row = _row(
        "test01.jpg",
        "Một người đàn ông mặc áo sơ mi trắng và cà vạt xanh, đeo kính mắt, "
        "ngồi tại bàn làm việc với laptop, được bao quanh bởi hiệu ứng công "
        "nghệ và bản đồ thế giới trên nền xanh lam tươi sáng.",
    )
    ket_qua = kiem_mot_caption(row)
    assert ket_qua.chep_few_shot is False


def test_khong_bao_nham_thuat_ngu_di_truyen_lap():
    """Ca 2 — thuật ngữ chuyên ngành 'di truyền' buộc phải lặp, không phải vòng vo."""
    row = _row(
        "test02.jpg",
        "Một nam giáo viên mặc áo tím nhạt ngồi trước máy tính, trình bày sơ "
        "đồ di truyền và biểu đồ chi tiết về cơ chế di truyền của vi khuẩn E.coli "
        "trên bảng trắng.",
    )
    ket_qua = kiem_mot_caption(row)
    assert ket_qua.vong_vo is False


def test_khong_bao_nham_thuat_ngu_hoa_hoc_lap():
    """Ca 3 — thuật ngữ 'hóa học' lặp lại vì nội dung chuyên ngành."""
    row = _row(
        "test03.jpg",
        "Một màn hình chiếu hiển thị bài giảng hóa học về amino axit với các "
        "công thức phản ứng hóa học viết bằng chữ vàng trên nền xanh lục, bao "
        "gồm các phương trình tính toán và hướng dẫn giải bài tập.",
    )
    ket_qua = kiem_mot_caption(row)
    assert ket_qua.vong_vo is False


def test_khong_bao_nham_thuat_ngu_hoi_thao_lap():
    """Ca 4 — 'hội thảo' lặp 2 nghĩa khác nhau (danh từ ghép + tính từ mô tả cuộc họp)."""
    row = _row(
        "test04.jpg",
        "Các quan chức ngồi quanh bàn hội thảo dài với cờ Việt Nam và Đức, hoa "
        "trắng trang trí, tham gia một cuộc họp báo hoặc hội thảo ngoại giao "
        "trong phòng gỗ nâu sang trọng.",
    )
    ket_qua = kiem_mot_caption(row)
    assert ket_qua.vong_vo is False


def test_khong_bao_nham_doi_tuong_ten_vat_the_hop_le():
    """Ca 5, 6 — doi_tuong là tên vật thể / thương hiệu hợp lệ, không phải OCR."""
    row5 = _row("test05.jpg", "Khuôn viên trường đại học với biển hiệu lớn.", doi_tuong=["biển hiệu đại học", "tòa nhà", "cây cối"])
    ket_qua5 = kiem_mot_caption(row5)
    assert ket_qua5.nhet_chu_ocr is False

    row6 = _row(
        "test06.jpg",
        "Nam giáo viên đứng cạnh laptop Dell trước bảng trắng.",
        doi_tuong=["nam giáo viên", "laptop Dell", "bảng trắng"],
    )
    ket_qua6 = kiem_mot_caption(row6)
    assert ket_qua6.nhet_chu_ocr is False


def test_bat_duoc_doi_tuong_nhet_ocr_co_dau():
    """Ca 7 — lỗi thật 001.jpg: doi_tuong mô tả chuỗi chữ OCR ('THANHNIEN')
    dù phần tử có dấu tiếng Việt xen vào ('chữ', 'màu', 'xanh') nên phép kiểm
    'không dấu' cũ bỏ sót."""
    row = _row(
        "001.jpg",
        "Một biển quảng cáo màu xanh lam trên đường phố.",
        doi_tuong=["chữ 'THANHNIEN' màu xanh lam"],
    )
    ket_qua = kiem_mot_caption(row)
    assert ket_qua.nhet_chu_ocr is True


def test_bat_duoc_ngon_ngu_la_trong_doi_tuong():
    """Ca 8 — lỗi thật 047.jpg: chữ Hàn lẫn trong doi_tuong, bộ chấm cũ chỉ
    soi row.caption nên bỏ sót."""
    row = _row(
        "047.jpg",
        "Hai người chơi nhạc trong ánh sáng ấm áp.",
        doi_tuong=["hai người", "đàn guitar", "ghế", "ánh sáng따뜻"],
    )
    ket_qua = kiem_mot_caption(row)
    assert ket_qua.ngon_ngu_la is True


def test_bat_duoc_doi_tuong_nhet_ocr_khong_dau_van_giu():
    """Ca 9 — phép kiểm 'không dấu' cũ (kiem_nhet_chu_ocr) vẫn phải hoạt động,
    không bị thay thế bởi kiem_doi_tuong_la_chuoi_chu."""
    row = _row(
        "test09.jpg",
        "Trung tâm giáo dục đang tổ chức một buổi học trực tuyến.",
        doi_tuong=["enjoy", "admit", "avoid"],
    )
    ket_qua = kiem_mot_caption(row)
    assert ket_qua.nhet_chu_ocr is True


def test_bat_duoc_vong_vo_that_giang_day_lap_dung_2_lan():
    """Ca 10 — vòng vo thật, lặp đúng 2 lần, không phải thuật ngữ chuyên ngành
    miễn trừ — phải vẫn bị bắt (chống việc chọn nhầm giải pháp nâng ngưỡng >=3)."""
    row = _row("test10.jpg", "Người giảng dạy đang giảng dạy tại Trung tâm học tập.")
    ket_qua = kiem_mot_caption(row)
    assert ket_qua.vong_vo is True


def test_bat_duoc_ngon_ngu_la_trong_caption_han_tu():
    """Ca 11 — ngôn ngữ lạ trong caption chính (không phải doi_tuong) vẫn phải bắt."""
    row = _row("test11.jpg", "Một bức ảnh模糊 của tòa nhà cao tầng trong thành phố lớn.")
    ket_qua = kiem_mot_caption(row)
    assert ket_qua.ngon_ngu_la is True


def test_cau_dai_lap_mot_cum_danh_tu_khong_bi_bao_nham():
    """
    Caption dài nhắc lại một danh từ ở vế sau là hành văn bình thường.

    Bốn ca thật từ cổng chặn v2 — trước khi chuẩn hoá theo độ dài câu, cả bốn
    đều bị gắn cờ vòng vo, đẩy tỷ lệ lỗi lên 20,69% trên tập 29 caption.
    """
    ca_that = [
        "Một thầy giáo mặc áo tím đang giảng dạy tại laptop với một sơ đồ sinh "
        "thái hiển thị trên bảng, gồm các khái niệm về môi trường, nhân tố sinh "
        "thái và quy luật tác động, xung quanh là các hình ảnh thiên nhiên xanh tươi.",
        "Một tòa nhà đại học lớn với khung cửa sổ kính xanh lục nhạt nằm phía "
        "sau, có con đường dẫn đến và cây xanh bao quanh trong khuôn viên trường đại học.",
        "Nhiều học sinh nữ ngồi trên ghế xanh dương trong lớp học, với thầy giáo "
        "nam mặc áo sơ mi đỏ đang ghi viết công thức toán học trên bảng trắng, "
        "một số học sinh giơ tay để trả lời câu hỏi.",
        "Một nhóm học sinh mặc áo trắng và quần đỏ đang biểu diễn âm nhạc trên "
        "sân khấu với các nhạc cụ piano và violon, quanh sân khấu trang trí bởi "
        "những quả bóng đầy màu sắc.",
    ]
    for i, caption in enumerate(ca_that):
        assert kiem_mot_caption(_row(f"dai{i}.jpg", caption)).vong_vo is False, caption[:60]


def test_mat_do_lap_tach_bach_cau_ngan_lap_va_cau_dai_tu_nhien():
    """Cùng một cụm lặp, câu ngắn vượt ngưỡng còn câu dài thì không."""
    ngan = "Một đội bóng rổ đang chơi bóng rổ trên sân bóng rổ xanh."
    dai = (
        "Một tòa nhà đại học lớn với khung cửa sổ kính xanh lục nhạt nằm phía "
        "sau, có con đường dẫn đến và cây xanh bao quanh trong khuôn viên trường đại học."
    )
    assert mat_do_lap(ngan) > NGUONG_MAT_DO_LAP
    assert mat_do_lap(dai) <= NGUONG_MAT_DO_LAP
