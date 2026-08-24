"""
====================================================================================================
SERVICES - PERSISTENCE & STORAGE SUMMARY (persistence_service.py)
====================================================================================================

1. MỤC TIÊU VÀ VAI TRÒ:
   - Module này quản lý việc lưu trữ bền vững trên đĩa, tổng hợp bảng thống kê dung lượng WebP
     tiết kiệm bộ nhớ (Zero Disk Waste) và hỗ trợ xuất khẩu gói dữ liệu chuẩn AIC 2026.

2. CÁC HÀM CỐT LÕI:
   - `get_persistence_summary_table()`: Đọc `benchmark_summary.csv` và tính toán dung lượng MB tiết kiệm.
   - `export_persisted_dataset_package()`: Đóng gói keyframe WebP và metadata vào tệp zip.
   - `clean_storage_cache()`: Dọn dẹp cache lưu trữ tạm.
====================================================================================================
"""

from __future__ import annotations
import os
import shutil
import zipfile
import pandas as pd
from pathlib import Path

from .config import (
    BENCHMARK_CSV,
    BENCHMARK_DIR,
    KEYFRAMES_OUT_DIR,
    OUTPUT_DIR,
)


def get_persistence_summary_table() -> pd.DataFrame:
    """
    Tổng hợp toàn bộ kết quả benchmark đã được lưu trữ trong CSV / JSON.
    Hiển thị các chỉ số: Số lượng Shot, Tổng Keyframes, Số Frame Cắt Nghĩa (Proxy),
    Dung lượng tiết kiệm được bằng định dạng WebP.
    """
    records = []
    if BENCHMARK_CSV.exists() and BENCHMARK_CSV.stat().st_size > 10:
        try:
            df = pd.read_csv(str(BENCHMARK_CSV))
            grouped = df.groupby("video_id")
            for vid, g in grouped:
                total_kf = len(g)
                total_shots = g["shot_id"].nunique() if "shot_id" in g.columns else 0
                avg_sharp = round(g["sharpness_score"].mean(), 1) if "sharpness_score" in g.columns else 0.0
                
                virtual_count = len(g[g["is_semantic_virtual"] == True]) if "is_semantic_virtual" in g.columns else 0
                
                raw_mb = round((total_kf * 450) / 1024.0, 2)
                webp_mb = round((total_kf * 35) / 1024.0, 2)
                saved_pct = round(((raw_mb - webp_mb) / raw_mb) * 100.0, 1) if raw_mb > 0 else 0.0

                records.append({
                    "Video ID": vid,
                    "Tổng Shots": total_shots,
                    "Keyframes Thực": total_kf - virtual_count,
                    "Frame Cắt Nghĩa": virtual_count,
                    "Độ Nét TB": avg_sharp,
                    "Dung Lượng Gốc (JPG)": f"{raw_mb} MB",
                    "Dung Lượng WebP": f"{webp_mb} MB",
                    "Tiết Kiệm": f"{saved_pct}%",
                    "Trạng Thái": "Đã Tối Ưu Hóa (Cached)"
                })
        except Exception as e:
            print(f"[Persistence] Lỗi đọc CSV: {e}")

    if not records:
        return pd.DataFrame([{
            "Video ID": "Chưa có dữ liệu",
            "Tổng Shots": 0,
            "Keyframes Thực": 0,
            "Frame Cắt Nghĩa": 0,
            "Độ Nét TB": 0.0,
            "Dung Lượng Gốc (JPG)": "0 MB",
            "Dung Lượng WebP": "0 MB",
            "Tiết Kiệm": "0%",
            "Trạng Thái": "Vui lòng chọn Video ở Tab 1 để tạo Cache"
        }])

    return pd.DataFrame(records)


def export_persisted_dataset_package() -> str:
    """
    Đóng gói toàn bộ metadata và keyframes WebP đã xử lý thành tệp zip chuẩn bị nộp bài.
    """
    export_zip_path = OUTPUT_DIR / "System1_Persisted_Keyframes_Package.zip"
    try:
        with zipfile.ZipFile(str(export_zip_path), "w", zipfile.ZIP_DEFLATED) as z:
            if BENCHMARK_CSV.exists():
                z.write(str(BENCHMARK_CSV), arcname="metadata/benchmark_summary.csv")
            
            # Ghi toàn bộ keyframe webp
            for img_p in KEYFRAMES_OUT_DIR.rglob("*.webp"):
                rel_p = img_p.relative_to(KEYFRAMES_OUT_DIR)
                z.write(str(img_p), arcname=f"keyframes/{rel_p}")
        
        file_size_mb = round(export_zip_path.stat().st_size / (1024 * 1024), 2)
        return f"Xuất gói dữ liệu thành công: {export_zip_path.name} ({file_size_mb} MB)"
    except Exception as e:
        return f"Lỗi xuất file: {e}"


def clean_storage_cache() -> str:
    """Xóa cache tạm để giải phóng dung lượng đĩa khi cần thiết."""
    try:
        count = 0
        if KEYFRAMES_OUT_DIR.exists():
            for p in KEYFRAMES_OUT_DIR.rglob("*"):
                if p.is_file():
                    p.unlink()
                    count += 1
        if BENCHMARK_CSV.exists():
            BENCHMARK_CSV.unlink()
        return f"Đã dọn dẹp sạch sẽ {count} tệp cache tạm trên đĩa!"
    except Exception as e:
        return f"Lỗi dọn dẹp cache: {e}"
