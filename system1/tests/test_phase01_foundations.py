from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from system1.artifacts.checkpoint import sha256_file
from system1.artifacts.store import ArtifactStore
from system1.config import resolve_phase01_config
from system1.phase01.checkpoint import (
    CheckpointManager,
    compute_fingerprint,
    downstream_stages,
)
from system1.phase01.phase00 import (
    Phase00Candidate,
    discover_phase00_candidates,
    resolve_phase00_release,
)
from system1.phase01.preflight import (
    RuntimePreflightResult,
    run_phase01_preflight,
    run_phase01_storage_preflight,
)
from system1.phase01.runner import _restore_phase00_if_needed

CONFIG_DIR = Path(__file__).resolve().parents[1] / "configs"


def candidate(release_id: str, timestamp: str | None) -> Phase00Candidate:
    completed_at = datetime.fromisoformat(timestamp.replace("Z", "+00:00")) if timestamp else None
    return Phase00Candidate(
        release_id=release_id,
        completed_at=completed_at,
        manifest_path=f"{release_id}/phase00_ingestion/reports/phase00_sync_manifest.json",
        manifest={"release_id": release_id, "status": "complete", "completed_at": timestamp},
    )


def test_phase00_auto_resolve_uses_unique_latest_completed_timestamp() -> None:
    selected = resolve_phase00_release(
        [
            candidate("canonical_release_v001", "2026-08-01T00:00:00Z"),
            candidate("canonical_release_v002", "2026-08-02T00:00:00Z"),
        ]
    )
    assert selected.release_id == "canonical_release_v002"
    assert selected.completed_at == datetime(2026, 8, 2, tzinfo=timezone.utc)


def test_phase00_override_allows_legacy_complete_manifest_without_timestamp() -> None:
    selected = resolve_phase00_release(
        [candidate("canonical_release_v001", None)],
        release_id_override="canonical_release_v001",
    )
    assert selected.release_id == "canonical_release_v001"


@pytest.mark.parametrize(
    "candidates,match",
    [
        ([candidate("a", None)], "completed_at is missing"),
        (
            [
                candidate("a", "2026-08-01T00:00:00Z"),
                candidate("b", "2026-08-01T00:00:00Z"),
            ],
            "share the latest",
        ),
    ],
)
def test_phase00_auto_resolve_rejects_ambiguous_candidates(
    candidates: list[Phase00Candidate], match: str
) -> None:
    with pytest.raises(ValueError, match=match):
        resolve_phase00_release(candidates)


def test_phase00_discovery_accepts_only_complete_matching_manifests(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    for release_id, status in (("canonical_release_v001", "complete"), ("draft", "running")):
        store.write_json(
            f"{release_id}/phase00_ingestion/reports/phase00_sync_manifest.json",
            {
                "release_id": release_id,
                "status": status,
                "completed_at": "2026-08-01T00:00:00Z",
            },
        )
    assert [item.release_id for item in discover_phase00_candidates(store)] == [
        "canonical_release_v001"
    ]


def test_storage_preflight_accepts_writable_public_checkpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    objects: dict[str, dict] = {}

    class FakeApi:
        def __init__(self, token=None) -> None:
            assert token == "token"

        def repo_info(self, **_kwargs):
            return type("RepoInfo", (), {"private": False})()

    class FakeStore:
        def __init__(self, **kwargs) -> None:
            assert kwargs["cache_dir"] == "/tmp/phase01-test-cache"

        def write_json(self, relative_path, payload):
            objects[str(relative_path)] = payload

        def read_json(self, relative_path):
            return objects[str(relative_path)]

    monkeypatch.setenv("HF_TOKEN", "token")
    monkeypatch.setattr("system1.phase01.preflight.HfApi", FakeApi)
    monkeypatch.setattr(
        "system1.phase01.preflight.HuggingFaceDatasetArtifactStore", FakeStore
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

    run_phase01_storage_preflight(
        resolved, cache_dir="/tmp/phase01-test-cache"
    )

    assert len(objects) == 1


def test_full_preflight_reuses_runtime_result_after_fixture_exists(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    release = tmp_path / "canonical_release_v001"
    (release / "tables").mkdir(parents=True)
    (release / "raw_mapping").mkdir()
    (release / "manifests").mkdir()
    (release / "frame_timeline").mkdir()
    (release / "manifests" / "batch_000.txt").write_text(
        "L30_V040\n", encoding="utf-8"
    )
    pd.DataFrame(
        [{"video_id": "L30_V040", "frame_timeline_ref": "frame_timeline/L30_V040.parquet"}]
    ).to_parquet(release / "tables" / "videos.parquet", index=False)
    pd.DataFrame(
        [
            {
                "video_id": "L30_V040",
                "canonical_repo_id": "org/raw",
                "canonical_repo_type": "dataset",
                "canonical_revision": "main",
                "canonical_prefix": "canonical_raw_v001",
                "canonical_video_path": "raw_videos/L30_V040.mp4",
                "canonical_metadata_path": "metadata/L30_V040.json",
            }
        ]
    ).to_parquet(
        release / "raw_mapping" / "media_store_manifest.parquet", index=False
    )
    pd.DataFrame(
        [{"video_id": "L30_V040", "frame_id": 0, "pts_time": 0.0}]
    ).to_parquet(release / "frame_timeline" / "L30_V040.parquet", index=False)
    resolved = resolve_phase01_config(
        CONFIG_DIR,
        user_settings={"batch_id": "batch_000", "worker_id": "worker_000"},
        phase00_release_id="canonical_release_v001",
        environment="local",
    )
    runtime = RuntimePreflightResult(
        environment="local",
        release_id="canonical_release_v001",
        batch_id="batch_000",
        cuda_available=True,
        scratch_free_gb=100.0,
        model_cache_free_gb=100.0,
        versions={"python": "3.13.0"},
    )
    monkeypatch.setattr("system1.phase01.preflight._validate_prompt_files", lambda *_: None)
    monkeypatch.setattr("system1.phase01.preflight.load_transnet_artifact", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(
        "system1.phase01.preflight.run_phase01_runtime_preflight",
        lambda *_args, **_kwargs: pytest.fail("runtime preflight ran twice"),
    )

    result = run_phase01_preflight(
        resolved,
        release_dir=release,
        transnet_artifact_dir=tmp_path / "transnet",
        scratch_root=tmp_path / "scratch",
        validate_remote=False,
        runtime_result=runtime,
    )

    assert result.versions == {"python": "3.13.0"}


def test_phase00_restore_downloads_only_the_selected_batch_timelines(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    release_id = "canonical_release_v001"
    remote_root = tmp_path / "remote"
    store = ArtifactStore(remote_root)
    phase_root = remote_root / release_id / "phase00_ingestion"
    (phase_root / "tables").mkdir(parents=True)
    (phase_root / "raw_mapping").mkdir(parents=True)
    (phase_root / "manifests").mkdir(parents=True)
    (phase_root / "frame_timeline").mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "video_id": "L21_V001",
                "frame_timeline_ref": "frame_timeline/L21_V001.parquet",
            },
            {
                "video_id": "L21_V002",
                "frame_timeline_ref": "frame_timeline/L21_V002.parquet",
            },
        ]
    ).to_parquet(phase_root / "tables" / "videos.parquet", index=False)
    pd.DataFrame([{"video_id": "L21_V001"}]).to_parquet(
        phase_root / "raw_mapping" / "media_store_manifest.parquet", index=False
    )
    (phase_root / "manifests" / "batch_000.txt").write_text(
        "L21_V001\n", encoding="utf-8"
    )
    for video_id in ("L21_V001", "L21_V002"):
        pd.DataFrame([{"frame_id": 0, "pts_time": 0.0}]).to_parquet(
            phase_root / "frame_timeline" / f"{video_id}.parquet", index=False
        )
    remote_files = [path for path in phase_root.rglob("*") if path.is_file()]
    selected_manifest = {
        "release_id": release_id,
        "status": "complete",
        "completed_at": "2026-08-16T00:00:00Z",
        "files": [
            {
                "relative_path": path.relative_to(phase_root).as_posix(),
                "sha256": sha256_file(path),
            }
            for path in remote_files
        ],
    }
    monkeypatch.setattr(
        "system1.phase01.runner._hf_store", lambda _storage, **_kwargs: store
    )

    output = tmp_path / "output"
    _restore_phase00_if_needed(
        output_root=output,
        release_id=release_id,
        batch_id="batch_000",
        storage={"repo_id": "unused"},
        selected_manifest=selected_manifest,
    )

    release = output / release_id
    selected = release / "frame_timeline" / "L21_V001.parquet"
    assert selected.is_file()
    assert not (release / "frame_timeline" / "L21_V002.parquet").exists()
    selected.write_bytes(b"corrupt")
    _restore_phase00_if_needed(
        output_root=output,
        release_id=release_id,
        batch_id="batch_000",
        storage={"repo_id": "unused"},
        selected_manifest=selected_manifest,
    )
    assert sha256_file(selected) == sha256_file(
        phase_root / "frame_timeline" / "L21_V001.parquet"
    )


def stage_hashes() -> dict[str, str]:
    stages = (
        "shots",
        "keyframes",
        "asr",
        "ocr",
        "shot_captions",
        "shot_transcript_links",
        "scenes",
        "scene_transcript_links",
        "scene_summaries",
        "package",
        "sync",
    )
    return {stage: compute_fingerprint(stage) for stage in stages}


def manager(tmp_path: Path) -> CheckpointManager:
    return CheckpointManager(
        ArtifactStore(tmp_path / "persistent"),
        release_id="canonical_release_v001",
        video_id="L21_V001",
        config_hash=compute_fingerprint("full"),
        stage_config_hashes=stage_hashes(),
    )


def test_checkpoint_promotes_outputs_before_complete_state(tmp_path: Path) -> None:
    checkpoint = manager(tmp_path)
    output = tmp_path / "shots.parquet"
    output.write_bytes(b"shot-data")
    fingerprint = compute_fingerprint("video", "timeline")

    checkpoint.promote_stage(
        "shots",
        input_fingerprint=fingerprint,
        outputs=[output],
        model={"model_id": "TransNetV2", "model_revision": "abc"},
        schema_version="shots_v1",
    )

    state = checkpoint.load_state()
    assert state["stages"]["shots"]["status"] == "complete"
    assert checkpoint.is_reusable("shots", input_fingerprint=fingerprint)
    restored = checkpoint.restore_stage("shots", tmp_path / "restore")
    assert restored[0].read_bytes() == b"shot-data"


def test_checkpoint_v1_migrates_to_v2_without_invalidating_upstream(
    tmp_path: Path,
) -> None:
    checkpoint = manager(tmp_path)
    output = tmp_path / "shots.parquet"
    output.write_bytes(b"shot-data")
    fingerprint = compute_fingerprint("video", "timeline")
    checkpoint.promote_stage(
        "shots",
        input_fingerprint=fingerprint,
        outputs=[output],
        schema_version="shots_v1",
    )
    old_state = checkpoint.store.read_json(checkpoint.state_path)
    shot_record = old_state["stages"]["shots"]
    for stage, record in old_state["stages"].items():
        record.update(
            {
                "status": "complete",
                "input_fingerprint": fingerprint,
                "config_hash": checkpoint.stage_config_hashes[stage],
                "schema_version": f"{stage}_legacy",
                "output_checksums": dict(shot_record["output_checksums"]),
                "completed_at": shot_record["completed_at"],
            }
        )
    old_state["status"] = "complete"
    old_state["schema_version"] = "phase01_checkpoint_state_v1"
    old_state["stages"].pop("scene_transcript_links")
    checkpoint.store.write_json(checkpoint.state_path, old_state)

    restored = manager(tmp_path)
    migrated = restored.load_state()

    assert migrated["schema_version"] == "phase01_checkpoint_state_v2"
    assert migrated["status"] == "running"
    assert migrated["stages"]["shots"]["status"] == "complete"
    assert migrated["stages"]["scene_transcript_links"]["status"] == "pending"
    assert restored.is_reusable(
        "shots", input_fingerprint=fingerprint, restore_dir=tmp_path / "restore"
    )


def test_scene_transcript_links_checkpoint_restores_independently(
    tmp_path: Path,
) -> None:
    checkpoint = manager(tmp_path)
    output = tmp_path / "scene_transcript_links.parquet"
    output.write_bytes(b"links")
    fingerprint = compute_fingerprint("scenes", "asr")
    checkpoint.promote_stage(
        "scene_transcript_links",
        input_fingerprint=fingerprint,
        outputs=[output],
        schema_version="scene_transcript_links_v2",
    )

    restored_dir = tmp_path / "restored-links"
    assert checkpoint.is_reusable(
        "scene_transcript_links",
        input_fingerprint=fingerprint,
        restore_dir=restored_dir,
    )
    assert (restored_dir / output.name).read_bytes() == b"links"


def test_checkpoint_groups_stage_outputs_into_one_backend_upload(tmp_path: Path) -> None:
    class RecordingStore:
        def __init__(self, root: Path) -> None:
            self.delegate = ArtifactStore(root)
            self.upload_batches: list[list[tuple[Path, str | Path]]] = []

        def __getattr__(self, name: str):
            return getattr(self.delegate, name)

        def upload_files(self, files, *, commit_message: str, num_threads: int = 2):
            batch = list(files)
            self.upload_batches.append(batch)
            return self.delegate.upload_files(
                batch,
                commit_message=commit_message,
                num_threads=num_threads,
            )

    store = RecordingStore(tmp_path / "persistent")
    checkpoint = CheckpointManager(
        store,
        release_id="canonical_release_v001",
        video_id="L21_V001",
        config_hash=compute_fingerprint("full"),
        stage_config_hashes=stage_hashes(),
    )
    shots = tmp_path / "shots.parquet"
    predictions = tmp_path / "transnet_predictions.json"
    shots.write_bytes(b"shots")
    predictions.write_bytes(b"predictions")

    checkpoint.promote_stage(
        "shots",
        input_fingerprint=compute_fingerprint("source"),
        outputs=[shots, predictions],
        schema_version="shots_v1",
    )

    assert len(store.upload_batches) == 1
    assert [source.name for source, _remote in store.upload_batches[0]] == [
        "shots.parquet",
        "transnet_predictions.json",
        "state.json",
    ]
    assert str(store.upload_batches[0][-1][1]).endswith(
        "phase01_checkpoints/canonical_release_v001/L21_V001/state.json"
    )


def test_failure_diagnostics_persist_without_completing_stage(tmp_path: Path) -> None:
    checkpoint = manager(tmp_path)
    quality = tmp_path / "scene_partition_quality.json"
    boundaries = tmp_path / "scene_boundary_diagnostics.jsonl"
    quality.write_text('{"status":"failed_quality_gate"}\n', encoding="utf-8")
    boundaries.write_text('{"gap_index":0}\n', encoding="utf-8")

    diagnostics_ref = checkpoint.persist_failure_diagnostics(
        "scenes",
        input_fingerprint="f" * 64,
        outputs=[quality, boundaries],
    )

    persistent = tmp_path / "persistent" / diagnostics_ref
    assert (persistent / quality.name).read_bytes() == quality.read_bytes()
    assert (persistent / boundaries.name).read_bytes() == boundaries.read_bytes()
    assert "/failures/scenes/" in diagnostics_ref
    checkpoint.mark_failed(
        "scenes",
        input_fingerprint="f" * 64,
        retryable=False,
        error={
            "message": "manual review required",
            "details": {"diagnostics_ref": diagnostics_ref},
        },
    )
    scene_state = checkpoint.load_state()["stages"]["scenes"]
    assert scene_state["status"] == "failed_terminal"
    assert scene_state["output_checksums"] == {}
    assert scene_state["error"]["details"]["diagnostics_ref"] == diagnostics_ref


def test_corrupt_checkpoint_output_is_not_reusable(tmp_path: Path) -> None:
    checkpoint = manager(tmp_path)
    output = tmp_path / "shots.parquet"
    output.write_bytes(b"valid")
    fingerprint = compute_fingerprint("input")
    record = checkpoint.promote_stage(
        "shots",
        input_fingerprint=fingerprint,
        outputs=[output],
        schema_version="shots_v1",
    )
    remote_path = next(iter(record["output_checksums"]))
    (tmp_path / "persistent" / remote_path).write_bytes(b"corrupt")
    assert checkpoint.is_reusable("shots", input_fingerprint=fingerprint) is False
    assert checkpoint.load_state()["stages"]["shots"]["status"] == "invalidated"


def test_missing_checkpoint_output_invalidates_complete_state(tmp_path: Path) -> None:
    checkpoint = manager(tmp_path)
    output = tmp_path / "shots.parquet"
    output.write_bytes(b"valid")
    fingerprint = compute_fingerprint("input")
    record = checkpoint.promote_stage(
        "shots",
        input_fingerprint=fingerprint,
        outputs=[output],
        schema_version="shots_v1",
    )
    remote_path = next(iter(record["output_checksums"]))
    (tmp_path / "persistent" / remote_path).unlink()

    assert checkpoint.is_reusable("shots", input_fingerprint=fingerprint) is False
    state = checkpoint.load_state()
    assert state["stages"]["shots"]["status"] == "invalidated"
    assert state["stages"]["shots"]["output_checksums"] == {}


def test_changed_input_invalidates_complete_stage_and_only_its_downstream(
    tmp_path: Path,
) -> None:
    checkpoint = manager(tmp_path)
    output = tmp_path / "shots.parquet"
    output.write_bytes(b"valid")
    checkpoint.promote_stage(
        "shots",
        input_fingerprint=compute_fingerprint("old-input"),
        outputs=[output],
        schema_version="shots_v1",
    )

    assert not checkpoint.is_reusable(
        "shots", input_fingerprint=compute_fingerprint("new-input")
    )
    state = checkpoint.load_state()
    assert state["stages"]["shots"]["status"] == "invalidated"
    assert state["stages"]["keyframes"]["status"] == "pending"
    assert state["stages"]["asr"]["status"] == "pending"


def test_promoting_changed_upstream_invalidates_only_downstream(tmp_path: Path) -> None:
    checkpoint = manager(tmp_path)
    output = tmp_path / "out.parquet"
    output.write_bytes(b"data")
    checkpoint.promote_stage(
        "asr",
        input_fingerprint=compute_fingerprint("asr-v1"),
        outputs=[output],
        schema_version="asr_segments_v1",
    )
    assert "shots" not in downstream_stages("asr")
    assert set(downstream_stages("asr")) == {
            "shot_transcript_links",
            "scenes",
            "scene_transcript_links",
            "scene_summaries",
        "package",
        "sync",
    }


def test_failed_stage_invalidates_previously_complete_downstream(tmp_path: Path) -> None:
    checkpoint = manager(tmp_path)
    output = tmp_path / "out.parquet"
    output.write_bytes(b"data")
    checkpoint.promote_stage(
        "package",
        input_fingerprint=compute_fingerprint("package"),
        outputs=[output],
        schema_version="package_v1",
    )
    checkpoint.mark_failed(
        "shots",
        input_fingerprint=compute_fingerprint("changed-source"),
        retryable=True,
        error={"message": "source download failed"},
    )
    state = checkpoint.load_state()
    assert state["stages"]["shots"]["status"] == "failed_retryable"
    assert state["stages"]["package"]["status"] == "invalidated"


def test_checkpoint_state_never_contains_secrets(tmp_path: Path) -> None:
    checkpoint = manager(tmp_path)
    state = checkpoint.load_state()
    serialized = json.dumps(state)
    assert "HF_TOKEN" not in serialized
    assert "GEMINI_API_KEY" not in serialized


def test_stage_output_fingerprint_is_derived_from_promoted_checksums(tmp_path: Path) -> None:
    checkpoint = manager(tmp_path)
    output = tmp_path / "shots.parquet"
    output.write_bytes(b"first")
    checkpoint.promote_stage(
        "shots",
        input_fingerprint=compute_fingerprint("source"),
        outputs=[output],
        schema_version="shots_v1",
    )
    first = checkpoint.stage_output_fingerprint("shots")
    output.write_bytes(b"second")
    checkpoint.promote_stage(
        "shots",
        input_fingerprint=compute_fingerprint("source"),
        outputs=[output],
        schema_version="shots_v1",
    )
    assert checkpoint.stage_output_fingerprint("shots") != first
