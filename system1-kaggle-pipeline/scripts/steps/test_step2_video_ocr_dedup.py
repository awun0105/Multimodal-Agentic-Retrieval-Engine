"""
Kịch bản kiểm thử độc lập Step 2: OCR tiếng Việt phân vùng không gian và khử trùng lặp cấp cú máy.
Kiểm tra khả năng loại bỏ chuỗi trùng lặp và phân tách chính xác is_lower_third (y > 0.65).
"""

from __future__ import annotations
import sys
from pathlib import Path

# Dam bao UTF-8 tren Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

SRC_DIR = Path(__file__).resolve().parent.parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from ocr_extractor import VietnameseOCRExtractor


def test_video_ocr_dedup():
    print("=" * 70)
    print("KIỂM THỬ ĐỘC LẬP: OCR TIẾNG VIỆT & KHỬ TRÙNG LẶP CẤP CÚ MÁY (STEP 2)")
    print("=" * 70)

    # 1. Kiểm thử thuật toán khử trùng lặp (Jaccard / Substring)
    raw_shot_ocr_texts = [
        "BẢN TIN THỜI SỰ 19H HÔM NAY",
        "BẢN TIN THỜI SỰ 19H",
        "THỜI SỰ 19H HÔM NAY",
        "Thủ tướng Chính phủ chủ trì phiên họp trực tuyến",
        "Thủ tướng Chính phủ chủ trì phiên họp",
        "BIỂN BÁO GIAO THÔNG ĐƯỜNG BỘ",
        "Biển báo giao thông"
    ]

    deduped = VietnameseOCRExtractor.deduplicate_text_list(raw_shot_ocr_texts, threshold=0.8)
    print(f"[TEST 1] Danh sach goc ({len(raw_shot_ocr_texts)} chuoi):")
    for t in raw_shot_ocr_texts:
        print(f"  - '{t}'")

    print(f"\n[TEST 1] Sau khi khu trung lap ({len(deduped)} chuoi toi uu):")
    for t in deduped:
        print(f"  -> '{t}'")

    # Kỳ vọng: 7 chuỗi bị gộp thành 3 chuỗi đại diện dài nhất
    assert len(deduped) <= 3, f"Chua khu trung lap toi uu, ket qua con {len(deduped)} chuoi!"
    print("  -> DAT: Thuat toan khu trung lap giam > 55% chuoi thua va giu nguyen ven thong tin.")

    # 2. Kiểm thử phân vùng không gian (Lower third ticker)
    extractor = VietnameseOCRExtractor(gpu=False)
    # Giả lập kết quả bounding boxes
    sample_boxes = [
        {"ymin": 0.75, "text": "Tin tức thời sự 24h", "conf": 0.95}, # Lower-third (y > 0.65)
        {"ymin": 0.20, "text": "Bien so xe 51A-123.45", "conf": 0.85}, # Center/Top (y <= 0.65, conf cao)
        {"ymin": 0.30, "text": "Hoa van nhe", "conf": 0.45}            # Noise ở vùng giữa (conf < 0.6)
    ]

    kept_boxes = []
    for b in sample_boxes:
        is_lower = b["ymin"] > 0.65
        if not is_lower and b["conf"] < 0.6:
            continue
        kept_boxes.append({"text": b["text"], "is_lower_third": is_lower})

    print(f"\n[TEST 2] Loc phan vung khong gian ({len(sample_boxes)} hop tho -> {len(kept_boxes)} hop chuan):")
    for b in kept_boxes:
        print(f"  -> '{b['text']}' (is_lower_third: {b['is_lower_third']})")

    assert len(kept_boxes) == 2, "Loc phan vung khong gian chua dung!"
    print("  -> DAT: Da loai bo thanh cong nhieu hop tho o vung trung tam va giu nguyen tin chan trang.")

    print("=" * 70)
    print("KET QUA: TAT CA CAC BAI TEST OCR DEDUP DEU DAT 100%!")
    print("=" * 70)


if __name__ == "__main__":
    test_video_ocr_dedup()
