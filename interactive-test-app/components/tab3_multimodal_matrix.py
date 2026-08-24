"""
====================================================================================================
COMPONENTS - TAB 3: MULTIMODAL INSPECTION MATRIX (tab3_multimodal_matrix.py)
====================================================================================================

1. MỤC TIÊU VÀ VAI TRÒ:
   - Tab 3 cung cấp ma trận thanh tra đa phương thức 4 góc nhìn chuyên sâu:
     a) Bóc tách OCR 2-Tier (Chân trang vs Toàn cục).
     b) Dual-Stream Vision Embedding (SigLIP SO400M 1152d vs ViSigLIP 768d).
     c) Luồng làm giàu câu truy vấn trung thực qua Từ điển Văn hóa Bản địa (Cultural Lexicon).
     d) Khung hình Cắt nghĩa (Proxy ảo) vs Đề xuất lọc bỏ.

2. ĐẦU VÀO / ĐẦU RA:
   - Đầu vào: `inspector_query_input` (Textbox query), `inspector_video_select` (Dropdown video).
   - Đầu ra: `inspector_html_out` (HTML ma trận soi 4 góc nhìn).
====================================================================================================
"""

from __future__ import annotations
import gradio as gr
from services.config import TARGET_BENCHMARK_VIDEOS
from services.search_service import run_multimodal_step_inspector


def create_tab_multimodal_matrix():
    with gr.TabItem("Bảng So Sánh Đa Phương Thức & Kết Quả Xử Lý Chi Tiết (Multimodal Inspection Matrix)"):
        gr.Markdown("""
        ### Bảng So Sánh Trực Quan Toàn Diện Các Bước Đã Xử Lý (Steps 1 - 6)
        Nhập câu truy vấn và chọn video để đối chiếu trực quan: **Kết quả bóc tách OCR 2-Tier**, **Vision Embedding Tiếng Việt vs Tiếng Anh**, **Luồng Dịch Thuật & Làm Giàu Ngữ Nghĩa**, và **Khung Hình Cắt Nghĩa vs Đề Xuất Lọc Bỏ**.
        """)
        with gr.Row():
            inspector_query_input = gr.Textbox(
                label="1. Nhập Câu Truy Vấn Kiểm Thử (Tiếng Việt)",
                value="Người múa lân trên đường phố có cô gái mặc áo dài đội nón lá",
                placeholder="Ví dụ: Người múa lân, áo dài nón lá, bản tin thời sự 19h..."
            )
            inspector_video_select = gr.Dropdown(
                label="2. Chọn Video Đối Chiếu",
                choices=TARGET_BENCHMARK_VIDEOS,
                value=TARGET_BENCHMARK_VIDEOS[0]
            )
            run_inspect_btn = gr.Button("So Sánh & Phân Tích Đa Phương Thức", variant="primary")

        inspector_html_out = gr.HTML(value="<div style='background-color: #2e3440; padding: 15px; border-radius: 6px; color: #eceff4; text-align: center;'>Nhấn nút <b>'So Sánh & Phân Tích Đa Phương Thức'</b> ở trên để xem ma trận thanh tra Steps 1 - 6...</div>")

        run_inspect_btn.click(
            fn=run_multimodal_step_inspector,
            inputs=[inspector_video_select, inspector_query_input],
            outputs=[inspector_html_out]
        )
        inspector_video_select.change(
            fn=run_multimodal_step_inspector,
            inputs=[inspector_video_select, inspector_query_input],
            outputs=[inspector_html_out]
        )
        inspector_query_input.submit(
            fn=run_multimodal_step_inspector,
            inputs=[inspector_video_select, inspector_query_input],
            outputs=[inspector_html_out]
        )

        return {
            "inspector_query_input": inspector_query_input,
            "inspector_video_select": inspector_video_select,
            "run_inspect_btn": run_inspect_btn,
            "inspector_html_out": inspector_html_out
        }
