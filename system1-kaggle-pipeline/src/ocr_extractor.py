"""
Phase 02: Vietnamese OCR & News Tickers Lower Thirds Segmentation
Module nhận diện ký tự quang học tiếng Việt sử dụng EasyOCR trên GPU/CPU.

Tối ưu hóa:
1. Phân vùng quét chuyên biệt cho chân trang tin tức (News Tickers y > 0.65).
2. Slide bài giảng trực tuyến và chữ toàn trang.
3. Bảng tên, biển hiệu, số áo vận động viên (y <= 0.65, conf >= 0.7).
4. Khử trùng lặp văn bản cấp cú máy (Shot-Level Deduplication qua Jaccard/Substring).

Hợp đồng dữ liệu đầu vào (Input):
- image_path_or_array: Đường dẫn ảnh hoặc mảng NumPy BGR.
- confidence_threshold: Ngưỡng độ tin cậy tối thiểu (mặc định: 0.4).

Hợp đồng dữ liệu đầu ra (Output):
- Dict: {full_text: str, boxes: List[Dict: [text, confidence, box, is_lower_third]]}.
"""

from __future__ import annotations
import cv2
import numpy as np
from pathlib import Path
from typing import Any


class VietnameseOCRExtractor:
    def __init__(self, languages: list[str] = ["vi", "en"], gpu: bool = True):
        self.languages = languages
        self.gpu = gpu
        self.reader = None

    def _load_reader(self):
        if self.reader is None:
            import easyocr
            self.reader = easyocr.Reader(self.languages, gpu=self.gpu)

    @staticmethod
    def compute_jaccard_similarity(str1: str, str2: str) -> float:
        """Tính độ tương đồng Jaccard giữa 2 chuỗi từ."""
        set1 = set(str1.lower().split())
        set2 = set(str2.lower().split())
        if not set1 or not set2:
            return 0.0
        intersection = len(set1.intersection(set2))
        union = len(set1.union(set2))
        return intersection / union if union > 0 else 0.0

    @classmethod
    def deduplicate_text_list(cls, texts: list[str], threshold: float = 0.85) -> list[str]:
        """
        Khử trùng lặp danh sách văn bản trong cùng một cú máy:
        Gộp các chuỗi con hoặc chuỗi có độ tương đồng Jaccard >= threshold.
        """
        if not texts:
            return []

        # Sắp xếp theo độ dài giảm dần để ưu tiên giữ câu đầy đủ nhất
        sorted_texts = sorted(list(set(texts)), key=len, reverse=True)
        unique_texts: list[str] = []

        for candidate in sorted_texts:
            candidate_clean = candidate.strip()
            if not candidate_clean or len(candidate_clean) < 2:
                continue

            is_duplicate = False
            for existing in unique_texts:
                # Kiểm tra chuỗi con hoặc Jaccard cao
                if candidate_clean.lower() in existing.lower():
                    is_duplicate = True
                    break
                if cls.compute_jaccard_similarity(candidate_clean, existing) >= threshold:
                    is_duplicate = True
                    break

            if not is_duplicate:
                unique_texts.append(candidate_clean)

        return unique_texts

    def extract_text_from_image(
        self,
        image_path_or_array: Path | str | np.ndarray,
        confidence_threshold: float = 0.4
    ) -> dict[str, Any]:
        """
        Quét chữ từ ảnh và trả về danh sách text boxes cùng text tổng hợp.
        """
        self._load_reader()
        
        if isinstance(image_path_or_array, (str, Path)):
            img = cv2.imread(str(image_path_or_array))
        else:
            img = image_path_or_array

        if img is None:
            return {"full_text": "", "boxes": []}

        h, w, _ = img.shape
        results = self.reader.readtext(img)

        boxes: list[dict[str, Any]] = []
        extracted_texts: list[str] = []

        for bbox, text, conf in results:
            if conf < confidence_threshold:
                continue
            text = text.strip()
            if not text:
                continue

            # Chuẩn hóa tọa độ bbox [ymin, xmin, ymax, xmax] theo tỷ lệ 0.0 - 1.0
            pts = np.array(bbox, dtype=np.float32)
            xmin = float(np.min(pts[:, 0]) / w)
            xmax = float(np.max(pts[:, 0]) / w)
            ymin = float(np.min(pts[:, 1]) / h)
            ymax = float(np.max(pts[:, 1]) / h)

            # Phân loại vị trí (Lower-third ticker hoặc slide/main)
            is_lower_third = ymin > 0.65

            # Nếu ở vùng trung tâm (không phải chân trang), yêu cầu confidence cao hơn để chống nhiễu
            if not is_lower_third and conf < 0.6:
                continue

            extracted_texts.append(text)
            boxes.append({
                "text": text,
                "confidence": round(float(conf), 3),
                "box": [round(ymin, 4), round(xmin, 4), round(ymax, 4), round(xmax, 4)],
                "is_lower_third": is_lower_third
            })

        # Khử trùng lặp nhanh
        deduped = self.deduplicate_text_list(extracted_texts)

        return {
            "full_text": " ".join(deduped),
            "boxes": boxes
        }
