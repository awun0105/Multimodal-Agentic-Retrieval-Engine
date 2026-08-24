"""
====================================================================================================
COMPONENTS - TAB 2: PERSISTENCE & STORAGE HUB (tab2_storage_hub.py)
====================================================================================================

1. MỤC TIÊU VÀ VAI TRÒ:
   - Tab 2 cung cấp bảng điều khiển quản lý dữ liệu lưu trữ bền vững:
     * Hiển thị bảng tổng hợp toàn bộ video đã xử lý: Tổng số Shot, Keyframe thực, Frame ảo, Dung lượng WebP tiết kiệm (%).
     * Nút 1-Click xuất toàn bộ báo cáo CSV, JSON và Bộ dữ liệu hợp nhất (Unified Final Dataset).

2. ĐẦU VÀO / ĐẦU RA:
   - Đầu vào: `refresh_persist_btn`, `export_report_btn`.
   - Đầu ra: `persistence_table_output` (DataFrame), `persist_status_html` (HTML báo cáo).
====================================================================================================
"""

from __future__ import annotations
import gradio as gr
from services.persistence_service import get_persistence_summary_table
from services.search_service import export_benchmark_report


def create_tab_storage_hub():
    with gr.TabItem("Trinh Quan Ly & Luu Tru Ket Qua (Persistence & Storage)"):
        gr.Markdown("""
        ### Bang Tong Hop Du Lieu Doi Soat Da Luu Tru & Tiet Kiem Bo Nho WebP
        Bang duoi day hien thi toan bo cac video da duoc xu ly va luu vao `benchmark_summary.csv` va JSON:
        """)

        with gr.Row():
            refresh_persist_btn = gr.Button("Tai Lai Danh Sach Da Luu", variant="secondary")
            export_report_btn = gr.Button("Luu & Xuat Bao Cao (CSV / JSON)", variant="primary")

        persist_status_html = gr.HTML()
        persistence_table_output = gr.DataFrame(
            value=get_persistence_summary_table(),
            interactive=False,
            label="Danh Sach Video Da Duoc Xu Ly & Luu Tru"
        )

        refresh_persist_btn.click(
            fn=get_persistence_summary_table,
            inputs=None,
            outputs=[persistence_table_output]
        )
        export_report_btn.click(
            fn=export_benchmark_report,
            inputs=None,
            outputs=[persistence_table_output, persist_status_html]
        )

        return {
            "refresh_persist_btn": refresh_persist_btn,
            "export_report_btn": export_report_btn,
            "persistence_table_output": persistence_table_output,
            "persist_status_html": persist_status_html
        }
