"""
Tính 6 chỉ số đề bài yêu cầu, theo cách đo được — không cảm tính.

Vì sao cần file riêng: "caption chi tiết" hay "tuân thủ prompt" nghe thì hiểu,
nhưng khi so 3 model với nhau mà mỗi lần đánh giá bằng cảm nhận thì kết luận
không đứng vững. Mỗi chỉ số ở đây quy về một con số.
"""

from __future__ import annotations

import re
import statistics
from dataclasses import asdict, dataclass, field
from typing import Any

# Dấu hiệu model nói thừa ngoài JSON.
_RAC_NGOAI_JSON = re.compile(
    r"(```|đây là|dưới đây|here is|here's|hy vọng|hope this|chắc chắn|sure[,!]|"
    r"tôi (sẽ|xin|không thể)|as an ai|xin lỗi|sorry)",
    re.IGNORECASE,
)

TRUONG_BAT_BUOC = ("doi_tuong", "mau_sac", "hanh_dong", "boi_canh", "caption_chi_tiet")


@dataclass
class KetQuaMotAnh:
    """Kết quả chạy model trên một ảnh."""

    ten_anh: str
    thanh_cong: bool
    latency_sec: float | None = None
    vram_peak_gb: float | None = None
    so_ky_tu_caption: int = 0
    so_tu_caption: int = 0
    so_doi_tuong: int = 0
    so_mau_sac: int = 0
    du_truong: bool = False
    co_rac_ngoai_json: bool = False
    loi: str | None = None
    ket_qua: dict[str, Any] | None = None


@dataclass
class TongKetModel:
    """Tổng kết cho một model sau khi chạy hết bộ ảnh."""

    model_key: str
    model_name: str = ""
    backend: str = ""
    tong_so_anh: int = 0
    so_anh_thanh_cong: int = 0

    ty_le_json_hop_le: float = 0.0
    ty_le_tuan_thu_prompt: float = 0.0

    latency_trung_binh: float = 0.0
    latency_p50: float = 0.0
    latency_p95: float = 0.0

    vram_dinh_gb: float | None = None

    caption_ky_tu_trung_binh: float = 0.0
    caption_tu_trung_binh: float = 0.0
    doi_tuong_trung_binh: float = 0.0
    mau_sac_trung_binh: float = 0.0

    danh_sach_loi: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def danh_gia_mot_anh(
    ten_anh: str,
    ket_qua: dict | None,
    text_tho: str = "",
    loi: Exception | None = None,
) -> KetQuaMotAnh:
    """
    Chấm điểm kết quả của một ảnh.

    `text_tho` là output chưa parse của model — cần để đo độ tuân thủ prompt
    (JSON đã parse xong thì không còn thấy phần rác model nói thừa).
    """
    if loi is not None or ket_qua is None:
        return KetQuaMotAnh(
            ten_anh=ten_anh,
            thanh_cong=False,
            loi=f"{type(loi).__name__}: {loi}" if loi else "không có kết quả",
        )

    caption = str(ket_qua.get("caption_chi_tiet", ""))
    doi_tuong = ket_qua.get("doi_tuong") or []
    mau_sac = ket_qua.get("mau_sac") or []

    return KetQuaMotAnh(
        ten_anh=ten_anh,
        thanh_cong=True,
        latency_sec=ket_qua.get("_latency_sec"),
        vram_peak_gb=ket_qua.get("_vram_peak_gb"),
        so_ky_tu_caption=len(caption),
        so_tu_caption=len(caption.split()),
        so_doi_tuong=len(doi_tuong),
        so_mau_sac=len(mau_sac),
        du_truong=all(truong in ket_qua for truong in TRUONG_BAT_BUOC),
        co_rac_ngoai_json=bool(_RAC_NGOAI_JSON.search(text_tho)) if text_tho else False,
        ket_qua=ket_qua,
    )


def tong_ket(
    model_key: str,
    danh_sach: list[KetQuaMotAnh],
    *,
    model_name: str = "",
    backend: str = "",
) -> TongKetModel:
    """Gộp kết quả từng ảnh thành một bảng số cho báo cáo."""
    tk = TongKetModel(
        model_key=model_key,
        model_name=model_name,
        backend=backend,
        tong_so_anh=len(danh_sach),
    )
    if not danh_sach:
        return tk

    thanh_cong = [r for r in danh_sach if r.thanh_cong]
    tk.so_anh_thanh_cong = len(thanh_cong)
    tk.ty_le_json_hop_le = round(len(thanh_cong) / len(danh_sach), 4)

    tk.danh_sach_loi = [r.loi for r in danh_sach if r.loi][:20]

    if not thanh_cong:
        return tk

    # Tuân thủ prompt = đủ trường VÀ không nói thừa ngoài JSON.
    tuan_thu = [r for r in thanh_cong if r.du_truong and not r.co_rac_ngoai_json]
    tk.ty_le_tuan_thu_prompt = round(len(tuan_thu) / len(danh_sach), 4)

    latencies = [r.latency_sec for r in thanh_cong if r.latency_sec is not None]
    if latencies:
        tk.latency_trung_binh = round(statistics.fmean(latencies), 3)
        tk.latency_p50 = round(statistics.median(latencies), 3)
        tk.latency_p95 = round(_phan_vi(latencies, 0.95), 3)

    vrams = [r.vram_peak_gb for r in thanh_cong if r.vram_peak_gb is not None]
    if vrams:
        tk.vram_dinh_gb = round(max(vrams), 3)

    tk.caption_ky_tu_trung_binh = round(
        statistics.fmean([r.so_ky_tu_caption for r in thanh_cong]), 1
    )
    tk.caption_tu_trung_binh = round(statistics.fmean([r.so_tu_caption for r in thanh_cong]), 1)
    tk.doi_tuong_trung_binh = round(statistics.fmean([r.so_doi_tuong for r in thanh_cong]), 2)
    tk.mau_sac_trung_binh = round(statistics.fmean([r.so_mau_sac for r in thanh_cong]), 2)

    return tk


def _phan_vi(gia_tri: list[float], p: float) -> float:
    """
    Phân vị thứ p (0-1).

    Tự viết thay vì dùng statistics.quantiles vì hàm đó cần >= 2 phần tử —
    chạy thử 1 ảnh sẽ crash.
    """
    if not gia_tri:
        return 0.0
    sap_xep = sorted(gia_tri)
    if len(sap_xep) == 1:
        return sap_xep[0]
    vi_tri = p * (len(sap_xep) - 1)
    duoi = int(vi_tri)
    tren = min(duoi + 1, len(sap_xep) - 1)
    phan_le = vi_tri - duoi
    return sap_xep[duoi] * (1 - phan_le) + sap_xep[tren] * phan_le


def do_on_dinh(cac_lan_chay: list[list[KetQuaMotAnh]]) -> dict:
    """
    Đo độ ổn định khi chạy cùng bộ ảnh nhiều lần.

    Đề bài yêu cầu kiểm tra "độ ổn định khi chạy nhiều ảnh liên tiếp". Cách đo:
    chạy cùng 10 ảnh 3 lần, xem latency có trôi và tỷ lệ JSON hợp lệ có tụt không.
    """
    if len(cac_lan_chay) < 2:
        return {"du_lieu": "cần ít nhất 2 lần chạy để đo độ ổn định"}

    ty_le_moi_lan = []
    latency_moi_lan = []
    for lan in cac_lan_chay:
        if not lan:
            continue
        thanh_cong = [r for r in lan if r.thanh_cong]
        ty_le_moi_lan.append(len(thanh_cong) / len(lan))
        lat = [r.latency_sec for r in thanh_cong if r.latency_sec is not None]
        if lat:
            latency_moi_lan.append(statistics.fmean(lat))

    ket_qua: dict[str, Any] = {
        "so_lan_chay": len(cac_lan_chay),
        "ty_le_json_moi_lan": [round(t, 4) for t in ty_le_moi_lan],
        "latency_tb_moi_lan": [round(l, 3) for l in latency_moi_lan],
    }
    if len(ty_le_moi_lan) >= 2:
        ket_qua["ty_le_json_do_lech"] = round(statistics.stdev(ty_le_moi_lan), 4)
    if len(latency_moi_lan) >= 2:
        ket_qua["latency_do_lech"] = round(statistics.stdev(latency_moi_lan), 3)
    return ket_qua
