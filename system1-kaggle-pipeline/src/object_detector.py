"""
Phase 02: Dynamic Object Tracking & Shot-Level Normalization
Module phân tích phát hiện và theo dõi định danh vật thể liên tục sử dụng YOLOv8n kết hợp ByteTrack.

Chức năng:
1. Batch inference nhận diện vật thể trên danh sách ảnh tĩnh keyframe.
2. Tracking động trên luồng video (5 FPS qua vid_stride) để ghi nhận hành trình [first_seen, last_seen].
3. Thống kê số lượng vật thể duy nhất trong mỗi cú máy (shot-level deduplication).

Hợp đồng dữ liệu đầu vào (Input):
- video_path: Đường dẫn tệp video MP4/MKV.
- image_paths: Danh sách đường dẫn ảnh tĩnh.

Hợp đồng dữ liệu đầu ra (Output):
- Dict[int, Dict]: {track_id: {class, max_conf, first_seen, last_seen}}.
"""

from __future__ import annotations
import sys
import cv2
from pathlib import Path
from collections import Counter

class YOLOObjectDetector:
    def __init__(self, device: str = "cuda", model_name: str = "yolov8n.pt"):
        self.device = device
        self.model_name = model_name
        self.model = None
        self._load_model()

    def _load_model(self):
        try:
            from ultralytics import YOLO
            # Khởi tạo mô hình và chuyển sang GPU/CPU
            self.model = YOLO(self.model_name)
            self.model.to(self.device)
            print(f"[YOLO] Nap thanh cong {self.model_name} tren thiet bi {self.device}")
        except Exception as e:
            print(f"[YOLO] Khong the nap ultralytics YOLO: {e}")

    def detect_objects_batch(self, image_paths: list[str | Path], batch_size: int = 64) -> list[dict]:
        """
        Chạy nhận diện vật thể theo lô (Batch Inference) trên danh sách ảnh tĩnh.
        """
        results = []
        if self.model is None:
            return [{"classes": [], "scores": []} for _ in image_paths]

        for i in range(0, len(image_paths), batch_size):
            batch_paths = image_paths[i:i + batch_size]
            try:
                batch_res = self.model.predict(
                    source=[str(p) for p in batch_paths],
                    device=self.device,
                    verbose=False,
                    conf=0.25
                )
                for res in batch_res:
                    classes = []
                    scores = []
                    for box in res.boxes:
                        cls_id = int(box.cls[0])
                        cls_name = self.model.names[cls_id]
                        score = float(box.conf[0])
                        classes.append(cls_name)
                        scores.append(score)
                    results.append({
                        "classes": classes,
                        "scores": scores
                    })
            except Exception as e:
                print(f"[YOLO] Loi trong qua trinh chay batch tu {i} den {i+len(batch_paths)}: {e}")
                for _ in batch_paths:
                    results.append({"classes": [], "scores": []})
        return results

    def track_video_objects(self, video_path: str | Path, fps_sample: float = 5.0) -> dict[int, dict]:
        """
        Thực hiện tracking vật thể trên toàn bộ video sử dụng vid_stride để bỏ qua frame tin cậy.
        Trả về danh sách các track vật thể kèm thông tin thời gian xuất hiện:
        track_id -> {
            "class": tên vật thể,
            "max_conf": độ tự tin lớn nhất,
            "first_seen": thời gian xuất hiện đầu tiên (giây),
            "last_seen": thời gian xuất hiện cuối cùng (giây)
        }
        """
        active_tracks = {}
        if self.model is None:
            return active_tracks

        # 1. Lấy thông tin FPS gốc của video
        cap = cv2.VideoCapture(str(video_path))
        raw_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        cap.release()

        # Tính bước nhảy khung hình (vid_stride) để đạt tần suất quét mong muốn (ví dụ 5 FPS)
        vid_stride = max(1, int(raw_fps / fps_sample))

        try:
            # Chạy ByteTrack trên luồng video
            track_res = self.model.track(
                source=str(video_path),
                persist=True,
                tracker="bytetrack.yaml",
                vid_stride=vid_stride,
                device=self.device,
                verbose=False,
                conf=0.25
            )

            for idx, res in enumerate(track_res):
                # Tính mốc thời gian pts_sec hiện tại dựa trên bước nhảy
                pts_sec = idx * (vid_stride / raw_fps)

                if res.boxes is None or res.boxes.id is None:
                    continue

                ids = res.boxes.id.int().cpu().tolist()
                classes = res.boxes.cls.int().cpu().tolist()
                confs = res.boxes.conf.float().cpu().tolist()

                for track_id, cls_id, conf in zip(ids, classes, confs):
                    cls_name = self.model.names[cls_id]
                    if track_id not in active_tracks:
                        active_tracks[track_id] = {
                            "class": cls_name,
                            "max_conf": conf,
                            "first_seen": pts_sec,
                            "last_seen": pts_sec
                        }
                    else:
                        active_tracks[track_id]["max_conf"] = max(active_tracks[track_id]["max_conf"], conf)
                        active_tracks[track_id]["last_seen"] = pts_sec

        except Exception as e:
            print(f"[YOLO Tracker] Loi tracking tren video {video_path}: {e}")

        return active_tracks

    @staticmethod
    def extract_event_keyframe_timestamps(
        active_tracks: dict[int, dict],
        shot_start_sec: float,
        shot_end_sec: float,
        min_duration_sec: float = 0.8,
        crowd_threshold: int = 5
    ) -> list[dict]:
        """
        Trích xuất danh sách các mốc thời gian keyframe dựa trên sự kiện xuất hiện/biến mất của vật thể:
        - Nếu số lượng người duy nhất trong shot <= crowd_threshold (5 người): Lấy keyframe tại first_seen (xuất hiện) và last_seen (biến mất) cho các tracklet có duration >= min_duration_sec (0.8s).
        - Nếu số lượng người > 5: Áp dụng Heuristic ức chế đám đông (Crowd Suppression), trả về cờ crowd_mode=True để nhường quyền lấy mẫu đều.
        """
        events: list[dict] = []
        shot_tracks = {
            t_id: info for t_id, info in active_tracks.items()
            if not (info["last_seen"] < shot_start_sec or info["first_seen"] > shot_end_sec)
        }

        # Đếm số lượng người duy nhất
        person_tracks = [t for t in shot_tracks.values() if t.get("class") == "person"]
        is_crowd = len(person_tracks) > crowd_threshold

        if is_crowd:
            # Chế độ đám đông: Giảm ưu tiên lấy keyframe từng người
            return [{
                "timestamp_sec": (shot_start_sec + shot_end_sec) / 2.0,
                "event_type": "crowd_scene",
                "object_class": "person_crowd",
                "unique_person_count": len(person_tracks),
                "is_crowd": True
            }]

        # Chế độ đối tượng đơn lẻ/nhóm nhỏ (<= 5 người): Bắt trọn khoảnh khắc vàng
        for t_id, info in shot_tracks.items():
            duration = info["last_seen"] - info["first_seen"]
            if duration < min_duration_sec:
                continue  # Bỏ qua vật thể lướt qua chớp tắt dưới 0.8s

            # Sự kiện xuất hiện trong cú máy
            if shot_start_sec <= info["first_seen"] <= shot_end_sec:
                events.append({
                    "timestamp_sec": info["first_seen"],
                    "event_type": "object_entered",
                    "track_id": t_id,
                    "object_class": info["class"],
                    "conf": info["max_conf"],
                    "is_crowd": False
                })

            # Sự kiện biến mất / rời khỏi cú máy
            if shot_start_sec <= info["last_seen"] <= shot_end_sec and duration >= 1.5:
                events.append({
                    "timestamp_sec": info["last_seen"],
                    "event_type": "object_exited",
                    "track_id": t_id,
                    "object_class": info["class"],
                    "conf": info["max_conf"],
                    "is_crowd": False
                })

        # Sắp xếp theo mốc thời gian tăng dần
        events.sort(key=lambda x: x["timestamp_sec"])
        return events

