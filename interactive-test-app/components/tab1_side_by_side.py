"""
====================================================================================================
COMPONENTS - TAB 1: SIDE-BY-SIDE TIMELINE BENCHMARK (tab1_side_by_side.py)
====================================================================================================

1. MỤC TIÊU VÀ VAI TRÒ:
   - Tab 1 cho phép người dùng đối soát trực quan từng giây giữa:
     * Cột Trái: Keyframe gốc của Ban Tổ Chức (Ground Truth).
     * Cột Giữa: Trục thời gian chuẩn và nút nhảy thẳng đến giây trên YouTube.
     * Cột Phải: Keyframe do System 1 tự trích xuất, phân loại Anchor (Lá mạ), Frame Cắt Nghĩa (Tím),
       Đề xuất lọc bỏ (Đỏ), và Hàng giữ tĩnh liên tục (Duy trì góc máy).
   - Khi nhấp vào bất kỳ ảnh nào trong Gallery, hệ thống tự động mở thẻ Metadata & Vector Embedding chi tiết.

2. ĐẦU VÀO / ĐẦU RA:
   - Đầu vào: `benchmark_video_select` (Dropdown video), `duration_mode_select` (Radio thời lượng).
   - Đầu ra: `btc_gallery_output`, `self_gallery_output`, `side_by_side_html_output`, `selected_frame_detail`.
====================================================================================================
"""

from __future__ import annotations
import gradio as gr
from services.config import TARGET_BENCHMARK_VIDEOS
from services.model_service import get_video_metadata
from services.timeline_service import render_side_by_side_comparison


def create_tab_side_by_side():
    with gr.TabItem("So Sanh Truc Quan Side-by-Side (BTC vs. System 1 Tu Xu Ly)"):
        gr.Markdown("""
        ### Bang Doi Soat Dong Thoi Gian (Timeline Comparison)
        Chon video va **Pham vi Thoi luong** de xem:
        """)

        with gr.Row():
            with gr.Column(scale=2):
                benchmark_video_select = gr.Dropdown(
                    label="1. Chon Video Doi Soat",
                    choices=TARGET_BENCHMARK_VIDEOS,
                    value=TARGET_BENCHMARK_VIDEOS[0]
                )
            with gr.Column(scale=2):
                duration_mode_select = gr.Radio(
                    label="2. Pham Vi Thoi Luong Hien Thi",
                    choices=[
                        ("60 Giay Dau (1 Phut Mau)", "60s"),
                        ("3 Phut Dau (180s)", "180s"),
                        ("5 Phut Dau (300s)", "300s"),
                        ("Toan Bo Video (Full Video)", "full")
                    ],
                    value="60s"
                )
            with gr.Column(scale=1):
                compare_btn = gr.Button("Nap & So Sanh Timeline", variant="primary")
                cancel_btn = gr.Button("Bo Qua / Huy Hang Doi", variant="stop")

        side_by_side_html_output = gr.HTML()

        with gr.Row():
            with gr.Column(scale=1):
                gr.Markdown("#### Nua Trai: Luoi Keyframe Goc Cua Ban To Chuc (BTC)")
                btc_gallery_output = gr.Gallery(label="BTC Keyframes", columns=3, height="auto")
            with gr.Column(scale=1):
                gr.Markdown("#### Nua Phai: Luoi Keyframe Do System 1 Tu Xu Ly (Sac Net Nhat)")
                self_gallery_output = gr.Gallery(label="System 1 Keyframes", columns=3, height="auto")

        selected_frame_detail = gr.HTML("<div style='background-color: #2e3440; padding: 12px; border-radius: 6px; color: #d8dee9; font-style: italic; text-align: center;'>Nhap vao bat ky anh Keyframe nao o tren de xem day du Metadata chi tiet va link xem video...</div>")

        def on_select_btc_image(evt: gr.SelectData, current_video: str):
            meta = get_video_metadata(current_video)
            watch_url = meta.get("watch_url", f"https://www.youtube.com/watch?v={current_video}")
            caption = evt.value.get("caption", "") if isinstance(evt.value, dict) else str(evt.value)
            
            return f"""
            <div style="border: 2px solid #88c0d0; border-radius: 8px; padding: 15px; background-color: #242933; color: #eceff4; margin-top: 10px; font-family: sans-serif;">
                <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #434c5e; padding-bottom: 8px; margin-bottom: 10px;">
                    <h4 style="margin: 0; color: #88c0d0; font-size: 15px;">[CHI TIẾT METADATA & FAISS EMBEDDING - KEYFRAME BAN TỔ CHỨC (BTC)]: {caption}</h4>
                    <span style="background-color: #3b4252; color: #8be9fd; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-family: monospace;">Mã Nộp Bài: {current_video}</span>
                </div>
                
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px; font-size: 12px; margin-bottom: 10px;">
                    <div style="background-color: #2e3440; padding: 10px; border-radius: 4px; border-left: 3px solid #8be9fd;">
                        <div style="color: #8be9fd; font-weight: bold; margin-bottom: 4px;">1. CẤU TRÚC VECTOR & FAISS EMBEDDING</div>
                        <div><b>Vector Model En:</b> SigLIP SO400M (1152 chiều - 384x384 HD)</div>
                        <div><b>Vector Model Vi:</b> ViSigLIP-OT (768 chiều - 224x224)</div>
                        <div><b>Chuẩn Hóa Không Gian:</b> L2 Normalization (Dot Product = Cosine Similarity)</div>
                        <div><b>SQLite Vector Map:</b> <code>vector_map(vector_id -> video_ref, frame_idx)</code></div>
                    </div>
                    <div style="background-color: #2e3440; padding: 10px; border-radius: 4px; border-left: 3px solid #a3be8c;">
                        <div style="color: #a3be8c; font-weight: bold; margin-bottom: 4px;">2. TRƯỜNG THÔNG TIN ĐA PHƯƠNG THỨC</div>
                        <div><b>Video:</b> {meta.get('title')} ({meta.get('author')})</div>
                        <div><b>Nguồn dữ liệu:</b> Gói dữ liệu gốc Ban tổ chức (Ground Truth)</div>
                        <div><b>Mô hình tra cứu kết hợp:</b> RRF Multi-Stream Consensus (Dense + Sparse)</div>
                        <div><b>Trạng thái phân loại:</b> Đã đồng bộ Timeline và liên kết mốc thời gian</div>
                    </div>
                </div>

                <div style="display: flex; gap: 10px; align-items: center;">
                    <a href="{watch_url}" target="_blank" style="background-color: #bf616a; color: white; padding: 6px 14px; border-radius: 4px; text-decoration: none; font-weight: bold; font-size: 12px;">
                        [>] Mở Xem Trực Tiếp Trên YouTube
                    </a>
                    <span style="color: #d8dee9; font-size: 11px; font-style: italic;">
                        Lưu ý: Khung hình BTC được dùng làm mốc quy chiếu (Anchor Reference) để kiểm duyệt và làm giàu timeline.
                    </span>
                </div>
            </div>
            """

        def on_select_self_image(evt: gr.SelectData, current_video: str):
            meta = get_video_metadata(current_video)
            watch_url = meta.get("watch_url", f"https://www.youtube.com/watch?v={current_video}")
            caption = evt.value.get("caption", "") if isinstance(evt.value, dict) else str(evt.value)
            
            return f"""
            <div style="border: 2px solid #a3be8c; border-radius: 8px; padding: 15px; background-color: #242933; color: #eceff4; margin-top: 10px; font-family: sans-serif;">
                <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #434c5e; padding-bottom: 8px; margin-bottom: 10px;">
                    <h4 style="margin: 0; color: #a3be8c; font-size: 15px;">[CHI TIẾT METADATA & FAISS EMBEDDING - KEYFRAME SYSTEM 1 TỰ XỬ LÝ]: {caption}</h4>
                    <span style="background-color: #3b4252; color: #a3be8c; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-family: monospace;">Mã Nộp Bài: {current_video}</span>
                </div>

                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px; font-size: 12px; margin-bottom: 10px;">
                    <div style="background-color: #2e3440; padding: 10px; border-radius: 4px; border-left: 3px solid #bd93f9;">
                        <div style="color: #bd93f9; font-weight: bold; margin-bottom: 4px;">1. CẤU TRÚC VECTOR & FAISS EMBEDDING</div>
                        <div><b>Dual-Stream Embed:</b> <code>SigLIP SO400M (1152d) + ViSigLIP (768d)</code></div>
                        <div><b>Lớp Đọc Từ Hiếm:</b> Tự động ánh xạ Fact-Grounded Visual Anchors bản địa</div>
                        <div><b>Bộ Lọc Frame Cắt Nghĩa:</b> Proxy trỏ về Anchor Frame gốc, Zero Disk Waste</div>
                        <div><b>Chỉ Số Lọc Bỏ:</b> Nhận diện trùng lặp thị giác >= 0.92 hoặc ảnh mờ</div>
                    </div>
                    <div style="background-color: #2e3440; padding: 10px; border-radius: 4px; border-left: 3px solid #ebcb8b;">
                        <div style="color: #ebcb8b; font-weight: bold; margin-bottom: 4px;">2. TRƯỜNG DỮ LIỆU ĐÃ BÓC TÁCH & LÀM GIÀU</div>
                        <div><b>Vật thể YOLOv8:</b> Đếm số lượng định lượng (`Cờ x 2, Người x 1, Chó x 1...`)</div>
                        <div><b>OCR 2-Tier:</b> Lower-third chân trang + Deep VLM Vintern-1B + Jaccard Dedup</div>
                        <div><b>Video Genre:</b> Tự động điều chỉnh trọng số RRF (Dense Weight vs Sparse Weight)</div>
                        <div><b>Độ Nét Laplacian:</b> Tự động fallback làm nét khi gặp cú máy mờ chuyển động</div>
                    </div>
                </div>

                <div style="display: flex; gap: 10px; align-items: center;">
                    <a href="{watch_url}" target="_blank" style="background-color: #bf616a; color: white; padding: 6px 14px; border-radius: 4px; text-decoration: none; font-weight: bold; font-size: 12px;">
                        [>] Mở Xem Trực Tiếp Trên YouTube
                    </a>
                    <span style="color: #50fa7b; font-size: 11px; font-weight: bold;">
                        [OK] Khung hình đã được trích xuất sắc nét nhất, làm giàu toàn diện và nạp sẵn vào FAISS Index!
                    </span>
                </div>
            </div>
            """

        btc_gallery_output.select(fn=on_select_btc_image, inputs=[benchmark_video_select], outputs=[selected_frame_detail])
        self_gallery_output.select(fn=on_select_self_image, inputs=[benchmark_video_select], outputs=[selected_frame_detail])

        compare_event = compare_btn.click(
            fn=render_side_by_side_comparison,
            inputs=[benchmark_video_select, duration_mode_select],
            outputs=[btc_gallery_output, self_gallery_output, side_by_side_html_output],
            show_progress="minimal"
        )
        sel_event = benchmark_video_select.change(
            fn=render_side_by_side_comparison,
            inputs=[benchmark_video_select, duration_mode_select],
            outputs=[btc_gallery_output, self_gallery_output, side_by_side_html_output],
            show_progress="minimal",
            cancels=[compare_event]
        )
        dur_event = duration_mode_select.change(
            fn=render_side_by_side_comparison,
            inputs=[benchmark_video_select, duration_mode_select],
            outputs=[btc_gallery_output, self_gallery_output, side_by_side_html_output],
            show_progress="minimal",
            cancels=[compare_event, sel_event]
        )

        cancel_btn.click(
            fn=None,
            inputs=None,
            outputs=None,
            cancels=[compare_event, sel_event, dur_event]
        )

        return {
            "benchmark_video_select": benchmark_video_select,
            "duration_mode_select": duration_mode_select,
            "btc_gallery_output": btc_gallery_output,
            "self_gallery_output": self_gallery_output,
            "side_by_side_html_output": side_by_side_html_output
        }
