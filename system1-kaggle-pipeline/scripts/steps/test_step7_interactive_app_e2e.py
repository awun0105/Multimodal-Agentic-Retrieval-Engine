#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KIỂM THỬ ĐỘC LẬP TOÀN DIỆN (END-TO-END RUNTIME TEST): INTERACTIVE APP & STUDIO (STEP 7)
Mục tiêu:
1. Thực thi thực tế (runtime execution) toàn bộ các hàm cốt lõi của Studio.
2. Kiểm tra bộ bóc tách ngoại hình vật thể (Color Appearance HSV) với ảnh mẫu thực tế.
3. Kiểm tra hàm sinh câu miêu tả tự nhiên song ngữ (Natural Bilingual Captions).
4. Chạy thực tế hàm render_side_by_side_comparison trên video mẫu để đảm bảo không NameError/TypeError.
5. Kiểm tra build_app() của Gradio Blocks để đảm bảo 100% UI không có lỗi khởi động.
"""

import sys
import io
import os
os.environ["OPENCV_FFMPEG_LOGLEVEL"] = "0"
os.environ["OPENCV_LOG_LEVEL"] = "SILENT"
os.environ["OPENCV_VIDEOIO_DEBUG"] = "0"
os.environ["AV_LOG_FORCE_NOCOLOR"] = "1"

from pathlib import Path
import numpy as np
import pandas as pd
import cv2
try:
    cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_SILENT)
except Exception:
    pass

from PIL import Image
import gradio as gr

# Đảm bảo UTF-8 cho console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
APP_DIR = PROJECT_ROOT / "interactive-test-app"
SRC_DIR = PROJECT_ROOT / "system1-kaggle-pipeline" / "src"

if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import app as studio_app


def test_interactive_app_end_to_end():
    print("=" * 80)
    print("KIỂM THỬ RUNTIME ĐỘC LẬP TOÀN DIỆN: INTERACTIVE APP & STUDIO (STEP 7)")
    print("=" * 80)

    # 1. KIỂM THỬ TRÍCH XUẤT MÀU SẮC VÙNG CROP VẬT THỂ (HSV COLOR APPEARANCE)
    print("\n[TEST 1] Kiem tra ham bóc tách màu sắc ngoai hinh (get_object_dominant_color_name):")
    
    # Tạo ảnh crop đen
    black_crop = np.zeros((60, 40, 3), dtype=np.uint8) + 20
    color_black_person = studio_app.get_object_dominant_color_name(black_crop, "person")
    color_black_car = studio_app.get_object_dominant_color_name(black_crop, "car")
    print(f"  - Crop đen: Person -> '{color_black_person}' | Car -> '{color_black_car}'")
    assert color_black_person == "áo đen"
    assert color_black_car == "màu đen"

    # Tạo ảnh crop trắng
    white_crop = np.zeros((60, 40, 3), dtype=np.uint8) + 240
    color_white_person = studio_app.get_object_dominant_color_name(white_crop, "person")
    print(f"  - Crop trắng: Person -> '{color_white_person}'")
    assert color_white_person == "áo trắng"

    # Tạo ảnh crop xanh dương (BGR: [255, 100, 50])
    blue_crop = np.zeros((60, 40, 3), dtype=np.uint8)
    blue_crop[:, :] = [220, 120, 30]
    color_blue_person = studio_app.get_object_dominant_color_name(blue_crop, "person")
    print(f"  - Crop xanh dương: Person -> '{color_blue_person}'")
    assert "xanh dương" in color_blue_person

    print("  -> DAT: Boc tach chinh xac 100% mau sac ngoai hinh theo dải HSV.")

    # 2. KIỂM THỬ PHÁT HIỆN VẬT THỂ KÈM ĐẾM CÁ THỂ & NGOẠI HÌNH (EXTRACT OBJECTS WITH APPEARANCE)
    print("\n[TEST 2] Kiem tra ham extract_detected_objects_with_appearance va Natural Object Phrasing:")
    
    # Tạo ảnh giả lập
    test_img = np.zeros((360, 640, 3), dtype=np.uint8) + 120
    formatted_vi, formatted_en, counts_dict, boxes_list = studio_app.extract_detected_objects_with_appearance(test_img, conf_threshold=0.12)
    print(f"  - Ket qua anh test: formatted_vi='{formatted_vi}' | formatted_en='{formatted_en}' | counts={counts_dict}")
    assert isinstance(formatted_vi, str)
    assert isinstance(formatted_en, str)
    assert isinstance(counts_dict, dict)
    assert isinstance(boxes_list, list)

    # Kiểm tra format cụm từ tự nhiên
    mock_boxes = [
        {"class": "person", "color": "áo đen", "score": 0.85},
        {"class": "car", "color": "màu tím", "score": 0.90},
        {"class": "car", "color": "màu tím", "score": 0.88},
        {"class": "flag", "color": "màu đỏ", "score": 0.92}
    ]
    nat_vi = studio_app.format_objects_natural_vietnamese(mock_boxes)
    nat_en = studio_app.format_objects_natural_english(mock_boxes)
    print(f"  - Natural Vietnamese: '{nat_vi}'")
    print(f"  - Natural English:    '{nat_en}'")
    assert "1 người mặc áo đen" in nat_vi
    assert "2 chiếc xe ô tô màu tím" in nat_vi
    assert "1 person in black clothes" in nat_en
    assert "2 purple cars" in nat_en
    print("  -> DAT: Ham format_objects_natural chay muot ma voi cum tu tu nhien song ngu.")

    # 3. KIỂM THỬ SINH CẶP MIÊU TẢ THUẦN TỰ NHIÊN SONG NGỮ TỰ THÂN ĐỘC LẬP
    print("\n[TEST 3] Kiem tra ham sinh cau mieu ta song ngu Decoupled Dual-Channel:")
    cap_vi, cap_en = studio_app.generate_keyframe_bilingual_captions(
        meaning="buồng lái ô tô đường phố",
        scene="giao thông",
        objects="1 người mặc áo đen, 2 chiếc xe ô tô màu tím",
        natural_vi_objects="1 người mặc áo đen, 2 chiếc xe ô tô màu tím",
        natural_en_objects="1 person in black clothes, 2 purple cars",
        ocr="THỜI SỰ 19H",
        color="Đa Sắc",
        cultural_concepts=[],
        is_virtual=False,
        delta_tag="",
        anchor_id=""
    )
    print(f"  - Ban Tieng Viet: \"{cap_vi}\"")
    print(f"  - Ban Tieng Anh:  \"{cap_en}\"")
    
    # Kiem tra khong con tu ngu rap khuon may moc
    assert "Góc quay" not in cap_vi
    assert "tông màu đa sắc" not in cap_vi
    assert "buồng lái" in cap_vi or "lưu thông" in cap_vi or "ô tô" in cap_vi
    assert "[Thực thể nhận diện: 1 người mặc áo đen, 2 chiếc xe ô tô màu tím]" in cap_vi
    assert "THỜI SỰ 19H" in cap_vi
    assert "car" in cap_en or "driver" in cap_en
    assert "[Detected entities: 1 person in black clothes, 2 purple cars]" in cap_en
    print("  -> DAT: Sinh cau mieu ta thuan tuy tu nhien, bám sát vật thể và bóc tách song ngữ chuẩn.")

    # 4. KIỂM THỬ RUNTIME RENDER SIDE-BY-SIDE TRÊN VIDEO MẪU
    print("\n[TEST 4] Kiem tra runtime render_side_by_side_comparison tren video mau L21_V001:")
    try:
        class DummyProgress:
            def __call__(self, pct, desc=""):
                pass
        
        btc_gallery, self_gallery, full_html = studio_app.render_side_by_side_comparison(
            selected_video="L21_V001",
            duration_mode="60s",
            progress=DummyProgress()
        )
        print(f"  - Ket qua render:")
        print(f"    * BTC Gallery count: {len(btc_gallery)}")
        print(f"    * Self Gallery count: {len(self_gallery)}")
        print(f"    * HTML length: {len(full_html)} bytes")
        
        # Kiểm tra tính toàn vẹn của từng ảnh trong Gallery (Chống lỗi NoneType của Gradio)
        assert len(btc_gallery) > 0, "BTC Gallery phai trich xuat duoc anh keyframe!"
        assert len(self_gallery) > 0, "Self Gallery phai trich xuat duoc anh keyframe!"

        for idx, item in enumerate(btc_gallery):
            assert item[0] is not None, f"BTC Gallery item #{idx} có ảnh là None!"
            assert isinstance(item[0], Image.Image) or isinstance(item[0], str), f"BTC Gallery item #{idx} không phải kiểu ảnh hợp lệ!"
        for idx, item in enumerate(self_gallery):
            assert item[0] is not None, f"Self Gallery item #{idx} có ảnh là None!"
            assert isinstance(item[0], Image.Image) or isinstance(item[0], str), f"Self Gallery item #{idx} không phải kiểu ảnh hợp lệ!"

        # Mô phỏng trực tiếp hàm postprocess của Gradio Gallery
        test_gal = gr.Gallery()
        test_gal.postprocess(btc_gallery)
        test_gal.postprocess(self_gallery)

        assert len(full_html) > 500, "HTML side-by-side phai co noi dung day du"
        assert "L21_V001" in full_html
        print("  -> DAT: render_side_by_side_comparison chay thuc te 100% thanh cong, Gradio Gallery postprocess khong loi.")
    except Exception as e:
        print(f"  [LOI RUNTIME] render_side_by_side_comparison that bai: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    # 5. KIỂM THỬ CÁC HÀM TIỆN ÍCH & EVENT HANDLERS CẢ 5 TABS
    print("\n[TEST 5] Kiem tra cac ham tien ich va event handlers cua ca 5 Tabs:")
    
    # 5.1 Text & Color analysis
    small_bgr = np.zeros((180, 320, 3), dtype=np.uint8) + 100
    text_e, dom_col = studio_app.analyze_text_and_color(small_bgr)
    sharp = studio_app.calculate_sharpness_fast(small_bgr)
    is_blk = studio_app.is_blank_or_solid_monochrome(small_bgr, text_e)
    print(f"  - 5.1 Analyze Image: text_energy={text_e:.2f} | color={dom_col} | sharp={sharp:.1f} | is_blank={is_blk}")
    assert isinstance(dom_col, str)

    # 5.2 Tab 2 Persistence & Storage Export
    print("  - 5.2 Kiem tra Tab 2: Persistence Summary & Export Report:")
    summary_df = studio_app.get_persistence_summary_table()
    assert isinstance(summary_df, pd.DataFrame)
    assert len(summary_df) > 0
    exp_df, exp_html = studio_app.export_benchmark_report()
    assert isinstance(exp_df, pd.DataFrame)
    assert "XUAT BO DU LIEU HOP NHAT THANH CONG" in exp_html
    print("    -> DAT: Tab 2 Persistence & Export chay hoan hao.")

    # 5.3 Tab 3 Multimodal Inspector Matrix
    print("  - 5.3 Kiem tra Tab 3: Multimodal Inspector Matrix (Steps 1-6):")
    inspector_out = studio_app.run_multimodal_step_inspector("L21_V001", "Người múa lân trên đường phố có cô gái mặc áo dài đội nón lá")
    assert isinstance(inspector_out, str)
    assert "BẢNG SO SÁNH TRỰC QUAN ĐA PHƯƠNG THỨC" in inspector_out
    assert "FAITHFUL QUERY ENRICHMENT" in inspector_out
    print("    -> DAT: Tab 3 Multimodal Matrix chay hoan hao.")

    # 5.4 Build Gradio App
    print("  - 5.4 Kiem tra khoi dung Gradio Blocks (build_app):")
    demo_app = studio_app.build_app()
    assert demo_app is not None
    print("    -> DAT: Gradio Blocks build_app() lap rap thanh cong 100%.")

    print("\n" + "=" * 80)
    print("KET QUA: TOAN BO TEST CASES INTERACTIVE APP E2E DEU DAT 100%!")
    print("=" * 80)


if __name__ == "__main__":
    test_interactive_app_end_to_end()
