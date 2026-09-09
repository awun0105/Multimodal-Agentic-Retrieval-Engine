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
                "speech_evidence_status": "no_speech",
                "speech_evidence_fingerprint": "a" * 64,
                "visual_evidence_fingerprint": "b" * 64,
                "speech_summary_vi": None,
                "speech_summary_en": None,
                "visual_summary_vi": "Một cảnh",
                "visual_summary_en": "One scene",
                "audio_visual_relation": "no_speech",
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
                "vote_count": 2,
                "true_vote_weight": 0.2,
                "false_vote_weight": 1.8,
                "review_route": "primary",
                "consistency_review_triggered": False,
                "consistency_review_round": None,
                "degenerate_review_triggered": False,
                "speech_evidence_reliable": True,
                "speech_near_boundary_continuity": True,
                "speech_shared_segment_crosses_gap": True,
                "speech_shared_segment_ids": ["L21_V001_ASR00000"],
                "speech_inter_word_gap_sec": 0.18,
                "speech_left_word_distance_to_boundary_sec": 0.10,
                "speech_right_word_distance_to_boundary_sec": 0.08,
                "provider": "qwen_local",
                "model_name": "Qwen/Qwen2.5-VL-7B-Instruct",
                "model_version": "revision",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "diagnostics" / "scene_partition_quality.json").write_text(
        json.dumps(
            {
                "status": "pass",
                "degenerate_review_triggered": False,
                "final": {
                    "boundary_density": 0.0,
                    "one_shot_scene_rate": 1.0,
                    "mean_scene_duration_sec": 2.0,
                    "median_scene_duration_sec": 2.0,
                },
            }
        ),
        encoding="utf-8",
    )
    (root / "diagnostics" / "shot_caption_field_provenance.jsonl").write_text(
        json.dumps(
            {
                "shot_id": "L21_V001_SH00000",
                "caption_mode": "representative_only",
                "caption_evidence_fingerprint": "c" * 64,
                "trigger_reasons": [],
                "source_keyframe_ids": ["L21_V001:2"],
                "source_frame_ids": [2],
                "source_timestamps_sec": [0.5],
                "source_keyframe_roles": ["middle"],
                "source_selection_reasons": ["middle_within_quality_ratio"],
                "source_image_sha256s": ["d" * 64],
                "max_visual_change_score": None,
                "max_ocr_change_score": None,
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
    boundary = next(
        row
        for row in first_payload["samples"]
        if row["review_kind"] == "scene_boundary"
    )
    assert boundary["evidence"]["vote_count"] == 2
    assert boundary["evidence"]["partition_status"] == "pass"
    assert boundary["evidence"]["final_mean_scene_duration_sec"] == 2.0
    assert boundary["evidence"]["speech_evidence_reliable"] is True
    assert boundary["evidence"]["speech_near_boundary_continuity"] is True
    assert boundary["evidence"]["speech_shared_segment_crosses_gap"] is True
    assert boundary["evidence"]["speech_inter_word_gap_sec"] == 0.18
    assert "reason" not in boundary["evidence"]
    caption = next(
        row
        for row in first_payload["samples"]
        if row["review_kind"] == "shot_caption"
    )
    assert caption["evidence"]["caption_mode"] == "representative_only"
    assert caption["evidence"]["source_keyframe_ids"] == ["L21_V001:2"]
    assert caption["evidence"]["source_keyframe_refs"] == [
        "media://keyframes/L21_V001/L21_V001_f0000002.jpg"
    ]
    assert caption["evidence"]["caption_evidence_fingerprint"] == "c" * 64
    summary = next(
        row
        for row in first_payload["samples"]
        if row["review_kind"] == "scene_summary"
    )
    assert summary["evidence"]["speech_evidence_status"] == "no_speech"
    assert summary["evidence"]["speech_summary_vi"] is None
    assert summary["evidence"]["visual_summary_vi"] == "Một cảnh"
    assert summary["evidence"]["audio_visual_relation"] == "no_speech"
    assert summary["evidence"]["summary_vi"] == "Một cảnh"
    assert summary["evidence"]["speech_evidence_fingerprint"] == "a" * 64
    assert summary["evidence"]["visual_evidence_fingerprint"] == "b" * 64
