"""
Phase 02: KIS Multi-Attribute Semantic Enrichment
Module làm giàu ngữ nghĩa chuyên sâu cho đề thi KIS (Known-Item Search).

Trích xuất 6 nhóm thuộc tính then chốt:
1. Màu sắc chi tiết (Colors: trang phục, xe cộ, đồ vật, bối cảnh).
2. Góc quay & Khung cảnh (Camera angles: close-up, wide shot, drone/aerial, high/low angle).
3. Thời gian & Ánh sáng (Lighting/Time: sáng sớm, hoàng hôn, ban đêm, bóng râm).
4. Không gian & Vị trí tương đối (Spatial setting: trong vũng nước, trên khán đài, trong bếp).
5. Số lượng đồ vật đơn lẻ (Counts: 3 ổ bánh mì, 2 người đi xe đạp).
6. Hành động & Thứ tự sự kiện (Actions: bước vào rồi ngồi xuống).

Hợp đồng dữ liệu đầu vào (Input):
- frame_bgr: Mảng ảnh OpenCV BGR.
- ocr_texts: Danh sách từ khóa OCR tiếng Việt.

Hợp đồng dữ liệu đầu ra (Output):
- Dict: {colors, camera_angle, lighting_time, environment_setting, objects_and_counts, actions, dense_summary_vi, dense_summary_en}.
"""

from __future__ import annotations
import json
from pathlib import Path
from typing import Any


KIS_STRUCTURED_PROMPT = """
Bạn là chuyên gia phân tích thị giác cho hệ thống Video Retrieval Engine.
Hãy quan sát khung hình và phân tích chi tiết bằng Tiếng Anh và Tiếng Việt theo cấu trúc JSON chuẩn xác sau:
{
  "colors": ["red shirt", "blue motorbike", "yellow hat", "áo đỏ", "xe xanh"],
  "camera_angle": "close-up | wide-shot | aerial-drone | high-angle | eye-level",
  "lighting_time": "early morning | sunny daytime | sunset | nighttime | indoor | sáng sớm | ban đêm",
  "environment_setting": "puddle of water | stadium stands | kitchen | classroom | street | trong vũng nước | trên khán đài",
  "objects_and_counts": ["3 loaves of bread", "2 bicycles", "1 black car", "3 ổ bánh mì"],
  "actions": ["person pouring water", "chef cutting onions", "người đang rót nước", "nấu ăn"],
  "dense_summary_vi": "Mô tả chi tiết khung hình bằng tiếng Việt gồm màu sắc, góc máy, số lượng đồ vật và bối cảnh.",
  "dense_summary_en": "Detailed English description of the keyframe with colors, camera viewpoint, object count, and environment."
}
Chỉ trả về JSON thuần túy, không kèm giải thích.
"""


class KISDetailEnricher:
    """
    Bộ làm giàu ngữ nghĩa KIS đa chiều cho từng Keyframe.
    Hỗ trợ sinh prompt có cấu trúc và phân loại thuộc tính.
    """

    @staticmethod
    def parse_kis_json_response(raw_text: str) -> dict[str, Any]:
        """Giải mã JSON trả về từ VLM an toàn."""
        cleaned = raw_text.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        if cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

        try:
            return json.loads(cleaned)
        except Exception:
            return {
                "colors": [],
                "camera_angle": "unknown",
                "lighting_time": "unknown",
                "environment_setting": "unknown",
                "objects_and_counts": [],
                "actions": [],
                "dense_summary_vi": raw_text[:300],
                "dense_summary_en": ""
            }

    @staticmethod
    def extract_heuristics_from_image(frame_bgr, ocr_texts: list[str]) -> dict[str, Any]:
        """
        Trích xuất đặc trưng heuristic nhanh khi chạy offline không có LLM API:
        Phân tích độ sáng, tỷ lệ màu RGB/HSV chủ đạo và từ khóa OCR.
        """
        import cv2
        import numpy as np

        h, w, _ = frame_bgr.shape
        hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        
        # 1. Đoán ánh sáng/thời gian dựa trên độ sáng trung bình
        mean_v = np.mean(gray)
        if mean_v < 60:
            lighting = "nighttime / ban đêm / thiếu sáng"
        elif mean_v > 180:
            lighting = "bright sunny / trời nắng gắt"
        else:
            lighting = "daytime / ban ngày / ánh sáng tiêu chuẩn"

        # 2. Đoán màu sắc chủ đạo
        colors = []
        # Màu đỏ
        mask_red = cv2.inRange(hsv, np.array([0, 70, 50]), np.array([10, 255, 255]))
        if np.sum(mask_red > 0) / (h * w) > 0.05:
            colors.append("red / màu đỏ")
        # Màu xanh lá
        mask_green = cv2.inRange(hsv, np.array([35, 70, 50]), np.array([85, 255, 255]))
        if np.sum(mask_green > 0) / (h * w) > 0.1:
            colors.append("green / cây cỏ / màu xanh lá")
        # Màu xanh dương
        mask_blue = cv2.inRange(hsv, np.array([90, 70, 50]), np.array([130, 255, 255]))
        if np.sum(mask_blue > 0) / (h * w) > 0.08:
            colors.append("blue / bầu trời / màu xanh dương")

        return {
            "colors": colors,
            "camera_angle": "eye-level / standard",
            "lighting_time": lighting,
            "environment_setting": "general environment",
            "objects_and_counts": ocr_texts[:5],
            "actions": [],
            "dense_summary_vi": f"Khung hình trong bối cảnh {lighting}, màu chủ đạo: {', '.join(colors) if colors else 'đa dạng'}.",
            "dense_summary_en": f"Keyframe in {lighting} condition with dominant colors: {', '.join(colors)}."
        }
