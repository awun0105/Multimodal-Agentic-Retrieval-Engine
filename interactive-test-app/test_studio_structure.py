"""
====================================================================================================
KIỂM THỬ TÍNH TOÀN VẸN CẤU TRÚC 3 TẦNG: INTERACTIVE COCKPIT STUDIO (AIC 2026)
====================================================================================================

Tệp kiểm thử độc lập (Structural & Architectural Integrity Test):
- Kiểm tra tính toàn vẹn của cấu trúc thư mục (Components, Services, Templates, Plans).
- Kiểm tra import độc lập không phụ thuộc vòng tròn (Circular Import Check).
- Kiểm tra hợp đồng dữ liệu (Data Contracts) của từng Service.
- Kiểm tra khởi tạo độc lập của từng Tab Component trong Gradio Blocks.
- Kiểm tra 100% Re-export Backward Compatibility trong app.py.
====================================================================================================
"""

from __future__ import annotations
import sys
import os
import io
import time
import numpy as np
import pandas as pd
from pathlib import Path

# Đảm bảo UTF-8 console cho Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Thiết lập đường dẫn import
APP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = APP_DIR.parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def test_structural_and_architectural_integrity():
    print("=" * 85)
    print("KIEM TRA TOAN VEN CAU TRUC 3 TANG: INTERACTIVE COCKPIT STUDIO (AIC 2026)")
    print("=" * 85)

    # ----------------------------------------------------------------------------------------------
    # TEST 1: KIỂM TRA SỰ TỒN TẠI CỦA CÁC THƯ MỤC VÀ TỆP CỐT LÕI
    # ----------------------------------------------------------------------------------------------
    print("\n[TEST 1] Kiem tra su ton tai cua cac thu muc va tep tin kien truc:")
    required_dirs = [
        APP_DIR / "services",
        APP_DIR / "components",
        APP_DIR / "templates",
        APP_DIR / "plans"
    ]
    for d in required_dirs:
        assert d.exists() and d.is_dir(), f"Thư mục thiếu: {d}"
        print(f"  - Thu muc: {d.name}/ -> TON TAI [OK]")

    required_files = [
        APP_DIR / "app.py",
        APP_DIR / "services" / "__init__.py",
        APP_DIR / "services" / "config.py",
        APP_DIR / "services" / "model_service.py",
        APP_DIR / "services" / "appearance_service.py",
        APP_DIR / "services" / "caption_service.py",
        APP_DIR / "services" / "timeline_service.py",
        APP_DIR / "services" / "persistence_service.py",
        APP_DIR / "services" / "search_service.py",
        APP_DIR / "templates" / "__init__.py",
        APP_DIR / "templates" / "theme_tokens.py",
        APP_DIR / "templates" / "card_templates.py",
        APP_DIR / "components" / "__init__.py",
        APP_DIR / "components" / "tab1_side_by_side.py",
        APP_DIR / "components" / "tab2_storage_hub.py",
        APP_DIR / "components" / "tab3_multimodal_matrix.py",
        APP_DIR / "components" / "tab4_hybrid_search.py",
        APP_DIR / "components" / "tab5_parameter_tuning.py",
        APP_DIR / "plans" / "STUDIO_MODULAR_ARCHITECTURE_AND_EXPANSION_PLAN.md",
    ]
    for f in required_files:
        assert f.exists() and f.is_file(), f"Tệp tin thiếu: {f}"
        print(f"  - Tep tin: {f.relative_to(APP_DIR)} ({f.stat().st_size} bytes) -> TON TAI [OK]")
    print("  -> DAT: 100% thu muc va tep tin kien truc hop le.")

    # ----------------------------------------------------------------------------------------------
    # TEST 2: KIỂM TRA NẠP ĐỘC LẬP TỪNG SERVICE TRONG TẦNG SERVICES (TẦNG 2)
    # ----------------------------------------------------------------------------------------------
    print("\n[TEST 2] Kiem tra nap doc lap tung Service trong tang services/:")
    import services.config as cfg
    assert len(cfg.TARGET_BENCHMARK_VIDEOS) == 10
    print(f"  - 2.1 config.py: 10 Target Videos -> [OK]")

    import services.model_service as mdl
    assert mdl.format_timestamp(75.0) == "01:15"
    assert mdl.parse_duration_limit("60s") == 60.0
    print(f"  - 2.2 model_service.py: format_timestamp & parse_duration -> [OK]")

    import services.appearance_service as app_srv
    test_crop_black = np.zeros((50, 50, 3), dtype=np.uint8) + 10
    col_black = app_srv.get_object_dominant_color_name(test_crop_black, "person")
    assert col_black == "áo đen"
    nat_vi = app_srv.format_objects_natural_vietnamese([
        {"class": "person", "color": "áo đen"},
        {"class": "car", "color": "màu tím"},
        {"class": "car", "color": "màu tím"}
    ])
    assert "1 người mặc áo đen" in nat_vi and "2 chiếc xe ô tô màu tím" in nat_vi
    print(f"  - 2.3 appearance_service.py: HSV Color & Natural Phrasing -> [OK]")

    import services.caption_service as cap_srv
    cap_vi, cap_en = cap_srv.generate_keyframe_bilingual_captions(
        meaning="Bản tin thời sự",
        scene="Trường quay",
        natural_vi_objects="1 người mặc áo đen",
        natural_en_objects="1 person in black clothes"
    )
    assert "[Thực thể nhận diện: 1 người mặc áo đen]" in cap_vi
    assert "[Detected entities: 1 person in black clothes]" in cap_en
    print(f"  - 2.4 caption_service.py: Decoupled Dual-Channel Captions -> [OK]")

    import services.timeline_service as time_srv
    assert hasattr(time_srv, "render_side_by_side_comparison")
    print(f"  - 2.5 timeline_service.py: render_side_by_side_comparison -> [OK]")

    import services.persistence_service as per_srv
    summary_df = per_srv.get_persistence_summary_table()
    assert isinstance(summary_df, pd.DataFrame)
    print(f"  - 2.6 persistence_service.py: get_persistence_summary_table -> [OK]")

    import services.search_service as search_srv
    assert hasattr(search_srv, "run_multimodal_step_inspector")
    print(f"  - 2.7 search_service.py: run_multimodal_step_inspector -> [OK]")
    print("  -> DAT: 100% Services hoat dong doc lap khong loi.")

    # ----------------------------------------------------------------------------------------------
    # TEST 3: KIỂM TRA TEMPLATES & CSS THEME (TẦNG 3)
    # ----------------------------------------------------------------------------------------------
    print("\n[TEST 3] Kiem tra Templates va CSS Theme (tang templates/):")
    from templates.theme_tokens import STUDIO_CSS
    assert len(STUDIO_CSS) > 200
    assert ".side-by-side-card" in STUDIO_CSS
    print(f"  - 3.1 theme_tokens.py: CSS Dark Theme length = {len(STUDIO_CSS)} chars -> [OK]")

    from templates.card_templates import (
        render_timeline_center_cell,
        render_continuous_holding_row,
        render_side_by_side_header
    )
    c_cell = render_timeline_center_cell(10, 15, "00:10 -> 00:15", "https://youtu.be/demo")
    assert "00:10" in c_cell and "Xem YouTube" in c_cell
    h_row = render_continuous_holding_row(20, 25, "00:20 -> 00:25", "https://youtu.be/demo")
    assert "Cú máy tĩnh liên tục" in h_row
    h_banner = render_side_by_side_header(
        selected_video="L21_V001",
        title="Bản tin thời sự 19h",
        author="HTV",
        watch_url="https://youtu.be/demo",
        total_time_str="25:13",
        total_video_sec=1513.9,
        latency_str="45ms",
        duration_mode="60s",
        text_bumper_count=2,
        btc_count=10,
        total_btc_frames=120,
        self_count=14
    )
    assert "L21_V001" in h_banner and "Bản tin thời sự 19h" in h_banner
    print(f"  - 3.2 card_templates.py: HTML Renderers -> [OK]")
    print("  -> DAT: 100% Templates hoat dong chuan xac.")

    # ----------------------------------------------------------------------------------------------
    # TEST 4: KIỂM TRA KHỞI TẠO TỪNG TAB COMPONENT (TẦNG 1) TRONG GRADIO BLOCKS
    # ----------------------------------------------------------------------------------------------
    print("\n[TEST 4] Kiem tra khoi tao tung Tab Component trong Gradio Blocks:")
    import gradio as gr
    from components import (
        create_tab_side_by_side,
        create_tab_storage_hub,
        create_tab_multimodal_matrix,
        create_tab_hybrid_search,
        create_tab_parameter_tuning
    )

    with gr.Blocks() as test_block:
        with gr.Tabs():
            t1 = create_tab_side_by_side()
            assert "benchmark_video_select" in t1 and "side_by_side_html_output" in t1
            print("  - 4.1 Tab 1 Side-by-Side: Khoi tao Widgets thanh cong -> [OK]")

            t2 = create_tab_storage_hub()
            assert "persistence_table_output" in t2
            print("  - 4.2 Tab 2 Storage Hub: Khoi tao Widgets thanh cong -> [OK]")

            t3 = create_tab_multimodal_matrix()
            assert "inspector_html_out" in t3
            print("  - 4.3 Tab 3 Multimodal Matrix: Khoi tao Widgets thanh cong -> [OK]")

            t4 = create_tab_hybrid_search()
            assert "q_gallery" in t4
            print("  - 4.4 Tab 4 Hybrid Search: Khoi tao Widgets thanh cong -> [OK]")

            t5 = create_tab_parameter_tuning()
            assert "s1_btn" in t5
            print("  - 4.5 Tab 5 Parameter Tuning: Khoi tao Widgets thanh cong -> [OK]")
    print("  -> DAT: 100% Tab Components lap rap muot ma.")

    # ----------------------------------------------------------------------------------------------
    # TEST 5: KIỂM TRA TOÀN DIỆN ENTRYPOINT VÀ RE-EXPORTS (app.py)
    # ----------------------------------------------------------------------------------------------
    print("\n[TEST 5] Kiem tra Entrypoint app.py va 100% Re-export Backward Compatibility:")
    import app as studio_app
    re_exported_symbols = [
        "PROJECT_ROOT", "DATASET_DIR", "SQLITE_DB_PATH", "FAISS_INDEX_PATH", "BENCHMARK_DIR",
        "TARGET_BENCHMARK_VIDEOS", "get_clip_model", "get_local_yolo_model", "format_timestamp",
        "parse_duration_limit", "pil_to_base64_thumb", "get_video_metadata", "get_btc_keyframe_image",
        "get_self_extracted_image", "create_placeholder_keyframe_image", "get_object_dominant_color_name", "format_objects_natural_vietnamese",
        "format_objects_natural_english", "extract_detected_objects_with_appearance",
        "analyze_image_full_spectrum", "analyze_text_and_color", "calculate_sharpness_fast",
        "is_blank_or_solid_monochrome", "generate_keyframe_bilingual_captions",
        "extract_video_keyframes_for_duration", "render_side_by_side_comparison",
        "get_persistence_summary_table", "export_persisted_dataset_package", "clean_storage_cache",
        "run_multimodal_step_inspector", "export_benchmark_report", "build_app", "STUDIO_CSS"
    ]
    for sym in re_exported_symbols:
        assert hasattr(studio_app, sym), f"app.py thiếu re-export biểu tượng: {sym}"
        print(f"  - Re-export: studio_app.{sym} -> [OK]")

    demo_app = studio_app.build_app()
    assert isinstance(demo_app, gr.Blocks)
    print("  - build_app() tra ve hop le doi tuong gr.Blocks -> [OK]")
    print("  -> DAT: 100% Re-exports va Entrypoint dat chuan Backward Compatibility.")

    print("\n" + "=" * 85)
    print("KET QUA: TOAN BO KIEM TRA KIEN TRUC & CAU TRUC 3 TANG DAT 100% ALL PASS!")
    print("=" * 85)


if __name__ == "__main__":
    test_structural_and_architectural_integrity()
