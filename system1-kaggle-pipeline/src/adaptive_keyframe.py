"""
Phase 01: Smart Adaptive Keyframe Extraction & Quality Filtering
Module trích xuất Keyframe thông minh, tối ưu chuyên sâu cho video tiếng Việt.

Chức năng chính:
1. Lấy mẫu đa dải thích ứng (20%, 50%, 80%) theo độ dài cú máy.
2. Lọc độ sắc nét bằng phương sai Laplacian (Laplacian Variance >= 40.0) và quét dò +-2 frames nét nhất.
3. Lọc bỏ khung hình quá tối (fade-in/fade-out) hoặc quá chói.
4. Tự động sinh ảnh thu nhỏ WebP 128x128 phục vụ chế độ Lean Mode.

Hợp đồng dữ liệu đầu vào (Input):
- video_path: Đường dẫn tệp video MP4/MKV.
- shots: Danh sách cú máy từ Phase 01 Shot Detector.

Hợp đồng dữ liệu đầu ra (Output):
- List[Dict]: [keyframe_id, shot_id, frame_id, pts_time_sec, sharpness, brightness, keyframe_path, thumbnail_path].
"""

from __future__ import annotations
import cv2
import numpy as np
from pathlib import Path
from PIL import Image
from typing import Any


def calculate_sharpness(frame_bgr: np.ndarray) -> float:
    """Tính độ sắc nét của khung hình bằng phương sai toán tử Laplacian."""
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def calculate_brightness(frame_bgr: np.ndarray) -> float:
    """Tính độ sáng trung bình của khung hình (0 - 255)."""
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    return float(np.mean(gray))


def enhance_frame_sharpness(frame_bgr: np.ndarray) -> np.ndarray:
    """
    Tăng cường độ sắc nét cho khung hình mờ (Unsharp Masking / Gaussian High-pass Boost)
    để phục hồi chi tiết khi cú máy không có khung hình nào đạt ngưỡng độ nét chuẩn.
    """
    if frame_bgr is None:
        return frame_bgr
    try:
        gaussian = cv2.GaussianBlur(frame_bgr, (0, 0), 2.0)
        enhanced = cv2.addWeighted(frame_bgr, 1.6, gaussian, -0.6, 0)
        return enhanced
    except Exception:
        return frame_bgr


def extract_adaptive_keyframes(
    video_path: Path | str,
    shots: list[dict[str, Any]],
    output_keyframe_dir: Path,
    output_thumbnail_dir: Path,
    min_sharpness: float = 40.0,
    min_brightness: float = 15.0,
    max_brightness: float = 245.0,
    thumbnail_size: tuple[int, int] = (128, 128)
) -> list[dict[str, Any]]:
    """
    Trích xuất danh sách keyframes chất lượng cao từ các shots.
    Tích hợp cơ chế cứu ảnh mờ bằng Sharpening Fallback nếu toàn bộ cú máy có độ nét thấp.
    """
    video_path = str(video_path)
    output_keyframe_dir.mkdir(parents=True, exist_ok=True)
    output_thumbnail_dir.mkdir(parents=True, exist_ok=True)

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"Không thể mở file video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    keyframe_records: list[dict[str, Any]] = []
    keyframe_counter = 1

    for shot in shots:
        start_f = shot["start_frame"]
        end_f = shot["end_frame"]
        shot_len = end_f - start_f + 1
        duration_sec = shot["duration_sec"]

        if duration_sec < 3.0:
            candidate_ratios = [0.5]
        elif duration_sec <= 10.0:
            candidate_ratios = [0.2, 0.5, 0.8]
        else:
            num_samples = min(int(duration_sec / 3.0) + 1, 8)
            candidate_ratios = [i / (num_samples + 1) for i in range(1, num_samples + 1)]

        shot_candidates = []

        for ratio in candidate_ratios:
            target_frame_idx = start_f + int(shot_len * ratio)
            target_frame_idx = min(target_frame_idx, end_f)

            cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame_idx)
            ret, frame = cap.read()
            if not ret or frame is None:
                continue

            brightness = calculate_brightness(frame)
            if brightness < min_brightness or brightness > max_brightness:
                continue

            sharpness = calculate_sharpness(frame)
            is_fallback = False

            if sharpness < min_sharpness:
                best_frame = frame
                best_sharpness = sharpness
                best_idx = target_frame_idx
                for offset in [-2, -1, 1, 2]:
                    test_idx = target_frame_idx + offset
                    if start_f <= test_idx <= end_f:
                        cap.set(cv2.CAP_PROP_POS_FRAMES, test_idx)
                        r_test, f_test = cap.read()
                        if r_test and f_test is not None:
                            s_test = calculate_sharpness(f_test)
                            if s_test > best_sharpness:
                                best_sharpness = s_test
                                best_frame = f_test
                                best_idx = test_idx
                
                frame = best_frame
                sharpness = best_sharpness
                target_frame_idx = best_idx

                # Nếu vẫn mờ < min_sharpness, áp dụng bộ lọc làm nét
                if sharpness < min_sharpness:
                    frame = enhance_frame_sharpness(frame)
                    sharpness = calculate_sharpness(frame)
                    is_fallback = True

            shot_candidates.append({
                "frame": frame,
                "frame_idx": target_frame_idx,
                "sharpness": sharpness,
                "brightness": brightness,
                "is_fallback": is_fallback
            })

        for cand in shot_candidates:
            frame = cand["frame"]
            target_frame_idx = cand["frame_idx"]
            sharpness = cand["sharpness"]
            brightness = cand["brightness"]
            is_fallback = cand["is_fallback"]

            # Lưu file ảnh Keyframe (JPG)
            keyframe_name = f"{keyframe_counter:04d}.jpg"
            keyframe_file = output_keyframe_dir / keyframe_name
            cv2.imwrite(str(keyframe_file), frame, [cv2.IMWRITE_JPEG_QUALITY, 90])

            # Lưu file Thumbnail (WebP 128x128)
            thumb_name = f"{keyframe_counter:04d}.webp"
            thumb_file = output_thumbnail_dir / thumb_name
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            pil_img = Image.fromarray(rgb_frame)
            pil_img.thumbnail(thumbnail_size)
            pil_img.save(str(thumb_file), "WEBP", quality=65)

            pts_time = round(target_frame_idx / fps, 4)
            keyframe_records.append({
                "keyframe_id": keyframe_counter,
                "shot_id": shot["shot_id"],
                "frame_id": target_frame_idx,
                "pts_time_sec": pts_time,
                "sharpness": round(sharpness, 2),
                "brightness": round(brightness, 2),
                "is_sharpened_fallback": is_fallback,
                "keyframe_path": str(keyframe_file),
                "thumbnail_path": str(thumb_file)
            })
            keyframe_counter += 1

    cap.release()
    return keyframe_records
