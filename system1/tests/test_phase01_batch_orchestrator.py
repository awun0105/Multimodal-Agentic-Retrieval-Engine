from __future__ import annotations

import gc
import importlib
import json
import weakref
import zipfile
from pathlib import Path
from typing import ClassVar

import pandas as pd
import pytest

from system1.artifacts.checkpoint import sha256_file
from system1.artifacts.store import ArtifactStore
from system1.asr import AsrResult
from system1.config import resolve_phase01_config

production = importlib.import_module("system1.phase01.production")
CONFIG_DIR = Path(__file__).resolve().parents[1] / "configs"


@pytest.fixture(autouse=True)
def _stable_available_ram(monkeypatch) -> None:
    monkeypatch.setattr(production, "_available_ram_gb", lambda: 100.0)


class FakeGeminiClient:
    requests: ClassVar[list[str]] = []

    def __init__(self, **_kwargs) -> None:
        pass

    def request(self, request):
        self.requests.append(request.request_kind)
        if request.request_kind == "shot_caption":
            return {"caption_vi": "Một cảnh", "caption_en": "A scene"}
        if request.request_kind == "scene_summary":
            return {"summary_vi": "Một cảnh", "summary_en": "A scene"}
        raise AssertionError(request.request_kind)

    def request_many(self, requests):
        return [self.request(request) for request in requests]


class FakeLocalStructuredClient:
    requests: ClassVar[list[str]] = []

    def __init__(self, provider: str) -> None:
        self.provider = provider
        self.provider_name = provider

    def request(self, request):
        self.requests.append(request.request_kind)
        if request.request_kind == "keyframe_ocr":
            return {
                "full_text": "",
                "ocr_blocks": [],
                "language": "vi",
                "confidence": None,
            }
        if request.request_kind == "shot_caption":
            return {
                "caption_vi": "Một cảnh",
                "caption_en": "A scene",
                "objects_vi": ["cảnh"],
                "objects_en": ["scene"],
                "actions_vi": [],
                "actions_en": [],
                "visible_text_summary_vi": "",
                "visible_text_summary_en": "",
                "scene_type": "unknown",
            }
        if request.request_kind == "scene_summary":
            return {"summary_vi": "Một cảnh", "summary_en": "A scene"}
        raise AssertionError(request.request_kind)

    def request_many(self, requests):
        return [self.request(request) for request in requests]


class ChunkLocalStructuredClient:
    load_counts: ClassVar[dict[str, int]] = {}
    close_counts: ClassVar[dict[str, int]] = {}
    resident: ClassVar[set[str]] = set()
    instances: ClassVar[list[weakref.ReferenceType]] = []

    def __init__(self, provider: str, lifecycle_callback=None) -> None:
        self.provider = provider
        self.provider_name = provider
        self.lifecycle_callback = lifecycle_callback
        self.loaded = False
        self.instances.append(weakref.ref(self))

    @classmethod
    def reset(cls) -> None:
        cls.load_counts = {}
        cls.close_counts = {}
        cls.resident = set()
        cls.instances = []

    def request(self, request):
        if not self.loaded and self.provider in {"qwen_local", "vintern_local"}:
            assert not self.resident
            self.loaded = True
            self.resident.add(self.provider)
            self.load_counts[self.provider] = self.load_counts.get(self.provider, 0) + 1
            if self.lifecycle_callback is not None:
                self.lifecycle_callback(
                    {
                        "status": "loaded",
                        "provider": self.provider,
                        "model": self.provider,
                        "load_seconds": 0.01,
                    }
                )
        if request.request_kind == "keyframe_ocr":
            return {
                "full_text": "",
                "ocr_blocks": [],
                "language": "vi",
                "confidence": None,
            }
        if request.request_kind == "shot_caption":
            return {
                "caption_vi": "Một cảnh",
                "caption_en": "A scene",
                "objects_vi": ["cảnh"],
                "objects_en": ["scene"],
                "actions_vi": [],
                "actions_en": [],
                "visible_text_summary_vi": "",
                "visible_text_summary_en": "",
                "scene_type": "unknown",
            }
        if request.request_kind == "scene_summary":
            return {"summary_vi": "Một cảnh", "summary_en": "A scene"}
        raise AssertionError(request.request_kind)

    def request_many(self, requests):
        return [self.request(request) for request in requests]

    def close(self) -> None:
        if not self.loaded:
            return
        self.resident.remove(self.provider)
        self.loaded = False
        self.close_counts[self.provider] = self.close_counts.get(self.provider, 0) + 1
        if self.lifecycle_callback is not None:
            self.lifecycle_callback(
                {
                    "status": "unloaded",
                    "provider": self.provider,
                    "model": self.provider,
                }
            )


def _configure_batch_fixture(
    tmp_path: Path, monkeypatch, video_ids: list[str]
) -> tuple[Path, ArtifactStore, object]:
    release = tmp_path / "output" / "canonical_release_v001"
    (release / "manifests").mkdir(parents=True)
    (release / "tables").mkdir()
    (release / "raw_mapping").mkdir()
    (release / "frame_timeline").mkdir()
    (release / "manifests" / "batch_000.txt").write_text(
        "\n".join(video_ids) + "\n", encoding="utf-8"
    )
    video_rows: list[dict[str, object]] = []
    media_rows: list[dict[str, object]] = []
    for video_id in video_ids:
        video = tmp_path / f"{video_id}.mp4"
        metadata = tmp_path / f"{video_id}.json"
        video.write_bytes(f"fixture-video-{video_id}".encode())
        metadata.write_text(json.dumps({"video_id": video_id}), encoding="utf-8")
        video_rows.append({"video_id": video_id})
        media_rows.append(
            {
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
            }
        )
        pd.DataFrame(
            [
                {
                    "video_id": video_id,
                    "frame_id": 0,
                    "pts_time": 0.0,
                    "duration_time": 0.04,
                }
            ]
        ).to_parquet(release / "frame_timeline" / f"{video_id}.parquet", index=False)
    pd.DataFrame(video_rows).to_parquet(
        release / "tables" / "videos.parquet", index=False
    )
    pd.DataFrame(media_rows).to_parquet(
        release / "raw_mapping" / "media_store_manifest.parquet", index=False
    )

    checkpoint_store = ArtifactStore((tmp_path / "checkpoint").resolve())
    checkpoint_store.root.mkdir()
    monkeypatch.setattr(
        production, "_hf_store", lambda _config, **_kwargs: checkpoint_store
    )
    monkeypatch.setattr(production, "_scratch_free_gb", lambda _scratch: 100.0)
    monkeypatch.setattr(
        production, "load_transnet_artifact", lambda *_args, **_kwargs: object()
    )

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
        pd.DataFrame(
            [
                {
                    "keyframe_id": f"{video_id}:0",
                    "video_id": video_id,
                    "frame_id": 0,
                    "timestamp_sec": 0.0,
                    "shot_id": shot_id,
                    "scene_id": None,
                    "keyframe_role": "middle",
                    "quality_score": 10.0,
                    "is_representative": True,
                    "selection_reason": "middle_within_quality_ratio",
                    "keyframe_ref": f"media://keyframes/{video_id}/{image_name}.jpg",
                    "thumbnail_ref": f"media://thumbnails/{video_id}/{image_name}.webp",
                    "status": "pass",
                }
            ]
        ).to_parquet(output_dir / "keyframes.parquet", index=False)
        (output_dir / "keyframe_diagnostics.jsonl").write_text("", encoding="utf-8")

    monkeypatch.setattr(production, "_build_keyframes", keyframes)
    monkeypatch.setattr(
        production,
        "transcribe_video",
        lambda *_args, **_kwargs: AsrResult("no_audio", [], None, 0, None),
    )
    monkeypatch.setattr(production, "GeminiStructuredClient", FakeGeminiClient)
    monkeypatch.setattr(
        production,
        "_structured_client_for_model",
        lambda model_config, **kwargs: ChunkLocalStructuredClient(
            str(model_config["provider"]), kwargs.get("lifecycle_callback")
        ),
    )
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
    return release, checkpoint_store, resolved


def test_single_video_production_orchestrator_checkpoints_and_packages(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    FakeGeminiClient.requests = []
    FakeLocalStructuredClient.requests = []
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
    monkeypatch.setattr(
        production, "_hf_store", lambda _config, **_kwargs: checkpoint_store
    )
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
    monkeypatch.setattr(
        production,
        "_structured_client_for_model",
        lambda model_config, **_kwargs: FakeLocalStructuredClient(str(model_config["provider"])),
    )
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
    progress = capsys.readouterr().out
    assert '"event": "video"' in progress
    assert '"event": "stage"' in progress
    assert '"stage": "shots"' in progress
    assert '"scratch_free_gb":' in progress
    assert payload["counts"]["complete_local"] == 1
    assert payload["videos_failed"] == 0
    assert (release / "artifacts" / "structure" / f"{video_id}_structure.zip").is_file()
    state = checkpoint_store.read_json(
        f"phase01_checkpoints/canonical_release_v001/{video_id}/state.json"
    )
    assert state["stages"]["package"]["status"] == "complete"
    assert state["stages"]["sync"]["status"] == "pending"
    assert not (
        tmp_path
        / "scratch"
        / "canonical_release_v001"
        / "batch_000"
        / video_id
    ).exists()

    # A second Run All restores every valid stage and makes no semantic API call.
    monkeypatch.setattr(production, "_available_ram_gb", lambda: 3.0)
    second_report = production.process_production_batch(
        release_dir=release,
        config=resolved,
        scratch_root=tmp_path / "scratch",
        transnet_artifact_dir=tmp_path / "transnet",
        sync_release=False,
    )
    assert second_report == report
    assert FakeLocalStructuredClient.requests == [
        "keyframe_ocr",
        "shot_caption",
        "scene_summary",
    ]
    assert FakeGeminiClient.requests == []

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
    assert FakeLocalStructuredClient.requests == [
        "keyframe_ocr",
        "shot_caption",
        "scene_summary",
    ]
    assert FakeGeminiClient.requests == []
    artifact = release / "artifacts" / "structure" / f"{video_id}_structure.zip"
    with zipfile.ZipFile(artifact) as archive:
        names = set(archive.namelist())
        normalized = json.loads(
            archive.read(f"{video_id}/metadata_normalized.json").decode("utf-8")
        )
    assert f"{video_id}/diagnostics/ocr_status.json" in names
    assert f"{video_id}/ocr_status.json" not in names
    assert normalized["title"] == "updated"


def test_eight_videos_load_each_heavy_model_once_per_chunk(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    video_ids = [f"L21_V{index:03d}" for index in range(1, 9)]
    ChunkLocalStructuredClient.reset()
    FakeGeminiClient.requests = []
    release, checkpoint_store, resolved = _configure_batch_fixture(
        tmp_path, monkeypatch, video_ids
    )

    report = production.process_production_batch(
        release_dir=release,
        config=resolved,
        scratch_root=tmp_path / "scratch",
        transnet_artifact_dir=tmp_path / "transnet",
        sync_release=False,
    )

    payload = json.loads(report.read_text(encoding="utf-8"))
    progress = capsys.readouterr().out
    assert payload["counts"]["complete_local"] == 8
    assert ChunkLocalStructuredClient.load_counts == {
        "vintern_local": 2,
        "qwen_local": 2,
    }
    assert ChunkLocalStructuredClient.close_counts == {
        "vintern_local": 2,
        "qwen_local": 2,
    }
    assert ChunkLocalStructuredClient.resident == set()
    gc.collect()
    assert all(reference() is None for reference in ChunkLocalStructuredClient.instances)
    assert progress.count('"event": "chunk",') == 4
    assert progress.count('"event": "model",') == 10
    assert progress.count('"status": "closed"') == 2
    assert '"chunk_index": 1' in progress
    assert '"chunk_size": 4' in progress
    assert '"elapsed_seconds":' in progress
    assert '"gpu_peak_allocated_gb":' in progress
    assert '"ram_available_gb":' in progress
    assert '"process_rss_gb":' in progress
    for milestone in (
        "chunk_start",
        "after_ocr",
        "after_captions",
        "after_scenes",
        "after_summaries",
        "qwen_unloaded",
        "chunk_end",
    ):
        assert f'"status": "{milestone}"' in progress
    events = [
        json.loads(line.removeprefix("[phase01] "))
        for line in progress.splitlines()
        if line.startswith("[phase01] ")
    ]

    def event_index(**expected):
        return next(
            index
            for index, event in enumerate(events)
            if all(event.get(key) == value for key, value in expected.items())
        )

    assert event_index(event="model", model="qwen_local", status="loaded") < event_index(
        event="stage", stage="scene_summaries", status="complete"
    )
    assert event_index(
        event="stage", stage="scene_summaries", status="complete"
    ) < event_index(event="model", model="qwen_local", status="unloaded")
    assert event_index(event="memory", status="qwen_unloaded") < event_index(
        event="stage", stage="package", status="start"
    )
    for video_id in video_ids:
        artifact = (
            release / "artifacts" / "structure" / f"{video_id}_structure.zip"
        )
        assert artifact.is_file()
        state = checkpoint_store.read_json(
            f"phase01_checkpoints/canonical_release_v001/{video_id}/state.json"
        )
        package_record = state["stages"]["package"]
        assert package_record["status"] == "complete"
        [(remote_name, expected_sha)] = package_record["output_checksums"].items()
        assert Path(remote_name).name == artifact.name
        assert sha256_file(artifact) == expected_sha


def test_interruption_during_second_chunk_resumes_completed_stages(
    tmp_path: Path, monkeypatch
) -> None:
    video_ids = [f"L21_V{index:03d}" for index in range(1, 9)]
    ChunkLocalStructuredClient.reset()
    FakeGeminiClient.requests = []
    release, checkpoint_store, resolved = _configure_batch_fixture(
        tmp_path, monkeypatch, video_ids
    )
    original_build_captions = production._build_captions

    def interrupt_second_chunk(**kwargs):
        if kwargs["video_id"] == video_ids[4]:
            raise KeyboardInterrupt("simulated notebook interruption")
        return original_build_captions(**kwargs)

    monkeypatch.setattr(production, "_build_captions", interrupt_second_chunk)
    with pytest.raises(KeyboardInterrupt, match="simulated notebook interruption"):
        production.process_production_batch(
            release_dir=release,
            config=resolved,
            scratch_root=tmp_path / "scratch",
            transnet_artifact_dir=tmp_path / "transnet",
            sync_release=False,
        )

    interrupted_state = checkpoint_store.read_json(
        f"phase01_checkpoints/canonical_release_v001/{video_ids[4]}/state.json"
    )
    assert interrupted_state["stages"]["ocr"]["status"] == "complete"
    assert interrupted_state["stages"]["shot_captions"]["status"] == "pending"
    for video_id in video_ids[:4]:
        completed_state = checkpoint_store.read_json(
            f"phase01_checkpoints/canonical_release_v001/{video_id}/state.json"
        )
        assert completed_state["stages"]["package"]["status"] == "complete"
    assert ChunkLocalStructuredClient.resident == set()

    monkeypatch.setattr(production, "_build_captions", original_build_captions)
    ChunkLocalStructuredClient.reset()
    report = production.process_production_batch(
        release_dir=release,
        config=resolved,
        scratch_root=tmp_path / "scratch",
        transnet_artifact_dir=tmp_path / "transnet",
        sync_release=False,
    )

    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["counts"]["complete_local"] == 8
    assert ChunkLocalStructuredClient.load_counts == {"qwen_local": 1}
    resumed_state = checkpoint_store.read_json(
        f"phase01_checkpoints/canonical_release_v001/{video_ids[4]}/state.json"
    )
    assert resumed_state["stages"]["shot_captions"]["status"] == "complete"
    assert resumed_state["stages"]["package"]["status"] == "complete"


def test_caption_failure_for_one_video_does_not_block_other_video_checkpoint(
    tmp_path: Path, monkeypatch
) -> None:
    video_ids = ["L21_V001", "L21_V002"]
    ChunkLocalStructuredClient.reset()
    release, checkpoint_store, resolved = _configure_batch_fixture(
        tmp_path, monkeypatch, video_ids
    )
    original_build_captions = production._build_captions

    def fail_first_video(**kwargs):
        if kwargs["video_id"] == video_ids[0]:
            raise RuntimeError("simulated caption failure")
        return original_build_captions(**kwargs)

    monkeypatch.setattr(production, "_build_captions", fail_first_video)
    with pytest.raises(RuntimeError, match="1 failed video"):
        production.process_production_batch(
            release_dir=release,
            config=resolved,
            scratch_root=tmp_path / "scratch",
            transnet_artifact_dir=tmp_path / "transnet",
            sync_release=False,
        )

    failed_state = checkpoint_store.read_json(
        "phase01_checkpoints/canonical_release_v001/L21_V001/state.json"
    )
    completed_state = checkpoint_store.read_json(
        "phase01_checkpoints/canonical_release_v001/L21_V002/state.json"
    )
    assert failed_state["stages"]["shot_captions"]["status"] == "failed_terminal"
    assert {
        stage
        for stage, record in failed_state["stages"].items()
        if record["status"] == "complete"
    } == {"shots", "keyframes", "asr", "ocr"}
    for stage in (
        "shot_transcript_links",
        "scenes",
        "scene_summaries",
        "package",
        "sync",
    ):
        assert failed_state["stages"][stage]["status"] == "pending"
    failed_stage_root = (
        checkpoint_store.root
        / "phase01_checkpoints"
        / "canonical_release_v001"
        / video_ids[0]
        / "stages"
    )
    assert {path.name for path in failed_stage_root.iterdir()} == {
        "shots",
        "keyframes",
        "asr",
        "ocr",
    }
    assert completed_state["stages"]["package"]["status"] == "complete"
    assert ChunkLocalStructuredClient.resident == set()
    report = json.loads(
        (
            release
            / "manifests"
            / "worker_reports"
            / "structure_batch_000_worker_000.json"
        ).read_text(encoding="utf-8")
    )
    assert [video["video_id"] for video in report["videos"]] == video_ids
    assert report["videos"][0]["status"] == "failed_terminal"
    assert report["videos"][1]["status"] == "complete_local"


def test_critical_ram_blocks_heavy_model_load_and_marks_ocr_retryable(
    tmp_path: Path, monkeypatch
) -> None:
    video_id = "L21_V001"
    release, checkpoint_store, resolved = _configure_batch_fixture(
        tmp_path, monkeypatch, [video_id]
    )
    client_factory_calls = 0
    heavy_load_calls = 0

    class GuardedClient:
        def __init__(self, callback) -> None:
            self.callback = callback

        def request_many(self, _requests):
            nonlocal heavy_load_calls
            self.callback("vintern_local")
            heavy_load_calls += 1
            raise AssertionError("heavy model load must not be attempted")

    def client_factory(*_args, **kwargs):
        nonlocal client_factory_calls
        client_factory_calls += 1
        return GuardedClient(kwargs["pre_load_callback"])

    monkeypatch.setattr(production, "_available_ram_gb", lambda: 3.0)
    monkeypatch.setattr(production, "_structured_client_for_model", client_factory)

    with pytest.raises(RuntimeError, match="1 failed video"):
        production.process_production_batch(
            release_dir=release,
            config=resolved,
            scratch_root=tmp_path / "scratch",
            transnet_artifact_dir=tmp_path / "transnet",
            sync_release=False,
        )

    state = checkpoint_store.read_json(
        f"phase01_checkpoints/canonical_release_v001/{video_id}/state.json"
    )
    assert client_factory_calls == 1
    assert heavy_load_calls == 0
    assert state["stages"]["ocr"]["status"] == "failed_retryable"
    assert state["stages"]["ocr"]["error"]["error_type"] == "InsufficientMemoryError"


def test_critical_ram_blocks_asr_before_model_load(
    tmp_path: Path, monkeypatch
) -> None:
    video_id = "L21_V001"
    release, checkpoint_store, resolved = _configure_batch_fixture(
        tmp_path, monkeypatch, [video_id]
    )
    heavy_load_calls = 0
    client_factory_calls = 0

    def guarded_asr(*_args, pre_load_callback, **_kwargs):
        nonlocal heavy_load_calls
        pre_load_callback("nemo")
        heavy_load_calls += 1
        raise AssertionError("NeMo load must not be attempted")

    def client_factory(*_args, **_kwargs):
        nonlocal client_factory_calls
        client_factory_calls += 1
        raise AssertionError("OCR client must not be created after ASR failure")

    monkeypatch.setattr(production, "_available_ram_gb", lambda: 3.0)
    monkeypatch.setattr(production, "transcribe_video", guarded_asr)
    monkeypatch.setattr(production, "_structured_client_for_model", client_factory)

    with pytest.raises(RuntimeError, match="1 failed video"):
        production.process_production_batch(
            release_dir=release,
            config=resolved,
            scratch_root=tmp_path / "scratch",
            transnet_artifact_dir=tmp_path / "transnet",
            sync_release=False,
        )

    state = checkpoint_store.read_json(
        f"phase01_checkpoints/canonical_release_v001/{video_id}/state.json"
    )
    assert heavy_load_calls == 0
    assert client_factory_calls == 0
    assert state["stages"]["asr"]["status"] == "failed_retryable"
    assert state["stages"]["asr"]["error"]["error_type"] == "InsufficientMemoryError"
