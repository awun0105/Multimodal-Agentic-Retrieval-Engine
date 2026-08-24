"""
====================================================================================================
AIC 2026 - INTERACTIVE VISUAL RETRIEVAL COCKPIT & SIDE-BY-SIDE BENCHMARK STUDIO
====================================================================================================

1. MỤC TIÊU VÀ VAI TRÒ CỦA FILE:
   - File này (`app.py`) đóng vai trò là ROOT ASSEMBLER & MAIN ENTRYPOINT cho toàn bộ giao diện 
     Interactive Studio của cuộc thi AIC 2026.
   - Nhiệm vụ cốt lõi:
     a) Khởi tạo và lắp ráp 5 Tabs giao diện người dùng từ tầng `components/`.
     b) Nạp CSS Design Tokens chuẩn Dark Theme từ tầng `templates/`.
     c) Re-export 100% các hàm nghiệp vụ từ tầng `services/` nhằm đảm bảo tính tương thích ngược
        (100% Backward Compatibility) tuyệt đối cho các test suite hiện tại và code bên ngoài.
     d) Tự động kiểm tra và giải phóng cổng mạng (Port 7860/7861), tự động mở trình duyệt.

2. TỔNG QUAN KIẾN TRÚC 3 TẦNG (3-TIER MODULAR ARCHITECTURE):
   ┌────────────────────────────────────────────────────────────────────────────────────────┐
   │                                   TẦNG 1: COMPONENTS (UI)                              │
   │  - tab1_side_by_side.py    : Đối soát dòng thời gian BTC vs System 1 tự xử lý          │
   │  - tab2_storage_hub.py     : Bảng tổng hợp tiết kiệm bộ nhớ WebP & Xuất báo cáo        │
   │  - tab3_multimodal_matrix.py : Bảng soi đa phương thức chi tiết Steps 1 - 6           │
   │  - tab4_hybrid_search.py   : Tìm kiếm KIS Sub-200ms kết hợp SigLIP + FTS5 BM25        │
   │  - tab5_parameter_tuning.py: Studio tùy chỉnh tham số cắt cảnh & lọc độ nét            │
   └───────────────────────────────────────────┬────────────────────────────────────────────┘
                                               │ (Gọi & Lắp Ráp)
   ┌───────────────────────────────────────────▼────────────────────────────────────────────┐
   │                                  ROOT ASSEMBLER: app.py                                │
   │  - build_app()             : Khởi tạo khối Gradio Blocks                               │
   │  - Re-exports              : Giữ 100% tương thích ngược cho unit test và pipeline      │
   │  - Network Port Manager    : Tự động kill process chiếm port & đổi port an toàn        │
   └──────────────────────┬─────────────────────────────────────────────┬───────────────────┘
                          │                                             │
   ┌──────────────────────▼─────────────────────┐  ┌────────────────────▼───────────────────┐
   │        TẦNG 2: SERVICES (DATA & LOGIC)     │  │   TẦNG 3: TEMPLATES (HTML & CSS)       │
   │  - config.py            : Hằng số & Paths  │  │  - theme_tokens.py: Dark Theme CSS     │
   │  - model_service.py     : Loaders AI & Zip │  │  - card_templates.py: HTML Card Frame  │
   │  - appearance_service.py: HSV & Phrasing   │  └────────────────────────────────────────┘
   │  - caption_service.py   : Decoupled Caption│
   │  - timeline_service.py  : Keyframe & Sync  │
   │  - persistence_service.py: WebP Summary    │
   │  - search_service.py    : Inspector Matrix │
   └────────────────────────────────────────────┘

3. HƯỚNG DẪN DÀNH CHO CÁC AI AGENT KẾ NHIỆM (AGENT DEVELOPER GUIDE):
   - Muốn thêm Tab mới:
     1. Tạo file mới trong `components/tabX_new_feature.py` và định nghĩa hàm `create_tab_new_feature()`.
     2. Đăng ký hàm đó vào `components/__init__.py`.
     3. Gọi `create_tab_new_feature()` bên trong hàm `build_app()` của `app.py`.
   - Muốn thêm Nghiệp vụ/Thuật toán mới:
     1. Thêm hàm vào đúng service tương ứng trong `services/` (hoặc tạo service mới).
     2. Re-export hàm đó trong `services/__init__.py` và `app.py` nếu cần dùng rộng rãi.
   - Tuyệt đối không nhồi nhét mã HTML hoặc logic xử lý nặng trực tiếp vào file này!
====================================================================================================
"""

from __future__ import annotations
import os
import sys

# Khóa toàn bộ cảnh báo giải mã C-level của OpenCV và FFmpeg
os.environ["OPENCV_FFMPEG_LOGLEVEL"] = "0"
os.environ["OPENCV_LOG_LEVEL"] = "SILENT"
os.environ["OPENCV_VIDEOIO_DEBUG"] = "0"
os.environ["AV_LOG_FORCE_NOCOLOR"] = "1"

try:
    import cv2
    cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_SILENT)
except Exception:
    pass

import time
import socket
import subprocess
import webbrowser
import threading
from pathlib import Path
import gradio as gr

# --------------------------------------------------------------------------------------------------
# KHỐI 1: THIẾT LẬP ĐƯỜNG DẪN IMPORT HỆ THỐNG
# Đảm bảo Python nhận diện được thư mục interactive-test-app làm module gốc
# --------------------------------------------------------------------------------------------------
APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

# --------------------------------------------------------------------------------------------------
# KHỐI 2: NẠP VÀ RE-EXPORT CÁC HẰNG SỐ & DỊCH VỤ NGHIỆP VỤ (TẦNG 2 - SERVICES)
# Giữ 100% Backward Compatibility cho test_step7_interactive_app_e2e.py và toàn bộ codebase
# --------------------------------------------------------------------------------------------------
from services import (
    # Hằng số và cấu hình đường dẫn
    PROJECT_ROOT,
    DATASET_DIR,
    SQLITE_DB_PATH,
    FAISS_INDEX_PATH,
    BENCHMARK_DIR,
    BENCHMARK_CSV,
    TARGET_BENCHMARK_VIDEOS,
    # Quản lý Model và Dữ liệu ảnh
    get_clip_model,
    get_local_yolo_model,
    format_timestamp,
    parse_duration_limit,
    pil_to_base64_thumb,
    get_video_metadata,
    get_btc_keyframe_image,
    get_self_extracted_image,
    create_placeholder_keyframe_image,
    # Bóc tách ngoại hình, màu sắc HSV và phrasing tự nhiên
    get_object_dominant_color_name,
    format_objects_natural_vietnamese,
    format_objects_natural_english,
    extract_detected_objects_with_appearance,
    analyze_image_full_spectrum,
    analyze_text_and_color,
    calculate_sharpness_fast,
    is_blank_or_solid_monochrome,
    # Sinh miêu tả song ngữ Decoupled Dual-Channel
    generate_keyframe_bilingual_captions,
    # Đồng bộ hóa dòng thời gian và trích xuất keyframe
    extract_video_keyframes_for_duration,
    render_side_by_side_comparison,
    # Quản lý lưu trữ và xuất báo cáo
    get_persistence_summary_table,
    export_persisted_dataset_package,
    clean_storage_cache,
    # Thanh tra đa phương thức Steps 1-6
    run_multimodal_step_inspector,
    export_benchmark_report,
)

# --------------------------------------------------------------------------------------------------
# KHỐI 3: NẠP GIAO DIỆN & CSS DESIGN TOKENS (TẦNG 3 - TEMPLATES)
# --------------------------------------------------------------------------------------------------
from templates import STUDIO_CSS

# --------------------------------------------------------------------------------------------------
# KHỐI 4: NẠP CÁC THÀNH PHẦN GIAO DIỆN TỪNG TAB (TẦNG 1 - COMPONENTS)
# --------------------------------------------------------------------------------------------------
from components import (
    create_tab_side_by_side,
    create_tab_storage_hub,
    create_tab_multimodal_matrix,
    create_tab_hybrid_search,
    create_tab_parameter_tuning,
)


# --------------------------------------------------------------------------------------------------
# KHỐI 5: HÀM LẮP RÁP TOÀN BỘ GIAO DIỆN GRADIO BLOCKS (ROOT ASSEMBLER)
# --------------------------------------------------------------------------------------------------
def build_app():
    """
    Lắp ráp toàn bộ 5 Tabs giao diện vào khối Gradio Blocks thống nhất.
    
    Returns:
        gr.Blocks: Đối tượng Gradio Blocks sẵn sàng khởi chạy qua app.launch().
    """
    with gr.Blocks(title="AIC 2026 - Multimodal Side-by-Side Timeline Studio", css=STUDIO_CSS) as demo:
        gr.Markdown("""
        # AIC 2026 - Side-by-Side Timeline Benchmark & Visual Retrieval Cockpit
        ### Đối chiếu 5 Video Đầu + 5 Video Cuối: Dữ Liệu Ban Tổ Chức (BTC) vs. Hệ Thống Tự Xử Lý (System 1)
        """)

        with gr.Tabs():
            tab1_widgets = create_tab_side_by_side()
            tab2_widgets = create_tab_storage_hub()
            tab3_widgets = create_tab_multimodal_matrix()
            tab4_widgets = create_tab_hybrid_search()
            tab5_widgets = create_tab_parameter_tuning()

        # Tự động nạp timeline video đầu tiên ngay khi mở giao diện
        demo.load(
            fn=render_side_by_side_comparison,
            inputs=[tab1_widgets["benchmark_video_select"], tab1_widgets["duration_mode_select"]],
            outputs=[
                tab1_widgets["btc_gallery_output"],
                tab1_widgets["self_gallery_output"],
                tab1_widgets["side_by_side_html_output"]
            ],
            show_progress="minimal"
        )

    return demo


# --------------------------------------------------------------------------------------------------
# KHỐI 6: QUẢN LÝ TIẾN TRÌNH & CỔNG MẠNG (PORT NETWORK MANAGER)
# Tự động giải phóng cổng hoặc chuyển cổng thông minh khi khởi động
# --------------------------------------------------------------------------------------------------
def is_port_in_use(port: int = 7860) -> bool:
    """Kiểm tra xem cổng port có đang bị tiến trình khác chiếm dụng không."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def get_pid_occupying_port(port: int = 7860) -> int | None:
    """Tìm mã PID của tiến trình đang chiếm cổng port trên hệ điều hành Windows."""
    try:
        output = subprocess.check_output(["netstat", "-ano", "-p", "tcp"], encoding="utf-8")
        for line in output.splitlines():
            if f":{port} " in line and "LISTENING" in line:
                parts = line.strip().split()
                return int(parts[-1])
    except Exception:
        pass
    return None


def kill_process_by_pid(pid: int) -> bool:
    """Dừng tiến trình chiếm dụng port bằng taskkill cưỡng bức."""
    try:
        subprocess.run(["taskkill", "/F", "/PID", str(pid)], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return True
    except Exception:
        return False


# --------------------------------------------------------------------------------------------------
# KHỐI 7: MAIN RUNNER - ĐIỂM KHỞI ĐỘNG CHÍNH CỦA STUDIO
# --------------------------------------------------------------------------------------------------
if __name__ == "__main__":
    port_target = 7860

    if is_port_in_use(port_target):
        pid = get_pid_occupying_port(port_target)
        print("=" * 75)
        print(f"[THONG TIN] Phat hien cong {port_target} dang co tien trinh (PID: {pid}).")
        print(f"[TU DONG] Dang giai phong cong {port_target} de khoi dong phien moi...")
        print("=" * 75)
        if pid:
            kill_process_by_pid(pid)
            time.sleep(0.8)

        if is_port_in_use(port_target):
            p = port_target + 1
            while is_port_in_use(p):
                p += 1
            port_target = p
            print(f"[CHUYEN CONG] Da chuyen sang cong moi: http://127.0.0.1:{port_target}")

    app = build_app()
    target_url = f"http://127.0.0.1:{port_target}"
    print("\n" + "=" * 75)
    print(f"  [KHOI CHAY THANH CONG] MAY CHU RETRIEVAL COCKPIT STUDIO (AIC 2026)")
    print(f"  -> Truy cap truc tiep tai: {target_url}")
    print(f"  -> Trinh duyet web se tu dong mo trong giay lat...")
    print("=" * 75 + "\n")

    def auto_open_browser():
        time.sleep(1.2)
        try:
            webbrowser.open_new_tab(target_url)
        except Exception:
            pass

    threading.Thread(target=auto_open_browser, daemon=True).start()

    app.launch(
        server_name="127.0.0.1",
        server_port=port_target,
        share=False,
        inbrowser=True,
        show_error=True
    )
