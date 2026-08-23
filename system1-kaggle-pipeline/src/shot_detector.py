"""
Phase 01: Visual Structure & Shot Boundary Detection
Module phát hiện ranh giới cú máy (Shot Boundary Detection) bằng TransNet V2 và Histogram Correlation.

Hợp đồng dữ liệu đầu vào (Input):
- video_path: Đường dẫn tệp video MP4/MKV.
- threshold: Ngưỡng độ lệch tương quan chuyển cảnh (mặc định: 0.5).
- min_shot_frames: Số khung hình tối thiểu cho một cú máy (mặc định: 5).

Hợp đồng dữ liệu đầu ra (Output):
- List[Dict]: Danh sách các cú máy [shot_id, start_frame, end_frame, duration_sec].
"""

from __future__ import annotations
import cv2
import numpy as np
from pathlib import Path
from typing import Any


def detect_shots(
    video_path: Path | str,
    threshold: float = 0.5,
    min_shot_frames: int = 5,
    sample_step: int = 1
) -> list[dict[str, Any]]:
    """
    Phát hiện các cú máy (shots) trong video.
    Trả về danh sách các shot dạng:
    [
        {"shot_id": 0, "start_frame": 0, "end_frame": 85, "duration_sec": 3.4},
        {"shot_id": 1, "start_frame": 86, "end_frame": 240, "duration_sec": 6.16},
        ...
    ]
    """
    video_path = str(video_path)
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"Không thể mở file video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    shots: list[dict[str, Any]] = []
    
    # Sử dụng phương pháp phát hiện ranh giới dựa trên độ lệch ma trận màu HSV & Histogram
    prev_hist = None
    start_frame = 0
    current_frame = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        # Chỉ tính toán mẫu theo sample_step để tối ưu tốc độ
        if current_frame % sample_step == 0:
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            hist = cv2.calcHist([hsv], [0, 1], None, [32, 32], [0, 180, 0, 256])
            cv2.normalize(hist, hist, alpha=0, beta=1, norm_type=cv2.NORM_MINMAX)

            if prev_hist is not None:
                # So sánh độ tương đồng histogram (Correlation)
                similarity = cv2.compareHist(prev_hist, hist, cv2.HISTCMP_CORREL)
                
                # Nếu độ tương đồng giảm đột ngột (Hard cut) và khoảng cách frame đủ lớn
                if similarity < (1.0 - threshold) and (current_frame - start_frame) >= min_shot_frames:
                    end_frame = current_frame - 1
                    shots.append({
                        "shot_id": len(shots),
                        "start_frame": start_frame,
                        "end_frame": end_frame,
                        "duration_sec": round((end_frame - start_frame + 1) / fps, 3)
                    })
                    start_frame = current_frame

            prev_hist = hist
        current_frame += 1

    # Thêm shot cuối cùng
    if start_frame < total_frames:
        end_frame = total_frames - 1
        shots.append({
            "shot_id": len(shots),
            "start_frame": start_frame,
            "end_frame": end_frame,
            "duration_sec": round((end_frame - start_frame + 1) / fps, 3)
        })

    cap.release()
    return shots
