from __future__ import annotations

import csv
import heapq
import os
import tempfile
from pathlib import Path

import pandas as pd

from system1.release.types import release_root


def write_batches(release_dir: Path, videos: list[dict[str, object]], num_batches: int = 1) -> list[Path]:
    if num_batches < 1:
        raise ValueError("num_batches must be >= 1")
    if not videos:
        raise ValueError("cannot assign batches: videos table is empty")
    manifests_dir = release_dir / "manifests"
    manifests_dir.mkdir(parents=True, exist_ok=True)
    effective_num_batches = min(num_batches, len(videos))
    assignments = _assign_cost_aware(videos, effective_num_batches)
    manifest_path = manifests_dir / "batch_manifest.csv"
    fieldnames = [
        "batch_id",
        "video_id",
        "estimated_compute_cost",
        "assigned_worker",
        "status",
        "structure_artifact_path",
        "feature_artifact_path",
        "error_note",
    ]
    batch_ids = sorted({str(row["batch_id"]) for row in assignments})
    with tempfile.TemporaryDirectory(prefix=".batch_assignment_", dir=manifests_dir) as temp_dir:
        temp_root = Path(temp_dir)
        staged_manifest = temp_root / manifest_path.name
        with staged_manifest.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(assignments)
        for batch_id in batch_ids:
            batch_video_ids = [str(row["video_id"]) for row in assignments if row["batch_id"] == batch_id]
            (temp_root / f"{batch_id}.txt").write_text(
                "".join(f"{video_id}\n" for video_id in batch_video_ids),
                encoding="utf-8",
            )

        os.replace(staged_manifest, manifest_path)
        generated_names = {f"{batch_id}.txt" for batch_id in batch_ids}
        for batch_id in batch_ids:
            os.replace(temp_root / f"{batch_id}.txt", manifests_dir / f"{batch_id}.txt")
        for stale_path in manifests_dir.glob("batch_*.txt"):
            if stale_path.name not in generated_names:
                stale_path.unlink()

    batch_paths = [manifests_dir / f"{batch_id}.txt" for batch_id in batch_ids]
    return batch_paths


def assign_batches(
    output_dir: Path | str,
    *,
    num_batches: int = 1,
) -> Path:
    if num_batches < 1:
        raise ValueError("num_batches must be >= 1")
    release_dir = release_root(output_dir)
    videos_path = release_dir / "tables" / "videos.parquet"
    if not videos_path.exists():
        raise FileNotFoundError(f"missing ingestion output: {videos_path}")
    videos_df = pd.read_parquet(videos_path).sort_values("video_id")
    videos = videos_df.to_dict("records")
    batch_paths = write_batches(release_dir, videos, num_batches=num_batches)
    return batch_paths[0]


def _assign_cost_aware(videos: list[dict[str, object]], num_batches: int) -> list[dict[str, object]]:
    # --- TỐI ƯU GIẢI THUẬT: Sử dụng cấu trúc dữ liệu Min-Heap thay thế vòng lặp min() tuyến tính ---
    # Cấu trúc phần tử trong heap: (tổng_chi_phí_hiện_tại_của_bucket, chỉ_mục_bucket)
    heap = [(0.0, idx) for idx in range(num_batches)]
    heapq.heapify(heap)

    rows: list[dict[str, object]] = []

    # Kỹ thuật Heuristic: Luôn ưu tiên xử lý video nặng trước (giảm dần theo cost) để tối ưu phân bổ tải song song
    for video in sorted(videos, key=lambda item: (-_cost(item), str(item["video_id"]))):
        # Lấy nhanh Worker có tổng chi phí thấp nhất (nhàn rỗi nhất) tại thời điểm hiện tại chỉ mất O(1)
        current_cost, batch_index = heapq.heappop(heap)

        batch_id = f"batch_{batch_index:03d}"
        worker_id = f"worker_{batch_index:03d}"
        cost = _cost(video)

        # Tích lũy chi phí cho Worker và đẩy ngược lại vào cây Heap trong O(log M)
        heapq.heappush(heap, (current_cost + cost, batch_index))

        rows.append(
            {
                "batch_id": batch_id,
                "video_id": str(video["video_id"]),
                "estimated_compute_cost": cost,
                "assigned_worker": worker_id,
                "status": "pending",
                "structure_artifact_path": f"artifacts/structure/{video['video_id']}_structure.zip",
                "feature_artifact_path": f"artifacts/features/{video['video_id']}_features.zip",
                "error_note": "",
            }
        )
    return sorted(rows, key=lambda row: (row["batch_id"], row["video_id"]))


def _cost(video: dict[str, object]) -> float:
    for key in ("estimated_compute_cost", "duration_seconds"):
        value = video.get(key)
        if value not in (None, ""):
            return float(value)
    return 1.0
