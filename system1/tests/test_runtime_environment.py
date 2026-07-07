from pathlib import Path
import json

import pytest

from system1.commands.common import release_dir
from system1.runtime import RuntimeEnvironment, RuntimePaths, detect_environment, parse_bool, resolve_runtime_environment, resolve_runtime_paths
from system1.ingest.pipeline import run_ingestion
from system1.batch.writer import assign_batches
from system1.structure.builder import process_structure_batch
from system1.features.builder import process_feature_batch
from system1.media.probe import VideoProbe, VideoProbeWithTimeline


@pytest.fixture(autouse=True)
def fast_frame_timeline_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_probe_with_timeline(path: Path, *, video_id: str) -> VideoProbeWithTimeline:  # noqa: ARG001
        return VideoProbeWithTimeline(
            probe=VideoProbe(25.0, "test_frame_timeline", 3, False, "decoded_frame_timeline", 0.12, 640, 360, False),
            frame_timeline=[
                {"video_id": video_id, "frame_id": 0, "pts_time": 0.0, "duration_time": 0.04},
                {"video_id": video_id, "frame_id": 1, "pts_time": 0.04, "duration_time": 0.04},
                {"video_id": video_id, "frame_id": 2, "pts_time": 0.08, "duration_time": 0.04},
            ],
        )

    monkeypatch.setattr("system1.ingest.pipeline.probe_video_with_timeline", fake_probe_with_timeline)


def test_runtime_module_exports_and_defaults(tmp_path, monkeypatch):
    monkeypatch.delenv("AIC_INPUT_ROOT", raising=False)
    monkeypatch.delenv("AIC_OUTPUT_ROOT", raising=False)
    monkeypatch.delenv("AIC_ARTIFACT_ROOT", raising=False)
    monkeypatch.delenv("AIC_RELEASE_ID", raising=False)
    monkeypatch.delenv("AIC_BATCH_ID", raising=False)
    monkeypatch.delenv("AIC_WORKER_ID", raising=False)
    monkeypatch.delenv("AIC_RESUME", raising=False)
    monkeypatch.delenv("AIC_SYNC", raising=False)
    monkeypatch.delenv("AIC_FORCE_REBUILD", raising=False)
    monkeypatch.chdir(tmp_path)

    paths = resolve_runtime_paths()

    assert isinstance(paths, RuntimePaths)
    assert detect_environment() in {"local", "colab", "kaggle"}
    assert paths.release_id == "competition_dataset_v001"
    assert paths.batch_id == "batch_000"
    assert paths.worker_id == "worker_000"
    assert paths.resume is True
    assert paths.sync is True
    assert paths.force_rebuild is False
    assert paths.input_root == (tmp_path / "input").resolve()
    assert paths.output_root == (tmp_path / "output").resolve()
    assert paths.artifact_root == (tmp_path / "system1_artifacts").resolve()
    assert not paths.input_root.exists()
    assert not paths.output_root.exists()
    assert not paths.artifact_root.exists()


def test_runtime_environment_respects_path_env_vars(tmp_path, monkeypatch):
    input_root = tmp_path / "input-root"
    output_root = tmp_path / "output-root"
    artifact_root = tmp_path / "artifact-root"
    config_root = tmp_path / "config-root"
    monkeypatch.setenv("AIC_DATA_ROOT", str(input_root))
    monkeypatch.setenv("AIC_RUNTIME_ROOT", str(output_root))
    monkeypatch.setenv("AIC_ARTIFACT_ROOT", str(artifact_root))
    monkeypatch.setenv("AIC_CONFIG_ROOT", str(config_root))

    runtime = resolve_runtime_environment()

    assert isinstance(runtime, RuntimeEnvironment)
    assert runtime.input_root == input_root.resolve()
    assert runtime.output_root == output_root.resolve()
    assert runtime.artifact_root == artifact_root.resolve()
    assert runtime.config_root == config_root.resolve()
    assert runtime.release_root == output_root.resolve() / "competition_dataset_v001"


def test_aic_input_root_wins_over_aic_data_root(tmp_path, monkeypatch):
    monkeypatch.setenv("AIC_INPUT_ROOT", str(tmp_path / "input-root"))
    monkeypatch.setenv("AIC_DATA_ROOT", str(tmp_path / "legacy-input-root"))
    assert resolve_runtime_paths().input_root == (tmp_path / "input-root").resolve()
    assert resolve_runtime_environment().input_root == (tmp_path / "input-root").resolve()


def test_aic_output_root_wins_over_aic_runtime_root(tmp_path, monkeypatch):
    monkeypatch.setenv("AIC_OUTPUT_ROOT", str(tmp_path / "output-root"))
    monkeypatch.setenv("AIC_RUNTIME_ROOT", str(tmp_path / "legacy-output-root"))
    assert resolve_runtime_paths().output_root == (tmp_path / "output-root").resolve()
    assert resolve_runtime_environment().output_root == (tmp_path / "output-root").resolve()


def test_runtime_paths_explicit_arguments_override_env(tmp_path, monkeypatch):
    monkeypatch.setenv("AIC_OUTPUT_ROOT", str(tmp_path / "env-output"))
    explicit_output = tmp_path / "explicit-output"
    paths = resolve_runtime_paths(output_root=explicit_output)
    assert paths.output_root == explicit_output.resolve()


def test_parse_bool_handles_known_values():
    assert parse_bool("1") is True
    assert parse_bool(" true ") is True
    assert parse_bool("YES") is True
    assert parse_bool("on") is True
    assert parse_bool("0", default=True) is False
    assert parse_bool(" false ", default=True) is False
    assert parse_bool("No", default=True) is False
    assert parse_bool("off", default=True) is False
    assert parse_bool(None, default=True) is True
    assert parse_bool("unknown", default=False) is False
    assert parse_bool("unknown", default=True) is True


def test_release_id_affects_release_dir_and_phase_outputs(tmp_path, monkeypatch):
    release_id = "competition_dataset_custom"
    monkeypatch.setenv("AIC_RELEASE_ID", release_id)

    output_dir = tmp_path / "output"
    input_dir = Path("input")

    assert release_dir(output_dir) == output_dir / release_id

    report_path = run_ingestion(output_dir, input_dir=input_dir, mode="debug_small_sample")
    assert report_path.parent.parent.name == release_id
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["release_id"] == release_id

    batch_manifest_path = assign_batches(output_dir, num_batches=1)
    assert batch_manifest_path.parent.parent.name == release_id

    structure_report = process_structure_batch(output_dir, input_dir=input_dir, batch_id="batch_000", worker_id="worker_x", mode="debug_small_sample", providers="mock")
    assert structure_report.parent.name == "worker_reports"
    assert structure_report.parents[2].name == release_id

    feature_report = process_feature_batch(output_dir, input_dir=input_dir, batch_id="batch_000", worker_id="worker_x", mode="debug_small_sample", providers="mock")
    assert feature_report.parent.name == "worker_reports"
    assert feature_report.parents[2].name == release_id


def test_merge_dataset_manifest_release_id_matches_folder(tmp_path, monkeypatch):
    release_id = "competition_dataset_custom"
    monkeypatch.setenv("AIC_RELEASE_ID", release_id)
    output_dir = tmp_path / "output"
    input_dir = Path("input")

    run_ingestion(output_dir, input_dir=input_dir, mode="debug_small_sample")
    assign_batches(output_dir, num_batches=1)
    process_structure_batch(output_dir, input_dir=input_dir, batch_id="batch_000", worker_id="worker_x", mode="debug_small_sample", providers="mock")
    process_feature_batch(output_dir, input_dir=input_dir, batch_id="batch_000", worker_id="worker_x", mode="debug_small_sample", providers="mock")

    from system1.release.merge import merge_worker_outputs
    merge_report = merge_worker_outputs(output_dir / release_id)
    manifest = json.loads((merge_report.parent / "dataset_manifest.json").read_text(encoding="utf-8"))
    assert manifest["release_id"] == release_id
