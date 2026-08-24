"""
====================================================================================================
TEMPLATES - CSS DESIGN TOKENS & DARK THEME (theme_tokens.py)
====================================================================================================

1. MỤC TIÊU VÀ VAI TRÒ:
   - Module này tập trung toàn bộ mã CSS tùy biến giao diện Dark Theme cao cấp (Nord & Dracula Palette).
   - Đảm bảo tính thẩm mỹ, độ tương phản cao, thanh cuộn mượt mà và hiệu ứng tương tác (Hover / Transitions).

2. BẢNG MÀU CHỦ ĐẠO:
   - Nền chính: `#1e1e2e` (Catppuccin Mocha / Dark Slate).
   - Viền thẻ chuẩn: `#434c5e` (Nord Gray).
   - Viền Cyan: `#88c0d0` (Keyframe BTC chuẩn).
   - Viền Tím Neon: `#bd93f9` (Frame Cắt Nghĩa / Semantic Virtual Link).
   - Viền Đỏ: `#bf616a` (Đề xuất lọc bỏ do trùng lặp hoặc mờ).
   - Viền Lá Mạ: `#a3be8c` (Keyframe System 1 sắc nét nhất).
====================================================================================================
"""

STUDIO_CSS = """
/* Reset & Dark Theme */
.gradio-container {
    background-color: #1e1e2e !important;
    color: #cdd6f4 !important;
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif !important;
}

/* Custom Scrollbars */
::-webkit-scrollbar {
    width: 8px;
    height: 8px;
}
::-webkit-scrollbar-track {
    background: #181825;
}
::-webkit-scrollbar-thumb {
    background: #45475a;
    border-radius: 4px;
}
::-webkit-scrollbar-thumb:hover {
    background: #585b70;
}

/* Card Transitions */
.side-by-side-card {
    transition: all 0.2s ease-in-out;
}
.side-by-side-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 6px 14px rgba(0, 0, 0, 0.45) !important;
}

/* Header Banner */
.studio-header {
    background: linear-gradient(135deg, #2e3440 0%, #3b4252 100%);
    border: 2px solid #5e81ac;
    border-radius: 8px;
    padding: 15px;
    margin-bottom: 15px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.35);
}

/* Badges */
.badge-tag {
    display: inline-block;
    padding: 2px 6px;
    border-radius: 4px;
    font-size: 10px;
    font-weight: bold;
    text-transform: uppercase;
}
"""
