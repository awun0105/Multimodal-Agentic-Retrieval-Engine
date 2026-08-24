"""
Ground Truth Sampler & Protocol Builder for AIC Embedding Phase 2
==================================================================
Mục tiêu:
Xây dựng tập mẫu Ground Truth phục vụ bài toán đánh giá độ chính xác (Accuracy Benchmark).
Tuân thủ nguyên tắc phân bổ:
- 90% mẫu nằm ở khoảng giữa video: [t_start = 60s, t_end = max(60s, duration - 60s)]
  (nhằm tập trung vào sự kiện thực tế, tránh intro/outro).
- 10% mẫu nằm ở 2 biên [0, 60s] và [t_end, duration] (nhằm kiểm thử tính kháng nhiễu logo/credits).
"""

import os
import sys
import json
import random
from typing import List, Dict, Any, Optional

if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

def sample_keyframes_by_distribution(
    keyframe_list: List[Dict[str, Any]],
    total_samples: int = 1000,
    middle_ratio: float = 0.90,
    intro_cutoff_sec: float = 60.0,
    outro_cutoff_sec: float = 60.0,
    seed: int = 42
) -> List[Dict[str, Any]]:
    """
    Lọc và lấy mẫu danh sách keyframe theo tỷ lệ 90% đoạn giữa / 10% đoạn biên.
    
    Mỗi phần tử trong keyframe_list cần có:
      - video_id: str
      - keyframe_id: str / int
      - timestamp_sec: float
      - duration_sec: float (tổng thời lượng video)
      - image_path: Optional[str]
    """
    random.seed(seed)
    
    middle_pool = []
    edge_pool = []
    
    for kf in keyframe_list:
        ts = float(kf.get("timestamp_sec", 0.0))
        duration = float(kf.get("duration_sec", 120.0))
        
        t_start = min(intro_cutoff_sec, duration * 0.2)
        t_end = max(t_start, duration - outro_cutoff_sec)
        
        if t_start <= ts <= t_end:
            kf_copy = dict(kf)
            kf_copy["is_middle_90"] = True
            middle_pool.append(kf_copy)
        else:
            kf_copy = dict(kf)
            kf_copy["is_middle_90"] = False
            edge_pool.append(kf_copy)
            
    target_middle_count = int(total_samples * middle_ratio)
    target_edge_count = total_samples - target_middle_count
    
    # Lấy mẫu ngẫu nhiên có kiểm soát
    sampled_middle = random.sample(middle_pool, min(target_middle_count, len(middle_pool)))
    sampled_edge = random.sample(edge_pool, min(target_edge_count, len(edge_pool)))
    
    combined = sampled_middle + sampled_edge
    random.shuffle(combined)
    
    print(f"[*] Tổng số keyframe đầu vào: {len(keyframe_list)}")
    print(f"[*] Keyframe đoạn giữa (>60s & <T-60s): {len(middle_pool)} -> Đã chọn: {len(sampled_middle)}")
    print(f"[*] Keyframe đoạn biên (Intro/Credits): {len(edge_pool)} -> Đã chọn: {len(sampled_edge)}")
    print(f"[*] Tổng mẫu Ground Truth xuất ra: {len(combined)} (Tỷ lệ giữa: {len(sampled_middle)/max(1, len(combined))*100:.1f}%)")
    
    return combined

def generate_mock_ground_truth_manifest(
    output_path: str,
    num_samples: int = 20
) -> str:
    """
    Sinh tập manifest mẫu dùng cho việc kiểm thử tính toàn vẹn (Self-test/Debug).
    """
    mock_keyframes = []
    for i in range(1, num_samples + 1):
        vid_id = f"L01_V{((i-1)//5) + 1:03d}"
        dur = 300.0  # 5 phút
        # Sinh timestamp ngẫu nhiên từ 5s đến 295s
        ts = random.uniform(5.0, dur - 5.0)
        
        mock_keyframes.append({
            "video_id": vid_id,
            "keyframe_id": f"{i:05d}",
            "timestamp_sec": round(ts, 2),
            "duration_sec": dur,
            "image_path": f"sample_keyframes/{vid_id}_{i:05d}.jpg",
            "caption_vi": f"Cảnh quay chi tiết người tham gia sự kiện tại video {vid_id} mốc {round(ts)} giây",
            "caption_en": f"Detailed scene of an event participant in video {vid_id} at {round(ts)} seconds"
        })
        
    sampled = sample_keyframes_by_distribution(
        mock_keyframes,
        total_samples=min(10, num_samples),
        middle_ratio=0.90
    )
    
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(sampled, f, ensure_ascii=False, indent=2)
        
    print(f"[+] Đã lưu manifest mẫu thành công tại: {output_path}")
    return output_path

if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd()
    test_out = os.path.join(base_dir, "..", "..", "data", "ground_truth_sample_manifest.json")
    generate_mock_ground_truth_manifest(test_out, num_samples=30)
