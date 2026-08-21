#!/usr/bin/env python3
"""Build TRAKE ground truth from consecutive keyframes in the same video."""

import json
import random
import sqlite3
from pathlib import Path
from typing import TypedDict

import numpy as np

# Fixed seed for reproducibility
random.seed(42)
np.random.seed(42)

DB_PATH = Path("D:/AIC/aic25-b1-v1/metadata/runtime.sqlite")
EMBEDDINGS_PATH = Path("D:/AIC/aic25-b1-v1/index/embeddings.f16.npy")
OUTPUT_PATH = Path("D:/AIC/aic25-b1-v1/reports/trake-benchmark.json")

class BenchmarkItem(TypedDict):
    """One test case: 3 keyframes (positive) or 2+1 distractor (negative)."""
    query_vector_ids: list[int]  # indices into embeddings.f16.npy
    expected_video_id: str
    category: str  # "positive" (3 from same video) or "distractor" (2 from A, 1 from B)

def load_data():
    """Load metadata and embeddings."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    # Load keyframes
    cur.execute("""
        SELECT keyframe_id, vector_id, video_id, keyframe_no 
        FROM keyframes 
        ORDER BY video_id, keyframe_no
    """)
    keyframes = cur.fetchall()
    print(f"Loaded {len(keyframes)} keyframes")
    
    # Load embeddings
    emb = np.load(EMBEDDINGS_PATH, allow_pickle=False)
    emb = emb.astype(np.float32)  # Convert from float16
    print(f"Loaded embeddings shape: {emb.shape}")
    
    # Group keyframes by video
    videos_kfs = {}
    for kf in keyframes:
        vid = kf['video_id']
        if vid not in videos_kfs:
            videos_kfs[vid] = []
        videos_kfs[vid].append({
            'keyframe_id': kf['keyframe_id'],
            'vector_id': kf['vector_id'],
            'keyframe_no': kf['keyframe_no']
        })
    
    conn.close()
    return videos_kfs, emb

def build_benchmark(videos_kfs: dict, embeddings: np.ndarray) -> list[BenchmarkItem]:
    """Build benchmark with positive (3 consecutive) and distractor (2+1 from different videos) cases."""
    benchmark = []
    
    # Filter videos with at least 10 keyframes for easier spacing
    valid_videos = {vid: kfs for vid, kfs in videos_kfs.items() if len(kfs) >= 10}
    print(f"Videos with >=10 keyframes: {len(valid_videos)}")
    
    video_ids = list(valid_videos.keys())
    n_positive = 30
    n_distractor = 30
    
    # Positive cases: 3 consecutive keyframes from same video
    for _ in range(n_positive):
        vid = random.choice(video_ids)
        kfs = valid_videos[vid]
        # Pick 3 keyframes with spacing (not necessarily consecutive, but from same video)
        start_idx = random.randint(0, len(kfs) - 3)
        indices = [start_idx, start_idx + 1, start_idx + 2]
        
        query_vector_ids = [kfs[i]['vector_id'] for i in indices]
        benchmark.append(BenchmarkItem(
            query_vector_ids=query_vector_ids,
            expected_video_id=vid,
            category="positive"
        ))
    
    # Distractor cases: 2 from video A, 1 from video B (simulates wrong scooping)
    for _ in range(n_distractor):
        vid_a, vid_b = random.sample(video_ids, 2)
        kfs_a = valid_videos[vid_a]
        kfs_b = valid_videos[vid_b]
        
        # 2 keyframes from A
        start_a = random.randint(0, len(kfs_a) - 2)
        idx_a1, idx_a2 = start_a, start_a + 1
        
        # 1 keyframe from B (the "intruder")
        idx_b = random.randint(0, len(kfs_b) - 1)
        
        query_vector_ids = [
            kfs_a[idx_a1]['vector_id'],
            kfs_a[idx_a2]['vector_id'],
            kfs_b[idx_b]['vector_id']
        ]
        
        # The "expected" is A, but query contains a scooping error from B
        # Algorithm should rank A lower because it only matches 2/3 events
        benchmark.append(BenchmarkItem(
            query_vector_ids=query_vector_ids,
            expected_video_id=vid_a,
            category="distractor"
        ))
    
    return benchmark

def main():
    print("Building TRAKE benchmark...")
    videos_kfs, embeddings = load_data()
    benchmark = build_benchmark(videos_kfs, embeddings)
    
    # Save benchmark
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, 'w') as f:
        json.dump(benchmark, f, indent=2)
    
    print(f"Benchmark saved to {OUTPUT_PATH}")
    print(f"  Positive cases: {sum(1 for x in benchmark if x['category'] == 'positive')}")
    print(f"  Distractor cases: {sum(1 for x in benchmark if x['category'] == 'distractor')}")

if __name__ == '__main__':
    main()
