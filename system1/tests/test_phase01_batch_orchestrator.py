from __future__ import annotations

import importlib
import json
import zipfile
from pathlib import Path

import pandas as pd

from system1.artifacts.store import ArtifactStore
from system1.asr import AsrResult
from system1.config import resolve_phase01_config

production = importlib.import_module("system1.phase01.production")
CONFIG_DIR = Path(__file__).resolve().parents[1] / "configs"


class FakeGeminiClient:
    requests: list[str] = []

    def __init__(self, **_kwargs) -> None:
        pass

    def request(self, request):
        self.requests.append(request.request_kind)
        if request.request_kind == "shot_caption":
            return {"caption_vi": "Một cảnh", "caption_en": "A scene"}
        if request.request_kind == "scene_summary":
            return {"summary_vi": "Một cảnh", "summary_en": "A scene"}
        raise AssertionError(request.request_kind)


def test_single_video_production_orchestrator_checkpoints_and_packages(
    tmp_path: Path, monkeypatch
) -> None:
    video_id = "L21_V001"
    release = tmp_path / "output" / "canonical_release_v001"
    (release / "manifests").mkdir(parents=True)
    (release / "tables").mkdir()
    (release / "raw_mapping").mkdir()
    (release / "frame_timeline").mkdir()
    (release / "manifests" / "batch_000.txt").write_text(
        video_id + "\n", encoding="utf-8"
    )
    video = tmp_path / f"{video_id}.mp4"
    metadata = tmp_path / f"{video_id}.json"
    video.write_bytes(b"fixture-video")
    metadata.write_text(json.dumps({"video_id": video_id}), encoding="utf-8")
    pd.DataFrame([{"video_id": video_id}]).to_parquet(
        release / "tables" / "videos.parquet", index=False
    )
    pd.DataFrame([{
        "video_id": video_id,
        "video_local_path": str(video),
        "metadata_local_path": str(metadata),
        "canonical_repo_id": "org/raw",
        "canonical_repo_type": "dataset",
        "canonical_revision": "main",
        "canonical_prefix": "canonical_raw_v001",
        "canonical_video_path": f"raw_videos/{video_id}.mp4",
        "canonical_metadata_path": f"metadata/{video_id}.json",
        "video_size_bytes": video.stat().st_size,
    }]).to_parquet(release / "raw_mapping" / "media_store_manifest.parquet", index=False)
    pd.DataFrame([{
        "video_id": video_id,
        "frame_id": 0,
        "pts_time": 0.0,
        "duration_time": 0.04,
    }]).to_parquet(release / "frame_timeline" / f"{video_id}.parquet", index=False)

    checkpoint_store = ArtifactStore((tmp_path / "checkpoint").resolve())
    checkpoint_store.root.mkdir()
    monkeypatch.setattr(production, "_hf_store", lambda _config: checkpoint_store)
    monkeypatch.setattr(production, "load_transnet_artifact", lambda *_args, **_kwargs: object())

    def detect(_video, *, output_path, **_kwargs):
        payload = {"frame_count": 1, "scenes_inclusive": [[0, 0]]}
        Path(output_path).write_text(json.dumps(payload), encoding="utf-8")
        return payload

    monkeypatch.setattr(production, "detect_shot_scenes", detect)

    def keyframes(*, video_id, output_dir, **_kwargs):
        shot_id = f"{video_id}_SH00000"
        (output_dir / "keyframes").mkdir()
        (output_dir / "thumbnails").mkdir()
        image_name = f"{video_id}_f0000000"
        (output_dir / "keyframes" / f"{image_name}.jpg").write_bytes(b"jpg")
        (output_dir / "thumbnails" / f"{image_name}.webp").write_bytes(b"webp")
        pd.DataFrame([{
            "keyframe_id": f"{video_id}:0", "video_id": video_id,
            "frame_id": 0, "timestamp_sec": 0.0, "shot_id": shot_id,
            "scene_id": None, "keyframe_role": "middle", "quality_score": 10.0,
            "is_representative": True,
            "selection_reason": "middle_within_quality_ratio",
            "keyframe_ref": f"media://keyframes/{video_id}/{image_name}.jpg",
            "thumbnail_ref": f"media://thumbnails/{video_id}/{image_name}.webp",
            "status": "pass",
        }]).to_parquet(output_dir / "keyframes.parquet", index=False)
        (output_dir / "keyframe_diagnostics.jsonl").write_text("", encoding="utf-8")

    monkeypatch.setattr(production, "_build_keyframes", keyframes)
    monkeypatch.setattr(
        production,
        "transcribe_video",
        lambda *_args, **_kwargs: AsrResult("no_audio", [], None, 0, None),
    )
    monkeypatch.setattr(production, "GeminiStructuredClient", FakeGeminiClient)
    resolved = resolve_phase01_config(
        CONFIG_DIR,
        user_settings={
            "batch_id": "batch_000",
            "worker_id": "worker_000",
            "hf_release_repo": "org/release",
        },
        phase00_release_id="canonical_release_v001",
        environment="local",
    )

    report = production.process_production_batch(
        release_dir=release,
        config=resolved,
        scratch_root=tmp_path / "scratch",
        transnet_artifact_dir=tmp_path / "transnet",
        sync_release=False,
    )

    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["counts"]["complete_local"] == 1
    assert payload["videos_failed"] == 0
    assert (release / "artifacts" / "structure" / f"{video_id}_structure.zip").is_file()
    state = checkpoint_store.read_json(
        f"phase01_checkpoints/canonical_release_v001/{video_id}/state.json"
    )
    assert state["stages"]["package"]["status"] == "complete"
    assert state["stages"]["sync"]["status"] == "pending"

    # A second Run All restores every valid stage and makes no semantic API call.
    second_report = production.process_production_batch(
        release_dir=release,
        config=resolved,
        scratch_root=tmp_path / "scratch",
        transnet_artifact_dir=tmp_path / "transnet",
        sync_release=False,
    )
    assert second_report == report
    assert FakeGeminiClient.requests == ["shot_caption", "scene_summary"]

    before_metadata_change = checkpoint_store.read_json(
        f"phase01_checkpoints/canonical_release_v001/{video_id}/state.json"
    )
    metadata.write_text(
        json.dumps({"video_id": video_id, "title": "updated"}), encoding="utf-8"
    )
    production.process_production_batch(
        release_dir=release,
        config=resolved,
        scratch_root=tmp_path / "scratch",
        transnet_artifact_dir=tmp_path / "transnet",
        sync_release=False,
    )
    after_metadata_change = checkpoint_store.read_json(
        f"phase01_checkpoints/canonical_release_v001/{video_id}/state.json"
    )
    assert (
        after_metadata_change["stages"]["shots"]["input_fingerprint"]
        == before_metadata_change["stages"]["shots"]["input_fingerprint"]
    )
    assert (
        after_metadata_change["stages"]["package"]["input_fingerprint"]
        != before_metadata_change["stages"]["package"]["input_fingerprint"]
    )
    assert FakeGeminiClient.requests == ["shot_caption", "scene_summary"]
    artifact = release / "artifacts" / "structure" / f"{video_id}_structure.zip"
    with zipfile.ZipFile(artifact) as archive:
        normalized = json.loads(
            archive.read(f"{video_id}/metadata_normalized.json").decode("utf-8")
        )
    assert normalized["title"] == "updated"
