"""
====================================================================================================
TEMPLATES - HTML CARDS & TIMELINE COMPONENTS (card_templates.py)
====================================================================================================

1. MỤC TIÊU VÀ VAI TRÒ:
   - Module này chứa toàn bộ hàm dựng chuỗi HTML tái sử dụng cho các thẻ bài trên bảng đối soát:
     a) Cột thời gian trung tâm với nút mở YouTube đúng giây (`render_timeline_center_cell`).
     b) Hàng trạng thái cú máy tĩnh liên tục (`render_continuous_holding_row`).
     c) Banner tiêu đề tổng kết thống kê số lượng frame BTC vs System 1 (`render_side_by_side_header`).
====================================================================================================
"""

from __future__ import annotations


def render_timeline_center_cell(t_start: int, t_end: int, t_slot_str: str, yt_url: str) -> str:
    """Tạo ô hiển thị mốc thời gian trung tâm với nút xem YouTube."""
    return f"""
    <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; background-color: #2e3440; border: 1px solid #434c5e; border-radius: 6px; padding: 8px; text-align: center;">
        <span style="font-weight: bold; color: #ebcb8b; font-size: 13px;">{t_slot_str}</span>
        <span style="font-size: 10px; color: #88c0d0; margin-bottom: 5px;">({t_start}s -> {t_end}s)</span>
        <a href="{yt_url}" target="_blank" style="background-color: #bf616a; color: white; padding: 3px 8px; border-radius: 4px; text-decoration: none; font-weight: bold; font-size: 10px; white-space: nowrap;">
            [>] Xem YouTube
        </a>
    </div>
    """


def render_continuous_holding_row(t_start: int, t_end: int, t_slot_str: str, yt_url: str) -> str:
    """Tạo dòng hiển thị liên tục cho các cú máy tĩnh kéo dài mà không bị skip ẩn."""
    timeline_cell = f"""
    <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; background-color: #242933; border: 1px solid #434c5e; border-radius: 6px; padding: 4px 8px; text-align: center;">
        <span style="font-weight: bold; color: #ebcb8b; font-size: 11px;">{t_slot_str}</span>
        <span style="font-size: 9px; color: #88c0d0; margin-bottom: 2px;">({t_start}s -> {t_end}s)</span>
        <a href="{yt_url}" target="_blank" style="background-color: #bf616a; color: white; padding: 2px 6px; border-radius: 3px; text-decoration: none; font-weight: bold; font-size: 9px; white-space: nowrap;">
            [>] Xem YouTube
        </a>
    </div>
    """
    return f"""
    <div style="display: grid; grid-template-columns: 1fr 140px 1fr; gap: 12px; align-items: stretch; margin-bottom: 8px; background-color: #242933; padding: 6px 8px; border-radius: 6px; border: 1px dashed #434c5e; opacity: 0.85;">
        <div style="color: #6c7a96; font-size: 11px; font-style: italic; display: flex; align-items: center; justify-content: center;">
            [BTC] Không lấy mẫu (Cú máy tiếp diễn)
        </div>
        <div style="display: flex; align-items: center; justify-content: center;">{timeline_cell}</div>
        <div style="color: #6c7a96; font-size: 11px; font-style: italic; display: flex; align-items: center; justify-content: center;">
            [System 1] Cú máy tĩnh liên tục (Duy trì góc nhìn mốc trước, không tạo frame thừa)
        </div>
    </div>
    """


def render_side_by_side_header(
    selected_video: str,
    title: str,
    author: str,
    watch_url: str,
    total_time_str: str,
    total_video_sec: float,
    latency_str: str,
    duration_mode: str,
    text_bumper_count: int,
    btc_count: int,
    total_btc_frames: int,
    self_count: int
) -> str:
    """Tạo thanh tiêu đề bảng điều khiển Side-by-Side."""
    return f"""
    <div style="border: 2px solid #5e81ac; border-radius: 8px; padding: 15px; margin-bottom: 15px; background-color: #3b4252; color: #eceff4;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 10px;">
            <h3 style="margin: 0; color: #88c0d0; font-size: 18px;">[VIDEO DOI SOAT]: {selected_video} - {title}</h3>
            <div style="display: flex; gap: 8px;">
                <span style="background: #ebcb8b; color: #2e3440; padding: 3px 10px; border-radius: 12px; font-weight: bold; font-size: 12px;">
                    Tong Thoi Luong Video: {total_time_str} ({total_video_sec:.1f}s)
                </span>
                <span style="background: #a3be8c; color: #2e3440; padding: 3px 10px; border-radius: 12px; font-weight: bold; font-size: 12px;">
                    Latency Nap: {latency_str}
                </span>
            </div>
        </div>
        <p style="margin: 0 0 8px 0; font-size: 13px; color: #d8dee9;">
            <b>Kenh:</b> {author} | <b>Che do xem:</b> <span style="color:#ebcb8b; font-weight:bold;">{duration_mode.upper()} / {total_time_str}</span> | 
            <b>Phat hien:</b> <span style="color:#88c0d0; font-weight:bold;">{text_bumper_count} Title Bumpers</span> | 
            <b>Link YouTube:</b> <a href="{watch_url}" target="_blank" style="color: #88c0d0;">{watch_url}</a>
        </p>
        <div style="display: grid; grid-template-columns: 1fr 140px 1fr; gap: 12px; font-weight: bold; font-size: 13px; text-align: center; background-color: #242933; padding: 8px; border-radius: 6px;">
            <div style="color: #8be9fd; text-align: left; padding-left: 8px;">[BAN TO CHUC - VIEN CYAN] ({btc_count} / {total_btc_frames} FRAMES)</div>
            <div style="color: #ebcb8b;">[TRUC DONG THOI GIAN] ({duration_mode.upper()})</div>
            <div style="color: #a3be8c; text-align: right; padding-right: 8px;">[TU XU LY - SYSTEM 1] ({self_count} FRAMES)</div>
        </div>
    </div>
    """
