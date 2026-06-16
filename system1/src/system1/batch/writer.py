from __future__ import annotations

import csv
from pathlib import Path


def write_batches(release_dir: Path, pairs: list[dict[str, str]]) -> None:
    manifest_path = release_dir / "manifests" / "batch_manifest.csv"
    with manifest_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["batch_id", "video_id"])
        writer.writeheader()
        for pair in pairs:
            writer.writerow({"batch_id": "batch_000", "video_id": pair["video_id"]})
    (release_dir / "manifests" / "batch_000.txt").write_text("".join(f"{pair['video_id']}\n" for pair in pairs), encoding="utf-8")
