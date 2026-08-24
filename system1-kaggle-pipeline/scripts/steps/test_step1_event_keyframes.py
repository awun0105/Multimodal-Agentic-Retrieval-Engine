"""
Kịch bản kiểm thử độc lập Step 1: Trích xuất Keyframe theo sự kiện vật thể (Object Event Keyframe Extraction).
Kiểm tra Heuristic ức chế đám đông (<= 5 người vs > 5 người) và lọc nhiễu thời lượng >= 0.8s.
"""

from __future__ import annotations
import sys
from pathlib import Path

# Dam bao UTF-8 tren Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

SRC_DIR = Path(__file__).resolve().parent.parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from object_detector import YOLOObjectDetector


def test_event_keyframe_extraction():
    print("=" * 70)
    print("KIỂM THỬ ĐỘC LẬP: TRÍCH XUẤT KEYFRAME THEO SỰ KIỆN VẬT THỂ (STEP 1)")
    print("=" * 70)

    # 1. Kịch bản 1: Cảnh ít người (3 người, 1 xe máy) -> Phải bắt trọn mốc first_seen & last_seen
    tracks_small_scene = {
        1: {"class": "person", "max_conf": 0.92, "first_seen": 2.0, "last_seen": 8.5}, # Duration 6.5s -> Entered & Exited
        2: {"class": "motorcycle", "max_conf": 0.88, "first_seen": 4.0, "last_seen": 7.0}, # Duration 3.0s -> Entered & Exited
        3: {"class": "person", "max_conf": 0.45, "first_seen": 5.0, "last_seen": 5.3}, # Duration 0.3s -> Noise (< 0.8s, bỏ qua)
        4: {"class": "person", "max_conf": 0.85, "first_seen": 1.0, "last_seen": 9.0}  # Duration 8.0s -> Entered & Exited
    }

    events_small = YOLOObjectDetector.extract_event_keyframe_timestamps(
        active_tracks=tracks_small_scene,
        shot_start_sec=0.0,
        shot_end_sec=10.0,
        min_duration_sec=0.8,
        crowd_threshold=5
    )

    print(f"[TEST 1] Canh it nguoi (<= 5 nguoi) trong shot 0.0s - 10.0s:")
    for ev in events_small:
        print(f"  -> Event '{ev['event_type']}' cho vat the '{ev['object_class']}' tai {ev['timestamp_sec']}s (is_crowd: {ev['is_crowd']})")

    # Kiểm tra: Track 3 bị lọc bỏ vì duration 0.3s < 0.8s
    track_ids = [ev.get("track_id") for ev in events_small]
    assert 3 not in track_ids, "Loi: Track 3 co duration 0.3s van bi bat!"
    assert len(events_small) >= 3, "Loi: Khong bat du cac su kien quan trong!"
    print("  -> DAT: Da bat dung cac moc vao/ra cua nguoi va xe, dong thoi loai bo 100% frame nhieu < 0.8s.")

    # 2. Kịch bản 2: Cảnh đám đông (7 người trên khán đài) -> Kích hoạt Crowd Suppression
    tracks_crowd_scene = {
        i: {"class": "person", "max_conf": 0.80, "first_seen": float(i), "last_seen": float(i + 3)}
        for i in range(1, 8) # 7 người
    }

    events_crowd = YOLOObjectDetector.extract_event_keyframe_timestamps(
        active_tracks=tracks_crowd_scene,
        shot_start_sec=0.0,
        shot_end_sec=15.0,
        min_duration_sec=0.8,
        crowd_threshold=5
    )

    print(f"\n[TEST 2] Canh dong nguoi (> 5 nguoi) trong shot 0.0s - 15.0s:")
    for ev in events_crowd:
        print(f"  -> Event '{ev['event_type']}' (is_crowd: {ev['is_crowd']}, unique_person_count: {ev.get('unique_person_count')})")

    assert len(events_crowd) == 1 and events_crowd[0]["is_crowd"] is True, "Loi: Heuristic dam dong chua kich hoat!"
    print("  -> DAT: Da kich hoat thanh cong Heuristic uc che dam dong, tranh bung no keyframe thua.")

    print("=" * 70)
    print("KET QUA: TAT CA CAC BAI TEST OBJECT EVENT KEYFRAMES DEU DAT 100%!")
    print("=" * 70)


if __name__ == "__main__":
    test_event_keyframe_extraction()
