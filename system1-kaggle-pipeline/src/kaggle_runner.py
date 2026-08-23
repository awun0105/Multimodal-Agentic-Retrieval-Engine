"""
System 1 Master Orchestrator: End-to-End Kaggle Pipeline Runner
Trình điều phối toàn diện 5 bước kết nối Phase 00 -> Phase 03 trên Kaggle GPU/TPU:

Quy trình tuần tự:
- Bước 1 [Khởi tạo]: Nạp các mô hình SigLIP Base, faster-whisper Large-V3, EasyOCR, YOLOv8n.
- Bước 2 [Phase 00 Ingestion]: Quét video, giải mã Packet Counting tạo frame_timeline.
- Bước 3 [Phase 01 & 02 Structure/Features]: TransNet V2 cuts, Smart Keyframes, ByteTrack, OCR, KIS Semantics, ASR.
- Bước 4 [Phase 02 Vectors]: Trích xuất ma trận vector SigLIP Base chuẩn hóa L2 = 1.0.
- Bước 5 [Phase 03 Packaging]: Đóng gói SQLite FTS5, FAISS SQ8 và nén release_artifacts.zip.
"""

from __future__ import annotations
import os
import cv2
import shutil
import zipfile
from pathlib import Path
from tqdm import tqdm
import yaml

from frame_timeline import generate_frame_timeline
from shot_detector import detect_shots
from adaptive_keyframe import extract_adaptive_keyframes
from asr_transcriber import VietnameseASRTranscriber
from ocr_extractor import VietnameseOCRExtractor
from vector_extractor import SigLIPVectorExtractor
from semantic_enricher import KISDetailEnricher
from object_detector import YOLOObjectDetector
from db_builder import build_sqlite_database, build_faiss_index


def run_pipeline(
    input_video_dir: Path,
    output_dir: Path,
    config_path: Path
):
    print("=" * 60)
    print("BẮT ĐẦU SYSTEM 1 KAGGLE PIPELINE (VIETNAMESE & KIS FOCUS)")
    print("=" * 60)

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    output_dir.mkdir(parents=True, exist_ok=True)
    temp_keyframes_dir = output_dir / "keyframes"
    temp_thumbs_dir = output_dir / "thumbnails"

    # 1. Khởi tạo các mô hình AI
    print("[1/5] Đang khởi tạo các mô hình AI...")
    device = config["pipeline"].get("device", "cuda")
    
    asr_module = VietnameseASRTranscriber(
        model_size=config["asr"]["model_size"],
        device=device,
        compute_type=config["asr"]["compute_type"]
    )
    
    ocr_module = VietnameseOCRExtractor(
        languages=config["ocr"]["languages"],
        gpu=(device == "cuda")
    )
    
    vector_module = SigLIPVectorExtractor(
        model_name=config["embeddings"]["model_name"],
        device=device,
        batch_size=config["embeddings"]["batch_size"]
    )
    
    yolo_module = YOLOObjectDetector(device=device)

    # 2. Quét danh sách video
    video_files = sorted(list(input_video_dir.glob("*.mp4")) + list(input_video_dir.glob("*.mkv")))
    print(f"[2/5] Tìm thấy {len(video_files)} video cần xử lý.")

    all_videos_meta = []
    all_keyframes_meta = []
    all_asr_meta = []
    all_ocr_meta = []
    all_semantics_meta = []
    all_keyframe_paths = []

    # 3. Xử lý từng video
    print("[3/5] Đang xử lý bóc tách video và phân tích thuộc tính KIS...")
    for vpath in tqdm(video_files, desc="Processing Videos"):
        vid = vpath.stem
        v_keyframe_dir = temp_keyframes_dir / vid
        v_thumb_dir = temp_thumbs_dir / vid

        # Timeline
        timeline_df = generate_frame_timeline(vpath)
        fps = timeline_df["fps"].iloc[0] if not timeline_df.empty else 25.0
        total_duration = timeline_df["pts_time_sec"].iloc[-1] if not timeline_df.empty else 0.0

        all_videos_meta.append({
            "video_id": vid,
            "title": vid,
            "author": "HTV/VTV/Online",
            "length_sec": total_duration,
            "watch_url": f"https://youtube.com/watch?v={vid}",
            "publish_date": ""
        })

        # Shot detection
        shots = detect_shots(
            vpath,
            threshold=config["shot_detection"]["threshold"],
            min_shot_frames=config["shot_detection"]["min_shot_frames"]
        )

        # Smart Keyframes
        kfs = extract_adaptive_keyframes(
            vpath,
            shots=shots,
            output_keyframe_dir=v_keyframe_dir,
            output_thumbnail_dir=v_thumb_dir,
            min_sharpness=config["keyframe_extraction"]["quality_filter"]["min_sharpness"],
            min_brightness=config["keyframe_extraction"]["quality_filter"]["min_brightness"],
            max_brightness=config["keyframe_extraction"]["quality_filter"]["max_brightness"]
        )

        # 3.b Chạy tracking vật thể ByteTrack động trên luồng video
        print(f"  - [YOLO Track] Dang chay ByteTrack cho video {vid}...")
        try:
            active_tracks = yolo_module.track_video_objects(vpath, fps_sample=5.0)
        except Exception as e:
            print(f"Loi khi chay YOLO Track tren {vid}: {e}")
            active_tracks = {}

        shot_lookup = {s["shot_id"]: s for s in shots}

        for k in kfs:
            k["video_id"] = vid
            all_keyframes_meta.append(k)
            all_keyframe_paths.append(k["keyframe_path"])

            # Phân tích các tracks hoạt động trong khoảng thời gian của shot này để đếm vật thể duy nhất
            shot = shot_lookup.get(k["shot_id"], {})
            shot_start_sec = shot.get("start_frame", k["frame_id"]) / fps
            shot_end_sec = shot.get("end_frame", k["frame_id"]) / fps

            shot_tracks = []
            for track_id, t_info in active_tracks.items():
                if t_info["first_seen"] <= shot_end_sec and t_info["last_seen"] >= shot_start_sec:
                    shot_tracks.append(t_info)

            # Đếm số lượng vật thể duy nhất của từng lớp (ví dụ: "3 cars", "1 person")
            from collections import Counter
            counts = Counter([t["class"] for t in shot_tracks])
            obj_count_strings = [f"{count} {lbl}{'s' if count > 1 else ''}" for lbl, count in counts.items()]

            # Tìm các vật thể đang xuất hiện trực tiếp tại thời điểm của keyframe (+-1.0s) để hiển thị chi tiết
            kf_time = k["pts_time_sec"]
            kf_tracks = []
            for track_id, t_info in active_tracks.items():
                if t_info["first_seen"] <= kf_time + 1.0 and t_info["last_seen"] >= kf_time - 1.0:
                    kf_tracks.append(t_info)
            obj_score_strings = [f"{t['class']} ({t['max_conf']:.2f})" for t in kf_tracks]
            objects_str = ", ".join(obj_score_strings)

            # OCR trên keyframe
            ocr_res = ocr_module.extract_text_from_image(k["keyframe_path"])
            ocr_texts = []
            for box_item in ocr_res["boxes"]:
                ocr_texts.append(box_item["text"])
                all_ocr_meta.append({
                    "keyframe_id": k["keyframe_id"],
                    "video_id": vid,
                    "text": box_item["text"],
                    "confidence": box_item["confidence"],
                    "is_lower_third": box_item["is_lower_third"]
                })

            # Phân tích thuộc tính KIS (màu sắc, góc máy, ánh sáng, không gian, số lượng)
            frame_img = cv2.imread(k["keyframe_path"])
            if frame_img is not None:
                sem_res = KISDetailEnricher.extract_heuristics_from_image(frame_img, ocr_texts)
                sem_res["keyframe_id"] = k["keyframe_id"]
                sem_res["video_id"] = vid
                # Điền kết quả đếm và chuỗi vật thể từ YOLOv8 ByteTrack
                sem_res["objects_and_counts"] = obj_count_strings
                sem_res["objects_str"] = objects_str
                all_semantics_meta.append(sem_res)

        # ASR
        try:
            asr_segs = asr_module.transcribe(
                vpath,
                initial_prompt=config["asr"]["initial_prompt"]
            )
            for seg in asr_segs:
                seg["video_id"] = vid
                all_asr_meta.append(seg)
        except Exception as e:
            print(f"Lỗi ASR trên video {vid}: {e}")

    # 4. Trích xuất Vector SigLIP
    print(f"[4/5] Đang trích xuất Vector SigLIP cho {len(all_keyframe_paths)} keyframes...")
    vectors = vector_module.extract_image_vectors(all_keyframe_paths, normalize_l2=True)

    # 5. Xây dựng Database và Index
    print("[5/5] Đang đóng gói SQLite FTS5 và FAISS SQ8...")
    db_out = output_dir / config["export"]["sqlite_filename"]
    build_sqlite_database(
        db_out,
        all_videos_meta,
        all_keyframes_meta,
        all_asr_meta,
        all_ocr_meta,
        all_semantics_meta
    )

    faiss_out = output_dir / config["export"]["faiss_index_filename"]
    build_faiss_index(vectors, faiss_out, quantization=config["export"]["faiss_quantization"])

    # Đóng gói zip
    zip_out = output_dir / config["export"]["output_zip_name"]
    print(f"Tạo gói phát hành cuối cùng: {zip_out}")
    with zipfile.ZipFile(zip_out, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(db_out, arcname=db_out.name)
        z.write(faiss_out, arcname=faiss_out.name)

    print("=" * 60)
    print("HOÀN THÀNH PIPELINE THÀNH CÔNG!")
    print(f"File kết quả sẵn sàng tải về: {zip_out}")
    print("=" * 60)


if __name__ == "__main__":
    current_dir = Path(__file__).resolve().parent
    config_file = current_dir.parent / "configs" / "pipeline_config.yaml"
    print("Runner initialized with config:", config_file)
