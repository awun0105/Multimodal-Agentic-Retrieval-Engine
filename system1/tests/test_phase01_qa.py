from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pandas as pd

from system1.phase01.qa import write_manual_review_report


def test_manual_review_report_is_deterministic_and_stratified(tmp_path: Path) -> None:
    artifact = tmp_path / "L21_V001_structure.zip"
    root = tmp_path / "payload" / "L21_V001"
    (root / "diagnostics").mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "keyframe_id": "L21_V001:2",
                "video_id": "L21_V001",
                "frame_id": 2,
                "shot_id": "L21_V001_SH00000",
                "is_representative": True,
                "keyframe_ref": "media://keyframes/L21_V001/L21_V001_f0000002.jpg",
                "quality_score": 12.0,
            }
        ]
    ).to_parquet(root / "keyframes.parquet", index=False)
    pd.DataFrame(
        [
            {
                "shot_id": "L21_V001_SH00000",
                "caption_vi": "Một người",
                "caption_en": "A person",
            }
        ]
    ).to_parquet(root / "shot_captions.parquet", index=False)
    pd.DataFrame(
        [
            {
                "scene_id": "L21_V001_SC00000",
                "scene_index": 0,
                "start_sec": 0.0,
                "end_sec": 2.0,
            }
        ]
    ).to_parquet(root / "scenes.parquet", index=False)
    pd.DataFrame(
        [
            {
                "scene_id": "L21_V001_SC00000",
                "summary_vi": "Một cảnh",
                "summary_en": "One scene",
            }
        ]
    ).to_parquet(root / "scene_summaries.parquet", index=False)
    (root / "diagnostics" / "scene_boundary_diagnostics.jsonl").write_text(
        json.dumps(
            {
                "after_shot_id": "L21_V001_SH00000",
                "is_boundary": False,
                "primary_boundary_score": 0.1,
                "review_route": "primary",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    with zipfile.ZipFile(artifact, "w") as archive:
        for path in root.rglob("*"):
            if path.is_file():
                archive.write(path, f"L21_V001/{path.relative_to(root)}")

    first = write_manual_review_report(
        release_dir=tmp_path / "release",
        batch_id="batch_000",
        worker_id="worker_000",
        video_results=[{"status": "complete", "artifact": str(artifact)}],
        sample_size=12,
    )
    first_payload = json.loads(first.read_text(encoding="utf-8"))
    second = write_manual_review_report(
        release_dir=tmp_path / "release",
        batch_id="batch_000",
        worker_id="worker_000",
        video_results=[{"status": "complete", "artifact": str(artifact)}],
        sample_size=12,
    )
    second_payload = json.loads(second.read_text(encoding="utf-8"))
    assert {row["review_kind"] for row in first_payload["samples"]} == {
        "shot_caption",
        "scene_boundary",
        "scene_summary",
    }
    assert first_payload["sample_size_actual"] == 3
    assert first_payload["samples"] == second_payload["samples"]
