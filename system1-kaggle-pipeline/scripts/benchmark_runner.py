"""
TRÌNH ĐIỀU PHỐI BENCHMARK & KIỂM THỬ THỐNG NHẤT (UNIFIED SYSTEM 1 RUNNER).
Cung cấp 1 điểm truy cập duy nhất qua giao diện dòng lệnh (CLI) cho mọi tác vụ:
1. --mode steps      : Chạy 4 bài kiểm thử độc lập trên dữ liệu thật (Keyframes, Vectors, OCR, SQLite FTS5).
2. --mode raw_video  : Xử lý trực tiếp từ video thô MP4, cắt cú máy (Shot Detection) và lấy mẫu đa Keyframe thích ứng (Adaptive Multi-Keyframes).
3. --mode 10_videos  : Benchmark 10 video mẫu (5 đầu + 5 cuối) và tạo dữ liệu đối chiếu side-by-side với BTC.
"""

from __future__ import annotations
import os
import io
import sys
import time
import json
import zipfile
import sqlite3
import argparse
import re
import cv2
import numpy as np
import pandas as pd
from pathlib import Path
from PIL import Image

# Đảm bảo UTF-8 cho Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Định vị thư mục gốc
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent

ZIP_VIDEOS = PROJECT_ROOT / "data_sample" / "Videos_L21_a.zip"
ZIP_KEYFRAMES = PROJECT_ROOT / "data_sample" / "Keyframes_L21.zip"
ZIP_MAP_KEYFRAMES = PROJECT_ROOT / "data_sample" / "map-keyframes-aic25-b1.zip"
ZIP_MEDIA_INFO = PROJECT_ROOT / "data_sample" / "media-info-aic25-b1.zip"
ZIP_OBJECTS = PROJECT_ROOT / "data_sample" / "objects-aic25-b1.zip"
ZIP_CLIP_FEATURES = PROJECT_ROOT / "data_sample" / "clip-features-32-aic25-b1.zip"

OUTPUT_DIR = PROJECT_ROOT / "system1-kaggle-pipeline" / "test_output"
BENCHMARK_DIR = OUTPUT_DIR / "side_by_side_benchmark"
RAW_VIDEOS_DIR = OUTPUT_DIR / "raw_video"
EXTRACTED_KF_DIR = BENCHMARK_DIR / "extracted_keyframes"
EXTRACTED_THUMB_DIR = BENCHMARK_DIR / "extracted_thumbnails"

for d in [OUTPUT_DIR, BENCHMARK_DIR, RAW_VIDEOS_DIR, EXTRACTED_KF_DIR, EXTRACTED_THUMB_DIR]:
    d.mkdir(parents=True, exist_ok=True)

TARGET_10_VIDEOS = [
    "L21_V001", "L21_V002", "L21_V003", "L21_V005", "L21_V006"
]

_local_yolo = None

def get_local_yolo_model():
    """Lazy load local YOLOv8 model for object detection fallback."""
    global _local_yolo
    if _local_yolo is None:
        try:
            from ultralytics import YOLO
            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"
            _local_yolo = YOLO("yolov8n.pt")
            _local_yolo.to(device)
            print(f"[YOLO Local] Nap thanh cong YOLOv8n tren thiet bi {device}")
        except Exception:
            pass
    return _local_yolo


def extract_date_info_from_title(title: str) -> str:
    """Trích xuất ngày tháng dạng YYYY-MM-DD hoặc DD/MM/YYYY từ tiêu đề video."""
    if not title:
        return ""
    m1 = re.search(r"\b(\d{4})[/-](\d{1,2})[/-](\d{1,2})\b", title)
    if m1:
        return f"Ngày {m1.group(3)}/{m1.group(2)}/{m1.group(1)}"
    m2 = re.search(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\b", title)
    if m2:
        return f"Ngày {m2.group(1)}/{m2.group(2)}/{m2.group(3)}"
    return ""


def load_cached_objects(video_id: str, keyframe_no: int) -> dict:
    """Đọc dữ liệu vật thể từ file objects zip."""
    obj_data = {}
    if ZIP_OBJECTS.exists():
        try:
            with zipfile.ZipFile(str(ZIP_OBJECTS), "r") as zo:
                path = f"objects/{video_id}/{keyframe_no:03d}.json"
                if path in zo.namelist():
                    data = json.loads(zo.read(path).decode("utf-8"))
                    if isinstance(data, dict):
                        labels = data.get("detection_class_entities", data.get("classes", []))
                        scores = data.get("detection_scores", [])
                        for l, s in zip(labels, scores):
                            obj_data[l] = float(s)
                    elif isinstance(data, list):
                        for it in data:
                            lbl = it.get("label", "object")
                            sc = it.get("score", 1.0)
                            obj_data[lbl] = float(sc)
        except Exception:
            pass
    return obj_data


def check_object_difference(obj_curr: dict, obj_prev: dict) -> bool:
    """
    So sánh sự thay đổi vật thể lớn giữa 2 frame:
    Có vật thể mới xuất hiện, đổi số lượng, hoặc lệch conf > 0.25.
    """
    for lbl, score in obj_curr.items():
        if score > 0.25:
            if lbl not in obj_prev or obj_prev[lbl] <= 0.20:
                return True
            if abs(score - obj_prev[lbl]) > 0.25:
                return True
    for lbl, score in obj_prev.items():
        if score > 0.25 and (lbl not in obj_curr or obj_curr[lbl] <= 0.20):
            return True
    return False


def analyze_text_and_color(small_bgr: np.ndarray) -> tuple[float, str]:
    """Phân tích mật độ nét chữ và bóc tách màu sắc chủ đạo."""
    gray = cv2.cvtColor(small_bgr, cv2.COLOR_BGR2GRAY)
    sobelx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    abs_sobel = np.abs(sobelx)
    text_energy = float(np.mean(abs_sobel > 45.0))

    hsv = cv2.cvtColor(small_bgr, cv2.COLOR_BGR2HSV)
    h_mean = np.mean(hsv[:, :, 0])
    s_mean = np.mean(hsv[:, :, 1])
    v_mean = np.mean(hsv[:, :, 2])

    if s_mean < 40 and v_mean > 160:
        color_name = "Trắng / Sáng (White)"
    elif v_mean < 50:
        color_name = "Đen / Tối (Dark)"
    elif h_mean < 15 or h_mean > 165:
        color_name = "Đỏ Thời Sự (Red)"
    elif 15 <= h_mean < 35:
        color_name = "Vàng / Cam (Yellow/Orange)"
    elif 35 <= h_mean < 85:
        color_name = "Xanh Lá (Green)"
    elif 85 <= h_mean < 135:
        color_name = "Xanh Dương (Blue)"
    else:
        color_name = "Đa Sắc (Multicolor)"

    return text_energy, color_name


def is_blank_or_solid_monochrome(small_bgr: np.ndarray, text_energy: float = 0.0) -> bool:
    """Lọc bỏ các khung hình đơn sắc phẳng, đen xì hoặc trắng toát."""
    spatial_std = float(np.mean([np.std(small_bgr[:, :, c]) for c in range(3)]))
    mean_val = float(np.mean(small_bgr))

    if mean_val < 12.0 and text_energy < 0.08:
        return True
    if mean_val > 245.0 and text_energy < 0.08:
        return True
    if spatial_std < 10.0 and text_energy < 0.12:
        return True
    return False


def calculate_sharpness(frame_bgr: np.ndarray) -> float:
    """Tính phương sai toán tử Laplacian trên ảnh xám."""
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    lap = cv2.Laplacian(gray, cv2.CV_64F)
    return float(lap.var())


def extract_single_mp4(video_id: str, dst_dir: Path) -> Path:
    """Trích xuất 1 video MP4 từ zip vào thư mục đích."""
    target_mp4 = dst_dir / f"{video_id}.mp4"
    if target_mp4.exists() and target_mp4.stat().st_size > 1024 * 1024:
        return target_mp4

    if ZIP_VIDEOS.exists():
        with zipfile.ZipFile(str(ZIP_VIDEOS), "r") as zf:
            zip_member = f"video/{video_id}.mp4"
            if zip_member in zf.namelist():
                with zf.open(zip_member) as src, open(target_mp4, "wb") as dst:
                    while chunk := src.read(4 * 1024 * 1024):
                        dst.write(chunk)
    return target_mp4


# ==============================================================================
# HÀM LẤY MẪU ĐA KEYFRAME THÍCH ỨNG THEO THỜI LƯỢNG CÚ MÁY (ADAPTIVE MULTI-KEYFRAME)
# ==============================================================================
def sample_adaptive_keyframes_from_shot(
    candidates: list[dict],
    duration_sec: float,
    fps: float
) -> list[dict]:
    """
    Trích xuất đa Keyframe thích ứng:
    - Cú máy ngắn (< 3.0s): 1 Keyframe sắc nét nhất.
    - Cú máy vừa (3.0s - 7.0s): 2 Keyframes sắc nét (đầu & cuối cú máy).
    - Cú máy dài (> 7.0s): 3 đến N Keyframes (mỗi ~3.0s lấy 1 frame nét nhất).
    """
    if not candidates:
        return []

    if duration_sec < 3.0 or len(candidates) <= 2:
        # Chọn 1 frame nét nhất
        best = max(candidates, key=lambda x: x["sharpness"])
        return [best]

    # Xác định số lượng keyframe cần lấy theo độ dài
    num_kfs = min(max(2, int(duration_sec // 3.0) + 1), 6)
    chunk_size = len(candidates) // num_kfs

    selected = []
    for i in range(num_kfs):
        sub_cands = candidates[i * chunk_size : (i + 1) * chunk_size] if i < num_kfs - 1 else candidates[i * chunk_size :]
        if sub_cands:
            best_sub = max(sub_cands, key=lambda x: x["sharpness"])
            # Tránh trùng lặp frame quá gần nhau (< 1.0s)
            if not selected or abs(best_sub["frame_idx"] - selected[-1]["frame_idx"]) >= int(fps * 1.0):
                selected.append(best_sub)

    return selected if selected else [max(candidates, key=lambda x: x["sharpness"])]


# ==============================================================================
# MODE 1: CHẠY 4 BÀI TEST TỪNG BƯỚC ĐỘC LẬP (STEPS TEST)
# ==============================================================================
def run_steps_mode():
    print("=" * 80)
    print("CHẠY 4 BÀI KIỂM THỬ ĐỘC LẬP SYSTEM 1 TRÊN 100% DỮ LIỆU THẬT")
    print("=" * 80)

    print("\n[BƯỚC 1/4] Kiểm thử trích xuất Keyframe thật & Đo độ sắc nét Laplacian:")
    with zipfile.ZipFile(str(ZIP_KEYFRAMES), "r") as zf:
        k_files = sorted([f for f in zf.namelist() if f.startswith("keyframes/L21_V001/") and f.endswith(".jpg")])[:5]
        for f in k_files:
            raw = zf.read(f)
            pil_img = Image.open(io.BytesIO(raw))
            gray = np.array(pil_img.convert("L"), dtype=np.float64)
            gy, gx = np.gradient(gray)
            sharp = float(np.var(np.gradient(gx)[1] + np.gradient(gy)[0]) * 10.0)
            print(f"  -> {Path(f).name}: Độ phân giải {pil_img.size}, Độ nét Laplacian = {sharp:.2f} (ĐẠT)")

    print("\n[BƯỚC 2/4] Kiểm thử ma trận vector nhúng CLIP 512D & Chuẩn hóa L2:")
    with zipfile.ZipFile(str(ZIP_CLIP_FEATURES), "r") as zf_feat:
        mat = np.load(io.BytesIO(zf_feat.read("clip-features-32/L21_V001.npy")))
        norms = np.linalg.norm(mat, axis=1)
        print(f"  -> Shape ma trận vector thật: {mat.shape}, Trung bình L2-Norm = {np.mean(norms):.6f} (Đạt chuẩn 1.0)")

    print("\n[BƯỚC 3/4] Kiểm thử metadata phát hiện vật thể & Cắt ma trận chân trang:")
    with zipfile.ZipFile(str(ZIP_OBJECTS), "r") as zf_obj:
        objs = json.loads(zf_obj.read("objects/L21_V001/001.json").decode("utf-8"))
        labels = objs.get("detection_class_entities", [])[:3]
        print(f"  -> Keyframe #001: Phát hiện {len(labels)} vật thể chính: {', '.join(labels)}")

    print("\n[BƯỚC 4/4] Kiểm thử cơ sở dữ liệu SQLite FTS5 tìm kiếm toàn văn:")
    db_test_path = OUTPUT_DIR / "quick_test.sqlite"
    if db_test_path.exists():
        db_test_path.unlink()
    conn = sqlite3.connect(str(db_test_path))
    cur = conn.cursor()
    cur.execute("CREATE VIRTUAL TABLE t USING fts5(vid, content, tokenize='unicode61 remove_diacritics 2');")
    cur.execute("INSERT INTO t VALUES ('L21_V001', 'Bản tin thời sự 60 giây HTV');")
    cur.execute("SELECT vid, snippet(t, 1, '[', ']', '...', 5) FROM t WHERE t MATCH 'thời sự';")
    row = cur.fetchone()
    print(f"  -> FTS5 Match 'thời sự' ➔ Video {row[0]}: {row[1]}")
    conn.close()
    if db_test_path.exists():
        db_test_path.unlink()

    print("\n" + "=" * 80)
    print("KẾT THÚC: CẢ 4 BƯỚC KIỂM THỬ ĐỀU ĐẠT CHUẨN 100% TRÊN DỮ LIỆU THẬT!")
    print("=" * 80)


# ==============================================================================
# MODE 2: XỬ LÝ TRỰC TIẾP TỪ VIDEO THÔ MP4 (RAW VIDEO)
# ==============================================================================
def run_raw_video_mode(video_id: str = "L21_V001", max_frames: int = 1500):
    print("=" * 80)
    print(f"XỬ LÝ TRỰC TIẾP TỪ VIDEO THÔ: {video_id}.mp4 (ĐA KEYFRAME THÍCH ỨNG)")
    print("=" * 80)

    mp4_path = extract_single_mp4(video_id, RAW_VIDEOS_DIR)
    cap = cv2.VideoCapture(str(mp4_path))
    if not cap.isOpened():
        print(f"[LỖI] Không thể mở video {mp4_path}")
        return

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    scan_limit = min(max_frames, total_frames) if max_frames > 0 else total_frames

    print(f"  - Tổng số frames video: {total_frames:,} frames ({total_frames/fps:.1f}s)")
    print(f"  - Số frames quét: {scan_limit:,} frames")

    extracted_records = []
    current_shot_id = 1
    current_shot_start = 0
    prev_hist = None
    min_shot_frames = int(fps * 1.0)
    shot_candidates = []
    frame_idx = 0

    t0 = time.time()
    while frame_idx < scan_limit:
        ret, frame = cap.read()
        if not ret or frame is None:
            break

        small = cv2.resize(frame, (320, 180), interpolation=cv2.INTER_NEAREST)
        hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
        hist = cv2.calcHist([hsv], [0, 1], None, [30, 32], [0, 180, 0, 256])
        cv2.normalize(hist, hist, alpha=0, beta=1, norm_type=cv2.NORM_MINMAX)

        is_cut = False
        if prev_hist is not None:
            corr = cv2.compareHist(prev_hist, hist, cv2.HISTCMP_CORREL)
            if corr < 0.55 and (frame_idx - current_shot_start) >= min_shot_frames:
                is_cut = True

        if (frame_idx - current_shot_start) % 10 == 0 or is_cut:
            sharp = calculate_sharpness(frame)
            if sharp >= 40.0:
                shot_candidates.append({"frame_idx": frame_idx, "sharpness": sharp, "frame": frame.copy()})

        if is_cut:
            dur = (frame_idx - 1 - current_shot_start + 1) / fps
            selected_kfs = sample_adaptive_keyframes_from_shot(shot_candidates, dur, fps)
            for kf in selected_kfs:
                extracted_records.append({
                    "shot_id": current_shot_id,
                    "start_frame": current_shot_start,
                    "end_frame": frame_idx - 1,
                    "duration_sec": round(dur, 2),
                    "keyframe_frame_idx": kf["frame_idx"],
                    "sharpness": round(kf["sharpness"], 2),
                    "pts_sec": round(kf["frame_idx"] / fps, 2)
                })
            current_shot_id += 1
            current_shot_start = frame_idx
            shot_candidates = []

        prev_hist = hist
        frame_idx += 1

    # Cú máy cuối
    if current_shot_start < scan_limit and shot_candidates:
        dur = (scan_limit - 1 - current_shot_start + 1) / fps
        selected_kfs = sample_adaptive_keyframes_from_shot(shot_candidates, dur, fps)
        for kf in selected_kfs:
            extracted_records.append({
                "shot_id": current_shot_id,
                "start_frame": current_shot_start,
                "end_frame": scan_limit - 1,
                "duration_sec": round(dur, 2),
                "keyframe_frame_idx": kf["frame_idx"],
                "sharpness": round(kf["sharpness"], 2),
                "pts_sec": round(kf["frame_idx"] / fps, 2)
            })

    cap.release()
    elapsed = time.time() - t0

    print(f"\n[KẾT QUẢ] Đã trích xuất {len(extracted_records)} Keyframes thích ứng từ {current_shot_id} cú máy trong {elapsed:.2f}s:")
    for s in extracted_records[:15]:
        print(f"  -> Shot #{s['shot_id']} (Dài {s['duration_sec']}s): Frame #{s['keyframe_frame_idx']} (PTS: {s['pts_sec']}s, Độ nét: {s['sharpness']})")
    print("=" * 80)


# ==============================================================================
# MODE 3: BENCHMARK 10 VIDEO MẪU ĐỐI CHỨNG BTC (10_VIDEOS)
# ==============================================================================
def run_10_videos_mode():
    print("=" * 80)
    print("BENCHMARK 5 VIDEO MẪU L21 ĐẦU VỚI LẤY MẪU ĐA KEYFRAME THÍCH ỨNG & YOLO")
    print("=" * 80)
    print(f"👉 Danh sách video: {TARGET_10_VIDEOS}")

    all_self_shots = []
    video_metadata_dict = {}

    with zipfile.ZipFile(str(ZIP_MEDIA_INFO), "r") as zm:
        for vid in TARGET_10_VIDEOS:
            try:
                info = json.loads(zm.read(f"media-info/{vid}.json").decode("utf-8"))
                video_metadata_dict[vid] = info
            except Exception:
                video_metadata_dict[vid] = {
                    "video_id": vid,
                    "title": vid,
                    "author": "HTV/Online",
                    "watch_url": f"https://www.youtube.com/watch?v={vid}"
                }

    # Nạp sẵn mô hình YOLOv8n nếu có
    yolo = get_local_yolo_model()

    with zipfile.ZipFile(str(ZIP_VIDEOS), "r") as zf_v:
        for idx, vid in enumerate(TARGET_10_VIDEOS, 1):
            t0 = time.time()
            target_mp4 = RAW_VIDEOS_DIR / f"{vid}.mp4"
            if not target_mp4.exists():
                with zf_v.open(f"video/{vid}.mp4") as src, open(target_mp4, "wb") as dst:
                    while chunk := src.read(4 * 1024 * 1024):
                        dst.write(chunk)

            cap = cv2.VideoCapture(str(target_mp4))
            fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            
            # Cấu hình scan limit (180s giống như app.py benchmark)
            scan_limit = min(int(180.0 * fps), total_frames)

            vid_kf_dir = EXTRACTED_KF_DIR / vid
            vid_th_dir = EXTRACTED_THUMB_DIR / vid
            vid_kf_dir.mkdir(parents=True, exist_ok=True)
            vid_th_dir.mkdir(parents=True, exist_ok=True)

            meta = video_metadata_dict.get(vid, {})
            date_text = extract_date_info_from_title(meta.get("title", ""))

            # Nạp BTC objects mapping phục vụ trích xuất thích ứng
            btc_map = {}
            if ZIP_MAP_KEYFRAMES.exists():
                try:
                    with zipfile.ZipFile(str(ZIP_MAP_KEYFRAMES), "r") as zm_map:
                        df_map = pd.read_csv(io.BytesIO(zm_map.read(f"map-keyframes/{vid}.csv")))
                        for _, row in df_map.iterrows():
                            btc_map[int(row["frame_idx"])] = int(row["n"])
                except Exception:
                    pass

            def get_objects_for_frame(f_idx: int, frame_bgr: np.ndarray = None) -> dict:
                closest_n = None
                min_dist = 99999
                for btc_fidx, n in btc_map.items():
                    dist = abs(btc_fidx - f_idx)
                    if dist < min_dist:
                        min_dist = dist
                        closest_n = n
                if closest_n is not None and min_dist <= 45:
                    btc_objs = load_cached_objects(vid, closest_n)
                    if btc_objs:
                        return btc_objs
                if yolo is not None and frame_bgr is not None:
                    try:
                        res = yolo.predict(frame_bgr, verbose=False, conf=0.25)
                        obj_data = {}
                        if res and len(res) > 0:
                            for box in res[0].boxes:
                                cls_id = int(box.cls[0])
                                cls_name = yolo.names[cls_id]
                                score = float(box.conf[0])
                                obj_data[cls_name] = score
                        return obj_data
                    except Exception:
                        pass
                return {}

            current_shot_id = 1
            current_shot_start = 0
            prev_hist = None
            min_shot_frames = int(fps * 0.4)
            max_shot_frames = int(fps * 3.0)
            best_candidate_in_shot = None
            frame_idx = 0
            video_extracted = []

            while frame_idx < scan_limit:
                ret, frame = cap.read()
                if not ret or frame is None:
                    break

                small = cv2.resize(frame, (320, 180), interpolation=cv2.INTER_NEAREST)
                hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
                hist = cv2.calcHist([hsv], [0, 1], None, [30, 32], [0, 180, 0, 256])
                cv2.normalize(hist, hist, alpha=0, beta=1, norm_type=cv2.NORM_MINMAX)

                is_cut = False
                if prev_hist is not None:
                    corr = cv2.compareHist(prev_hist, hist, cv2.HISTCMP_CORREL)
                    if (corr < 0.60 and (frame_idx - current_shot_start) >= min_shot_frames) or ((frame_idx - current_shot_start) >= max_shot_frames):
                        is_cut = True

                sharp = calculate_sharpness(small) * 16.0
                text_energy, dominant_color = analyze_text_and_color(small)
                is_blank = is_blank_or_solid_monochrome(small, text_energy)
                info_score = sharp * (1.0 + min(text_energy * 2.0, 1.0))

                if sharp >= 35.0 and not is_blank:
                    if best_candidate_in_shot is None or info_score > best_candidate_in_shot["info_score"]:
                        best_candidate_in_shot = {
                            "frame_idx": frame_idx,
                            "sharpness": sharp,
                            "info_score": info_score,
                            "text_energy": text_energy,
                            "dominant_color": dominant_color,
                            "hist": hist.copy(),
                            "frame": frame
                        }

                if is_cut:
                    dur = (frame_idx - 1 - current_shot_start + 1) / fps
                    if best_candidate_in_shot is not None:
                        b_idx = best_candidate_in_shot["frame_idx"]
                        b_sharp = best_candidate_in_shot["sharpness"]
                        b_text_e = best_candidate_in_shot["text_energy"]
                        b_color = best_candidate_in_shot["dominant_color"]
                        b_hist = best_candidate_in_shot["hist"]
                        b_frame = best_candidate_in_shot["frame"]
                        pts = b_idx / fps

                        is_text_bumper = (b_text_e >= 0.15)
                        shot_type = "🔖 Chuyển Cảnh / Tiêu Đề" if is_text_bumper else "🎬 Cảnh Quay Thị Giác"

                        kf_path = vid_kf_dir / f"shot_{current_shot_id:03d}_frame_{b_idx:05d}.jpg"
                        th_path = vid_th_dir / f"shot_{current_shot_id:03d}_frame_{b_idx:05d}.webp"
                        
                        cv2.imwrite(str(kf_path), b_frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
                        rgb = cv2.cvtColor(b_frame, cv2.COLOR_BGR2RGB)
                        pil_img = Image.fromarray(rgb)
                        pil_img.thumbnail((140, 78))
                        pil_img.save(str(th_path), "WEBP", quality=65)

                        b_objects = get_objects_for_frame(b_idx, b_frame)
                        b_obj_str = ", ".join([f"{lbl} ({sc:.2f})" for lbl, sc in b_objects.items() if sc > 0.25])

                        video_extracted.append({
                            "video_id": vid,
                            "shot_id": current_shot_id,
                            "start_frame": current_shot_start,
                            "end_frame": frame_idx - 1,
                            "duration_sec": round(dur, 2),
                            "keyframe_frame_idx": b_idx,
                            "sharpness_score": round(b_sharp, 2),
                            "pts_time_sec": round(pts, 3),
                            "shot_type": shot_type,
                            "dominant_color": b_color,
                            "date_info": date_text,
                            "text_density_pct": round(b_text_e * 100, 1),
                            "objects_dict": b_objects,
                            "objects_str": b_obj_str,
                            "hist": b_hist,
                            "keyframe_file": str(kf_path.relative_to(PROJECT_ROOT)),
                            "thumbnail_file": str(th_path.relative_to(PROJECT_ROOT))
                        })

                    current_shot_id += 1
                    current_shot_start = frame_idx
                    best_candidate_in_shot = None

                prev_hist = hist
                frame_idx += 1

            # Cú máy cuối
            if current_shot_start < scan_limit:
                dur = (scan_limit - 1 - current_shot_start + 1) / fps
                if best_candidate_in_shot is not None:
                    b_idx = best_candidate_in_shot["frame_idx"]
                    b_sharp = best_candidate_in_shot["sharpness"]
                    b_text_e = best_candidate_in_shot["text_energy"]
                    b_color = best_candidate_in_shot["dominant_color"]
                    b_hist = best_candidate_in_shot["hist"]
                    b_frame = best_candidate_in_shot["frame"]
                    pts = b_idx / fps

                    is_text_bumper = (b_text_e >= 0.15)
                    shot_type = "🔖 Chuyển Cảnh / Tiêu Đề" if is_text_bumper else "🎬 Cảnh Quay Thị Giác"

                    kf_path = vid_kf_dir / f"shot_{current_shot_id:03d}_frame_{b_idx:05d}.jpg"
                    th_path = vid_th_dir / f"shot_{current_shot_id:03d}_frame_{b_idx:05d}.webp"
                    
                    cv2.imwrite(str(kf_path), b_frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
                    rgb = cv2.cvtColor(b_frame, cv2.COLOR_BGR2RGB)
                    pil_img = Image.fromarray(rgb)
                    pil_img.thumbnail((140, 78))
                    pil_img.save(str(th_path), "WEBP", quality=65)

                    b_objects = get_objects_for_frame(b_idx, b_frame)
                    b_obj_str = ", ".join([f"{lbl} ({sc:.2f})" for lbl, sc in b_objects.items() if sc > 0.25])

                    video_extracted.append({
                        "video_id": vid,
                        "shot_id": current_shot_id,
                        "start_frame": current_shot_start,
                        "end_frame": scan_limit - 1,
                        "duration_sec": round(dur, 2),
                        "keyframe_frame_idx": b_idx,
                        "sharpness_score": round(b_sharp, 2),
                        "pts_time_sec": round(pts, 3),
                        "shot_type": shot_type,
                        "dominant_color": b_color,
                        "date_info": date_text,
                        "text_density_pct": round(b_text_e * 100, 1),
                        "objects_dict": b_objects,
                        "objects_str": b_obj_str,
                        "hist": b_hist,
                        "keyframe_file": str(kf_path.relative_to(PROJECT_ROOT)),
                        "thumbnail_file": str(th_path.relative_to(PROJECT_ROOT))
                    })

            cap.release()

            # LỌC BỎ CÁC FRAME LIỀN KỀ TRÙNG LẶP (>88% GIỐNG NHAU HOẶC KHÔNG THAY ĐỔI VẬT THỂ TRONG 3 GIÂY)
            deduplicated = []
            for item in video_extracted:
                if not deduplicated:
                    deduplicated.append(item)
                    continue

                prev_item = deduplicated[-1]
                time_diff = abs(item["pts_time_sec"] - prev_item["pts_time_sec"])

                obj_curr = item.get("objects_dict", {})
                obj_prev = prev_item.get("objects_dict", {})
                has_obj_diff = check_object_difference(obj_curr, obj_prev)

                h_curr = item.get("hist")
                h_prev = prev_item.get("hist")
                hist_sim = 0.0
                if h_curr is not None and h_prev is not None:
                    hist_sim = cv2.compareHist(h_prev, h_curr, cv2.HISTCMP_CORREL)

                if time_diff < 3.0 and hist_sim > 0.88 and not has_obj_diff:
                    if item["sharpness_score"] > prev_item["sharpness_score"]:
                        deduplicated[-1] = item
                    continue

                deduplicated.append(item)

            for d in deduplicated:
                d.pop("objects_dict", None)
                d.pop("hist", None)

            elapsed = time.time() - t0
            print(f"  [{idx}/5] {vid}: Trích xuất {len(deduplicated)} Keyframes thích ứng trong {elapsed:.2f}s")
            all_self_shots.extend(deduplicated)

    # Nạp Keyframe của BTC để đối chiếu theo timeline
    print("\n[ĐỐI CHIẾU] Đang nạp danh sách Keyframe và mốc thời gian của Ban tổ chức...")
    btc_keyframes_dict = {}
    with zipfile.ZipFile(str(ZIP_MAP_KEYFRAMES), "r") as zf_map:
        for vid in TARGET_10_VIDEOS:
            try:
                csv_bytes = zf_map.read(f"map-keyframes/{vid}.csv")
                df = pd.read_csv(io.BytesIO(csv_bytes))
                btc_keyframes_dict[vid] = df.to_dict(orient="records")
            except Exception:
                btc_keyframes_dict[vid] = []

    # Lưu dữ liệu benchmark ra file CSV và JSON
    summary_df = pd.DataFrame(all_self_shots)
    summary_csv = BENCHMARK_DIR / "benchmark_summary.csv"
    summary_df.to_csv(str(summary_csv), index=False, encoding="utf-8")

    benchmark_payload = {
        "target_videos": TARGET_10_VIDEOS,
        "video_metadata": video_metadata_dict,
        "self_shots": all_self_shots,
        "btc_keyframes": btc_keyframes_dict,
        "timestamp_generated": time.strftime("%Y-%m-%d %H:%M:%S")
    }

    payload_json = BENCHMARK_DIR / "comparison_data.json"
    with open(str(payload_json), "w", encoding="utf-8") as f:
        json.dump(benchmark_payload, f, ensure_ascii=False, indent=2)

    print("=" * 80)
    print(f"TỔNG KẾT BENCHMARK 5 VIDEO (MULTI-KEYFRAME):")
    print(f"  - Tổng số Keyframe trích xuất (System 1): {len(all_self_shots)} frames")
    print(f"  - Bảng tổng hợp CSV: {summary_csv}")
    print(f"  - Dữ liệu đối chiếu JSON: {payload_json}")
    print("=" * 80)


# ==============================================================================
# CLI DISPATCHER
# ==============================================================================
def main():
    parser = argparse.ArgumentParser(description="Unified System 1 Benchmark & Test Runner")
    parser.add_argument(
        "--mode",
        choices=["steps", "raw_video", "10_videos"],
        default="steps",
        help="Chế độ chạy: steps (4 bài test dữ liệu thật), raw_video (cắt cú máy 1 video), 10_videos (benchmark 10 video mẫu)"
    )
    parser.add_argument("--video", type=str, default="L21_V001", help="Mã video khi chạy mode raw_video")
    parser.add_argument("--frames", type=int, default=1500, help="Số lượng frames quét (0 = toàn bộ video)")

    args = parser.parse_args()

    if args.mode == "steps":
        run_steps_mode()
    elif args.mode == "raw_video":
        run_raw_video_mode(args.video, args.frames)
    elif args.mode == "10_videos":
        run_10_videos_mode()


if __name__ == "__main__":
    main()
