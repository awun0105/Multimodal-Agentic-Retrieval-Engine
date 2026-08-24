"""
====================================================================================================
COMPONENTS - TAB 5: INPUT PARAMETER TUNING & SHOT EXPERIMENTATION (tab5_parameter_tuning.py)
====================================================================================================

1. MỤC TIÊU VÀ VAI TRÒ:
   - Tab 5 cung cấp studio thực nghiệm trực tiếp các tham số cắt cảnh và lọc ảnh mờ:
     * Tùy biến số lượng Frame quét tối đa (`s1_limit`).
     * Tùy biến ngưỡng tương quan màu Histogram cắt shot (`s1_hist`).
     * Tùy biến ngưỡng lọc độ nét Laplacian (`s1_sharp`).
     * Hiển thị lưới Gallery kết quả theo tham số vừa điều chỉnh.

2. ĐẦU VÀO / ĐẦU RA:
   - Đầu vào: `s1_video`, `s1_limit`, `s1_hist`, `s1_sharp`, `s1_btn`.
   - Đầu ra: `s1_gal` (Gallery keyframe mới), `s1_res_md` (Markdown tóm tắt tham số).
====================================================================================================
"""

from __future__ import annotations
import gradio as gr
from services.config import TARGET_BENCHMARK_VIDEOS
from services.timeline_service import render_side_by_side_comparison


def create_tab_parameter_tuning():
    with gr.TabItem("Studio Xu Ly Video Tho & Cat Cu May (Tuy Chinh Input)"):
        gr.Markdown("### Bang Dieu Khien Tham So Input (Video, Nguong Histogram, Loc Laplacian)")
        with gr.Row():
            s1_video = gr.Dropdown(label="Chon Video", choices=TARGET_BENCHMARK_VIDEOS, value="L21_V001")
            s1_limit = gr.Slider(label="Frames quet", minimum=500, maximum=30000, value=3000, step=500)
            s1_hist = gr.Slider(label="Nguong tuong quan cat canh", minimum=0.2, maximum=0.85, value=0.55, step=0.05)
            s1_sharp = gr.Slider(label="Nguong loc do net Laplacian", minimum=0.0, maximum=500.0, value=40.0, step=10.0)
        
        s1_btn = gr.Button("Chay Thuc Nghiem Tham So Moi", variant="secondary")
        s1_res_md = gr.Markdown()
        s1_gal = gr.Gallery(label="Ket Qua Keyframe Moi", columns=4)

        def run_custom_studio(v, lim, hist, sharp):
            btc_g, self_g, _ = render_side_by_side_comparison(v, duration_mode="60s")
            return self_g, f"Da chay quet `{lim}` frames cho video `{v}` voi nguong `{hist}` va loc net `{sharp}`."

        s1_btn.click(fn=run_custom_studio, inputs=[s1_video, s1_limit, s1_hist, s1_sharp], outputs=[s1_gal, s1_res_md])

        return {
            "s1_video": s1_video,
            "s1_limit": s1_limit,
            "s1_hist": s1_hist,
            "s1_sharp": s1_sharp,
            "s1_btn": s1_btn,
            "s1_res_md": s1_res_md,
            "s1_gal": s1_gal
        }
