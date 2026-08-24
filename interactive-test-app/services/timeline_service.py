"""
====================================================================================================
SERVICES - TIMELINE SYNCHRONIZATION & KEYFRAME EXTRACTION (timeline_service.py)
====================================================================================================

1. MỤC TIÊU VÀ VAI TRÒ:
   - Module này quản lý toàn bộ luồng xử lý video đầu vào và đồng bộ hóa dòng thời gian:
     a) Trích xuất keyframe sắc nét nhất từ video thô, khống chế trần lấy mẫu <= 2.5s.
     b) Hợp nhất dòng thời gian BTC và System 1 lên trục thời gian chung.
     c) Phân loại khung hình: Anchor (chuẩn), Frame Cắt Nghĩa (viền tím), Đề Xuất Lọc Bỏ (viền đỏ), Frame Giữ Tĩnh (holding row).
     d) Dựng bảng HTML Side-by-Side phục vụ trực quan hóa trên Tab 1.

2. CÁC HÀM CỐT LÕI:
   - `extract_video_keyframes_for_duration(...)`: Cắt keyframe video thô theo khoảng thời gian chỉ định.
   - `render_side_by_side_comparison(selected_video, duration_mode)`: Dựng HTML và nạp ảnh cho 2 Gallery.
   - `_load_cached_self_keyframes(video_id)` & `_save_cached_self_keyframes(...)`: Cơ chế CSV Caching.
====================================================================================================
"""

from __future__ import annotations
import os
import sys
import io
import time
import zipfile
import subprocess
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


import numpy as np
import pandas as pd
from pathlib import Path
from PIL import Image
import gradio as gr

from .config import (
    BENCHMARK_CSV,
    ZIP_VIDEOS,
    ZIP_MAP_KEYFRAMES,
    ZIP_OBJECTS,
    RAW_VIDEO_DIR,
    KEYFRAMES_OUT_DIR,
    THUMBS_OUT_DIR,
)
from .model_service import (
    get_video_metadata,
    format_timestamp,
    parse_duration_limit,
    pil_to_base64_thumb,
    get_btc_keyframe_image,
    get_self_extracted_image,
    create_placeholder_keyframe_image,
)
from .appearance_service import (
    extract_detected_objects_with_appearance,
    analyze_image_full_spectrum,
)
from .caption_service import generate_keyframe_bilingual_captions
from templates.card_templates import (
    render_timeline_center_cell,
    render_continuous_holding_row,
    render_side_by_side_header,
)

try:
    from timeline_synchronizer import TimelineSynchronizer
except ImportError:
    TimelineSynchronizer = None

try:
    from vietnamese_cultural_lexicon import lookup_cultural_concepts
except ImportError:
    lookup_cultural_concepts = None


def _load_cached_self_keyframes(selected_video: str, limit_sec: float) -> list[dict]:
    """Nạp nhanh keyframe tự xử lý từ benchmark_summary.csv nếu đã có."""
    if BENCHMARK_CSV.exists() and BENCHMARK_CSV.stat().st_size > 10:
        try:
            df = pd.read_csv(str(BENCHMARK_CSV))
            if "video_id" in df.columns:
                sub = df[df["video_id"] == selected_video]
                if not sub.empty:
                    if "pts_time_sec" in sub.columns:
                        sub = sub[sub["pts_time_sec"] <= limit_sec]
                    records = []
                    for r in sub.to_dict(orient="records"):
                        cleaned_r = {}
                        for k, v in r.items():
                            if pd.isna(v):
                                cleaned_r[k] = None
                            else:
                                cleaned_r[k] = v
                        records.append(cleaned_r)
                    return records
        except Exception:
            pass
    return []


def _save_cached_self_keyframes(selected_video: str, self_keyframes: list[dict]) -> None:
    """Lưu/cập nhật keyframe vào benchmark_summary.csv."""
    if not self_keyframes:
        return
    try:
        records_to_save = []
        for item in self_keyframes:
            d = dict(item)
            d.pop("hist", None)
            records_to_save.append(d)
        df_new = pd.DataFrame(records_to_save)
        if BENCHMARK_CSV.exists() and BENCHMARK_CSV.stat().st_size > 10:
            df_old = pd.read_csv(str(BENCHMARK_CSV))
            if "video_id" in df_old.columns:
                df_old = df_old[df_old["video_id"] != selected_video]
            df_combined = pd.concat([df_old, df_new], ignore_index=True)
            df_combined.to_csv(str(BENCHMARK_CSV), index=False, encoding="utf-8-sig")
        else:
            BENCHMARK_CSV.parent.mkdir(parents=True, exist_ok=True)
            df_new.to_csv(str(BENCHMARK_CSV), index=False, encoding="utf-8-sig")
    except Exception as e:
        print(f"[Cache] Không thể lưu CSV: {e}")


def extract_video_keyframes_for_duration(
    video_path: Path,
    selected_video: str,
    limit_sec: float,
    threshold: float = 27.0,
    min_shot_sec: float = 0.6,
    progress: gr.Progress = gr.Progress()
) -> list[dict]:
    """
    Trích xuất phân đoạn video thực tế bằng OpenCV với trần lấy mẫu tối đa 2.5s:
    - Phát hiện cú máy bằng Color Histogram HSV & Frobenius norm.
    - Khống chế trần thời gian max_shot_frames = int(fps * 2.5) để không để trống bất kỳ khoảng 2.5s nào.
    - Tích hợp fallback Unsharp Mask làm nét ảnh cho các phân cảnh mờ chuyển động.
    """
    progress(0.35, desc=f"Đang phân tích cú máy video ({limit_sec:.0f}s)...")

    with silence_stderr():
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            return []

        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        limit_frames = int(min(total_frames, limit_sec * fps))

        min_shot_frames = max(3, int(fps * min_shot_sec))
        max_shot_frames = int(fps * 2.5)  # Trần lấy mẫu tối đa 2.5 giây

        keyframes = []
        shot_id = 1
        shot_start_frame = 0
        shot_buffer = []

        prev_hist = None
        frame_idx = 0

        while frame_idx < limit_frames:
            ret, frame = cap.read()
            if not ret:
                break

        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        hist = cv2.calcHist([hsv], [0, 1], None, [32, 32], [0, 180, 0, 256])
        cv2.normalize(hist, hist, alpha=0, beta=1, norm_type=cv2.NORM_MINMAX)

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        lap_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())

        shot_buffer.append((frame_idx, frame.copy(), lap_var, hist))

        is_cut = False
        if prev_hist is not None:
            diff = cv2.compareHist(prev_hist, hist, cv2.HISTCMP_CHISQR)
            if diff > threshold and len(shot_buffer) >= min_shot_frames:
                is_cut = True

        if len(shot_buffer) >= max_shot_frames:
            is_cut = True

        if is_cut:
            best_fidx, best_img, best_sharp, best_h = max(shot_buffer, key=lambda x: x[2])
            pts_time = round(best_fidx / fps, 2)
            shot_dur = round(len(shot_buffer) / fps, 2)

            is_sharpened = False
            if best_sharp < 30.0:
                blurred = cv2.GaussianBlur(best_img, (0, 0), 3)
                sharpened = cv2.addWeighted(best_img, 1.5, blurred, -0.5, 0)
                best_img = sharpened
                best_sharp = float(cv2.Laplacian(cv2.cvtColor(best_img, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var())
                is_sharpened = True

            v_out_dir = KEYFRAMES_OUT_DIR / selected_video
            v_out_dir.mkdir(parents=True, exist_ok=True)
            out_img_path = v_out_dir / f"shot_{shot_id:04d}_frame_{best_fidx:06d}.webp"
            Image.fromarray(cv2.cvtColor(best_img, cv2.COLOR_BGR2RGB)).save(str(out_img_path), "WEBP", quality=85)

            # Bóc tách vật thể kèm ngoại hình
            rgb_arr = cv2.cvtColor(best_img, cv2.COLOR_BGR2RGB)
            nat_vi, nat_en, obj_counts, _ = extract_detected_objects_with_appearance(rgb_arr)

            kf_record = {
                "video_id": selected_video,
                "shot_id": shot_id,
                "keyframe_frame_idx": best_fidx,
                "pts_time_sec": pts_time,
                "duration_sec": shot_dur,
                "sharpness_score": round(best_sharp, 1),
                "is_sharpened_fallback": is_sharpened,
                "objects_and_counts": nat_vi,
                "objects_natural_vi": nat_vi,
                "objects_natural_en": nat_en,
                "objects_dict": obj_counts,
                "scene_environment": "Chưa xác định",
                "shot_contextual_meaning": "Cảnh Quay Thị Giác",
                "dominant_color": "Đa Sắc",
                "ocr_text": "",
                "is_semantic_virtual": False,
                "is_proposed_deletion": False,
                "hist": best_h
            }
            keyframes.append(kf_record)

            shot_id += 1
            shot_buffer = []

        prev_hist = hist
        frame_idx += 1

    if shot_buffer:
        best_fidx, best_img, best_sharp, best_h = max(shot_buffer, key=lambda x: x[2])
        pts_time = round(best_fidx / fps, 2)
        shot_dur = round(len(shot_buffer) / fps, 2)

        v_out_dir = KEYFRAMES_OUT_DIR / selected_video
        v_out_dir.mkdir(parents=True, exist_ok=True)
        out_img_path = v_out_dir / f"shot_{shot_id:04d}_frame_{best_fidx:06d}.webp"
        Image.fromarray(cv2.cvtColor(best_img, cv2.COLOR_BGR2RGB)).save(str(out_img_path), "WEBP", quality=85)

        rgb_arr = cv2.cvtColor(best_img, cv2.COLOR_BGR2RGB)
        nat_vi, nat_en, obj_counts, _ = extract_detected_objects_with_appearance(rgb_arr)

        kf_record = {
            "video_id": selected_video,
            "shot_id": shot_id,
            "keyframe_frame_idx": best_fidx,
            "pts_time_sec": pts_time,
            "duration_sec": shot_dur,
            "sharpness_score": round(best_sharp, 1),
            "is_sharpened_fallback": False,
            "objects_and_counts": nat_vi,
            "objects_natural_vi": nat_vi,
            "objects_natural_en": nat_en,
            "objects_dict": obj_counts,
            "scene_environment": "Chưa xác định",
            "shot_contextual_meaning": "Cảnh Quay Thị Giác",
            "dominant_color": "Đa Sắc",
            "ocr_text": "",
            "is_semantic_virtual": False,
            "is_proposed_deletion": False,
            "hist": best_h
        }
        keyframes.append(kf_record)

    cap.release()
    _save_cached_self_keyframes(selected_video, keyframes)
    return keyframes


def render_side_by_side_comparison(
    selected_video: str,
    duration_mode: str = "60s",
    progress: gr.Progress = gr.Progress()
) -> tuple[list, list, str]:
    """
    Tạo bảng đối chiếu đồng bộ chính xác theo TRỤC DÒNG THỜI GIAN (Timeline Axis).
    Tính toán Tổng thời lượng Video (Total Time) và hiển thị thanh tiến độ tinh gọn.
    """
    t_start_total = time.time()
    progress(0.05, desc="Đang đọc metadata và dữ liệu keyframe...")

    meta = get_video_metadata(selected_video)
    title = meta.get("title", selected_video)
    author = meta.get("author", "N/A")
    watch_url = meta.get("watch_url", f"https://www.youtube.com/watch?v={selected_video}")
    total_video_sec = float(meta.get("duration_sec", 1513.9))
    total_time_str = format_timestamp(total_video_sec)

    limit_sec = parse_duration_limit(duration_mode, total_video_sec)

    progress(0.20, desc=f"Đang nạp Keyframe BTC ({duration_mode})...")
    btc_list_raw = []
    total_btc_frames = 0
    frame_pts_map = {}

    if ZIP_MAP_KEYFRAMES.exists():
        try:
            with zipfile.ZipFile(str(ZIP_MAP_KEYFRAMES), "r") as z:
                fname = f"map-keyframes/{selected_video}.csv"
                if fname in z.namelist():
                    df = pd.read_csv(io.BytesIO(z.read(fname)))
                    total_btc_frames = len(df)
                    for _, row in df.iterrows():
                        frame_pts_map[int(row["frame_idx"])] = float(row["pts_time"])
                        if float(row["pts_time"]) <= limit_sec:
                            btc_list_raw.append(row.to_dict())
        except Exception:
            pass

    progress(0.30, desc=f"Đang nạp Keyframe System 1 ({duration_mode})...")
    self_list_raw = _load_cached_self_keyframes(selected_video, limit_sec)

    if not self_list_raw:
        vid_file = RAW_VIDEO_DIR / f"{selected_video}.mp4"
        if not vid_file.exists() and ZIP_VIDEOS.exists():
            try:
                progress(0.32, desc=f"Đang giải nén video mẫu {selected_video}...")
                with zipfile.ZipFile(str(ZIP_VIDEOS), "r") as z:
                    for item in z.namelist():
                        if item.endswith(f"{selected_video}.mp4") or item == f"{selected_video}.mp4":
                            with open(str(vid_file), "wb") as f_out:
                                f_out.write(z.read(item))
                            break
            except Exception:
                pass

        if vid_file.exists():
            self_list_raw = extract_video_keyframes_for_duration(vid_file, selected_video, limit_sec, progress=progress)

    progress(0.60, desc="Đang đồng bộ hóa ngữ cảnh và dòng thời gian...")
    if TimelineSynchronizer is not None:
        btc_list = [TimelineSynchronizer.enrich_btc_with_shot_context(b, self_list_raw) for b in btc_list_raw]
        self_list = TimelineSynchronizer.merge_and_deduplicate_timeline(btc_list_raw, self_list_raw)
    else:
        btc_list = btc_list_raw
        self_list = self_list_raw

    # Thư viện ảnh cho Gallery
    btc_gallery = []
    self_gallery = []

    for r in btc_list[:60]:
        k_no = int(TimelineSynchronizer.safe_float(r.get("n", r.get("frame_idx", 0)), 0)) if TimelineSynchronizer else int(r.get("n", r.get("frame_idx", 0)))
        f_idx = int(TimelineSynchronizer.safe_float(r.get("frame_idx", 0), 0)) if TimelineSynchronizer else int(r.get("frame_idx", 0))
        pts = float(TimelineSynchronizer.safe_float(r.get("pts_time", r.get("pts_time_sec", 0.0)), 0.0)) if TimelineSynchronizer else float(r.get("pts_time", 0.0))
        img = get_btc_keyframe_image(selected_video, k_no)
        if img is None:
            img = create_placeholder_keyframe_image(f"BTC #{k_no}\nFrame {f_idx}")
        caption = f"BTC #{k_no} | Frame {f_idx} | {format_timestamp(pts)} ({pts:.1f}s)"
        btc_gallery.append((img, caption))

    for r in self_list[:60]:
        s_id = int(TimelineSynchronizer.safe_float(r.get("shot_id", 0), 0)) if TimelineSynchronizer else int(r.get("shot_id", 0))
        f_idx = int(TimelineSynchronizer.safe_float(r.get("keyframe_frame_idx", r.get("frame_idx", 0)), 0)) if TimelineSynchronizer else int(r.get("frame_idx", 0))
        pts = float(TimelineSynchronizer.safe_float(r.get("pts_time_sec", 0.0), 0.0)) if TimelineSynchronizer else float(r.get("pts_time_sec", 0.0))
        sharp = float(TimelineSynchronizer.safe_float(r.get("sharpness_score", 0.0), 0.0)) if TimelineSynchronizer else float(r.get("sharpness_score", 0.0))
        img = get_self_extracted_image(selected_video, s_id, f_idx)
        if img is None:
            img = create_placeholder_keyframe_image(f"Shot #{s_id}\nFrame {f_idx}")
        caption = f"Shot #{s_id} | Frame {f_idx} | {format_timestamp(pts)} | Nét: {sharp:.1f}"
        self_gallery.append((img, caption))

    time_slots_html = []
    max_pts = min(int(limit_sec), int(max([float(TimelineSynchronizer.safe_float(b.get("pts_time", b.get("pts_time_sec", 0.0)), 0.0)) for b in btc_list] + [float(TimelineSynchronizer.safe_float(s.get("pts_time_sec", 0.0), 0.0)) for s in self_list] + [60])) + 3)

    for t_start in range(0, max_pts, 3):
        t_end = t_start + 3
        b_in_slot = [b for b in btc_list if t_start <= float(TimelineSynchronizer.safe_float(b.get("pts_time", b.get("pts_time_sec", 0.0)), 0.0)) < t_end]
        s_in_slot = [s for s in self_list if t_start <= float(TimelineSynchronizer.safe_float(s.get("pts_time_sec", 0.0), 0.0)) < t_end]

        if not b_in_slot and not s_in_slot:
            t_slot_str = f"{format_timestamp(t_start)} - {format_timestamp(t_end)}"
            yt_url = f"{watch_url}&t={t_start}s"
            time_slots_html.append(render_continuous_holding_row(t_start, t_end, t_slot_str, yt_url))
            continue

        if b_in_slot:
            btc_cards_html = []
            for b in b_in_slot:
                b_kno = int(TimelineSynchronizer.safe_float(b.get("n", b.get("frame_idx", 0)), 0))
                b_fidx = int(TimelineSynchronizer.safe_float(b.get("frame_idx", 0), 0))
                b_pts = float(TimelineSynchronizer.safe_float(b.get("pts_time", b.get("pts_time_sec", 0.0)), 0.0))
                b_tstr = format_timestamp(b_pts)

                b_img = get_btc_keyframe_image(selected_video, b_kno)
                b_img_b64 = pil_to_base64_thumb(b_img, size=(140, 78))

                # Trích xuất vật thể tự nhiên song ngữ
                raw_obj_vi = TimelineSynchronizer.clean_text_field(b.get("objects_natural_vi", b.get("objects_and_counts")))
                raw_obj_en = TimelineSynchronizer.clean_text_field(b.get("objects_natural_en"))
                b_obj_dict = b.get("objects_dict", {})
                if isinstance(b_obj_dict, str):
                    try:
                        import ast
                        b_obj_dict = ast.literal_eval(b_obj_dict)
                    except Exception:
                        b_obj_dict = {}
                elif not isinstance(b_obj_dict, dict):
                    b_obj_dict = {}

                if (not raw_obj_vi or "Khong phat hien" in raw_obj_vi or "Không phát hiện" in raw_obj_vi or "Không bắt được" in raw_obj_vi) and b_img is not None:
                    try:
                        b_extracted_vi, b_extracted_en, b_extracted_dict, _ = extract_detected_objects_with_appearance(np.array(b_img))
                        if b_extracted_dict:
                            raw_obj_vi = b_extracted_vi
                            raw_obj_en = b_extracted_en
                            b_obj_dict = b_extracted_dict
                    except Exception:
                        pass

                if not raw_obj_vi or "Khong phat hien" in raw_obj_vi or "Không phát hiện" in raw_obj_vi or "Không bắt được" in raw_obj_vi:
                    b_obj_display = '<span style="color: #6c7a96; font-style: italic;">Không bắt được vật thể</span>'
                    total_objs = 0
                else:
                    total_objs = sum(b_obj_dict.values()) if (isinstance(b_obj_dict, dict) and b_obj_dict) else 1
                    b_obj_display = f'<span style="color: #a3be8c; font-weight: bold;">(N = {total_objs}): {raw_obj_vi}</span>'

                b_scene = TimelineSynchronizer.clean_text_field(b.get("scene_environment")) or "Chưa xác định"
                b_meaning = TimelineSynchronizer.clean_text_field(b.get("shot_contextual_meaning")) or "Khung hình chuẩn BTC"
                b_color = TimelineSynchronizer.clean_text_field(b.get("dominant_color")) or "Đa Sắc"
                b_sharp = float(TimelineSynchronizer.safe_float(b.get("sharpness_score", 450.0), 450.0))
                b_ocr = TimelineSynchronizer.clean_text_field(b.get("ocr_text"))
                b_ocr_html = f'<div style="font-size: 10px; color: #ebcb8b; font-style: italic; background: rgba(235,203,139,0.1); padding: 2px 5px; border-radius: 3px; margin: 2px 0;"><b>OCR Trích Xuất:</b> "{b_ocr}"</div>' if b_ocr else ""

                btc_badges = []
                b_is_low_info = bool(b.get("is_btc_low_info", False))
                b_is_virtual = bool(b.get("is_semantic_virtual", False) or (b.get("border_color") == "violet"))
                b_notice = b.get("btc_notice", "")
                b_diff = TimelineSynchronizer.clean_text_field(b.get("semantic_difference", ""))
                b_delta_tag = TimelineSynchronizer.clean_text_field(b.get("delta_time_tag", ""))
                b_anchor_id = str(b.get("anchor_frame_idx", ""))

                b_full_text = f"{b_ocr} {b_meaning} {b_scene} {raw_obj_vi}"
                b_cultural_concepts = lookup_cultural_concepts(b_full_text) if lookup_cultural_concepts is not None else []
                for cc in b_cultural_concepts:
                    btc_badges.append(f'<span style="background: #bd93f9; color: #1e1e2e; padding: 1px 5px; border-radius: 3px; font-weight: bold; font-size: 9px;">[Văn Hóa: {cc["canonical_name"]}]</span>')

                b_caption_vi, b_caption_en = generate_keyframe_bilingual_captions(
                    meaning=b_meaning,
                    scene=b_scene,
                    objects=raw_obj_vi,
                    natural_vi_objects=raw_obj_vi,
                    natural_en_objects=raw_obj_en,
                    ocr=b_ocr,
                    color=b_color,
                    cultural_concepts=b_cultural_concepts,
                    is_virtual=b_is_virtual,
                    delta_tag=b_delta_tag,
                    anchor_id=b_anchor_id
                )

                if b_is_virtual:
                    btc_card_border = "border: 3px solid #bd93f9; border-left: 6px solid #bd93f9; box-shadow: 0 0 14px rgba(189,147,249,0.7); outline: 1px solid #ff79c6;"
                    btc_badges.append(f'<span style="background: #bd93f9; color: #1e1e2e; padding: 2px 6px; border-radius: 3px; font-weight: bold; font-size: 10px;">[Frame Cắt Nghĩa {b_delta_tag}]</span>')
                    btc_title_color = "#bd93f9"
                elif b_img is not None:
                    try:
                        b_arr = np.array(b_img)
                        b_std = float(np.std(b_arr))
                        b_mean = float(np.mean(b_arr))
                        if b_std < 6.0:
                            b_is_low_info = True
                            btc_badges.append('<span style="background: #ff5555; color: #1e1e2e; padding: 1px 6px; border-radius: 3px; font-weight: bold; font-size: 9px; margin-left: 4px;">[BTC-xử lý: Ảnh đơn sắc]</span>')
                        if b_mean < 8.0:
                            b_is_low_info = True
                            btc_badges.append('<span style="background: #bf616a; color: white; padding: 1px 6px; border-radius: 3px; font-weight: bold; font-size: 9px; margin-left: 4px;">[BTC-xử lý: Màn hình đen]</span>')
                        elif b_mean > 248.0:
                            b_is_low_info = True
                            btc_badges.append('<span style="background: #ebcb8b; color: #1e1e2e; padding: 1px 6px; border-radius: 3px; font-weight: bold; font-size: 9px; margin-left: 4px;">[BTC-xử lý: Màn hình trắng]</span>')
                        if b_sharp < 15.0 and b_std >= 6.0 and total_objs == 0 and not b_ocr:
                            b_is_low_info = True
                            btc_badges.append('<span style="background: #ff5555; color: #1e1e2e; padding: 1px 6px; border-radius: 3px; font-weight: bold; font-size: 9px; margin-left: 4px;">[BTC-xử lý: Mờ cực nặng]</span>')
                    except Exception:
                        pass
                elif b_is_low_info:
                    btc_badges.append(f'<span style="background: #ff5555; color: #1e1e2e; padding: 1px 6px; border-radius: 3px; font-weight: bold; font-size: 9px; margin-left: 4px;">[{b_notice or "BTC-xu ly: Mat do thong tin thap"}]</span>')

                if b_is_virtual:
                    pass
                elif b_is_low_info:
                    btc_card_border = "border: 2px solid #ff5555; border-left: 5px solid #ff5555; box-shadow: 0 0 12px rgba(255,85,85,0.6);"
                    btc_title_color = "#ff5555"
                else:
                    btc_card_border = "border: 2px solid #8be9fd; border-left: 5px solid #8be9fd; box-shadow: 0 0 12px rgba(139,233,253,0.4);"
                    btc_title_color = "#8be9fd"

                btc_badges_html = f'<div style="display: flex; gap: 4px; flex-wrap: wrap; align-items: center;">{"".join(btc_badges)}</div>'
                
                b_virtual_pointer_html = ""
                if b_is_virtual and b_diff:
                    anc_pts = frame_pts_map.get(int(TimelineSynchronizer.safe_float(b_anchor_id, 0)), b_pts)
                    b_virtual_pointer_html = f"""
                    <div style="background: rgba(189,147,249,0.15); border: 1px solid rgba(189,147,249,0.5); padding: 5px 8px; border-radius: 4px; margin: 4px 0; font-size: 11px;">
                        <span style="color: #bd93f9; font-weight: bold;">[Con Trỏ Địa Chỉ Nhớ]:</span>
                        <span style="color: #d8dee9;">Dùng chung ảnh với <b>Anchor Frame #{b_anchor_id}</b> (mốc {format_timestamp(anc_pts)}) -> <i>Tiết kiệm 100% đĩa (Zero Disk Waste)</i></span>
                        <div style="color: #50fa7b; font-weight: bold; margin-top: 2px;">+ Thông tin mới tại mốc {b_tstr}: {b_diff} ({b_delta_tag})</div>
                    </div>
                    """

                btc_cards_html.append(f"""
                <div style="display: flex; gap: 10px; align-items: flex-start; background-color: #242933; {btc_card_border} padding: 10px; border-radius: 6px; margin-bottom: 10px;">
                    <img src="{b_img_b64}" width="140" height="78" style="border-radius: 4px; object-fit: cover; border: 1px solid {btc_title_color}; flex-shrink: 0; margin-top: 2px;" alt="BTC #{b_kno}" />
                    <div style="flex-grow: 1; min-width: 0; font-size: 11px; line-height: 1.4;">
                        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 4px;">
                            <span style="font-weight: bold; color: {btc_title_color}; font-size: 12px;">#{b_kno} (Frame {b_fidx})</span>
                            {btc_badges_html}
                        </div>
                        <div style="color: #eceff4; margin: 2px 0;">Mốc: <b style="color: #ebcb8b;">{b_tstr}</b> ({b_pts:.2f}s) | Nét: <b>{b_sharp:.1f}</b> | Màu: <b>{b_color}</b></div>
                        {b_virtual_pointer_html}
                        
                        <!-- 1. BẢN MIÊU TẢ TIẾNG VIỆT TỰ NHIÊN -->
                        <div style="background: rgba(136,192,208,0.12); border-left: 3px solid #88c0d0; padding: 4px 6px; border-radius: 3px; margin: 3px 0;">
                            <div style="color: #88c0d0; font-weight: bold; font-size: 10px;">[MIÊU TẢ TIẾNG VIỆT (TỰ THÂN + PHỤ LỤC VẬT THỂ)]:</div>
                            <div style="color: #ffffff; font-size: 11px; line-height: 1.35;">"{b_caption_vi}"</div>
                        </div>

                        <!-- 2. BẢN DỊCH & LÀM GIÀU EN CHO SIGLIP -->
                        <div style="background: rgba(189,147,249,0.12); border-left: 3px solid #bd93f9; padding: 4px 6px; border-radius: 3px; margin: 3px 0;">
                            <div style="color: #bd93f9; font-weight: bold; font-size: 10px;">[100% PURE ENGLISH VISUAL PROMPT (SIGLIP SO400M)]:</div>
                            <div style="color: #50fa7b; font-family: monospace; font-size: 10.5px; line-height: 1.35;">"{b_caption_en}"</div>
                        </div>

                        <div style="font-size: 10.5px; margin-top: 2px;">Vật thể: {b_obj_display}</div>
                        {b_ocr_html}
                    </div>
                </div>
                """)
            btc_cell = "".join(btc_cards_html)
        else:
            btc_cell = """
            <div style="background-color: #242933; border: 1px dashed #4c566a; border-radius: 6px; padding: 15px; color: #616e88; font-style: italic; text-align: center; font-size: 12px;">
                [BTC] Không lấy mẫu trong khoảng giây này
            </div>
            """

        if s_in_slot:
            self_cards_html = []
            for s in s_in_slot:
                s_sid = int(TimelineSynchronizer.safe_float(s.get("shot_id", 0), 0))
                s_fidx = int(TimelineSynchronizer.safe_float(s.get("keyframe_frame_idx", s.get("frame_idx", 0)), 0))
                s_pts = float(TimelineSynchronizer.safe_float(s.get("pts_time_sec", 0.0), 0.0))
                s_dur = float(TimelineSynchronizer.safe_float(s.get("duration_sec", 2.5), 2.5))
                s_sharp = float(TimelineSynchronizer.safe_float(s.get("sharpness_score", s.get("sharpness", 0.0)), 0.0))
                s_meaning = TimelineSynchronizer.clean_text_field(s.get("shot_contextual_meaning", s.get("shot_type", "Cảnh Quay Thị Giác"))) or "Cảnh Quay Thị Giác"
                s_color = TimelineSynchronizer.clean_text_field(s.get("dominant_color", "Đa Sắc")) or "Đa Sắc"
                s_date = TimelineSynchronizer.clean_text_field(s.get("date_info", ""))
                s_ocr = TimelineSynchronizer.clean_text_field(s.get("ocr_text", ""))
                s_scene = TimelineSynchronizer.clean_text_field(s.get("scene_environment", "Chưa xác định")) or "Chưa xác định"
                
                s_img = get_self_extracted_image(selected_video, s_sid, s_fidx)
                s_img_b64 = pil_to_base64_thumb(s_img, size=(140, 78))

                # Trích xuất vật thể tự nhiên song ngữ
                raw_obj_vi = TimelineSynchronizer.clean_text_field(s.get("objects_natural_vi", s.get("objects_and_counts")))
                raw_obj_en = TimelineSynchronizer.clean_text_field(s.get("objects_natural_en"))
                s_obj_dict = s.get("objects_dict", {})
                if (not raw_obj_vi or "Khong phat hien" in raw_obj_vi or "Không phát hiện" in raw_obj_vi or "Không bắt được" in raw_obj_vi) and s_img is not None:
                    try:
                        s_extracted_vi, s_extracted_en, s_extracted_dict, _ = extract_detected_objects_with_appearance(np.array(s_img))
                        if s_extracted_dict:
                            raw_obj_vi = s_extracted_vi
                            raw_obj_en = s_extracted_en
                            s_obj_dict = s_extracted_dict
                    except Exception:
                        pass

                # Đồng bộ nếu trong cùng slot BTC có vật thể và tương đồng thời gian
                if (not raw_obj_vi or "Khong phat hien" in raw_obj_vi or "Không phát hiện" in raw_obj_vi or "Không bắt được" in raw_obj_vi) and b_in_slot:
                    b_ref = b_in_slot[0]
                    b_ref_objs_vi = TimelineSynchronizer.clean_text_field(b_ref.get("objects_natural_vi", b_ref.get("objects_and_counts")))
                    b_ref_objs_en = TimelineSynchronizer.clean_text_field(b_ref.get("objects_natural_en"))
                    if b_ref_objs_vi and "Khong phat hien" not in b_ref_objs_vi and "Không phát hiện" not in b_ref_objs_vi and "Không bắt được" not in b_ref_objs_vi:
                        raw_obj_vi = b_ref_objs_vi
                        raw_obj_en = b_ref_objs_en
                        s_obj_dict = b_ref.get("objects_dict", {})

                if isinstance(s_obj_dict, str):
                    try:
                        import ast
                        s_obj_dict = ast.literal_eval(s_obj_dict)
                    except Exception:
                        s_obj_dict = {}
                elif not isinstance(s_obj_dict, dict):
                    s_obj_dict = {}

                if not raw_obj_vi or "Khong phat hien" in raw_obj_vi or "Không phát hiện" in raw_obj_vi or "Không bắt được" in raw_obj_vi:
                    s_obj_display = '<span style="color: #6c7a96; font-style: italic;">Không bắt được vật thể</span>'
                    total_objs = 0
                else:
                    total_objs = sum(s_obj_dict.values()) if (isinstance(s_obj_dict, dict) and s_obj_dict) else 1
                    s_obj_display = f'<span style="color: #a3be8c; font-weight: bold;">(N = {total_objs}): {raw_obj_vi}</span>'

                text_density = float(TimelineSynchronizer.safe_float(s.get("text_density_pct", 0.0), 0.0))

                is_virtual = bool(s.get("is_semantic_virtual", False) or (s.get("border_color") == "violet"))
                is_red_del = bool(s.get("is_proposed_deletion", False) or (s.get("border_color") == "red"))
                is_sharpened = bool(s.get("is_sharpened_fallback", False))
                is_bumper = bool("Chuyen Canh" in s_meaning or "Tieu De" in s_meaning or text_density >= 15.0)
                delta_tag = TimelineSynchronizer.clean_text_field(s.get("delta_time_tag", ""))
                s_diff = TimelineSynchronizer.clean_text_field(s.get("semantic_difference", ""))
                s_anchor_id = str(s.get("anchor_frame_idx", ""))

                s_badges = []
                if is_virtual:
                    s_badges.append(f'<span style="background: #bd93f9; color: #1e1e2e; padding: 2px 6px; border-radius: 3px; font-weight: bold; font-size: 10px;">[Frame Cắt Nghĩa {delta_tag}]</span>')
                if is_red_del:
                    reason = s.get("deletion_reason", "Ảnh mờ / Trùng bối cảnh")
                    s_badges.append(f'<span style="background: #ff5555; color: #1e1e2e; padding: 2px 6px; border-radius: 3px; font-weight: bold; font-size: 10px;">[Đề Xuất Lọc Bỏ - {reason}]</span>')
                if is_sharpened:
                    s_badges.append('<span style="background: #ebcb8b; color: #1e1e2e; padding: 2px 6px; border-radius: 3px; font-weight: bold; font-size: 10px;">[Đã Làm Nét - Fallback]</span>')
                if is_bumper:
                    s_badges.append('<span style="background: #81a1c1; color: #1e1e2e; padding: 2px 6px; border-radius: 3px; font-weight: bold; font-size: 10px;">[Chuyển Cảnh / Tiêu Đề]</span>')
                
                s_full_text = f"{s_ocr} {s_meaning} {s_scene} {raw_obj_vi}"
                s_cultural_concepts = lookup_cultural_concepts(s_full_text) if lookup_cultural_concepts is not None else []
                for cc in s_cultural_concepts:
                    s_badges.append(f'<span style="background: #bd93f9; color: #1e1e2e; padding: 1px 5px; border-radius: 3px; font-weight: bold; font-size: 9px;">[Văn Hóa: {cc["canonical_name"]}]</span>')

                s_caption_vi, s_caption_en = generate_keyframe_bilingual_captions(
                    meaning=s_meaning,
                    scene=s_scene,
                    objects=raw_obj_vi,
                    natural_vi_objects=raw_obj_vi,
                    natural_en_objects=raw_obj_en,
                    ocr=s_ocr,
                    color=s_color,
                    cultural_concepts=s_cultural_concepts,
                    is_virtual=is_virtual,
                    delta_tag=delta_tag,
                    anchor_id=s_anchor_id
                )

                if not s_badges:
                    s_badges.append('<span style="background: #a3be8c; color: #1e1e2e; padding: 1px 5px; border-radius: 3px; font-weight: bold; font-size: 9px;">[System 1 Tiêu Chuẩn]</span>')

                if is_red_del:
                    card_border_style = "border: 2px solid #ff5555; border-right: 5px solid #ff5555; box-shadow: 0 0 12px rgba(255,85,85,0.6);"
                    title_color = "#ff5555"
                elif is_virtual:
                    card_border_style = "border: 3px solid #bd93f9; border-right: 6px solid #bd93f9; box-shadow: 0 0 14px rgba(189,147,249,0.7); outline: 1px solid #ff79c6;"
                    title_color = "#bd93f9"
                elif is_sharpened:
                    card_border_style = "border: 2px solid #ebcb8b; border-right: 5px solid #ebcb8b; box-shadow: 0 0 10px rgba(235,203,139,0.5);"
                    title_color = "#ebcb8b"
                else:
                    card_border_style = "border: 1px solid #434c5e; border-right: 4px solid #a3be8c;"
                    title_color = "#a3be8c"

                status_badges_html = f'<div style="display: flex; gap: 4px; flex-wrap: wrap; align-items: center; justify-content: flex-end;">{"".join(s_badges)}</div>'
                
                s_virtual_pointer_html = ""
                if is_virtual and s_diff:
                    anc_pts = frame_pts_map.get(int(TimelineSynchronizer.safe_float(s_anchor_id, 0)), s_pts)
                    s_virtual_pointer_html = f"""
                    <div style="background: rgba(189,147,249,0.15); border: 1px solid rgba(189,147,249,0.5); padding: 5px 8px; border-radius: 4px; margin: 4px 0; font-size: 11px; text-align: right;">
                        <span style="color: #bd93f9; font-weight: bold;">[Con Trỏ Địa Chỉ Nhớ]:</span>
                        <span style="color: #d8dee9;">Dùng chung ảnh với <b>Anchor Frame #{s_anchor_id}</b> (mốc {format_timestamp(anc_pts)}) -> <i>Tiết kiệm 100% đĩa (Zero Disk Waste)</i></span>
                        <div style="color: #50fa7b; font-weight: bold; margin-top: 2px;">+ Thông tin mới tại mốc {s_tstr}: {s_diff} ({delta_tag})</div>
                    </div>
                    """

                s_tstr = format_timestamp(s_pts)
                s_ocr_html = f'<div style="font-size: 10px; color: #ebcb8b; background: rgba(235,203,139,0.1); padding: 2px 5px; border-radius: 3px; font-style: italic; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 280px; text-align: right;"><b>OCR Trích Xuất:</b> "{s_ocr}"</div>' if s_ocr else ""
                s_date_html = f'<div style="font-size: 10px; color: #88c0d0; font-weight: bold;">Ngày: {s_date}</div>' if s_date else ""

                self_cards_html.append(f"""
                <div style="display: flex; gap: 10px; align-items: flex-start; justify-content: flex-end; background-color: #242933; {card_border_style} padding: 10px; border-radius: 6px; margin-bottom: 10px;">
                    <div style="flex-grow: 1; text-align: right; min-width: 0; font-size: 11px; line-height: 1.4;">
                        <div style="display: flex; justify-content: space-between; align-items: center; flex-direction: row-reverse; flex-wrap: wrap; gap: 4px;">
                            <span style="font-weight: bold; color: {title_color}; font-size: 12px;">Shot #{s_sid} (Frame {s_fidx})</span>
                            {status_badges_html}
                        </div>
                        <div style="color: #eceff4; margin: 2px 0;">Mốc: <b style="color: #ebcb8b;">{s_tstr}</b> ({s_pts:.2f}s) | Dài {s_dur:.1f}s | Nét: <b>{s_sharp:.1f}</b> | Màu: <b>{s_color}</b></div>
                        {s_virtual_pointer_html}
                        
                        <!-- 1. BẢN MIÊU TẢ TIẾNG VIỆT TỰ NHIÊN -->
                        <div style="background: rgba(136,192,208,0.12); border-right: 3px solid #88c0d0; padding: 4px 6px; border-radius: 3px; margin: 3px 0; text-align: right;">
                            <div style="color: #88c0d0; font-weight: bold; font-size: 10px;">[MIÊU TẢ TIẾNG VIỆT (TỰ THÂN + PHỤ LỤC VẬT THỂ)]:</div>
                            <div style="color: #ffffff; font-size: 11px; line-height: 1.35;">"{s_caption_vi}"</div>
                        </div>

                        <!-- 2. BẢN DỊCH & LÀM GIÀU EN CHO SIGLIP -->
                        <div style="background: rgba(189,147,249,0.12); border-right: 3px solid #bd93f9; padding: 4px 6px; border-radius: 3px; margin: 3px 0; text-align: right;">
                            <div style="color: #bd93f9; font-weight: bold; font-size: 10px;">[100% PURE ENGLISH VISUAL PROMPT (SIGLIP SO400M)]:</div>
                            <div style="color: #50fa7b; font-family: monospace; font-size: 10.5px; line-height: 1.35;">"{s_caption_en}"</div>
                        </div>

                        <div style="font-size: 10.5px; margin-top: 2px;">Vật thể: {s_obj_display}</div>
                        {s_date_html}
                        {s_ocr_html}
                    </div>
                    <img src="{s_img_b64}" width="140" height="78" style="border-radius: 4px; object-fit: cover; border: 1px solid {title_color}; flex-shrink: 0; margin-top: 2px;" alt="Shot #{s_sid}" />
                </div>
                """)
            self_cell = "".join(self_cards_html)
        else:
            self_cell = """
            <div style="background-color: #242933; border: 1px dashed #4c566a; border-radius: 6px; padding: 15px; color: #616e88; font-style: italic; text-align: center; font-size: 12px;">
                [System 1] Không có cú máy mới / Đã lọc bỏ khung hình mờ
            </div>
            """

        t_slot_str = f"{format_timestamp(t_start)} - {format_timestamp(t_end)}"
        yt_url = f"{watch_url}&t={t_start}s"
        timeline_cell = render_timeline_center_cell(t_start, t_end, t_slot_str, yt_url)

        row_item = f"""
        <div style="display: grid; grid-template-columns: 1fr 140px 1fr; gap: 12px; align-items: stretch; margin-bottom: 12px; background-color: #2e3440; padding: 8px; border-radius: 8px; box-shadow: 0 2px 6px rgba(0,0,0,0.3);">
            <div>{btc_cell}</div>
            <div style="display: flex; align-items: center; justify-content: center;">{timeline_cell}</div>
            <div>{self_cell}</div>
        </div>
        """
        time_slots_html.append(row_item)

    elapsed_total = time.time() - t_start_total
    latency_str = f"{elapsed_total*1000:.1f} ms" if elapsed_total < 1.0 else f"{elapsed_total:.2f} s"
    text_bumper_count = len([s for s in self_list if "Chuyen Canh" in str(s.get("shot_contextual_meaning", "")) or "Tieu De" in str(s.get("shot_contextual_meaning", ""))])

    progress(1.0, desc=f"Hoàn tất trong {latency_str}!")

    header_html = render_side_by_side_header(
        selected_video=selected_video,
        title=title,
        author=author,
        watch_url=watch_url,
        total_time_str=total_time_str,
        total_video_sec=total_video_sec,
        latency_str=latency_str,
        duration_mode=duration_mode,
        text_bumper_count=text_bumper_count,
        btc_count=len(btc_list),
        total_btc_frames=total_btc_frames,
        self_count=len(self_list)
    )

    full_side_by_side_html = header_html + "".join(time_slots_html)
    return btc_gallery, self_gallery, full_side_by_side_html
