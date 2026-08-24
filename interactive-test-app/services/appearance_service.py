"""
====================================================================================================
SERVICES - APPEARANCE ANALYSIS & NATURAL OBJECT PHRASING (appearance_service.py)
====================================================================================================

1. MỤC TIÊU VÀ VAI TRÒ:
   - Module này chịu trách nhiệm phân tích thị giác chuyên sâu trên từng bounding box và toàn ảnh:
     a) Bóc tách màu sắc ngoại hình thực tế qua không gian màu HSV (`get_object_dominant_color_name`).
     b) Định dạng cụm từ vật thể tự nhiên chuẩn ngữ pháp tiếng Việt và tiếng Anh (`format_objects_natural_*`).
     c) Trích xuất toàn diện vật thể YOLO kèm thuộc tính màu sắc (`extract_detected_objects_with_appearance`).
     d) Đánh giá phổ ảnh: Độ nét Laplacian, Năng lượng văn bản Sobel, Khử frame trống/đơn sắc.

2. CÁC HÀM CỐT LÕI:
   - `get_object_dominant_color_name(crop_img, class_name)`: Nhận diện màu áo người và màu vỏ đồ vật.
   - `format_objects_natural_vietnamese(counts_dict)`: Tạo chuỗi tự nhiên '1 người mặc áo đen, 2 chiếc xe ô tô màu tím'.
   - `format_objects_natural_english(counts_dict)`: Tạo chuỗi tự nhiên '1 person in black clothes, 2 purple cars'.
   - `extract_detected_objects_with_appearance(img_bgr, conf_thresh)`: Bóc tách vật thể từ mô hình YOLO.
   - `analyze_image_full_spectrum(img_bgr)` & `analyze_text_and_color()`: Đánh giá chất lượng toàn ảnh.
====================================================================================================
"""

from __future__ import annotations
from collections import Counter, defaultdict
import cv2
import numpy as np
from PIL import Image

from .model_service import get_local_yolo_model


def get_object_dominant_color_name(crop_img: np.ndarray, class_name: str = "") -> str:
    """
    Bóc tách màu sắc ngoại hình thực tế của đối tượng thông qua phân tích không gian màu HSV:
    - Đối với Người (person): Phân tích nửa trên của bounding box để trích xuất màu áo/trang phục.
    - Đối với Phương tiện / Đồ vật: Phân tích 80% vùng trung tâm để loại bỏ viền nền ngoại cảnh.
    """
    if crop_img is None or crop_img.size == 0:
        return "không xác định"

    try:
        h, w = crop_img.shape[:2]
        if h < 4 or w < 4:
            return "không xác định"

        # Trích xuất vùng trọng tâm theo loại đối tượng
        if class_name.lower() in ["person", "người"]:
            # Tập trung vào vùng áo (từ 15% đến 65% chiều cao của người)
            y_start = int(h * 0.15)
            y_end = int(h * 0.65)
            x_start = int(w * 0.20)
            x_end = int(w * 0.80)
            target_region = crop_img[y_start:y_end, x_start:x_end]
            prefix = "áo "
        else:
            # 80% vùng lõi trung tâm của vật thể
            y_start = int(h * 0.10)
            y_end = int(h * 0.90)
            x_start = int(w * 0.10)
            x_end = int(w * 0.90)
            target_region = crop_img[y_start:y_end, x_start:x_end]
            prefix = "màu "

        if target_region.size == 0:
            target_region = crop_img

        # Chuyển đổi sang HSV
        hsv = cv2.cvtColor(target_region, cv2.COLOR_BGR2HSV)
        h_channel = hsv[:, :, 0]
        s_channel = hsv[:, :, 1]
        v_channel = hsv[:, :, 2]

        mean_v = np.mean(v_channel)
        mean_s = np.mean(s_channel)

        # 1. Nhận diện các sắc thái đặc biệt: Đen, Trắng, Xám
        if mean_v < 45.0:
            return f"{prefix}đen"
        if mean_v > 185.0 and mean_s < 45.0:
            return f"{prefix}trắng"
        if mean_s < 35.0:
            return f"{prefix}xám"

        # 2. Bỏ qua các điểm ảnh quá tối hoặc quá nhạt để phân tích sắc độ (Hue)
        valid_mask = (v_channel >= 40) & (s_channel >= 40)
        if np.count_nonzero(valid_mask) > 10:
            valid_hues = h_channel[valid_mask]
            median_hue = float(np.median(valid_hues))
        else:
            median_hue = float(np.median(h_channel))

        # 3. Phân loại theo dải Hue chuẩn OpenCV [0, 180]
        if median_hue < 10 or median_hue >= 170:
            color_name = "đỏ"
        elif 10 <= median_hue < 25:
            color_name = "cam"
        elif 25 <= median_hue < 35:
            color_name = "vàng"
        elif 35 <= median_hue < 85:
            color_name = "xanh lá"
        elif 85 <= median_hue < 130:
            color_name = "xanh dương"
        elif 130 <= median_hue < 160:
            color_name = "tím"
        elif 160 <= median_hue < 170:
            color_name = "hồng"
        else:
            color_name = "đa sắc"

        return f"{prefix}{color_name}"
    except Exception:
        return "không xác định"


def format_objects_natural_vietnamese(detected_boxes: list[dict] | dict | list[str]) -> str:
    """
    Chuyển đổi danh sách vật thể sang cụm từ văn xuôi tự nhiên Tiếng Việt:
    Ví dụ: "1 người mặc áo đen, 2 chiếc xe ô tô màu tím, 3 lá cờ màu đỏ"
    """
    if not detected_boxes:
        return "Không bắt được vật thể"

    # Chuẩn hóa đầu vào
    normalized_boxes: list[dict] = []
    if isinstance(detected_boxes, dict):
        for k, v in detected_boxes.items():
            parts = str(k).split("_")
            c_name = parts[0]
            col_part = parts[1] if len(parts) > 1 else ""
            color = ""
            if col_part:
                color = f"áo {col_part}" if c_name == "person" else f"màu {col_part}"
            for _ in range(max(1, int(v))):
                normalized_boxes.append({"class": c_name, "color": color})
    elif isinstance(detected_boxes, (list, tuple)):
        for item in detected_boxes:
            if isinstance(item, dict):
                normalized_boxes.append(item)
            elif isinstance(item, str):
                normalized_boxes.append({"class": item, "color": ""})
    else:
        return "Không bắt được vật thể"

    if not normalized_boxes:
        return "Không bắt được vật thể"

    # Từ điển danh từ kèm lượng từ tự nhiên
    class_natural_names = {
        "person": ("người", ""),
        "car": ("chiếc xe ô tô", "màu"),
        "motorcycle": ("chiếc xe máy", "màu"),
        "bicycle": ("chiếc xe đạp", "màu"),
        "bus": ("chiếc xe buýt", "màu"),
        "truck": ("chiếc xe tải", "màu"),
        "dog": ("con chó", ""),
        "cat": ("con mèo", ""),
        "cell phone": ("chiếc điện thoại", ""),
        "tv": ("màn hình tivi", ""),
        "laptop": ("chiếc laptop", ""),
        "chair": ("cái ghế", ""),
        "cup": ("cái cốc", ""),
        "bottle": ("chai nước", ""),
        "clock": ("đồng hồ", ""),
        "flag": ("lá cờ", ""),
        "boat": ("con thuyền", ""),
        "bench": ("ghế dài", ""),
        "backpack": ("ba lô", ""),
        "handbag": ("túi xách", "")
    }

    # Gom nhóm theo (class, color)
    group_counts = Counter()
    for box in normalized_boxes:
        c_name = box.get("class", "object").lower()
        color = box.get("color", "")
        group_counts[(c_name, color)] += 1

    phrases = []
    for (c_name, color), count in group_counts.items():
        noun_info = class_natural_names.get(c_name, (c_name, ""))
        noun = noun_info[0]
        
        # Xử lý màu sắc
        if color and color != "không xác định":
            if c_name == "person":
                if color.startswith("áo "):
                    desc = f"mặc {color}"
                else:
                    desc = f"mặc áo {color}"
            else:
                desc = color
            phrases.append(f"{count} {noun} {desc}".strip())
        else:
            phrases.append(f"{count} {noun}".strip())

    return ", ".join(phrases) if phrases else "Không bắt được vật thể"


def format_objects_natural_english(detected_boxes: list[dict] | dict | list[str]) -> str:
    """
    Chuyển đổi danh sách vật thể sang cụm từ văn xuôi tự nhiên Tiếng Anh chuẩn ngữ pháp (Pure English):
    Ví dụ: "1 person in black clothes, 2 purple cars, 3 red flags, 1 black dog"
    """
    if not detected_boxes:
        return "No distinct objects detected"

    # Chuẩn hóa đầu vào
    normalized_boxes: list[dict] = []
    if isinstance(detected_boxes, dict):
        for k, v in detected_boxes.items():
            parts = str(k).split("_")
            c_name = parts[0]
            col_part = parts[1] if len(parts) > 1 else ""
            color = ""
            if col_part:
                color = f"áo {col_part}" if c_name == "person" else f"màu {col_part}"
            for _ in range(max(1, int(v))):
                normalized_boxes.append({"class": c_name, "color": color})
    elif isinstance(detected_boxes, (list, tuple)):
        for item in detected_boxes:
            if isinstance(item, dict):
                normalized_boxes.append(item)
            elif isinstance(item, str):
                normalized_boxes.append({"class": item, "color": ""})
    else:
        return "No distinct objects detected"

    if not normalized_boxes:
        return "No distinct objects detected"

    # Ánh xạ từ loại và số nhiều trong Tiếng Anh
    class_en_names = {
        "person": ("person", "people"),
        "car": ("car", "cars"),
        "motorcycle": ("motorcycle", "motorcycles"),
        "bicycle": ("bicycle", "bicycles"),
        "bus": ("bus", "buses"),
        "truck": ("truck", "trucks"),
        "dog": ("dog", "dogs"),
        "cat": ("cat", "cats"),
        "cell phone": ("mobile phone", "mobile phones"),
        "tv": ("television screen", "television screens"),
        "laptop": ("laptop", "laptops"),
        "chair": ("chair", "chairs"),
        "cup": ("cup", "cups"),
        "bottle": ("bottle", "bottles"),
        "clock": ("clock", "clocks"),
        "flag": ("flag", "flags"),
        "boat": ("boat", "boats"),
        "bench": ("bench", "benches"),
        "backpack": ("backpack", "backpacks"),
        "handbag": ("handbag", "handbags")
    }

    # Ánh xạ màu sắc sang Tiếng Anh
    color_map_en = {
        "áo đen": "in black clothes",
        "áo trắng": "in white clothes",
        "áo xanh dương": "in blue clothes",
        "áo xanh lá": "in green clothes",
        "áo đỏ": "in red clothes",
        "áo vàng": "in yellow clothes",
        "áo cam": "in orange clothes",
        "áo tím": "in purple clothes",
        "áo hồng": "in pink clothes",
        "áo xám": "in grey clothes",
        "màu đen": "black",
        "màu trắng": "white",
        "màu xanh dương": "blue",
        "màu xanh lá": "green",
        "màu đỏ": "red",
        "màu vàng": "yellow",
        "màu cam": "orange",
        "màu tím": "purple",
        "màu hồng": "pink",
        "màu xám": "grey",
        "đen": "black",
        "trắng": "white",
        "xanh dương": "blue",
        "xanh lá": "green",
        "đỏ": "red",
        "vàng": "yellow",
        "tím": "purple"
    }

    # Gom nhóm theo (class, color)
    group_counts = Counter()
    for box in normalized_boxes:
        c_name = box.get("class", "object").lower()
        color = box.get("color", "")
        group_counts[(c_name, color)] += 1

    phrases = []
    for (c_name, color), count in group_counts.items():
        singular, plural = class_en_names.get(c_name, (c_name, f"{c_name}s"))
        noun = singular if count == 1 else plural

        if color and color in color_map_en:
            en_color = color_map_en[color]
            if c_name == "person":
                phrases.append(f"{count} {noun} {en_color}")
            else:
                phrases.append(f"{count} {en_color} {noun}")
        else:
            phrases.append(f"{count} {noun}")

    return ", ".join(phrases)


def extract_detected_objects_with_appearance(
    img_array: np.ndarray,
    conf_threshold: float = 0.12,
    model_tier: str = "yolov8n"
) -> tuple[str, str, dict[str, int], list[dict]]:
    """
    Trích xuất vật thể kèm ngoại hình màu sắc thực tế và sinh cả 2 định dạng tự nhiên Tiếng Việt / Tiếng Anh.
    Trả về: (natural_vi_str, natural_en_str, counts_dict, detected_boxes)
    """
    if img_array is None or img_array.size == 0:
        return "Không bắt được vật thể", "No distinct objects detected", {}, []

    yolo_model = get_local_yolo_model(model_tier)
    if yolo_model is None:
        return "Không bắt được vật thể", "No distinct objects detected", {}, []

    try:
        # Chuẩn hóa ảnh RGB -> BGR cho OpenCV crop
        if len(img_array.shape) == 3 and img_array.shape[2] == 3:
            bgr_img = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
        else:
            bgr_img = img_array

        h_img, w_img = bgr_img.shape[:2]
        results = yolo_model(bgr_img, conf=conf_threshold, verbose=False)

        detected_boxes = []
        counts_dict = Counter()

        for r in results:
            if not hasattr(r, "boxes") or r.boxes is None:
                continue
            for b in r.boxes:
                cls_id = int(b.cls[0].item())
                cls_name = r.names.get(cls_id, f"cls_{cls_id}")
                conf = float(b.conf[0].item())

                xyxy = b.xyxy[0].cpu().numpy()
                x1, y1, x2, y2 = map(int, xyxy)
                x1, y1 = max(0, x1), max(0, y1)
                x2, y2 = min(w_img, x2), min(h_img, y2)

                if x2 > x1 and y2 > y1:
                    crop = bgr_img[y1:y2, x1:x2]
                    color_name = get_object_dominant_color_name(crop, cls_name)
                else:
                    color_name = "không xác định"

                counts_dict[cls_name] += 1
                detected_boxes.append({
                    "class": cls_name,
                    "color": color_name,
                    "box": [x1, y1, x2, y2],
                    "conf": round(conf, 2)
                })

        if not detected_boxes:
            return "Không bắt được vật thể", "No distinct objects detected", {}, []

        natural_vi = format_objects_natural_vietnamese(detected_boxes)
        natural_en = format_objects_natural_english(detected_boxes)

        return natural_vi, natural_en, dict(counts_dict), detected_boxes
    except Exception as e:
        print(f"[Appearance Service Error] {e}")
        return "Không bắt được vật thể", "No distinct objects detected", {}, []


def analyze_image_full_spectrum(img: Image.Image | None) -> dict:
    """Phân tích toàn diện ảnh: độ nét Laplacian, năng lượng văn bản Sobel, màu chủ đạo HSV, và phát hiện ảnh đơn sắc."""
    if img is None:
        return {
            "sharpness": 0.0,
            "text_energy": 0.0,
            "color": "Đa Sắc",
            "is_blank": True,
            "status": "Khong co du lieu anh"
        }
    try:
        arr = np.array(img.convert("RGB"))
        gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)

        # Độ nét Laplacian
        lap = cv2.Laplacian(gray, cv2.CV_64F)
        sharp = float(lap.var())

        # Năng lượng cạnh Sobel cho vùng văn bản
        sobelx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
        sobely = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
        text_energy = float(np.mean(np.abs(sobelx) + np.abs(sobely)))

        # Kiểm tra đơn sắc / mờ / đen
        std_val = float(np.std(arr))
        mean_val = float(np.mean(arr))
        is_blank = False
        status_reasons = []

        if std_val < 6.0:
            is_blank = True
            status_reasons.append("Ảnh đơn sắc (Zero Variance)")
        if mean_val < 8.0:
            is_blank = True
            status_reasons.append("Màn hình đen (Blank Dark)")
        elif mean_val > 248.0:
            is_blank = True
            status_reasons.append("Màn hình trắng (Blank White)")
        if sharp < 15.0 and not is_blank:
            status_reasons.append("Độ nét cực thấp (Mờ chuyển cảnh)")

        # Màu chủ đạo
        hsv = cv2.cvtColor(arr, cv2.COLOR_RGB2HSV)
        h_mean = np.median(hsv[:, :, 0])
        s_mean = np.mean(hsv[:, :, 1])
        v_mean = np.mean(hsv[:, :, 2])

        if v_mean < 45:
            dom_color = "Đen (Dark Studio)"
        elif v_mean > 200 and s_mean < 40:
            dom_color = "Trắng (Bright)"
        elif s_mean < 35:
            dom_color = "Xám (Neutral)"
        elif h_mean < 10 or h_mean >= 170:
            dom_color = "Đỏ Thời Sự (Red)"
        elif 85 <= h_mean < 130:
            dom_color = "Xanh Thời Sự (Blue Studio)"
        elif 35 <= h_mean < 85:
            dom_color = "Xanh Thiên Nhiên (Green Scene)"
        elif 20 <= h_mean < 35:
            dom_color = "Vàng Ấm (Warm Yellow)"
        else:
            dom_color = "Đa Sắc (Multicolor Scene)"

        return {
            "sharpness": round(sharp, 1),
            "text_energy": round(text_energy, 2),
            "color": dom_color,
            "is_blank": is_blank,
            "status": " | ".join(status_reasons) if status_reasons else "Đạt tiêu chuẩn System 1"
        }
    except Exception as e:
        return {
            "sharpness": 0.0,
            "text_energy": 0.0,
            "color": "Đa Sắc",
            "is_blank": True,
            "status": f"Lỗi phân tích: {e}"
        }


def analyze_text_and_color(img_bgr: np.ndarray) -> tuple[float, str]:
    """Phân tích năng lượng văn bản và màu chủ đạo HSV."""
    if img_bgr is None or img_bgr.size == 0:
        return 0.0, "Đa Sắc (Multicolor Scene)"
    try:
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        sobelx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
        sobely = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
        text_energy = float(np.mean(np.abs(sobelx) + np.abs(sobely)))
        
        hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
        h_mean = np.median(hsv[:, :, 0])
        s_mean = np.mean(hsv[:, :, 1])
        v_mean = np.mean(hsv[:, :, 2])
        if v_mean < 45:
            dom_color = "Đen (Dark Studio)"
        elif v_mean > 200 and s_mean < 40:
            dom_color = "Trắng (Bright)"
        elif s_mean < 35:
            dom_color = "Xám (Neutral)"
        elif h_mean < 10 or h_mean >= 170:
            dom_color = "Đỏ Thời Sự (Red)"
        elif 85 <= h_mean < 130:
            dom_color = "Xanh Thời Sự (Blue Studio)"
        elif 35 <= h_mean < 85:
            dom_color = "Xanh Thiên Nhiên (Green Scene)"
        elif 20 <= h_mean < 35:
            dom_color = "Vàng Ấm (Warm Yellow)"
        else:
            dom_color = "Đa Sắc (Multicolor Scene)"
        return text_energy, dom_color
    except Exception:
        return 0.0, "Đa Sắc (Multicolor Scene)"


def calculate_sharpness_fast(img_bgr: np.ndarray) -> float:
    """Tính độ nét nhanh bằng phương sai Laplacian."""
    if img_bgr is None or img_bgr.size == 0:
        return 0.0
    try:
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        return float(cv2.Laplacian(gray, cv2.CV_64F).var())
    except Exception:
        return 0.0


def is_blank_or_solid_monochrome(img_bgr: np.ndarray, text_energy: float = 0.0) -> bool:
    """Kiểm tra ảnh đơn sắc, mờ hoặc đen/trắng trống."""
    if img_bgr is None or img_bgr.size == 0:
        return True
    try:
        std_val = float(np.std(img_bgr))
        mean_val = float(np.mean(img_bgr))
        if std_val < 6.0 or mean_val < 8.0 or mean_val > 248.0:
            return True
        return False
    except Exception:
        return True

