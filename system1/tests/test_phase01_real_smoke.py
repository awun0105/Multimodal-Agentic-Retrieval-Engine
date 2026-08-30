from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from system1.config import load_configs
from system1.phase01 import smoke


CONFIG_DIR = Path(__file__).resolve().parents[1] / "configs"


def _settings() -> dict[str, str]:
    return {
        "batch_id": "batch_000",
        "worker_id": "worker_000",
        "hf_checkpoint_repo": "org/production-checkpoints",
        "checkpoint_revision": "model-artifacts-v1",
    }


def test_smoke_config_isolates_writes_but_keeps_production_model_store() -> None:
    policy = load_configs(CONFIG_DIR)["phase01"]["smoke"]
    resolved = smoke._resolve_smoke_config(
        config_dir=CONFIG_DIR,
        production_user_settings=_settings(),
        smoke_policy=policy,
        namespace="_smoke/run_123",
        batch_id="smoke_run_123",
        worker_id="smoke_run_123",
    )

    assert resolved.payload["storage"]["release"]["repo_id"] == (
        "1thesudden/AIOU26_release_test"
    )
    assert resolved.payload["storage"]["release"]["prefix"] == "_smoke/run_123"
    assert resolved.payload["storage"]["checkpoint"]["repo_id"] == (
        "1thesudden/AIOU26_checkpoints_test"
    )
    assert resolved.payload["storage"]["checkpoint"]["prefix"] == "_smoke/run_123"
    assert resolved.payload["storage"]["model_artifacts"]["repo_id"] == (
        "org/production-checkpoints"
    )
    assert resolved.payload["storage"]["model_artifacts"]["revision"] == (
        "model-artifacts-v1"
    )


def test_remote_cleanup_enumerates_exact_files_and_enforces_guards() -> None:
    class Store:
        repo_id = "org/test"
        prefix = "_smoke/run_123"

        def __init__(self) -> None:
            self.deleted: list[str] = []

        def list_files(self, _prefix: str):
            return [Path("a/file.json"), Path("b/file.zip")]

        def sync_files(self, files, *, delete_paths, **_kwargs):
            assert files == []
            self.deleted = list(delete_paths)

    store = Store()
    smoke._delete_smoke_files(store, configured_repo="org/test", run_id="run_123")
    assert store.deleted == ["a/file.json", "b/file.zip"]

    store.prefix = "canonical_release_v001"
    with pytest.raises(ValueError, match="unsafe remote smoke deletion"):
        smoke._delete_smoke_files(
            store, configured_repo="org/test", run_id="run_123"
        )


def test_smoke_mapping_accepts_source_branch_then_execution_pins_commit() -> None:
    policy = load_configs(CONFIG_DIR)["phase01"]["smoke"]
    raw = policy["source_raw"]
    mapping = {
        "canonical_repo_id": raw["repo_id"],
        "canonical_revision": "main",
        "canonical_prefix": "canonical_raw_v001",
        "canonical_video_path": "raw_videos/L30_V040.mp4",
        "canonical_metadata_path": "metadata/L30_V040.json",
    }

    assert smoke._validate_mapping(mapping, raw) == "main"


def test_worker_pipeline_never_starts_full_batch_after_smoke_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    production_started = False

    def fail_smoke(**_kwargs):
        raise smoke.Phase01SmokeError("failed", report_path=tmp_path / "smoke.json")

    def production(**_kwargs):
        nonlocal production_started
        production_started = True

    monkeypatch.setattr(smoke, "run_phase01_smoke", fail_smoke)
    monkeypatch.setattr(smoke, "run_phase01_pipeline", production)

    with pytest.raises(smoke.Phase01SmokeError):
        smoke.run_phase01_worker_pipeline(
            config_dir=CONFIG_DIR,
            output_root=tmp_path,
            user_settings=_settings(),
        )
    assert production_started is False


def test_worker_pipeline_runs_full_batch_only_after_smoke_pass(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    order: list[str] = []
    smoke_result = smoke.Phase01SmokeResult(
        run_id="run_123",
        ready_for_full_run=True,
        report_path=tmp_path / "smoke.json",
        remote_report_path=None,
    )
    production_result = SimpleNamespace(
        release_id="canonical_release_v001",
        release_dir=tmp_path / "release",
        resolved_config_path=tmp_path / "resolved.json",
        worker_report_path=tmp_path / "worker.json",
    )

    def pass_smoke(**_kwargs):
        order.append("smoke")
        return smoke_result

    def production(**_kwargs):
        order.append("production")
        return production_result

    monkeypatch.setattr(smoke, "run_phase01_smoke", pass_smoke)
    monkeypatch.setattr(smoke, "run_phase01_pipeline", production)

    result = smoke.run_phase01_worker_pipeline(
        config_dir=CONFIG_DIR,
        output_root=tmp_path,
        user_settings=_settings(),
    )

    assert order == ["smoke", "production"]
    assert result.smoke is smoke_result
    assert result.production is production_result
    last_run = json.loads((tmp_path / "phase01_worker_last_run.json").read_text())
    assert last_run["smoke"]["run_id"] == "run_123"
    assert last_run["production"]["release_id"] == "canonical_release_v001"
