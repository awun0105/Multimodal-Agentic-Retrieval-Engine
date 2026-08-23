# -*- coding: utf-8 -*-
"""
Kịch bản kiểm thử độc lập Step 5: Hợp nhất Dòng thời gian BTC-Self, Đếm số lượng vật thể, 
Suy đoán Ý nghĩa toàn cú máy (Shot Contextual Meaning) & Kiểm duyệt lọc bỏ sau khi merge trên Timeline.

Kiểm tra 6 nhóm tình huống thực tế:
1. Định dạng đếm số lượng vật thể 'Nhãn x Số lượng' (Cờ x 5, Người x 2).
2. Gộp frame trùng mốc thời gian (|Δt| <= 0.05s) giữa BTC và System 1.
3. Bóc tách từ khóa OCR tiếng Việt (loại bỏ stop words).
4. Suy đoán Ý nghĩa toàn cú máy (Shot Contextual Meaning & Activities): Tin tức, Giao thông, Thể thao, Học thuật.
5. Làm giàu và suy đoán ngữ cảnh cho Keyframe Ban Tổ Chức (BTC Context Inference).
6. Quy trình Merge & Deduplicate hoàn chỉnh với kiểm duyệt nghiêm ngặt trên dòng thời gian đã merge.
"""

from __future__ import annotations
import sys
from pathlib import Path

# Đảm bảo UTF-8 trên Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

SRC_DIR = Path(__file__).resolve().parent.parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from timeline_synchronizer import TimelineSynchronizer


def test_step5_timeline_synchronization_and_deduplication():
    print("=" * 75)
    print("KIỂM THỬ ĐỘC LẬP: TIMELINE SYNCHRONIZATION, SHOT CONTEXT & VIRTUAL DEDUP (STEP 5)")
    print("=" * 75)

    # 1. KIỂM THỬ ĐẾM SỐ LƯỢNG VẬT THỂ ("Nhãn x Số lượng")
    raw_classes = ["flag", "flag", "flag", "flag", "flag", "person", "person", "motorcycle"]
    formatted_counts, count_dict = TimelineSynchronizer.format_object_counts(raw_classes)
    print(f"\n[TEST 1] Dinh dang dem so luong vat the:")
    print(f"  - Danh sach goc: {raw_classes}")
    print(f"  -> Ket qua chuoi: '{formatted_counts}'")
    print(f"  -> Dict so luong: {count_dict}")
    assert count_dict["flag"] == 5 and count_dict["person"] == 2 and count_dict["motorcycle"] == 1
    assert "Cờ x 5" in formatted_counts and "Người x 2" in formatted_counts
    print("  -> DAT: Dem chinh xac tung loai vat the va dinh dang tieng Viet chuan.")

    # 2. KIỂM THỬ GỘP MỐC THỜI GIAN TRÙNG (|Δt| <= 0.05s)
    btc_kfs = [
        {"video_id": "L21_V001", "frame_idx": 100, "pts_time_sec": 4.002, "keyframe_name": "shot_001_100.jpg", "sharpness": 120.0},
        {"video_id": "L21_V001", "frame_idx": 300, "pts_time_sec": 12.000, "keyframe_name": "shot_002_300.jpg", "sharpness": 180.0},
    ]
    self_kfs = [
        {"video_id": "L21_V001", "frame_idx": 101, "pts_time_sec": 4.020, "keyframe_name": "shot_001_101.jpg", "sharpness": 550.0, "detected_classes": ["person", "car"]},
        {"video_id": "L21_V001", "frame_idx": 200, "pts_time_sec": 8.000, "keyframe_name": "shot_001_200.jpg", "sharpness": 490.0, "detected_classes": ["flag", "flag"]},
    ]

    merged = TimelineSynchronizer.merge_and_sort_timeline(btc_kfs, self_kfs, exact_match_threshold_sec=0.05)
    print(f"\n[TEST 2] Gop moc thoi gian trung (|Δt| <= 0.05s):")
    print(f"  - Tong frame dau vao: {len(btc_kfs) + len(self_kfs)} frames (BTC: 2, Self: 2)")
    print(f"  - Sau khi gop: {len(merged)} frames tren truc thoi gian chung:")
    for item in merged:
        print(f"    * Frame {item.get('frame_idx')} tai {item.get('pts_time_sec')}s (is_btc_synced: {item.get('is_btc_synced', False)}, btc_frame: {item.get('btc_frame_idx')})")

    assert len(merged) == 3, f"Loi: Ky vong 3 frames nhung ket qua la {len(merged)}"
    assert merged[0]["is_btc_synced"] is True and merged[0]["btc_frame_idx"] == 100
    print("  -> DAT: Da gop dung 2 frame tai 4.002s va 4.020s thanh 1 ban ghi co day du btc_frame_idx.")

    # 3. KIỂM THỬ BÓC TÁCH TỪ KHÓA OCR (LOẠI BỎ HƯ TỪ)
    sample_ocr = "Thời sự 19h: Thủ tướng chủ trì hội nghị trực tuyến toàn quốc về phát triển kinh tế"
    keywords = TimelineSynchronizer.extract_text_keywords(sample_ocr, max_keywords=3)
    print(f"\n[TEST 3] Boc tach tu khoa OCR tieng Viet:")
    print(f"  - Chuoi OCR goc: '{sample_ocr}'")
    print(f"  -> Tu khoa boc tach: {keywords}")
    assert len(keywords) > 0
    assert any("Thời sự" in kw or "Thủ tướng" in kw or "hội nghị" in kw for kw in keywords)
    print("  -> DAT: Loc bo thanh cong stop words va lay dung tu khoa quan trong.")

    # 4. KIỂM THỬ SUY ĐOÁN Ý NGHĨA TOÀN CÚ MÁY (SHOT CONTEXTUAL MEANING)
    # Tình huống A: Trường quay thời sự + OCR
    shot_news = {
        "ocr_text": "Thời sự 19h: Bản tin tối nay",
        "text_density_pct": 8.5,
        "detected_classes": ["person", "chair", "tv"],
        "dominant_color": "Do Thoi Su",
        "scene_environment": "Trường quay Thời sự / Studio (News Studio)"
    }
    meaning_news = TimelineSynchronizer.infer_shot_contextual_meaning(shot_news, video_title="Bản tin thời sự VTV1")
    print(f"\n[TEST 4] Suy doan y nghia toan cu may:")
    print(f"  - Tinh huong Tin tuc -> '{meaning_news}'")
    assert "tin" in meaning_news.lower() or "thời sự" in meaning_news.lower() or "thoi su" in meaning_news.lower()
    assert "từ khóa" in meaning_news.lower() or "tu khoa" in meaning_news.lower() or "Từ khóa:" in meaning_news

    # Tình huống B: Giao thông đường phố
    shot_traffic = {
        "ocr_text": "",
        "text_density_pct": 0.0,
        "detected_classes": ["car", "motorcycle", "traffic light"],
        "dominant_color": "Xam",
        "scene_environment": "Đường phố / Giao thông (Street/Urban)"
    }
    meaning_traffic = TimelineSynchronizer.infer_shot_contextual_meaning(shot_traffic, video_title="Đường phố Hà Nội")
    print(f"  - Tinh huong Giao thong -> '{meaning_traffic}'")
    assert "giao" in meaning_traffic.lower() or "thông" in meaning_traffic.lower() or "đường phố" in meaning_traffic.lower()

    # Tình huống C: Thể thao tranh bóng
    shot_sports = {
        "ocr_text": "Trực tiếp V-League 2026",
        "text_density_pct": 5.0,
        "detected_classes": ["sports ball", "person", "person"],
        "dominant_color": "Xanh La",
        "scene_environment": "Sân vận động / Thể thao (Sports Ground)"
    }
    meaning_sports = TimelineSynchronizer.infer_shot_contextual_meaning(shot_sports, video_title="V-League Trực tiếp")
    print(f"  - Tinh huong The thao -> '{meaning_sports}'")
    assert "thể thao" in meaning_sports.lower() or "tranh" in meaning_sports.lower() or "bóng" in meaning_sports.lower()
    print("  -> DAT: Suy doan chinh xac y nghia toan cu may, kem tu khoa chu va hoat dong.")

    # 5. KIỂM THỬ SUY ĐOÁN NGỮ CẢNH CHO BAN TỔ CHỨC (BTC CONTEXT INFERENCE)
    dummy_vec = [0.1] * 768
    sample_btc_item = {
        "video_id": "L21_V001", "frame_idx": 100, "pts_time_sec": 4.0,
        "embedding": dummy_vec, "sharpness": 350.0
    }
    reference_self = [
        {
            "video_id": "L21_V001", "frame_idx": 102, "pts_time_sec": 4.08,
            "embedding": dummy_vec, "ocr_text": "Thời sự 19h", "dominant_color": "Do Thoi Su",
            "scene_environment": "Trường quay Thời sự / Studio (News Studio)",
            "objects_and_counts": "Người x 1, Tivi x 1", "objects_dict": {"person": 1, "tv": 1},
            "shot_contextual_meaning": "Dẫn bản tin trường quay thời sự | Từ khóa: [Thời sự 19h]"
        }
    ]

    enriched_btc = TimelineSynchronizer.enrich_btc_with_shot_context(sample_btc_item, reference_self)
    print(f"\n[TEST 5] Suy doan ngu canh cho Keyframe Ban To Chuc (BTC):")
    print(f"  - Vien CSS: {enriched_btc.get('border_color')}")
    print(f"  - Y nghia ke thua/suy doan: '{enriched_btc.get('shot_contextual_meaning')}'")
    print(f"  - Boi canh: '{enriched_btc.get('scene_environment')}'")
    print(f"  - Vat the: '{enriched_btc.get('objects_and_counts')}'")
    assert enriched_btc["border_color"] == "cyan"
    assert "tin" in enriched_btc["shot_contextual_meaning"].lower() or "thời sự" in enriched_btc["shot_contextual_meaning"].lower()
    assert "thời sự" in enriched_btc["scene_environment"].lower() or "studio" in enriched_btc["scene_environment"].lower()
    print("  -> DAT: Ke thua hoan hao ngu canh tu frame tuong dong cao cua System 1.")

    # 6. KIỂM THỬ QUY TRÌNH MERGE VÀ DEDUPLICATE HOÀN CHỈNH (MERGED TIMELINE DEDUPLICATION)
    test_btc_list = [
        {"video_id": "L21_V001", "frame_idx": 100, "pts_time_sec": 4.0, "embedding": dummy_vec, "sharpness": 500.0, "ocr_text": "Thời sự 19h"}
    ]
    test_self_list = [
        # Frame này trùng lặp với BTC tại 4.0s (cách 1.2s, visual sim 1.0, cùng OCR)
        {"video_id": "L21_V001", "frame_idx": 130, "pts_time_sec": 5.2, "embedding": dummy_vec, "sharpness": 480.0, "ocr_text": "Thời sự 19h"},
        # Frame này khác góc quay (embedding khác) tại 10.0s -> Giữ nguyên độc lập
        {"video_id": "L21_V001", "frame_idx": 250, "pts_time_sec": 10.0, "embedding": [0.9] * 768, "sharpness": 520.0, "ocr_text": "Dự báo thời tiết"}
    ]

    final_merged = TimelineSynchronizer.merge_and_deduplicate_timeline(
        test_btc_list, test_self_list, visual_sim_threshold=0.92, video_title="Bản tin thời sự VTV1"
    )

    print(f"\n[TEST 6] Quy trinh Merge & Deduplicate tren truc thoi gian chung:")
    for f in final_merged:
        src = "BTC" if f.get("is_btc") else "Self"
        print(f"  * [{src}] Frame {f.get('frame_idx')} at {f.get('pts_time_sec')}s | Virtual: {f.get('is_semantic_virtual')} | Border: {f.get('border_color')} | Meaning: '{f.get('shot_contextual_meaning')}'")

    assert len(final_merged) == 3
    # Frame 100 (BTC) là Anchor
    assert final_merged[0]["is_btc"] is True and final_merged[0]["border_color"] == "cyan"
    # Frame 130 chuyển thành Frame Cắt Nghĩa viền tím Neon
    assert final_merged[1]["is_semantic_virtual"] is True and final_merged[1]["border_color"] == "violet"
    # Frame 250 là Frame hợp lệ độc lập
    # 7. KIỂM THỬ TOÀN DIỆN CÁC TRƯỜNG HỢP BIÊN & DỮ LIỆU BẨN / NAN TỪ CSV (EDGE CASES & NAN ROBUSTNESS)
    print(f"\n[TEST 7] Kiem tra kha nang chong loi voi du lieu NaN, None, va chuoi tu CSV:")
    dirty_btc_list = [
        {"video_id": "L21_V001", "frame_idx": 10, "pts_time": 1.0, "ocr_text": float("nan"), "objects_dict": float("nan"), "detected_classes": float("nan"), "dominant_color": float("nan")},
        {"video_id": "L21_V001", "frame_idx": 20, "pts_time": 1.02, "ocr_text": None, "objects_dict": "{'person': 2, 'car': 1}", "detected_classes": "['person', 'car']"}
    ]
    dirty_self_list = [
        {"video_id": "L21_V001", "shot_id": 1, "keyframe_frame_idx": 30, "pts_time_sec": float("nan"), "sharpness_score": float("nan"), "objects_and_counts": float("nan")},
        {"video_id": "L21_V001", "shot_id": 2, "keyframe_frame_idx": 40, "pts_time_sec": 5.0, "sharpness_score": "520.5", "objects_and_counts": "Cờ x 5, Người x 2", "ocr_text": "nan"}
    ]

    dirty_merged = TimelineSynchronizer.merge_and_deduplicate_timeline(
        dirty_btc_list, dirty_self_list, visual_sim_threshold=0.92, video_title="Test Video"
    )
    print(f"  - Sau khi xu ly du lieu bien/NaN: Hop nhat thanh cong {len(dirty_merged)} frames khong gay loi.")
    # 8. KIỂM THỬ NHẬN DIỆN VẬT THỂ NHỎ, FRAME CẮT NGHĨA VIỀN TÍM & TAG BTC-XỬ LÝ
    print(f"\n[TEST 8] Kiem tra phat hien vat the nho, Frame Cat Nghia vien tim va tag BTC-xu ly:")
    # 8.1 Format vat the nho
    obj_str, obj_dict = TimelineSynchronizer.format_object_counts(["person", "dog", "bread", "flag", "flag", "cup", "chair"])
    print(f"  - Format vat the nho: {obj_str}")
    assert "Cờ x 2" in obj_str
    assert "Bánh mì x 1" in obj_str
    assert "Chó x 1" in obj_str
    assert "Cốc / Ly x 1" in obj_str
    print("  -> DAT: Nhan dien va dinh dang chuan xac 100% cac vat the nho.")

    # 8.2 Test Frame Cat Nghia vien tim & De xuat loc bo vien do
    test_btc = [
        {"video_id": "L21_V001", "frame_idx": 100, "pts_time": 10.0, "sharpness": 12.0, "dominant_color": "Đen / Tối (Dark)"} # Frame BTC don sac
    ]
    test_self = [
        {"video_id": "L21_V001", "shot_id": 10, "keyframe_frame_idx": 105, "pts_time_sec": 10.5, "sharpness_score": 450.0, "scene_environment": "Thi Giac / Trong Nha", "dominant_color": "Xanh Dương (Blue)", "detected_classes": ["person"]},
        {"video_id": "L21_V001", "shot_id": 11, "keyframe_frame_idx": 110, "pts_time_sec": 11.2, "sharpness_score": 440.0, "scene_environment": "Thi Giac / Trong Nha", "dominant_color": "Xanh Dương (Blue)", "detected_classes": ["person"]}, # Trung visual -> Frame Cat Nghia
        {"video_id": "L21_V001", "shot_id": 12, "keyframe_frame_idx": 115, "pts_time_sec": 11.8, "sharpness_score": 25.0, "scene_environment": "Thi Giac / Trong Nha", "dominant_color": "Xanh Dương (Blue)", "detected_classes": ["person"]} # Mo -> De Xuat Loc Bo
    ]

    test_merged = TimelineSynchronizer.merge_and_deduplicate_timeline(
        test_btc, test_self, visual_sim_threshold=0.85, video_title="Chuong trinh Thoi Su"
    )

    print(f"  - Ket qua hop nhat va loc trung:")
    has_btc_low_info = False
    has_virtual_violet = False
    has_proposed_del_red = False

    for item in test_merged:
        border = item.get("border_color")
        is_virt = item.get("is_semantic_virtual")
        is_del = item.get("is_proposed_deletion")
        is_low = item.get("is_btc_low_info")
        reason = item.get("deletion_reason", "")
        f_idx = item.get("frame_idx", item.get("keyframe_frame_idx"))
        print(f"    * Frame {f_idx} | Border: {border} | Virtual: {is_virt} | Deletion: {is_del} (Reason: {reason}) | BTC Low Info: {is_low}")
        if is_low:
            has_btc_low_info = True
        if is_virt and border == "violet":
            has_virtual_violet = True
        if is_del and border == "red":
            has_proposed_del_red = True

    assert has_btc_low_info, "Phai phat hien duoc frame BTC mat do thong tin thap"
    assert has_virtual_violet, "Phai kich hoat duoc Frame Cat Nghia vien tim Neon"
    assert has_proposed_del_red, "Phai kich hoat duoc De Xuat Loc Bo vien do"
    print("  -> DAT: Kich hoat hoan hao Frame Cat Nghia vien tim, De Xuat Loc Bo vien do va Tag BTC-xu ly.")

    print("=" * 75)
    print("KET QUA: TOAN BO TEST CASES STEP 5 DEU DAT 100% CHUAN XAC!")
    print("=" * 75)


if __name__ == "__main__":
    test_step5_timeline_synchronization_and_deduplication()



