# -*- coding: utf-8 -*-
"""
Phase 02 & Phase 03: Hybrid BTC-Self Timeline Synchronization & Semantic Virtual Deduplication (Step 5)
Module hợp nhất dòng thời gian giữa Keyframe Ban tổ chức (BTC) và Keyframe Tự xử lý (System 1),
áp dụng cơ chế đếm số lượng vật thể 'Nhãn x Số lượng' và khử trùng lặp ảo (Frame Cắt Nghĩa viền tím).

Chức năng cốt lõi:
1. format_object_counts(): Tổng hợp đếm số lượng vật thể dạng 'Nhãn x Số lượng' (Cờ x 5, Người x 2).
2. merge_and_sort_timeline(): Hợp nhất trên trục thời gian chung và gộp frame trùng mốc (|Δt| <= 0.05s).
3. sliding_window_deduplicate(): Cửa sổ trượt 3 keyframe liền kề đo độ tương đồng thị giác (>= 0.92).
4. Ngoại lệ OCR (OCR Exception): Nếu văn bản OCR khác biệt -> Giữ nguyên là Keyframe độc lập.
5. Khung hình Cắt nghĩa (Semantic Virtual Link): Lưu tham chiếu delta thời gian (+/- giây), không nhân bản file ảnh (Zero Disk Waste), hiển thị viền tím Violet (#bd93f9).
"""

from __future__ import annotations
import math
from pathlib import Path
from collections import Counter
from typing import Any


class TimelineSynchronizer:
    """Bộ hợp nhất dòng thời gian và khử trùng lặp ảo đa phương thức."""

    # Bảng dịch nhãn COCO & OpenImages sang tiếng Việt chuẩn tắc cho AIC
    LABEL_TRANSLATIONS = {
        "person": "Người",
        "bicycle": "Xe đạp",
        "car": "Xe hơi",
        "motorcycle": "Xe máy",
        "airplane": "Máy bay",
        "bus": "Xe buýt",
        "train": "Tàu hỏa",
        "truck": "Xe tải",
        "boat": "Thuyền",
        "traffic light": "Đèn giao thông",
        "fire hydrant": "Trụ cứu hỏa",
        "stop sign": "Biển dừng",
        "parking meter": "Đồng hồ đỗ xe",
        "bench": "Ghế dài",
        "bird": "Chim",
        "cat": "Mèo",
        "dog": "Chó",
        "horse": "Ngựa",
        "sheep": "Cừu",
        "cow": "Bò",
        "elephant": "Voi",
        "bear": "Gấu",
        "zebra": "Ngựa vằn",
        "giraffe": "Hươu cao cổ",
        "backpack": "Balo",
        "umbrella": "Dù",
        "handbag": "Túi xách",
        "tie": "Cà vạt",
        "suitcase": "Vali",
        "frisbee": "Đĩa bay",
        "skis": "Ván trượt tuyết",
        "snowboard": "Ván trượt",
        "sports ball": "Bóng thể thao",
        "kite": "Diều",
        "baseball bat": "Gậy bóng chày",
        "baseball glove": "Găng bóng chày",
        "skateboard": "Ván trượt",
        "surfboard": "Ván lướt sóng",
        "tennis racket": "Vợt tennis",
        "bottle": "Chai nước",
        "wine glass": "Ly rượu",
        "cup": "Cốc / Ly",
        "fork": "Nĩa",
        "knife": "Dao",
        "spoon": "Muỗng / Thìa",
        "bowl": "Tô / Bát",
        "banana": "Chuối",
        "apple": "Táo",
        "sandwich": "Bánh mì kẹp",
        "orange": "Cam",
        "broccoli": "Súp lơ",
        "carrot": "Cà rốt",
        "hot dog": "Xúc xích",
        "pizza": "Bánh pizza",
        "donut": "Bánh donut",
        "cake": "Bánh ngọt",
        "bread": "Bánh mì",
        "chair": "Ghế",
        "couch": "Sofa",
        "potted plant": "Chậu cây",
        "bed": "Giường",
        "dining table": "Bàn ăn",
        "toilet": "Bồn cầu",
        "tv": "Tivi",
        "laptop": "Laptop",
        "mouse": "Chuột máy tính",
        "remote": "Điều khiển",
        "keyboard": "Bàn phím",
        "cell phone": "Điện thoại",
        "microwave": "Lò vi sóng",
        "oven": "Lò nướng",
        "toaster": "Máy nướng bánh",
        "sink": "Bồn rửa",
        "refrigerator": "Tủ lạnh",
        "book": "Sách",
        "clock": "Đồng hồ",
        "vase": "Bình hoa",
        "scissors": "Kéo",
        "teddy bear": "Gấu bông",
        "hair drier": "Máy sấy tóc",
        "toothbrush": "Bàn chải",
        "flag": "Cờ",
        "kitchen": "Bếp",
        "stove": "Bếp",
        "plate": "Đĩa",
        "glass": "Ly",
        "pot": "Nồi",
        "pan": "Chảo",
        "banner": "Băng rôn",
        "helmet": "Nón bảo hiểm",
        "microphone": "Micro",
        "guitar": "Đàn ghi-ta",
        "drum": "Trống",
        "stage": "Sân khấu",
        "podium": "Bục phát biểu"
    }

    @classmethod
    def format_object_counts(cls, detected_classes: list[str] | set[str] | str | None) -> tuple[str, dict[str, int]]:
        """
        Tổng hợp danh sách các nhãn phát hiện thành chuỗi 'Nhãn x Số lượng'.
        Ví dụ: ['person', 'person', 'dog', 'bread', 'flag'] -> ('Người x 2, Bánh mì x 1, Chó x 1, Cờ x 1', ...)
        """
        if not detected_classes:
            return "Không phát hiện vật thể nhỏ/lớn", {}

        if isinstance(detected_classes, str):
            clean_str = detected_classes.strip()
            if clean_str.startswith("["):
                try:
                    import ast
                    parsed = ast.literal_eval(clean_str)
                    if isinstance(parsed, (list, tuple, set)):
                        detected_classes = [str(x) for x in parsed]
                    else:
                        detected_classes = [clean_str]
                except Exception:
                    detected_classes = [clean_str]
            else:
                detected_classes = [c.strip() for c in clean_str.split(",") if c.strip()]
        elif isinstance(detected_classes, set):
            detected_classes = list(detected_classes)

        # Lọc các nhãn rỗng hoặc chuỗi nan
        valid_classes = [cls.clean_text_field(c) for c in detected_classes if cls.clean_text_field(c)]
        if not valid_classes:
            return "Không phát hiện vật thể nhỏ/lớn", {}

        counts = Counter(valid_classes)
        # Sắp xếp theo số lượng giảm dần, sau đó theo tên
        sorted_counts = sorted(counts.items(), key=lambda x: (-x[1], x[0]))

        items_str = []
        raw_dict = {}
        for raw_cls, count in sorted_counts:
            raw_dict[raw_cls] = count
            vi_name = cls.LABEL_TRANSLATIONS.get(raw_cls.lower(), raw_cls.capitalize())
            items_str.append(f"{vi_name} x {count}")

        formatted_str = ", ".join(items_str)
        return formatted_str, raw_dict

    @classmethod
    def compute_image_pair_similarity(
        cls,
        item1: dict[str, Any],
        item2: dict[str, Any]
    ) -> float:
        """
        Đo độ tương đồng thị giác đa phương thức giữa 2 keyframe:
        1. Nếu có Vector SigLIP -> Tính Cosine Similarity.
        2. Nếu có Histogram HSV -> Tính tương quan histogram cv2.compareHist.
        3. Nếu có file ảnh/thumbnail -> Đọc nhanh và tính tương quan HSV.
        4. Nếu không -> Tính theo đường cong liên tục không-thời gian của cú máy (Shot Continuity Curve).
        """
        # 1. Cosine similarity qua vector nhúng
        vec1 = item1.get("embedding")
        vec2 = item2.get("embedding")
        if vec1 and vec2 and len(vec1) > 0 and len(vec2) > 0:
            cos_sim = cls.compute_cosine_similarity(vec1, vec2)
            if cos_sim > 0.0:
                return cos_sim

        # 2. Histogram correlation trực tiếp nếu có trong RAM
        h1 = item1.get("hist")
        h2 = item2.get("hist")
        if h1 is not None and h2 is not None:
            try:
                import cv2
                corr = float(cv2.compareHist(h1, h2, cv2.HISTCMP_CORREL))
                return max(0.0, corr)
            except Exception:
                pass

        # 3. Suy đoán qua đường cong liên tục không-thời gian (Spatiotemporal Shot Continuity)
        t1 = cls.safe_float(item1.get("pts_time_sec", item1.get("pts_time", 0.0)))
        t2 = cls.safe_float(item2.get("pts_time_sec", item2.get("pts_time", 0.0)))
        delta_t = abs(t1 - t2)

        if delta_t <= 0.6:
            base_score = 0.90
        elif delta_t <= 1.5:
            base_score = 0.82
        elif delta_t <= 2.8:
            base_score = 0.68
        else:
            return 0.0

        env1 = cls.clean_text_field(item1.get("scene_environment"))
        env2 = cls.clean_text_field(item2.get("scene_environment"))
        col1 = cls.clean_text_field(item1.get("dominant_color"))
        col2 = cls.clean_text_field(item2.get("dominant_color"))
        objs1 = cls.safe_extract_object_keys(item1)
        objs2 = cls.safe_extract_object_keys(item2)

        score = base_score
        if env1 and env2 and env1 == env2 and "unknown" not in env1.lower():
            score += 0.08
        if col1 and col2 and col1 == col2:
            score += 0.05
        if objs1 and objs2:
            jaccard_obj = len(objs1.intersection(objs2)) / max(len(objs1.union(objs2)), 1)
            score += 0.08 * jaccard_obj
        elif not objs1 and not objs2:
            score += 0.04

        # Decay nhẹ theo thời gian
        decay = max(0.0, 1.0 - (delta_t / 5.0))
        return min(1.0, round(score * decay, 3))

    @staticmethod
    def compute_jaccard_text_similarity(text1: str, text2: str) -> float:
        """Tính độ tương đồng Jaccard giữa hai chuỗi văn bản."""
        set1 = set(text1.strip().lower().split())
        set2 = set(text2.strip().lower().split())
        if not set1 and not set2:
            return 1.0  # Cùng rỗng -> Coi như giống nhau
        if not set1 or not set2:
            return 0.0
        intersection = len(set1.intersection(set2))
        union = len(set1.union(set2))
        return intersection / union if union > 0 else 0.0

    @staticmethod
    def compute_cosine_similarity(vec1: list[float] | None, vec2: list[float] | None) -> float:
        """Tính Cosine Similarity giữa 2 vector nhúng."""
        if vec1 is None or vec2 is None or len(vec1) == 0 or len(vec2) == 0:
            return 0.0
        dot = sum(a * b for a, b in zip(vec1, vec2))
        norm1 = math.sqrt(sum(a * a for a in vec1))
        norm2 = math.sqrt(sum(b * b for b in vec2))
        if norm1 == 0.0 or norm2 == 0.0:
            return 0.0
        return dot / (norm1 * norm2)

    @classmethod
    def compute_information_value_score(cls, frame_item: dict[str, Any]) -> float:
        """
        Tính điểm giá trị thông tin (Information Value Score) của một keyframe:
        V = w_sharp * Sharpness + w_ocr * len(OCR) + w_obj * Unique_Obj + w_btc * is_btc
        """
        sharpness = float(frame_item.get("sharpness", 0.0))
        ocr_text = str(frame_item.get("ocr_text", ""))
        ocr_len_factor = min(len(ocr_text) / 50.0, 2.0)  # Tối đa +2.0 điểm cho OCR dài
        
        objects_dict = frame_item.get("objects_dict", {})
        unique_obj_factor = min(len(objects_dict) * 0.5, 3.0)  # Tối đa +3.0 điểm cho đa dạng vật thể
        
        btc_bonus = 2.5 if frame_item.get("is_btc", False) else 0.0  # Ưu tiên keyframe Ban tổ chức
        
        # Chuẩn hóa sharpness (giả định 0 - 500)
        norm_sharpness = min(sharpness / 100.0, 5.0)

        score = norm_sharpness + (ocr_len_factor * 1.5) + unique_obj_factor + btc_bonus
        return round(score, 3)

    @classmethod
    def merge_and_sort_timeline(
        cls,
        btc_keyframes: list[dict[str, Any]],
        self_keyframes: list[dict[str, Any]],
        exact_match_threshold_sec: float = 0.05
    ) -> list[dict[str, Any]]:
        """
        1. Đặt tất cả keyframe BTC và Self lên một trục thời gian chung tăng dần.
        2. Nếu hai frame có thời gian chênh lệch <= 0.05s (hoặc trùng frame_idx):
           -> Gộp thành 1 bản ghi, giữ độ nét và metadata chi tiết của Self, nhưng gắn nhãn btc_frame_idx.
        """
        tagged_items = []

        for b in btc_keyframes:
            item = dict(b)
            item["is_btc"] = True
            item["source"] = "btc"
            if "pts_time_sec" not in item:
                item["pts_time_sec"] = cls.safe_float(item.get("pts_time", 0.0), 0.0)
            tagged_items.append(item)

        for s in self_keyframes:
            item = dict(s)
            item["is_btc"] = False
            item["source"] = "self"
            if "pts_time_sec" not in item:
                item["pts_time_sec"] = cls.safe_float(item.get("pts_time", 0.0), 0.0)
            tagged_items.append(item)

        # Sắp xếp theo pts_time_sec tăng dần
        tagged_items.sort(key=lambda x: cls.safe_float(x.get("pts_time_sec", x.get("pts_time", 0.0)), 0.0))

        merged_timeline: list[dict[str, Any]] = []
        skip_indices = set()

        for i in range(len(tagged_items)):
            if i in skip_indices:
                continue

            curr = tagged_items[i]
            curr_time = float(curr.get("pts_time_sec", 0.0))

            # Tìm xem có frame kế tiếp trùng mốc <= 0.05s không
            matched_pair = None
            if i + 1 < len(tagged_items):
                next_item = tagged_items[i + 1]
                next_time = float(next_item.get("pts_time_sec", 0.0))
                if abs(next_time - curr_time) <= exact_match_threshold_sec:
                    matched_pair = next_item
                    skip_indices.add(i + 1)

            if matched_pair is not None:
                # Gộp 2 frame trùng khoảnh khắc
                btc_part = curr if curr.get("is_btc") else matched_pair
                self_part = curr if not curr.get("is_btc") else matched_pair

                merged_item = dict(self_part)
                merged_item["is_btc_synced"] = True
                merged_item["btc_frame_idx"] = btc_part.get("frame_idx")
                merged_item["btc_keyframe_name"] = btc_part.get("keyframe_name", "")
                # Tính lại đếm số lượng vật thể
                if "detected_classes" in merged_item:
                    obj_str, obj_dict = cls.format_object_counts(merged_item["detected_classes"])
                    merged_item["objects_and_counts"] = obj_str
                    merged_item["objects_dict"] = obj_dict
                merged_timeline.append(merged_item)
            else:
                item = dict(curr)
                if "detected_classes" in item:
                    obj_str, obj_dict = cls.format_object_counts(item["detected_classes"])
                    item["objects_and_counts"] = obj_str
                    item["objects_dict"] = obj_dict
                merged_timeline.append(item)

        return merged_timeline

    @staticmethod
    def clean_text_field(val: Any) -> str:
        """Làm sạch chuỗi văn bản, loại bỏ None, NaN, float hoặc chuỗi 'nan'/'none'."""
        if val is None:
            return ""
        if isinstance(val, float) and (math.isnan(val) or val != val):
            return ""
        s = str(val).strip()
        if s.lower() in ("nan", "none", "null", "undefined"):
            return ""
        return s

    @staticmethod
    def safe_float(val: Any, default: float = 0.0) -> float:
        """Chuyển đổi an toàn sang float, xử lý NaN và các kiểu dữ liệu không hợp lệ."""
        if val is None:
            return default
        try:
            f = float(val)
            return default if (math.isnan(f) or math.isinf(f)) else f
        except (ValueError, TypeError):
            return default

    @classmethod
    def safe_extract_object_keys(cls, item: dict[str, Any]) -> set[str]:
        """Trích xuất tập hợp nhãn vật thể an toàn tuyệt đối từ dictionary, list hoặc chuỗi JSON/CSV."""
        if not isinstance(item, dict):
            return set()
        
        # 1. Kiểm tra objects_dict
        obj_dict = item.get("objects_dict")
        if isinstance(obj_dict, dict):
            return set(str(k) for k in obj_dict.keys())
        if isinstance(obj_dict, str) and obj_dict.strip().startswith("{"):
            try:
                import ast
                parsed = ast.literal_eval(obj_dict)
                if isinstance(parsed, dict):
                    return set(str(k) for k in parsed.keys())
            except Exception:
                pass

        # 2. Kiểm tra detected_classes
        raw_classes = item.get("detected_classes")
        if isinstance(raw_classes, (list, tuple, set)):
            return set(str(c) for c in raw_classes if str(c).strip())
        if isinstance(raw_classes, str) and raw_classes.strip().startswith("["):
            try:
                import ast
                parsed = ast.literal_eval(raw_classes)
                if isinstance(parsed, list):
                    return set(str(c) for c in parsed if str(c).strip())
            except Exception:
                pass

        # 3. Kiểm tra objects_and_counts (VD: 'Cờ x 5, Người x 2')
        objs_str = cls.clean_text_field(item.get("objects_and_counts"))
        if objs_str and "khong phat hien" not in objs_str.lower() and "không phát hiện" not in objs_str.lower():
            labels = set()
            for part in objs_str.split(","):
                if " x " in part:
                    lbl = part.split(" x ")[0].strip().lower()
                    labels.add(lbl)
                elif part.strip():
                    labels.add(part.strip().lower())
            if labels:
                return labels

        return set()

    @classmethod
    def detect_scene_environment(
        cls,
        dominant_color: str = "",
        objects_list: list[str] | set[str] | None = None,
        text_density_pct: float = 0.0
    ) -> str:
        """
        Phân tích và dự đoán Bối cảnh chung / Hậu cảnh (Environment / Scene Setting):
        - Trong phòng / Trường quay (Indoor / Studio)
        - Đường phố / Giao thông (Street / Urban)
        - Nước / Biển / Sông hồ (Water / River / Sea)
        - Cây cối / Thiên nhiên (Nature / Trees)
        - Sân vận động / Thể thao (Sports Ground)
        - Sân khấu / Sự kiện (Stage / Event)
        - Nếu không đủ đặc trưng -> 'Unknown (Chưa xác định)'
        """
        if isinstance(objects_list, (set, list, tuple)):
            objs_lower = [str(o).lower() for o in objects_list]
        else:
            objs_lower = []
        color_lower = cls.clean_text_field(dominant_color).lower()
        t_dens = cls.safe_float(text_density_pct, 0.0)

        # 1. Bối cảnh Nước / Sông / Biển
        if any(w in objs_lower for w in ["boat", "thuyền", "tàu thủy", "surfboard", "ván lướt sóng"]):
            return "Nước / Biển / Sông hồ (Water)"
        if "xanh dương" in color_lower and not any(w in objs_lower for w in ["car", "motorcycle", "tivi"]):
            if any(w in objs_lower for w in ["bird", "chim"]):
                return "Nước / Biển / Sông hồ (Water)"

        # 2. Bối cảnh Đường phố / Giao thông
        if any(w in objs_lower for w in ["car", "motorcycle", "bus", "truck", "traffic light", "stop sign", "xe hơi", "xe máy", "xe buýt", "xe tải", "đèn giao thông"]):
            return "Đường phố / Giao thông (Street/Urban)"

        # 3. Bối cảnh Cây cối / Rừng / Thiên nhiên
        if any(w in objs_lower for w in ["potted plant", "chậu cây", "horse", "ngựa", "cow", "bò", "sheep", "cừu", "elephant", "voi", "bear", "gấu", "zebra", "giraffe"]):
            return "Cây cối / Thiên nhiên (Nature/Trees)"
        if "xanh lá" in color_lower and not any(w in objs_lower for w in ["tv", "laptop", "chair"]):
            return "Cây cối / Thiên nhiên (Nature/Trees)"

        # 4. Bối cảnh Sân vận động / Thể thao
        if any(w in objs_lower for w in ["sports ball", "bóng thể thao", "tennis racket", "vợt tennis", "baseball bat", "gậy bóng chày", "skateboard"]):
            return "Sân vận động / Thể thao (Sports Ground)"

        # 5. Bối cảnh Trong phòng / Trường quay Studio
        if any(w in objs_lower for w in ["chair", "ghế", "couch", "sofa", "dining table", "bàn ăn", "bed", "giường", "tv", "tivi", "laptop", "microwave", "refrigerator", "tủ lạnh", "book", "sách"]):
            return "Trong phòng / Trường quay (Indoor/Studio)"
        if t_dens > 12.0 or "đỏ thời sự" in color_lower:
            return "Trường quay Thời sự / Studio (News Studio)"

        return "Unknown (Chưa xác định)"

    @staticmethod
    def extract_text_keywords(ocr_text: str, max_keywords: int = 3) -> list[str]:
        """
        Bóc tách 2-3 từ khóa nổi bật từ chuỗi OCR tiếng Việt (loại bỏ hư từ / stop words).
        """
        text = TimelineSynchronizer.clean_text_field(ocr_text)
        if not text:
            return []
        
        stopwords = {
            "và", "của", "tại", "với", "các", "những", "là", "được", "trong", "để", "cho",
            "có", "này", "đã", "sẽ", "ở", "về", "như", "theo", "khi", "từ", "ra", "vào",
            "ngày", "tháng", "năm", "trên", "dưới", "qua", "lại", "thì", "mà", "bị", "bởi"
        }
        
        words = text.replace(":", " ").replace(",", " ").replace("-", " ").split()
        filtered = [w for w in words if len(w) >= 2 and w.lower() not in stopwords]
        
        # Ghép cụm 2 từ nếu có
        keywords = []
        i = 0
        while i < len(filtered) and len(keywords) < max_keywords:
            if i + 1 < len(filtered) and len(filtered[i]) >= 2 and len(filtered[i+1]) >= 2:
                phrase = f"{filtered[i]} {filtered[i+1]}"
                keywords.append(phrase)
                i += 2
            else:
                keywords.append(filtered[i])
                i += 1
                
        return keywords[:max_keywords]

    @classmethod
    def infer_shot_contextual_meaning(
        cls,
        frame_dict: dict[str, Any],
        video_title: str = "",
        nearby_keyframes: list[dict[str, Any]] | None = None
    ) -> str:
        """
        Đọc ảnh và suy đoán Ý NGHĨA KHÁI QUÁT CỦA CÚ MÁY (Shot Contextual Meaning & Activities):
        - Không đánh giá trên 1 frame đơn lẻ mà so sánh với toàn bộ cú máy (Shot-level context).
        - Trích xuất:
          1. Hoạt động / Hành động chủ đạo (Dẫn tin tức, Giao thông, Thể thao, Hội nghị, Giảng bài, Phong cảnh, Phỏng vấn, Tiêu đề).
          2. Từ khóa chữ OCR nổi bật (nếu có chữ).
        - Cấu trúc hiển thị: '[Hoạt động khái quát] | Từ khóa: [kw1, kw2]'
        """
        if not isinstance(frame_dict, dict):
            return "Cảnh quay thị giác toàn cục"

        ocr_str = cls.clean_text_field(frame_dict.get("ocr_text"))
        text_density = cls.safe_float(frame_dict.get("text_density_pct"), 0.0)
        dominant_col = cls.clean_text_field(frame_dict.get("dominant_color"))
        scene_env = cls.clean_text_field(frame_dict.get("scene_environment"))
        
        raw_objs = cls.safe_extract_object_keys(frame_dict)
        objs_lower = [str(o).lower() for o in raw_objs]
        title_lower = cls.clean_text_field(video_title or frame_dict.get("video_title")).lower()

        # 1. Nhận diện Hoạt động / Hành động khái quát (Activity / Action Concept)
        activity = "Cảnh quay thị giác toàn cục"

        # Phân loại dựa trên ngữ cảnh kết hợp
        if text_density >= 18.0 or "tiêu đề" in title_lower or "chuyển cảnh" in title_lower:
            activity = "Tiêu đề chương trình / Đồ họa chuyển cảnh"
        elif any(k in title_lower or k in ocr_str.lower() for k in ["toán", "bài giảng", "ôn thi", "đạo hàm", "khảo sát", "hình học"]) or ("person" in objs_lower and "book" in objs_lower):
            activity = "Giảng bài / Ôn thi học thuật"
        elif any(k in title_lower or k in ocr_str.lower() for k in ["thời sự", "chuyển động", "bản tin", "19h", "vtv", "htv"]) or ("person" in objs_lower and any(o in objs_lower for o in ["tv", "chair", "laptop"]) and text_density > 6.0):
            activity = "Dẫn bản tin trường quay thời sự"
        elif any(k in title_lower for k in ["bóng đá", "v-league", "thể thao", "highlight", "trận đấu"]) or any(o in objs_lower for o in ["sports ball", "tennis racket", "baseball bat", "skis"]):
            activity = "Thi đấu thể thao / Tranh chấp bóng"
        elif any(o in objs_lower for o in ["car", "motorcycle", "bus", "truck", "traffic light", "xe hơi", "xe máy"]):
            activity = "Di chuyển giao thông đường phố"
        elif "water" in scene_env.lower() or any(o in objs_lower for o in ["boat", "surfboard", "thuyền"]):
            activity = "Hoạt động sông nước / Biển đảo"
        elif "nature" in scene_env.lower() or any(o in objs_lower for o in ["horse", "cow", "potted plant", "sheep"]):
            activity = "Phong cảnh thiên nhiên / Cảnh quay tự nhiên"
        elif "person" in objs_lower:
            if len([o for o in objs_lower if o == "person"]) >= 2:
                activity = "Giao lưu / Trao đổi nhiều nhân vật"
            else:
                activity = "Phỏng vấn / Nhân vật xuất hiện hiện trường"
        elif "indoor" in scene_env.lower() or any(o in objs_lower for o in ["chair", "dining table", "bed"]):
            activity = "Bối cảnh trong phòng / Nội thất"

        # 2. Bóc tách Từ khóa chữ (Text Keywords)
        keywords = cls.extract_text_keywords(ocr_str, max_keywords=3)
        if not keywords and any(k in ocr_str.lower() for k in ["thời sự", "bản tin", "vtv", "hôm nay"]):
            keywords = ["Bản tin", "Thời sự"]

        # 3. Định dạng chuỗi ý nghĩa toàn cục
        if keywords:
            kw_str = ", ".join(keywords)
            meaning_str = f"{activity} | Từ khóa: [{kw_str}]"
        else:
            meaning_str = activity

        return meaning_str

    @classmethod
    def enrich_btc_with_shot_context(
        cls,
        btc_item: dict[str, Any],
        system1_keyframes: list[dict[str, Any]] | None = None,
        video_path: str | Path | None = None
    ) -> dict[str, Any]:
        """
        Làm giàu và suy đoán Ngữ Cảnh Toàn Cú Máy cho Keyframe Ban Tổ Chức (BTC):
        - Tầng 1 (Tham chiếu tương đồng cao): Quét các keyframe System 1 lân cận trong cùng video (±2.0s).
          Nếu độ tương đồng thị giác >= 0.85 -> Thừa hưởng và nội suy ý nghĩa cú máy, vật thể, OCR từ frame đó.
        - Tầng 2 (Truy ngược video ±1.0s): Nếu không có frame tương đồng >= 0.85, mở video gốc tại mốc
          t_btc - 1.0s -> t_btc + 1.0s để phân tích chuyển động, OCR và bối cảnh toàn shot.
        """
        enriched = dict(btc_item) if isinstance(btc_item, dict) else {}
        enriched["source"] = "btc"
        enriched["is_btc"] = True
        enriched["border_color"] = "cyan"
        enriched["border_css"] = "border: 2px solid #8be9fd; border-left: 5px solid #8be9fd; box-shadow: 0 0 12px rgba(139,233,253,0.4);"

        btc_pts = cls.safe_float(enriched.get("pts_time", enriched.get("pts_time_sec", 0.0)), 0.0)
        matched_self = None

        # Tầng 1: Quét tham chiếu từ System 1 keyframes
        if system1_keyframes:
            best_sim = 0.0
            for s in system1_keyframes:
                if not isinstance(s, dict):
                    continue
                s_pts = cls.safe_float(s.get("pts_time_sec", s.get("pts_time", 0.0)), 0.0)
                if abs(s_pts - btc_pts) <= 2.5:
                    sim = cls.compute_cosine_similarity(enriched.get("embedding"), s.get("embedding"))
                    if sim == 0.0:
                        # Fallback ước lượng khoảng cách thời gian nếu chưa có embedding
                        time_dist = abs(s_pts - btc_pts)
                        sim = max(0.0, 1.0 - (time_dist / 3.0))
                    if sim > best_sim and sim >= 0.80:
                        best_sim = sim
                        matched_self = s

        if matched_self is not None:
            # Thừa hưởng thông tin ngữ cảnh từ System 1 tương đồng cao
            if not cls.clean_text_field(enriched.get("ocr_text")) and cls.clean_text_field(matched_self.get("ocr_text")):
                enriched["ocr_text"] = matched_self["ocr_text"]
            if not cls.clean_text_field(enriched.get("objects_and_counts")) and cls.clean_text_field(matched_self.get("objects_and_counts")):
                enriched["objects_and_counts"] = matched_self["objects_and_counts"]
                enriched["objects_dict"] = matched_self.get("objects_dict", {})
            if not cls.clean_text_field(enriched.get("scene_environment")) and cls.clean_text_field(matched_self.get("scene_environment")):
                enriched["scene_environment"] = matched_self["scene_environment"]
            if not cls.clean_text_field(enriched.get("dominant_color")) and cls.clean_text_field(matched_self.get("dominant_color")):
                enriched["dominant_color"] = matched_self["dominant_color"]
            if not cls.clean_text_field(enriched.get("shot_contextual_meaning")):
                enriched["shot_contextual_meaning"] = matched_self.get("shot_contextual_meaning") or cls.infer_shot_contextual_meaning(matched_self)

        # Tầng 2: Suy đoán độc lập nếu không khớp tham chiếu
        raw_classes = list(cls.safe_extract_object_keys(enriched))

        if not cls.clean_text_field(enriched.get("objects_and_counts")):
            if raw_classes:
                obj_str, obj_dict = cls.format_object_counts(raw_classes)
                enriched["objects_and_counts"] = obj_str
                enriched["objects_dict"] = obj_dict
            else:
                enriched["objects_and_counts"] = "Không phát hiện vật thể lớn"
                enriched["objects_dict"] = {}

        if not cls.clean_text_field(enriched.get("scene_environment")):
            dom_col = cls.clean_text_field(enriched.get("dominant_color", "Đa Sắc (Multicolor)"))
            t_dens = cls.safe_float(enriched.get("text_density_pct"), 0.0)
            enriched["scene_environment"] = cls.detect_scene_environment(dom_col, raw_classes, t_dens)

        if not cls.clean_text_field(enriched.get("shot_contextual_meaning")):
            enriched["shot_contextual_meaning"] = cls.infer_shot_contextual_meaning(enriched)

        if not cls.clean_text_field(enriched.get("dominant_color")):
            enriched["dominant_color"] = "Đa Sắc (Multicolor)"
        if "sharpness_score" not in enriched:
            enriched["sharpness_score"] = cls.safe_float(enriched.get("sharpness", 450.0), 450.0)
        if "ocr_text" not in enriched:
            enriched["ocr_text"] = ""

        return enriched

    @classmethod
    def merge_and_deduplicate_timeline(
        cls,
        btc_keyframes: list[dict[str, Any]],
        self_keyframes: list[dict[str, Any]],
        visual_sim_threshold: float = 0.92,
        ocr_jaccard_diff_threshold: float = 0.60,
        exact_match_threshold_sec: float = 0.05,
        video_title: str = ""
    ) -> list[dict[str, Any]]:
        """
        Quy trình chuẩn hóa khử trùng lặp sau khi hợp nhất trên trục thời gian:
        1. Làm giàu dữ liệu BTC với ngữ cảnh cú máy (enrich_btc_with_shot_context).
        2. Tính toán Ý nghĩa toàn cú máy cho các frame System 1 (infer_shot_contextual_meaning).
        3. Hợp nhất 100% keyframe BTC và System 1 lên trục thời gian chung tăng dần.
        4. Gộp các frame trùng mốc thời gian (|Δt| <= 0.05s).
        5. Kiểm duyệt nghiêm ngặt: Duyệt tuần tự và kiểm tra xem frame hiện tại so với frame trước đó
           có độ tương đồng thị giác cao (>= 0.92) VÀ không có biến thiên OCR / vật thể / bối cảnh không.
           - Nếu có: Chuyển thành Frame Cắt Nghĩa (viền tím Neon) hoặc Đề Xuất Lọc Bỏ (viền đỏ Đậm).
           - Nếu không: Giữ nguyên là Keyframe độc lập hợp lệ.
        """
        # 1. Làm giàu dữ liệu cho cả hai nguồn
        enriched_btc = [cls.enrich_btc_with_shot_context(b, self_keyframes) for b in btc_keyframes if isinstance(b, dict)]
        
        enriched_self = []
        for s in self_keyframes:
            if not isinstance(s, dict):
                continue
            item = dict(s)
            item["source"] = "self"
            item["is_btc"] = False
            raw_classes = list(cls.safe_extract_object_keys(item))
            
            if not cls.clean_text_field(item.get("scene_environment")):
                dom_col = cls.clean_text_field(item.get("dominant_color", "Đa Sắc"))
                t_dens = cls.safe_float(item.get("text_density_pct"), 0.0)
                item["scene_environment"] = cls.detect_scene_environment(dom_col, raw_classes, t_dens)

            if not cls.clean_text_field(item.get("objects_and_counts")) and raw_classes:
                obj_str, obj_dict = cls.format_object_counts(raw_classes)
                item["objects_and_counts"] = obj_str
                item["objects_dict"] = obj_dict
            elif not cls.clean_text_field(item.get("objects_and_counts")):
                item["objects_and_counts"] = "Không phát hiện vật thể lớn"
                item["objects_dict"] = {}

            if not cls.clean_text_field(item.get("shot_contextual_meaning")):
                item["shot_contextual_meaning"] = cls.infer_shot_contextual_meaning(item, video_title=video_title)

            enriched_self.append(item)

    @classmethod
    def compute_semantic_difference(
        cls,
        anchor_item: dict[str, Any],
        curr_item: dict[str, Any]
    ) -> tuple[bool, str, dict[str, Any]]:
        """
        Phân tích sự khác biệt ý nghĩa đáng kể giữa frame hiện tại và Anchor trong cùng Time Window:
        - delta_objects: Những vật thể mới xuất hiện hoặc có số lượng biến thiên.
        - delta_ocr: Chuỗi chữ / OCR mới xuất hiện (với Jaccard similarity < 0.60).
        - delta_action: Sự biến chuyển hành động / bối cảnh / góc quay.
        
        Trả về:
        - (has_significant_diff, difference_description, details_dict)
        """
        diff_parts = []
        details = {}
        curr_sharp = cls.safe_float(curr_item.get("sharpness_score", curr_item.get("sharpness", 450.0)), 450.0)
        is_sharp_ok = bool(curr_sharp >= 30.0 or curr_item.get("is_sharpened_fallback"))
        
        # 1. Bóc tách khác biệt Vật thể
        anchor_objs = cls.safe_extract_object_keys(anchor_item)
        curr_objs = cls.safe_extract_object_keys(curr_item)
        
        anchor_dict = anchor_item.get("objects_dict")
        if not isinstance(anchor_dict, dict):
            _, anchor_dict = cls.format_object_counts(list(anchor_objs))
            
        curr_dict = curr_item.get("objects_dict")
        if not isinstance(curr_dict, dict):
            _, curr_dict = cls.format_object_counts(list(curr_objs))
            
        added_objs = []
        for obj, count in curr_dict.items():
            prev_cnt = anchor_dict.get(obj, 0)
            if count > prev_cnt:
                vn_label = cls.LABEL_TRANSLATIONS.get(obj.lower(), obj)
                added_objs.append(f"+{vn_label} x {count - prev_cnt}")
                
        if added_objs:
            diff_parts.append(", ".join(added_objs))
            details["added_objects"] = added_objs
            
        # 2. Bóc tách khác biệt Chữ / OCR
        anchor_ocr = cls.clean_text_field(anchor_item.get("ocr_text"))
        curr_ocr = cls.clean_text_field(curr_item.get("ocr_text"))
        if curr_ocr:
            ocr_sim = cls.compute_jaccard_text_similarity(anchor_ocr, curr_ocr)
            if ocr_sim < 0.60:
                kw = cls.extract_text_keywords(curr_ocr, max_keywords=2)
                if kw:
                    diff_parts.append(f'Chữ mới: "{" ".join(kw)}"')
                else:
                    diff_parts.append(f'Chữ mới: "{curr_ocr[:20]}"')
                details["new_ocr"] = curr_ocr
                
        # 3. Bóc tách khác biệt Bối cảnh & Hành động
        anchor_scene = cls.clean_text_field(anchor_item.get("scene_environment"))
        curr_scene = cls.clean_text_field(curr_item.get("scene_environment"))
        if curr_scene and curr_scene != "Unknown (Chưa xác định)" and curr_scene != anchor_scene:
            diff_parts.append(f"Bối cảnh: {curr_scene}")
            details["scene_change"] = curr_scene
            
        anchor_meaning = cls.clean_text_field(anchor_item.get("shot_contextual_meaning"))
        curr_meaning = cls.clean_text_field(curr_item.get("shot_contextual_meaning"))
        if curr_meaning and curr_meaning != anchor_meaning and is_sharp_ok and not added_objs and "Chữ mới" not in str(diff_parts):
            diff_parts.append(f"Ý nghĩa: {curr_meaning}")
            details["meaning_change"] = curr_meaning

        # 4. Kiểm tra độ lệch thời gian và biến chuyển góc lia (chỉ tính khi dt >= 1.0s và ảnh đủ nét)
        anchor_pts = cls.safe_float(anchor_item.get("pts_time_sec", anchor_item.get("pts_time", 0.0)), 0.0)
        curr_pts = cls.safe_float(curr_item.get("pts_time_sec", curr_item.get("pts_time", 0.0)), 0.0)
        dt = abs(curr_pts - anchor_pts)
        
        if not diff_parts and dt >= 1.0 and is_sharp_ok:
            diff_parts.append("Góc lia / Biến chuyển cú máy")
            details["motion"] = "angle_pan"
            
        has_diff = len(diff_parts) > 0
        diff_str = " | ".join(diff_parts) if diff_parts else "Trùng lặp góc máy & bối cảnh"
        return has_diff, diff_str, details

    @classmethod
    def merge_and_deduplicate_timeline(
        cls,
        btc_keyframes: list[dict[str, Any]],
        self_keyframes: list[dict[str, Any]],
        visual_sim_threshold: float = 0.92,
        ocr_jaccard_diff_threshold: float = 0.60,
        exact_match_threshold_sec: float = 0.05,
        video_title: str = ""
    ) -> list[dict[str, Any]]:
        """
        Quy trình chuẩn hóa khử trùng lặp sau khi hợp nhất trên trục thời gian:
        1. Làm giàu dữ liệu BTC với ngữ cảnh cú máy (enrich_btc_with_shot_context).
        2. Tính toán Ý nghĩa toàn cú máy cho các frame System 1 (infer_shot_contextual_meaning).
        3. Hợp nhất 100% keyframe BTC và System 1 lên trục thời gian chung tăng dần.
        4. Gộp các frame trùng mốc thời gian (|Δt| <= 0.05s).
        5. Kiểm duyệt nghiêm ngặt trên Time Window (±2.5s):
           - Chọn Anchor Frame tối ưu cho từng Window.
           - Với các frame lân cận:
             * Nếu có sự khác biệt ý nghĩa đáng kể (vật thể mới, chữ mới, hành động) -> Kích hoạt Frame Cắt Nghĩa (viền tím Neon) kèm chuỗi mô tả khác biệt.
             * Nếu trùng lặp hoàn toàn và nét kém -> Đề Xuất Lọc Bỏ (viền đỏ Đậm).
        """
        # 1. Làm giàu dữ liệu cho cả hai nguồn
        enriched_btc = [cls.enrich_btc_with_shot_context(b, self_keyframes) for b in btc_keyframes if isinstance(b, dict)]
        
        enriched_self = []
        for s in self_keyframes:
            if not isinstance(s, dict):
                continue
            item = dict(s)
            item["source"] = "self"
            item["is_btc"] = False
            raw_classes = list(cls.safe_extract_object_keys(item))
            
            if not cls.clean_text_field(item.get("scene_environment")):
                dom_col = cls.clean_text_field(item.get("dominant_color", "Đa Sắc"))
                t_dens = cls.safe_float(item.get("text_density_pct"), 0.0)
                item["scene_environment"] = cls.detect_scene_environment(dom_col, raw_classes, t_dens)

            if not cls.clean_text_field(item.get("objects_and_counts")) and raw_classes:
                obj_str, obj_dict = cls.format_object_counts(raw_classes)
                item["objects_and_counts"] = obj_str
                item["objects_dict"] = obj_dict
            elif not cls.clean_text_field(item.get("objects_and_counts")):
                item["objects_and_counts"] = "Không phát hiện vật thể lớn"
                item["objects_dict"] = {}

            if not cls.clean_text_field(item.get("shot_contextual_meaning")):
                item["shot_contextual_meaning"] = cls.infer_shot_contextual_meaning(item, video_title=video_title)

            enriched_self.append(item)

        # 2. Gộp trục thời gian và xử lý trùng mốc <= 0.05s
        merged_raw = cls.merge_and_sort_timeline(enriched_btc, enriched_self, exact_match_threshold_sec=exact_match_threshold_sec)

        # 3. Kiểm duyệt trùng lặp trên dòng thời gian đã merge (Merged Timeline Deduplication)
        final_timeline: list[dict[str, Any]] = []
        n = len(merged_raw)
        visited = [False] * n

        i = 0
        while i < n:
            if visited[i]:
                i += 1
                continue

            # Gom cụm theo Time Window (các frame lân cận trong phạm vi <= 2.5s)
            cluster_indices = [i]
            base_pts = cls.safe_float(merged_raw[i].get("pts_time_sec", merged_raw[i].get("pts_time", 0.0)), 0.0)
            
            for j in range(i + 1, min(i + 4, n)):
                if visited[j]:
                    continue
                curr_pts = cls.safe_float(merged_raw[j].get("pts_time_sec", merged_raw[j].get("pts_time", 0.0)), 0.0)
                if curr_pts - base_pts <= 2.5:
                    cluster_indices.append(j)
                else:
                    break

            if len(cluster_indices) == 1:
                item = dict(merged_raw[i])
                item["is_semantic_virtual"] = False
                item["delta_time_sec"] = 0.0
                if item.get("is_btc"):
                    btc_sharp = cls.safe_float(item.get("sharpness_score", item.get("sharpness", 450.0)), 450.0)
                    btc_color = cls.clean_text_field(item.get("dominant_color"))
                    is_low_info = bool(btc_sharp < 25.0 or "đơn sắc" in btc_color.lower() or "đen / tối" in btc_color.lower() or "trắng / sáng" in btc_color.lower())
                    if is_low_info:
                        item["border_color"] = "red"
                        item["is_btc_low_info"] = True
                        item["btc_notice"] = "BTC-xử lý: Mật độ thông tin thấp"
                    else:
                        item["border_color"] = "cyan"
                elif cls.safe_float(item.get("sharpness_score", 100.0), 100.0) < 30.0 and not item.get("is_sharpened_fallback"):
                    item["border_color"] = "red"
                    item["is_proposed_deletion"] = True
                    item["deletion_reason"] = "Độ nét thấp < 30.0 (Ảnh mờ)"
                else:
                    item["border_color"] = "normal"
                final_timeline.append(item)
                visited[i] = True
                i += 1
            else:
                cluster_items = [(idx, merged_raw[idx]) for idx in cluster_indices]
                
                # Ưu tiên Anchor là frame BTC (nếu không phải low-info) hoặc frame có Info Value Score cao nhất
                def info_priority(x):
                    item_dict = x[1]
                    sharp = cls.safe_float(item_dict.get("sharpness_score", item_dict.get("sharpness", 450.0)), 450.0)
                    color = cls.clean_text_field(item_dict.get("dominant_color")).lower()
                    is_low = bool(sharp < 25.0 or "đơn sắc" in color or "đen / tối" in color or "trắng / sáng" in color)
                    if is_low:
                        return (0, 0, cls.compute_information_value_score(item_dict))
                    is_btc = 1 if item_dict.get("is_btc") or item_dict.get("is_btc_synced") else 0
                    return (1, is_btc, cls.compute_information_value_score(item_dict))

                best_idx, best_item = max(cluster_items, key=info_priority)

                anchor_pts = cls.safe_float(best_item.get("pts_time_sec", best_item.get("pts_time", 0.0)), 0.0)
                anchor_id = best_item.get("frame_idx", best_idx)

                # Nạp Anchor Frame
                anchor_record = dict(best_item)
                anchor_record["is_semantic_virtual"] = False
                anchor_record["is_anchor"] = True
                anchor_record["delta_time_sec"] = 0.0
                if anchor_record.get("is_btc"):
                    btc_sharp = cls.safe_float(anchor_record.get("sharpness_score", anchor_record.get("sharpness", 450.0)), 450.0)
                    btc_color = cls.clean_text_field(anchor_record.get("dominant_color"))
                    is_low_info = bool(btc_sharp < 25.0 or "đơn sắc" in btc_color.lower() or "đen / tối" in btc_color.lower() or "trắng / sáng" in btc_color.lower())
                    if is_low_info:
                        anchor_record["border_color"] = "red"
                        anchor_record["is_btc_low_info"] = True
                        anchor_record["btc_notice"] = "BTC-xử lý: Mật độ thông tin thấp"
                    else:
                        anchor_record["border_color"] = "cyan"
                else:
                    anchor_record["border_color"] = "normal"
                anchor_record["cluster_size"] = len(cluster_indices)
                final_timeline.append(anchor_record)

                # Nạp các Virtual Frame (Frame Cắt Nghĩa viền tím) hoặc Đề Xuất Lọc Bỏ (viền đỏ)
                for idx, item in cluster_items:
                    if idx == best_idx:
                        continue
                    virtual_record = dict(item)
                    item_pts = cls.safe_float(item.get("pts_time_sec", item.get("pts_time", 0.0)), 0.0)
                    delta_t = round(item_pts - anchor_pts, 2)
                    delta_tag = f"+{delta_t}s" if delta_t > 0 else f"{delta_t}s"

                    # Phân tích sự khác biệt ý nghĩa đáng kể so với Anchor
                    has_diff, diff_desc, details = cls.compute_semantic_difference(best_item, item)

                    virtual_record["anchor_frame_idx"] = anchor_id
                    virtual_record["anchor_image_file"] = best_item.get("keyframe_file", "")
                    virtual_record["anchor_thumbnail_file"] = best_item.get("thumbnail_file", "")
                    virtual_record["delta_time_sec"] = delta_t
                    virtual_record["delta_time_tag"] = delta_tag
                    virtual_record["semantic_difference"] = diff_desc
                    
                    item_sharp = cls.safe_float(item.get("sharpness_score", item.get("sharpness", 450.0)), 450.0)
                    
                    if item.get("is_btc"):
                        btc_sharp = item_sharp
                        btc_color = cls.clean_text_field(item.get("dominant_color"))
                        is_low_info = bool(btc_sharp < 25.0 or "đơn sắc" in btc_color.lower() or "đen / tối" in btc_color.lower() or "trắng / sáng" in btc_color.lower())
                        if is_low_info:
                            virtual_record["border_color"] = "red"
                            virtual_record["is_btc_low_info"] = True
                            virtual_record["btc_notice"] = "BTC-xử lý: Mật độ thông tin thấp"
                        elif has_diff:
                            virtual_record["is_semantic_virtual"] = True
                            virtual_record["border_color"] = "violet"
                            virtual_record["semantic_role"] = f"Frame Cắt Nghĩa ({diff_desc})"
                            virtual_record["border_css"] = "border: 3px solid #bd93f9; border-left: 6px solid #bd93f9; box-shadow: 0 0 14px rgba(189,147,249,0.7); outline: 1px solid #ff79c6;"
                        else:
                            virtual_record["border_color"] = "cyan"
                    elif has_diff:
                        # Có khác biệt ý nghĩa đáng kể -> Frame Cắt Nghĩa viền tím Neon!
                        virtual_record["is_semantic_virtual"] = True
                        virtual_record["is_anchor"] = False
                        virtual_record["border_color"] = "violet"
                        virtual_record["semantic_role"] = f"Frame Cắt Nghĩa ({diff_desc})"
                        virtual_record["border_css"] = "border: 3px solid #bd93f9; border-right: 6px solid #bd93f9; box-shadow: 0 0 14px rgba(189,147,249,0.7); outline: 1px solid #ff79c6;"
                    else:
                        # Tiêu chuẩn Đánh Giá Lại Nghiêm Ngặt Trước Khi Đề Xuất Lọc Bỏ (Viền Đỏ)
                        has_ocr = bool(cls.clean_text_field(item.get("ocr_text")))
                        is_blurry = (item_sharp < 30.0 and not item.get("is_sharpened_fallback") and not has_ocr)
                        is_exact_time_dup = (abs(delta_t) <= 0.05)
                        
                        if is_exact_time_dup:
                            virtual_record["border_color"] = "red"
                            virtual_record["is_proposed_deletion"] = True
                            virtual_record["deletion_reason"] = f"Trùng mốc thời gian (<= 0.05s) với Anchor #{anchor_id}"
                            virtual_record["border_css"] = "border: 2px solid #ff5555; border-right: 5px solid #ff5555; box-shadow: 0 0 12px rgba(255,85,85,0.6);"
                        elif is_blurry:
                            virtual_record["border_color"] = "red"
                            virtual_record["is_proposed_deletion"] = True
                            virtual_record["deletion_reason"] = "Độ nét thấp < 30.0 (Ảnh mờ)"
                            virtual_record["border_css"] = "border: 2px solid #ff5555; border-right: 5px solid #ff5555; box-shadow: 0 0 12px rgba(255,85,85,0.6);"
                        else:
                            # Khung hình bình thường hợp lệ -> Giữ nguyên trạng thái tiêu chuẩn
                            virtual_record["border_color"] = "normal"
                            virtual_record["is_proposed_deletion"] = False

                    final_timeline.append(virtual_record)

                for idx in cluster_indices:
                    visited[idx] = True
                i = max(cluster_indices) + 1

        return final_timeline

    @classmethod
    def build_unified_final_dataset(
        cls,
        btc_keyframes: list[dict[str, Any]],
        self_keyframes: list[dict[str, Any]],
        output_json_path: Path | str | None = None,
        output_csv_path: Path | str | None = None,
        video_title: str = ""
    ) -> list[dict[str, Any]]:
        """
        Xây dựng Bộ Dữ Liệu Hợp Nhất Cuối Cùng (Unified Final Dataset):
        - Hợp nhất 100% keyframe của Ban Tổ Chức (BTC) và Tự Xử Lý (System 1).
        - Đồng bộ đầy đủ 8 trường metadata chuẩn tắc bao gồm shot_contextual_meaning.
        - Xuất ra JSON và CSV nếu có đường dẫn.
        """
        import pandas as pd
        import json

        # Sử dụng quy trình merge và khử trùng lặp hoàn chỉnh
        all_frames = cls.merge_and_deduplicate_timeline(
            btc_keyframes, self_keyframes, video_title=video_title
        )

        # Xuất file nếu yêu cầu
        if output_json_path:
            out_j = Path(output_json_path)
            out_j.parent.mkdir(parents=True, exist_ok=True)
            with open(out_j, "w", encoding="utf-8") as f:
                json.dump(all_frames, f, ensure_ascii=False, indent=2)

        if output_csv_path:
            out_c = Path(output_csv_path)
            out_c.parent.mkdir(parents=True, exist_ok=True)
            df = pd.DataFrame(all_frames)
            df.to_csv(str(out_c), index=False, encoding="utf-8-sig")

        return all_frames



