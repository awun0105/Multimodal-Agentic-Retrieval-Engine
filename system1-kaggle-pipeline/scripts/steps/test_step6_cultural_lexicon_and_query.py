"""
Kịch bản kiểm thử độc lập: Vietnamese Cultural Lexicon & Faithful Query Enricher (Step 6)
Phục vụ phân hệ System 1 (AIC 2026):
- Kiểm tra bóc tách các khái niệm văn hóa bản địa (múa lân, áo dài, nón lá, chợ nổi, bánh chưng).
- Kiểm tra nguyên tắc làm giàu truy vấn trung thực (No-Hallucination Rule).
- Xuất báo cáo định lượng và thời gian thực thi.
"""

import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

SRC_DIR = Path(__file__).resolve().parent.parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from vietnamese_cultural_lexicon import lookup_cultural_concepts, enrich_query_faithfully, VIETNAMESE_CULTURAL_LEXICON


def test_vietnamese_cultural_lexicon_and_query_enrichment():
    print("=" * 80)
    print("KIEM THU DOC LAP: VIETNAMESE CULTURAL LEXICON & FAITHFUL QUERY ENRICHMENT")
    print("=" * 80)

    # 1. KIỂM THỬ BỘ TỪ ĐIỂN KHÁI NIỆM BẢN ĐỊA
    print(f"\n[TEST 1] Kiem tra so luong va tinh toan ven cua Bo Tu Dien Ban Dia:")
    print(f"  - Tong so thuc the van hoa da dinh nghia: {len(VIETNAMESE_CULTURAL_LEXICON)} thuc the.")
    for k, v in VIETNAMESE_CULTURAL_LEXICON.items():
        assert "canonical_name" in v and "visual_anchor_en" in v and "aliases" in v
    print("  -> DAT: 100% thuc the van hoa co day du canonical_name, visual_anchor_en va aliases.")

    # 2. KIỂM THỬ NHẬN DIỆN THỰC THỂ THUẦN VIỆT TỪ CÂU TRUY VẤN
    print(f"\n[TEST 2] Kiem tra nhan dien cac khai niem ban dia trong cau truy van:")
    test_queries = [
        ("Nguoi dang mua lan tren pho dong duc", ["Múa lân"]),
        ("Co gai mac ao dai xanh doi non la di bo", ["Áo dài", "Nón lá"]),
        ("Canh cho noi tren song co nhieu ghe thuyen", ["Chợ nổi", "Ghe / Xuồng ba lá"]),
        ("Mam co ngay tet co banh chung va den ong sao", ["Bánh chưng", "Đèn ông sao"]),
        ("Ong dia bung bu cam quat nhay mua", ["Ông Địa"]),
        ("Bac tai dap xe xich lo cho khach nuoc ngoai", ["Xe xích lô"]),
        ("Cau thu sut bong tren san co", []) # Khong co tu van hoa ban dia
    ]

    for q, expected in test_queries:
        detected = lookup_cultural_concepts(q)
        detected_names = [d["canonical_name"] for d in detected]
        print(f"  - Query: '{q}' -> Phat hien: {detected_names}")
        assert detected_names == expected, f"Ky vong {expected}, nhung nhan {detected_names}"

    print("  -> DAT: Nhan dien chuan xac 100% cac khai niem ban dia tu cau truy van.")

    # 3. KIỂM THỬ NGUYÊN TẮC LÀM GIÀU TRUNG THỰC (NO HALLUCINATION)
    print(f"\n[TEST 3] Kiem tra nguyen tac lam giau trung thuc (Faithful Query Enrichment):")
    raw_query = "Hai nguoi mua lan tren duong pho"
    raw_translated = "Two people performing lion dance on the street"
    
    t0 = time.perf_counter()
    enriched = enrich_query_faithfully(raw_query, translated_text_en=raw_translated)
    t_elap_ms = (time.perf_counter() - t0) * 1000.0

    print(f"  - Query goc: '{enriched['raw_query_vi']}'")
    print(f"  - Dich tho: '{enriched['translated_en_raw']}'")
    print(f"  - Query lam giau: '{enriched['enriched_query_en']}'")
    print(f"  - FTS Boost: {enriched['fts_boost_keywords']}")
    print(f"  - Thoi gian xu ly: {t_elap_ms:.3f} ms")

    assert "Múa lân" in enriched["detected_cultural_concepts"]
    assert "traditional Vietnamese lion dance" in enriched["enriched_query_en"]
    assert t_elap_ms < 5.0, "Thoi gian lam giau query phai < 5ms"
    print("  -> DAT: Lam giau query trung thuc, khong hallucinate va do tre < 5ms.")

    print("\n" + "=" * 80)
    print("KET QUA: TOAN BO TEST CASES CULTURAL LEXICON & QUERY ENRICHER DAT 100%!")
    print("=" * 80)


if __name__ == "__main__":
    test_vietnamese_cultural_lexicon_and_query_enrichment()
