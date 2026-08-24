"""
====================================================================================================
SERVICES - AI MODELS & IMAGE UTILITIES (model_service.py)
====================================================================================================

1. MỤC TIÊU VÀ VAI TRÒ:
   - Module này quản lý toàn bộ vòng đời nạp mô hình AI (YOLO, CLIP, FAISS) và các thao tác
     xử lý ảnh nhị phân trong RAM cho Interactive Studio.
   - Hỗ trợ cơ chế Lazy Loading và In-Memory Zip Caching để tối ưu tốc độ đọc ảnh (Zero Disk Waste).

2. CÁC HÀM CỐT LÕI:
   - `get_local_yolo_model(model_tier)`: Nạp YOLO theo cấp độ (v8n, v8s, v8m, v8x, yolo11x) tự động CUDA/CPU.
   - `get_clip_model()`: Lazy load SentenceTransformer CLIP multilingual.
   - `get_btc_keyframe_image(video_id, k_no)`: Đọc byte ảnh BTC trực tiếp từ RAM zip cache.
   - `get_self_extracted_image(video_id, shot_id, frame_idx)`: Nạp ảnh WebP do System 1 tự xử lý.
   - `pil_to_base64_thumb(img, size)`: Chuyển đổi ảnh thành chuỗi base64 nhúng trực tiếp vào HTML.
   - `format_timestamp(seconds)` & `parse_duration_limit(duration_mode)`: Chuẩn hóa mốc thời gian.
====================================================================================================
"""

from __future__ import annotations
import os
import sys
import io
import time
import zipfile
import base64
from pathlib import Path
from typing import Any
from contextlib import contextmanager

# Tắt cảnh báo giải mã C-level của OpenCV FFmpeg
os.environ["OPENCV_FFMPEG_LOGLEVEL"] = "0"
os.environ["OPENCV_LOG_LEVEL"] = "SILENT"
os.environ["OPENCV_VIDEOIO_DEBUG"] = "0"
os.environ["AV_LOG_FORCE_NOCOLOR"] = "1"

import cv2
try:
    cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_SILENT)
except Exception:
    pass

import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageFont


@contextmanager
def silence_stderr():
    """Tắt hoàn toàn luồng stderr cấp C (File Descriptor 2) để loại bỏ sạch sẽ cảnh báo FFmpeg mmco."""
    try:
        devnull = os.open(os.devnull, os.O_WRONLY)
        old_stderr = os.dup(2)
        os.dup2(devnull, 2)
        os.close(devnull)
        try:
            yield
        finally:
            os.dup2(old_stderr, 2)
            os.close(old_stderr)
    except Exception:
        yield


from .config import (
    PROJECT_ROOT,
    DATASET_DIR,
    FAISS_INDEX_PATH,
    ZIP_KEYFRAMES_L21,
    ZIP_MEDIA_INFO,
    ZIP_OBJECTS,
    KEYFRAMES_OUT_DIR,
)

# --------------------------------------------------------------------------------------------------
# KHỐI 1: KHỞI TẠO BỘ NHỚ ĐỆM FAISS & ZIP CACHE
# --------------------------------------------------------------------------------------------------
_faiss_index = None
_clip_model = None

try:
    import faiss
    if FAISS_INDEX_PATH.exists():
        _faiss_index = faiss.read_index(str(FAISS_INDEX_PATH))
except Exception:
    pass

_l21_zip = None
if ZIP_KEYFRAMES_L21.exists():
    try:
        _l21_zip = zipfile.ZipFile(str(ZIP_KEYFRAMES_L21), "r")
    except Exception:
        pass


# --------------------------------------------------------------------------------------------------
# KHỐI 2: MÔ HÌNH NHÚNG NGÔN NGỮ ĐA PHƯƠNG THỨC (CLIP EMBEDDER)
# --------------------------------------------------------------------------------------------------
def get_clip_model():
    """Lazy load SentenceTransformer CLIP model."""
    global _clip_model
    if _clip_model is None:
        try:
            from sentence_transformers import SentenceTransformer
            _clip_model = SentenceTransformer("sentence-transformers/clip-ViT-B-32-multilingual-v1")
        except Exception:
            pass
    return _clip_model


# --------------------------------------------------------------------------------------------------
# KHỐI 3: MÔ HÌNH NHẬN DIỆN VẬT THỂ YOLO (LOCAL & GPU DETECTOR)
# --------------------------------------------------------------------------------------------------
_local_yolo = None
_current_yolo_tier = "yolov8n"


def get_local_yolo_model(model_tier: str = "yolov8n"):
    """
    Nạp bộ nhận diện YOLO theo cấp độ mô hình chỉ định (v8n, v8s, v8m, v8x, yolo11x).
    
    Args:
        model_tier (str): Tên cấp độ mô hình (mặc định 'yolov8n' cho Local CPU nhanh).
    
    Returns:
        Mô hình YOLO đã sẵn sàng thực thi inference.
    """
    global _local_yolo, _current_yolo_tier
    if _local_yolo is None or _current_yolo_tier != model_tier:
        try:
            models_dir = PROJECT_ROOT / "models"
            if str(models_dir) not in sys.path:
                sys.path.insert(0, str(models_dir))
            from yolo_detector_loader import YOLODetectorLoader
            _local_yolo = YOLODetectorLoader.get_model(model_name=model_tier)
            _current_yolo_tier = model_tier
        except Exception:
            try:
                from ultralytics import YOLO
                import torch
                device = "cuda" if torch.cuda.is_available() else "cpu"
                _local_yolo = YOLO(f"{model_tier}.pt")
                _local_yolo.to(device)
                _current_yolo_tier = model_tier
                print(f"[YOLO Local] Nap thanh cong {model_tier} tren {device}")
            except Exception as e:
                print(f"[YOLO Local] Khong the nap YOLO model '{model_tier}': {e}")
                _local_yolo = None
    return _local_yolo


# --------------------------------------------------------------------------------------------------
# KHỐI 4: HÀM TIỆN ÍCH THỜI GIAN & CHUỖI THỜI LƯỢNG
# --------------------------------------------------------------------------------------------------
def format_timestamp(seconds: float) -> str:
    """Chuyển đổi số giây thành định dạng chuẩn MM:SS (ví dụ 75.4s -> 01:15)."""
    if pd.isna(seconds) or seconds is None:
        return "00:00"
    try:
        sec = float(seconds)
        m = int(sec // 60)
        s = int(sec % 60)
        return f"{m:02d}:{s:02d}"
    except Exception:
        return "00:00"


def parse_duration_limit(duration_mode: str, total_video_sec: float = 1513.9) -> float:
    """Phân giải chuỗi chế độ xem thành số giây giới hạn tương ứng."""
    if not duration_mode:
        return 60.0
    mode = str(duration_mode).strip().lower()
    if mode == "15s":
        return 15.0
    elif mode == "30s":
        return 30.0
    elif mode == "60s":
        return 60.0
    elif mode == "90s":
        return 90.0
    elif mode == "120s":
        return 120.0
    elif mode == "180s":
        return 180.0
    elif mode == "toàn bộ video" or mode == "all" or mode == "full":
        return float(total_video_sec)
    try:
        if mode.endswith("s"):
            return float(mode[:-1])
        return float(mode)
    except Exception:
        return 60.0


# --------------------------------------------------------------------------------------------------
# KHỐI 5: TRÍCH XUẤT ẢNH & THUMBNAIL TỪ MEMORY/DISK
# --------------------------------------------------------------------------------------------------
def pil_to_base64_thumb(img: Image.Image | None, size: tuple[int, int] = (140, 78)) -> str:
    """Tạo chuỗi base64 cho ảnh thumbnail nhúng trực tiếp vào thẻ HTML."""
    if img is None:
        img = Image.new("RGB", size, color=(30, 30, 30))
    else:
        img = img.copy()
        img.thumbnail(size)
    buffered = io.BytesIO()
    img.save(buffered, format="JPEG", quality=80)
    img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
    return f"data:image/jpeg;base64,{img_str}"


def get_video_metadata(video_id: str) -> dict:
    """Lấy thông tin tiêu đề, tác giả, link YouTube và thời lượng từ zip media-info."""
    meta = {
        "title": f"Video {video_id}",
        "author": "Đài Truyền hình TP.HCM (HTV)",
        "watch_url": f"https://www.youtube.com/results?search_query={video_id}",
        "duration_sec": 1513.9
    }
    if ZIP_MEDIA_INFO.exists():
        try:
            with zipfile.ZipFile(str(ZIP_MEDIA_INFO), "r") as z:
                fname = f"media-info/{video_id}.json"
                if fname in z.namelist():
                    import json
                    d = json.loads(z.read(fname).decode("utf-8"))
                    meta["title"] = d.get("title", meta["title"])
                    meta["author"] = d.get("channel", d.get("uploader", meta["author"]))
                    meta["watch_url"] = d.get("webpage_url", d.get("url", meta["watch_url"]))
                    meta["duration_sec"] = float(d.get("duration", 1513.9))
        except Exception:
            pass
    return meta


from .config import (
    PROJECT_ROOT,
    DATASET_DIR,
    RAW_VIDEO_DIR,
    FAISS_INDEX_PATH,
    ZIP_KEYFRAMES_L21,
    ZIP_MEDIA_INFO,
    ZIP_OBJECTS,
    KEYFRAMES_OUT_DIR,
)


def create_placeholder_keyframe_image(label_text: str = "Keyframe", width: int = 320, height: int = 180) -> Image.Image:
    """Tạo ảnh PIL Image placeholder dự phòng có viền và chữ để đảm bảo không bao giờ trả về None cho Gradio Gallery."""
    img = Image.new("RGB", (width, height), color=(46, 52, 64))
    try:
        from PIL import ImageDraw
        draw = ImageDraw.Draw(img)
        draw.rectangle([2, 2, width - 3, height - 3], outline=(94, 129, 172), width=2)
        lines = label_text.split("\n")
        y_text = max(10, (height - len(lines) * 22) // 2)
        for line in lines:
            draw.text((15, y_text), line, fill=(236, 239, 244))
            y_text += 22
    except Exception:
        pass
    return img


def get_btc_keyframe_image(video_id: str, k_no: int, fallback_placeholder: bool = True) -> Image.Image | None:
    """Trích xuất ảnh Keyframe của Ban Tổ Chức từ tệp zip mẫu trực tiếp trong RAM (O(1) Set Lookup)."""
    global _l21_zip
    if _l21_zip is None and ZIP_KEYFRAMES_L21.exists():
        try:
            _l21_zip = zipfile.ZipFile(str(ZIP_KEYFRAMES_L21), "r")
        except Exception:
            _l21_zip = None
    if _l21_zip is not None:
        candidate_names = [
            f"keyframes/{video_id}/{k_no:03d}.jpg",
            f"keyframes/{video_id}/{k_no:04d}.jpg",
            f"keyframes/{video_id}/{k_no:05d}.jpg",
            f"keyframes/{video_id}/{k_no}.jpg",
            f"{video_id}/{k_no:03d}.jpg",
            f"{video_id}/{k_no}.jpg",
        ]
        namelist_set = getattr(_l21_zip, "_cached_namelist_set", None)
        if namelist_set is None:
            try:
                namelist_set = set(_l21_zip.namelist())
                _l21_zip._cached_namelist_set = namelist_set
            except Exception:
                namelist_set = set()
        for cand in candidate_names:
            if cand in namelist_set:
                try:
                    img_data = _l21_zip.read(cand)
                    return Image.open(io.BytesIO(img_data)).convert("RGB")
                except Exception:
                    pass
    if fallback_placeholder:
        return create_placeholder_keyframe_image(f"BTC #{k_no}\nVideo: {video_id}")
    return None


def get_self_extracted_image(video_id: str, shot_id: int, frame_idx: int, fallback_placeholder: bool = True) -> Image.Image | None:
    """Nạp ảnh Keyframe do System 1 tự xử lý từ thư mục output hoặc trích xuất tức thì từ video MP4."""
    paths_to_check = [
        KEYFRAMES_OUT_DIR / video_id / f"shot_{shot_id:04d}_frame_{frame_idx:06d}.webp",
        KEYFRAMES_OUT_DIR / video_id / f"shot_{shot_id:04d}_frame_{frame_idx:06d}.jpg",
        KEYFRAMES_OUT_DIR / f"{video_id}_{shot_id}_{frame_idx}.webp",
        KEYFRAMES_OUT_DIR / f"{video_id}_{shot_id}_{frame_idx}.jpg",
    ]
    for p in paths_to_check:
        if p.exists():
            try:
                return Image.open(str(p)).convert("RGB")
            except Exception:
                pass

    # Fallback trích xuất trực tiếp từ tệp video MP4 gốc nếu có
    vid_file = RAW_VIDEO_DIR / f"{video_id}.mp4"
    if vid_file.exists():
        try:
            with silence_stderr():
                cap = cv2.VideoCapture(str(vid_file))
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
                ret, frame = cap.read()
                cap.release()
            if ret and frame is not None:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                return Image.fromarray(rgb)
        except Exception:
            pass

    if fallback_placeholder:
        return create_placeholder_keyframe_image(f"System 1\nShot #{shot_id} | Frame {frame_idx}")
    return None
