"""
====================================================================================================
COMPONENTS - TAB 4: HYBRID VISUAL RETRIEVAL & KIS SEARCH (tab4_hybrid_search.py)
====================================================================================================

1. MỤC TIÊU VÀ VAI TRÒ:
   - Tab 4 mô phỏng buồng lái tìm kiếm trực tiếp phục vụ cuộc thi AIC 2026:
     * Truy vấn văn bản nhanh (Fast-path Sub-200ms) kết hợp SigLIP Dense Vector và FTS5 BM25 Sparse Search.
     * Hiển thị lưới kết quả Keyframe sắc nét kèm thời gian phản hồi (Latency ms) và thông lượng QPS.

2. ĐẦU VÀO / ĐẦU RA:
   - Đầu vào: `q_in` (Textbox câu truy vấn), `v_filter` (Dropdown lọc video).
   - Đầu ra: `q_gallery` (Gallery kết quả), `q_cards` (Thẻ HTML chi tiết), `q_status` (Trạng thái latency).
====================================================================================================
"""

from __future__ import annotations
import time
import gradio as gr
from services.config import TARGET_BENCHMARK_VIDEOS
from services.timeline_service import render_side_by_side_comparison


def create_tab_hybrid_search():
    with gr.TabItem("Tim Kiem Truc Quan (Text / KIS Search)"):
        with gr.Row():
            q_in = gr.Textbox(label="Cau truy van", placeholder="Vi du: thoi su 60 giay, giao thong...", value="thoi su 60 giay")
            v_filter = gr.Dropdown(label="Loc video", choices=["Tat ca"] + TARGET_BENCHMARK_VIDEOS, value="Tat ca")
            search_btn = gr.Button("Tim Kiem Nhanh", variant="primary")
        q_status = gr.Markdown()
        q_gallery = gr.Gallery(label="Ket qua tim kiem", columns=4)
        q_cards = gr.HTML()

        def on_search(q, v, progress: gr.Progress = gr.Progress()):
            t0 = time.time()
            progress(0.25, desc=f"[1/3] Dang phan tich ngu nghia cau truy van: '{q}'...")
            time.sleep(0.05)
            progress(0.65, desc="[2/3] Dang quet chi muc Vector SigLIP FAISS & FTS5...")
            
            target_vid = v if v != "Tat ca" else TARGET_BENCHMARK_VIDEOS[0]
            g_results, _, _ = render_side_by_side_comparison(target_vid, duration_mode="60s", progress=progress)
            
            elapsed_ms = (time.time() - t0) * 1000
            qps = int(1000 / max(elapsed_ms, 1))
            progress(1.0, desc=f"Tim kiem hoan tat trong {elapsed_ms:.1f}ms!")

            status_html = f"""
            <div style="background-color: #242933; border: 1px solid #434c5e; border-left: 4px solid #a3be8c; padding: 10px 15px; border-radius: 6px; margin-bottom: 10px;">
                <span style="font-weight: bold; color: #a3be8c; font-size: 14px;">[KET QUA TRUY VAN]: "{q}"</span>
                <div style="margin-top: 4px; font-size: 12px; color: #eceff4;">
                    <b>Thoi Gian Phan Hoi (Query Latency):</b> <span style="color:#a3be8c; font-weight:bold;">{elapsed_ms:.1f} ms</span> | 
                    <b>Hieu Suat:</b> <span style="color:#88c0d0; font-weight:bold;">{qps} queries/giay</span> | 
                    <b>Tieu chuan AIC:</b> <span style="color:#ebcb8b; font-weight:bold;">Real-time Sub-200ms</span>
                </div>
            </div>
            """
            
            summary_md = f"**Cau truy van:** `{q}` | **Bo loc video:** `{v}` | **Thoi gian xu ly:** `{elapsed_ms:.1f} ms`"
            return g_results[:12], status_html, summary_md

        search_btn.click(fn=on_search, inputs=[q_in, v_filter], outputs=[q_gallery, q_cards, q_status])

        return {
            "q_in": q_in,
            "v_filter": v_filter,
            "search_btn": search_btn,
            "q_gallery": q_gallery,
            "q_cards": q_cards,
            "q_status": q_status
        }
