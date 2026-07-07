import shutil
import json
import sqlite3
import csv
import hashlib
import os
import subprocess
import sys
import zipfile
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import numpy as np
import pytest
from typer.testing import CliRunner

from system1.commands import imports as imports_commands_module
from system1.cli import app
from system1.artifacts.package import validate_artifact_zip
from system1.config import REQUIRED_CONFIGS, load_configs, load_provider_plan
from system1.ingest.discovery import discover_media_inputs_tolerant, discover_paired_inputs
from system1.ingest.source_importer import (
    DriveShadowResult,
    _hf_retry_sleep_seconds,
    _is_hf_rate_limit_error,
    import_organizer_source,
    shadow_google_drive_folder,
    standardize_archive_source,
    stream_standardize_upload_raw_to_hf,
    upload_standardized_raw_to_hf,
)
from system1.ingest import source_importer as source_importer_module
from system1.media.probe import VideoProbe, VideoProbeWithTimeline
from system1.validation.release_validator import validate_release

runner = CliRunner()


@pytest.fixture(autouse=True)
def local_phase_execution(monkeypatch):
    monkeypatch.setenv("AIC_RESUME", "0")
    monkeypatch.setenv("AIC_SYNC", "0")

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


def invoke_app(command: list[str]):
    command_with_local_phase = list(command)
    if command_with_local_phase and command_with_local_phase[0] in {"ingest", "assign-batches", "process-batch", "feature-batch"}:
        if "--resume" not in command_with_local_phase and "--no-resume" not in command_with_local_phase:
            command_with_local_phase.append("--no-resume")
        if "--sync" not in command_with_local_phase and "--no-sync" not in command_with_local_phase:
            command_with_local_phase.append("--no-sync")
    return runner.invoke(app, command_with_local_phase)


def run_cli_sequence(commands: list[list[str]]) -> None:
    for command in commands:
        result = invoke_app(command)
        assert result.exit_code == 0, f"command failed: {command}\n{result.stdout}"


def phase_based_commands(
    output_dir: Path,
    *,
    mode: str = "debug_small_sample",
    providers: str = "mock",
) -> list[list[str]]:
    return [
        ["ingest", "--mode", mode, "--output", str(output_dir), "--input", "input"],
        ["assign-batches", "--mode", mode, "--num-batches", "1", "--output", str(output_dir)],
        [
            "process-batch",
            "--batch-id",
            "batch_000",
            "--mode",
            mode,
            "--providers",
            providers,
            "--output",
            str(output_dir),
            "--input",
            "input",
        ],
        [
            "feature-batch",
            "--batch-id",
            "batch_000",
            "--mode",
            mode,
            "--providers",
            providers,
            "--output",
            str(output_dir),
            "--input",
            "input",
        ],
        ["merge", "--mode", mode, "--output", str(output_dir)],
        ["build-index", "--mode", mode, "--output", str(output_dir)],
        ["build-db", "--mode", mode, "--output", str(output_dir)],
        ["validate", "--mode", mode, "--output", str(output_dir)],
    ]


def run_phase_based_release(
    tmp_path: Path,
    *,
    mode: str = "debug_small_sample",
    providers: str = "mock",
    package: bool = False,
) -> Path:
    output_dir = tmp_path / "output"
    run_cli_sequence(phase_based_commands(output_dir, mode=mode, providers=providers))
    release_dir = output_dir / "competition_dataset_v001"
    smoke = invoke_app(["smoke-test", "--release", str(release_dir)])
    assert smoke.exit_code == 0, smoke.stdout
    if package:
        packaged = invoke_app(["release", "--mode", mode, "--output", str(output_dir)])
        assert packaged.exit_code == 0, packaged.stdout
    return release_dir


def assert_artifact_zip_contract(
    zip_path: Path,
    *,
    video_id: str,
    artifact_type: str,
    expected_payload_files: set[str],
) -> None:
    manifest = validate_artifact_zip(zip_path)
    assert manifest["artifact_id"] == f"{video_id}_{artifact_type}"
    assert manifest["video_id"] == video_id
    assert manifest["artifact_type"] == artifact_type
    assert manifest["files"]

    with zipfile.ZipFile(zip_path) as archive:
        names = {name for name in archive.namelist() if not name.endswith("/")}
        assert all(name.startswith(f"{video_id}/") for name in names)
        assert f"{video_id}/artifact_manifest.json" in names
        assert f"{video_id}/checksums.json" in names
        assert expected_payload_files.issubset(names)

        checksums = json.loads(archive.read(f"{video_id}/checksums.json").decode("utf-8"))
        assert f"{video_id}/artifact_manifest.json" not in checksums
        assert f"{video_id}/checksums.json" not in checksums
        assert {item["path"] for item in manifest["files"]} == set(checksums)
        for path, expected in checksums.items():
            data = archive.read(path)
            assert expected["size_bytes"] == len(data)
            assert expected["sha256"] == hashlib.sha256(data).hexdigest()


def rewrite_zip_json_member(zip_path: Path, member_name: str, transform) -> None:
    temp_path = zip_path.with_name(f"{zip_path.name}.tmp")
    with zipfile.ZipFile(zip_path) as source, zipfile.ZipFile(temp_path, "w", compression=zipfile.ZIP_DEFLATED) as target:
        for member in source.infolist():
            data = source.read(member.filename)
            if member.filename == member_name:
                payload = json.loads(data.decode("utf-8"))
                data = json.dumps(transform(payload), indent=2, sort_keys=True).encode("utf-8") + b"\n"
            target.writestr(member, data)
    temp_path.replace(zip_path)


def remove_zip_member(zip_path: Path, member_name: str) -> None:
    temp_path = zip_path.with_name(f"{zip_path.name}.tmp")
    with zipfile.ZipFile(zip_path) as source, zipfile.ZipFile(temp_path, "w", compression=zipfile.ZIP_DEFLATED) as target:
        for member in source.infolist():
            if member.filename != member_name:
                target.writestr(member, source.read(member.filename))
    temp_path.replace(zip_path)


def prepare_structure_and_feature_artifacts(output_dir: Path) -> Path:
    commands = [
        ["ingest", "--mode", "debug_small_sample", "--output", str(output_dir), "--input", "input"],
        ["assign-batches", "--mode", "debug_small_sample", "--num-batches", "1", "--output", str(output_dir)],
        ["process-batch", "--batch-id", "batch_000", "--mode", "debug_small_sample", "--providers", "mock", "--output", str(output_dir), "--input", "input"],
        ["feature-batch", "--batch-id", "batch_000", "--mode", "debug_small_sample", "--providers", "mock", "--output", str(output_dir), "--input", "input"],
    ]
    for command in commands:
        result = invoke_app(command)
        assert result.exit_code == 0, result.stdout
    return output_dir / "competition_dataset_v001"



def test_system1_package_imports():
    import system1

    assert system1 is not None


def test_system1_module_entrypoint_exposes_drive_shadow_help():
    completed = subprocess.run(
        [sys.executable, "-m", "system1.cli", "drive-shadow", "--help"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "--source-folder-id" in completed.stdout
    assert "--dest-folder-id" in completed.stdout


def test_config_loading_reads_required_files():
    configs = load_configs(Path("configs"))
    assert set(REQUIRED_CONFIGS) == {f"{name}.yaml" for name in configs}
    assert configs["dataset"]["release_id"] == "competition_dataset_v001"
    assert "dataset_fps" not in configs["frame"]
    assert "fps_expected_default" not in configs["preprocessing"]
    assert configs["frame"]["fps_policy"]["scope"] == "per_video"
    assert configs["preprocessing"]["fps_policy"]["scope"] == "per_video"


def test_schema_files_are_complete_and_loadable():
    schema_dir = Path("schemas")
    expected = {
        "videos.schema.json",
        "media_store_manifest.schema.json",
        "asr_segments.schema.json",
        "scenes.schema.json",
        "shots.schema.json",
        "keyframes.schema.json",
        "frame_timeline.schema.json",
        "shot_transcript_links.schema.json",
        "scene_transcript_links.schema.json",
        "embeddings_meta.schema.json",
        "ocr.schema.json",
        "objects.schema.json",
        "image_captions.schema.json",
        "shot_captions.schema.json",
        "scene_summaries.schema.json",
        "text_sources.schema.json",
        "text_documents.schema.json",
        "feature_availability.schema.json",
        "vector_map.schema.json",
        "validation_report.schema.json",
    }
    assert expected.issubset({path.name for path in schema_dir.glob("*.json")})
    for filename in expected:
        schema = json.loads((schema_dir / filename).read_text(encoding="utf-8"))
        assert schema["type"] == "object"
        assert schema["required"]


def test_notebooks_are_operator_ready_thin_orchestration_shells():
    expected_commands = {
        "00A_master_ingestion_and_assignment.ipynb": [
            "drive-shadow",
            "standardize-archives",
            "upload-standardized-raw",
            "ingest",
            "assign-batches",
            "sync-phase00-ingestion",
            "AIC_HF_REPO_ID",
        ],
        "00B_master_ingestion_and_assignment.ipynb": [
            "drive-shadow",
            "stream-standardize-upload-raw",
            "--min-free-gb",
            "--drive-sync-sleep-seconds",
            "--cleanup-every-files",
            "--cleanup-every-gb",
            "ingest",
            "assign-batches",
            "sync-phase00-ingestion",
            "AIC_HF_REPO_ID",
        ],
        "00C_master_ingestion_and_assignment (local).ipynb": [
            "stream-standardize-upload-raw",
            "AIC_LOCAL_DATASET_DIR",
            "--min-free-gb",
            "--drive-sync-sleep-seconds",
            "--cleanup-every-files",
            "--cleanup-every-gb",
            "ingest",
            "assign-batches",
            "sync-phase00-ingestion",
            "AIC_HF_REPO_ID",
        ],
        "01_worker_structure_pipeline.ipynb": ["process-batch"],
        "02_worker_feature_enrichment.ipynb": ["feature-batch"],
        "03_merge_validate_index_release.ipynb": ["merge", "build-db", "build-index", "validate", "smoke-test", "release"],
    }
    for path in Path("notebooks").glob("*.ipynb"):
        notebook = json.loads(path.read_text(encoding="utf-8"))
        assert len(notebook["cells"]) >= 6, path
        joined = "\n".join("".join(cell.get("source", [])) for cell in notebook["cells"])
        assert "GitHub" in joined
        assert "git" in joined
        assert "clone" in joined
        assert "pull" in joined
        assert "pip" in joined
        assert "install" in joined
        assert "-e" in joined
        assert "AIC_REPO_ROOT" in joined
        assert "AIC_REPO_PARENT" in joined
        assert "Kaggle" in joined
        assert "Colab" in joined
        assert "AIC_DATA_ROOT" in joined
        assert "AIC_RUNTIME_ROOT" in joined
        assert "AIC_ARTIFACT_ROOT" in joined
        assert "execution_mode" in joined
        if not path.name.startswith("00"):
            assert "worker_id" in joined
            assert "batch_id" in joined
            assert "provider_mode" in joined
        assert "run_cli" in joined
        assert path.name in expected_commands
        for command in expected_commands[path.name]:
            assert command in joined


def test_stream_standardize_upload_raw_cli_passes_disk_safe_options(monkeypatch, tmp_path):
    captured: dict[str, object] = {}

    def fake_stream_standardize_upload_raw_to_hf(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return source_importer_module.CanonicalRawUploadResult(0, 0, 0, "manifest", "report")

    monkeypatch.setattr(
        imports_commands_module,
        "stream_standardize_upload_raw_to_hf",
        fake_stream_standardize_upload_raw_to_hf,
    )
    source_dir = tmp_path / "source"
    scratch_dir = tmp_path / "scratch"
    source_dir.mkdir()

    result = runner.invoke(
        app,
        [
            "stream-standardize-upload-raw",
            "--source-dir",
            str(source_dir),
            "--target-hf-repo-id",
            "org/repo",
            "--raw-import-id",
            "canonical_raw_v001",
            "--scratch-dir",
            str(scratch_dir),
            "--min-free-gb",
            "11",
            "--drive-sync-sleep-seconds",
            "12",
            "--cleanup-every-files",
            "13",
            "--cleanup-every-gb",
            "14",
        ],
    )

    assert result.exit_code == 0
    assert captured["kwargs"]["min_free_gb"] == 11
    assert captured["kwargs"]["drive_sync_sleep_seconds"] == 12
    assert captured["kwargs"]["cleanup_every_files"] == 13
    assert captured["kwargs"]["cleanup_every_gb"] == 14


def test_input_discovery_pairs_real_subset():
    pairs = discover_paired_inputs("input")
    assert [pair["video_id"] for pair in pairs] == ["L21_V001", "L21_V002", "L21_V003"]


def test_tolerant_input_discovery_reports_missing_and_unmatched_metadata(tmp_path):
    source = tmp_path / "standardize"
    (source / "raw_videos").mkdir(parents=True)
    (source / "metadata").mkdir()
    shutil.copy2(Path("input/raw_videos/L21_V001.mp4"), source / "raw_videos" / "A.mp4")
    shutil.copy2(Path("input/raw_videos/L21_V002.mp4"), source / "raw_videos" / "B.mp4")
    (source / "metadata" / "A.json").write_text('{"video_id":"A","title":"A title"}\n', encoding="utf-8")
    (source / "metadata" / "C.json").write_text('{"video_id":"C"}\n', encoding="utf-8")

    discovered = discover_media_inputs_tolerant(source)

    assert [pair["video_id"] for pair in discovered["pairs"]] == ["A", "B"]
    assert discovered["pairs"][0]["metadata_missing"] is False
    assert discovered["pairs"][1]["metadata_missing"] is True
    assert discovered["missing_metadata"] == ["B"]
    assert discovered["unmatched_metadata"] == [str(source / "metadata" / "C.json")]


def test_debug_release_generates_valid_release(tmp_path):
    release_dir = run_phase_based_release(tmp_path)
    sqlite_path = release_dir / "db" / "app.sqlite"
    with sqlite3.connect(sqlite_path) as connection:
        row = connection.execute("SELECT document_id FROM text_documents_fts WHERE text_documents_fts MATCH ? LIMIT 1", ("L21",)).fetchone()
        count = connection.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
    assert row is not None
    assert count == 3
    result = validate_release(release_dir)
    assert result.passed
    assert any("visual_search" in degraded for degraded in result.degraded)
    report = json.loads((release_dir / "manifests" / "validation_report.json").read_text(encoding="utf-8"))
    assert report["schema_validation"]["status"] == "pass"


def test_bronze_fast_generates_real_media_files(tmp_path):
    release_dir = run_phase_based_release(tmp_path, mode="bronze_fast")
    result = validate_release(release_dir)
    assert result.passed
    report = json.loads((release_dir / "manifests" / "validation_report.json").read_text(encoding="utf-8"))
    assert report["capabilities"]["core_runtime"] == "pass"
    assert report["capabilities"]["visual_search"] != "fail"
    assert list((release_dir / "media" / "keyframes").rglob("*.jpg"))
    assert list((release_dir / "media" / "thumbnails").rglob("*.webp"))
    assert (release_dir / "db" / "staging.duckdb").exists()


def test_cli_debug_pipeline_end_to_end(tmp_path):
    output_dir = tmp_path / "output"
    commands = [
        ["ingest", "--mode", "debug_small_sample", "--output", str(output_dir), "--input", "input"],
        ["assign-batches", "--mode", "debug_small_sample", "--num-batches", "1", "--output", str(output_dir)],
        ["process-batch", "--batch-id", "batch_000", "--mode", "debug_small_sample", "--providers", "mock", "--output", str(output_dir), "--input", "input"],
    ]
    for command in commands:
        result = invoke_app(command)
        assert result.exit_code == 0, result.stdout
    release_dir = output_dir / "competition_dataset_v001"
    assert (release_dir / "manifests" / "dataset_report.json").exists()
    assert (release_dir / "manifests" / "batch_000.txt").exists()
    assert (release_dir / "manifests" / "worker_reports" / "structure_batch_000_worker_000.json").exists()
    assert not (release_dir / "manifests" / "merge_report.json").exists()
    assert not (release_dir / "db" / "app.sqlite").exists()
    assert not (release_dir / "indexes" / "visual.faiss").exists()

def test_ingest_creates_only_ingestion_artifacts_and_is_idempotent(tmp_path):
    output_dir = tmp_path / "output"
    command = ["ingest", "--mode", "debug_small_sample", "--output", str(output_dir), "--input", "input"]
    first = invoke_app(command)
    second = invoke_app(command)
    assert first.exit_code == 0, first.stdout
    assert second.exit_code == 0, second.stdout
    release_dir = output_dir / "competition_dataset_v001"
    videos = pd.read_parquet(release_dir / "tables" / "videos.parquet")
    manifest = pd.read_parquet(release_dir / "raw_mapping" / "media_store_manifest.parquet")
    assert videos["video_id"].tolist() == ["L21_V001", "L21_V002", "L21_V003"]
    assert videos["video_id"].is_unique
    assert videos["video_ref"].str.startswith("media://raw_videos/").all()
    assert videos["source_extension"].eq(".mp4").all()
    assert "fps_detected" in videos.columns
    assert "duration_seconds" in videos.columns
    assert "is_vfr" in videos.columns
    assert "has_frame_timeline" in videos.columns
    assert "frame_timeline_ref" in videos.columns
    assert videos["has_frame_timeline"].all()
    frame_timeline_manifest = pd.read_parquet(release_dir / "manifests" / "frame_timeline_manifest.parquet")
    assert frame_timeline_manifest["video_id"].tolist() == ["L21_V001", "L21_V002", "L21_V003"]
    assert frame_timeline_manifest["status"].eq("pass").all()
    for row in frame_timeline_manifest.to_dict("records"):
        timeline = pd.read_parquet(release_dir / str(row["frame_timeline_ref"]))
        assert list(timeline.columns) == ["video_id", "frame_id", "pts_time", "duration_time"]
        assert timeline["video_id"].eq(row["video_id"]).all()
        assert timeline["frame_id"].tolist() == list(range(len(timeline)))
    assert manifest["video_local_path"].str.startswith("/").all()
    assert not (release_dir / "db" / "app.sqlite").exists()
    assert not (release_dir / "indexes" / "visual.faiss").exists()


def test_local_ingest_video_primary_tolerates_missing_and_unmatched_metadata(tmp_path):
    source = tmp_path / "standardize"
    output_dir = tmp_path / "output"
    (source / "raw_videos").mkdir(parents=True)
    (source / "metadata").mkdir()
    shutil.copy2(Path("input/raw_videos/L21_V001.mp4"), source / "raw_videos" / "A.mp4")
    shutil.copy2(Path("input/raw_videos/L21_V002.mp4"), source / "raw_videos" / "B.mp4")
    (source / "metadata" / "A.json").write_text('{"video_id":"A","title":"A title"}\n', encoding="utf-8")
    (source / "metadata" / "C.json").write_text('{"video_id":"C"}\n', encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "ingest",
            "--mode",
            "debug_small_sample",
            "--output",
            str(output_dir),
            "--source-uri",
            str(source),
            "--max-workers",
            "1",
            "--pairing-policy",
            "video-primary",
            "--no-resume",
            "--no-sync",
        ],
    )

    assert result.exit_code == 0, result.stdout
    release_dir = output_dir / "competition_dataset_v001"
    videos = pd.read_parquet(release_dir / "tables" / "videos.parquet")
    manifest = pd.read_parquet(release_dir / "raw_mapping" / "media_store_manifest.parquet")
    report = json.loads((release_dir / "manifests" / "dataset_report.json").read_text(encoding="utf-8"))
    missing_metadata = json.loads((release_dir / "manifests" / "missing_metadata.json").read_text(encoding="utf-8"))
    unmatched_metadata = json.loads((release_dir / "manifests" / "unmatched_metadata.json").read_text(encoding="utf-8"))

    assert videos["video_id"].tolist() == ["A", "B"]
    assert manifest.sort_values("video_id")["metadata_missing"].tolist() == [False, True]
    assert report["pairing_policy"] == "video_primary_tolerant"
    assert report["video_count"] == 2
    assert report["missing_metadata_count"] == 1
    assert report["unmatched_metadata_count"] == 1
    assert missing_metadata["missing_metadata"] == ["B"]
    assert unmatched_metadata["unmatched_metadata"] == [str(source / "metadata" / "C.json")]


def test_assign_batches_reads_ingested_videos_and_supports_multiple_batches(tmp_path):
    output_dir = tmp_path / "output"
    ingest = invoke_app(["ingest", "--mode", "debug_small_sample", "--output", str(output_dir), "--input", "input"])
    assigned = invoke_app(["assign-batches", "--mode", "debug_small_sample", "--num-batches", "2", "--output", str(output_dir)])
    assert ingest.exit_code == 0, ingest.stdout
    assert assigned.exit_code == 0, assigned.stdout
    release_dir = output_dir / "competition_dataset_v001"
    assert (release_dir / "manifests" / "batch_000.txt").exists()
    assert (release_dir / "manifests" / "batch_001.txt").exists()
    with (release_dir / "manifests" / "batch_manifest.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert {"batch_000", "batch_001"}.issubset({row["batch_id"] for row in rows})
    assert set(rows[0]) == {
        "batch_id",
        "video_id",
        "estimated_compute_cost",
        "assigned_worker",
        "status",
        "structure_artifact_path",
        "feature_artifact_path",
        "error_note",
    }
    assert not (release_dir / "db" / "app.sqlite").exists()

def test_process_batch_creates_only_structure_artifacts_for_selected_batch(tmp_path):
    output_dir = tmp_path / "output"
    invoke_app(["ingest", "--mode", "debug_small_sample", "--output", str(output_dir), "--input", "input"])
    invoke_app(["assign-batches", "--mode", "debug_small_sample", "--num-batches", "1", "--output", str(output_dir)])
    release_dir = output_dir / "competition_dataset_v001"
    videos_before = (release_dir / "tables" / "videos.parquet").stat().st_mtime_ns
    result = invoke_app(["process-batch", "--batch-id", "batch_000", "--mode", "debug_small_sample", "--providers", "mock", "--output", str(output_dir), "--input", "input"])
    assert result.exit_code == 0, result.stdout
    artifact_dir = release_dir / "artifacts" / "structure" / "L21_V001"
    assert artifact_dir.exists()
    for name in [
        "metadata_normalized.json",
        "asr_segments.parquet",
        "shots.parquet",
        "scenes.parquet",
        "keyframes.parquet",
        "image_captions.parquet",
        "shot_transcript_links.parquet",
        "scene_transcript_links.parquet",
        "scene_summaries.parquet",
        "manifest.json",
        "errors.jsonl",
    ]:
        assert (artifact_dir / name).exists()
    assert (artifact_dir / "keyframes").exists()
    assert (artifact_dir / "thumbnails").exists()
    assert not (artifact_dir / "L21_V001").exists()
    structure_zip = release_dir / "artifacts" / "structure" / "L21_V001_structure.zip"
    assert structure_zip.exists()
    assert_artifact_zip_contract(
        structure_zip,
        video_id="L21_V001",
        artifact_type="structure",
        expected_payload_files={
            "L21_V001/metadata_normalized.json",
            "L21_V001/asr_segments.parquet",
            "L21_V001/shots.parquet",
            "L21_V001/scenes.parquet",
            "L21_V001/keyframes.parquet",
            "L21_V001/image_captions.parquet",
            "L21_V001/shot_transcript_links.parquet",
            "L21_V001/scene_transcript_links.parquet",
            "L21_V001/scene_summaries.parquet",
            "L21_V001/manifest.json",
            "L21_V001/errors.jsonl",
        },
    )
    with zipfile.ZipFile(structure_zip) as archive:
        names = {name for name in archive.namelist() if not name.endswith("/")}
        assert not any("_canonical_cache" in name or "phase01_scratch" in name for name in names)
    assert (release_dir / "artifacts" / "structure_batches" / "batch_000" / "L21_V001.json").exists()
    assert not (release_dir / "artifacts" / "features").exists()
    assert not (release_dir / "db" / "app.sqlite").exists()
    assert not (release_dir / "indexes" / "visual.faiss").exists()
    assert (release_dir / "tables" / "videos.parquet").stat().st_mtime_ns == videos_before
    for name in [
        "asr_segments.parquet",
        "shots.parquet",
        "scenes.parquet",
        "keyframes.parquet",
        "image_captions.parquet",
        "shot_transcript_links.parquet",
        "scene_transcript_links.parquet",
        "scene_summaries.parquet",
    ]:
        assert not (release_dir / "tables" / name).exists()
    keyframes = pd.read_parquet(artifact_dir / "keyframes.parquet")
    assert keyframes.iloc[0]["keyframe_ref"] == "media://keyframes/L21_V001/L21_V001_f0000000.jpg"
    assert keyframes.iloc[0]["thumbnail_ref"] == "media://thumbnails/L21_V001/L21_V001_f0000000.webp"
    assert keyframes.iloc[0]["frame_id_method"] == "first_frame_extraction_assumed_frame_0"
    assert str(keyframes.iloc[0]["thumbnail_ref"]).endswith(".webp")
    shots = pd.read_parquet(artifact_dir / "shots.parquet")
    assert shots.iloc[0]["boundary_convention"] == "[start_frame, end_frame)"
    image_captions = pd.read_parquet(artifact_dir / "image_captions.parquet")
    assert {"caption_id", "keyframe_id", "video_id", "scene_id", "shot_id", "caption", "provider", "status"}.issubset(image_captions.columns)
    assert image_captions.iloc[0]["keyframe_id"] == "L21_V001:0"
    scene_summaries = pd.read_parquet(artifact_dir / "scene_summaries.parquet")
    assert {"scene_id", "video_id", "summary", "provider", "status"}.issubset(scene_summaries.columns)
    manifest = json.loads((artifact_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["phase01_contract"]["semantic_level"] == "semantic_light"
    assert manifest["phase01_contract"]["scene_summary_table"] == "scene_summaries.parquet"

def test_process_batch_ffmpeg_failure_writes_valid_placeholder_images(tmp_path):
    output_dir = tmp_path / "output"
    invoke_app(["ingest", "--mode", "debug_small_sample", "--output", str(output_dir), "--input", "input"])
    invoke_app(["assign-batches", "--mode", "debug_small_sample", "--num-batches", "1", "--output", str(output_dir)])
    with patch("subprocess.run", side_effect=__import__("subprocess").CalledProcessError(1, "ffmpeg")):
        result = invoke_app(["process-batch", "--batch-id", "batch_000", "--mode", "debug_small_sample", "--providers", "mock", "--output", str(output_dir), "--input", "input"])
    assert result.exit_code == 0, result.stdout
    artifact_dir = output_dir / "competition_dataset_v001" / "artifacts" / "structure" / "L21_V001"
    jpg = next((artifact_dir / "keyframes").glob("*.jpg"))
    webp = next((artifact_dir / "thumbnails").glob("*.webp"))
    assert jpg.read_bytes().startswith(b"\xff\xd8\xff")
    assert webp.read_bytes().startswith(b"RIFF")
    assert b"WEBP" in webp.read_bytes()[:16]

def test_process_batch_missing_batch_file_fails_clearly(tmp_path):
    output_dir = tmp_path / "output"
    invoke_app(["ingest", "--mode", "debug_small_sample", "--output", str(output_dir), "--input", "input"])
    result = invoke_app(["process-batch", "--batch-id", "batch_999", "--mode", "debug_small_sample", "--providers", "mock", "--output", str(output_dir), "--input", "input"])
    assert result.exit_code != 0

def test_feature_batch_creates_only_feature_artifacts_from_structure(tmp_path):
    output_dir = tmp_path / "output"
    invoke_app(["ingest", "--mode", "debug_small_sample", "--output", str(output_dir), "--input", "input"])
    invoke_app(["assign-batches", "--mode", "debug_small_sample", "--num-batches", "1", "--output", str(output_dir)])
    invoke_app(["process-batch", "--batch-id", "batch_000", "--mode", "debug_small_sample", "--providers", "mock", "--output", str(output_dir), "--input", "input"])
    release_dir = output_dir / "competition_dataset_v001"
    structure_manifest = release_dir / "artifacts" / "structure" / "L21_V001" / "manifest.json"
    structure_before = structure_manifest.stat().st_mtime_ns
    result = invoke_app(["feature-batch", "--batch-id", "batch_000", "--mode", "debug_small_sample", "--providers", "mock", "--output", str(output_dir), "--input", "input"])
    assert result.exit_code == 0, result.stdout
    artifact_dir = release_dir / "artifacts" / "features" / "L21_V001"
    assert artifact_dir.exists()
    for name in [
        "visual_embeddings.npy",
        "embeddings_meta.parquet",
        "ocr.parquet",
        "objects.parquet",
        "image_captions.parquet",
        "shot_captions.parquet",
        "scene_summaries_enriched.parquet",
        "text_sources.parquet",
        "feature_manifest.json",
        "errors.jsonl",
    ]:
        assert (artifact_dir / name).exists()
    assert not (artifact_dir / "L21_V001").exists()
    features_zip = release_dir / "artifacts" / "features" / "L21_V001_features.zip"
    assert features_zip.exists()
    assert_artifact_zip_contract(
        features_zip,
        video_id="L21_V001",
        artifact_type="features",
        expected_payload_files={
            "L21_V001/visual_embeddings.npy",
            "L21_V001/embeddings_meta.parquet",
            "L21_V001/ocr.parquet",
            "L21_V001/objects.parquet",
            "L21_V001/image_captions.parquet",
            "L21_V001/shot_captions.parquet",
            "L21_V001/scene_summaries_enriched.parquet",
            "L21_V001/text_sources.parquet",
            "L21_V001/feature_manifest.json",
            "L21_V001/errors.jsonl",
        },
    )
    assert (release_dir / "manifests" / "worker_reports" / "features_batch_000_worker_000.json").exists()
    embeddings = np.load(artifact_dir / "visual_embeddings.npy")
    embeddings_meta = pd.read_parquet(artifact_dir / "embeddings_meta.parquet")
    text_sources = pd.read_parquet(artifact_dir / "text_sources.parquet")
    assert embeddings.shape[0] == len(embeddings_meta)
    assert {"embedding_id", "keyframe_id", "video_id", "frame_id", "embedding_model", "model_slug", "embedding_dim", "vector_dim", "status", "provider"}.issubset(embeddings_meta.columns)
    assert embeddings.shape[1] == int(embeddings_meta.iloc[0]["vector_dim"])
    assert {"source_id", "video_id", "entity_type", "entity_id", "source_type", "raw_text", "normalized_text", "normalized_no_diacritics", "language", "provider", "status"}.issubset(text_sources.columns)
    assert "image_caption" in set(text_sources["source_type"])
    manifest = json.loads((artifact_dir / "feature_manifest.json").read_text(encoding="utf-8"))
    assert "source_structure_artifact" in manifest
    assert "visual_embeddings_shape" in manifest
    assert "provider_plan" in manifest
    assert any(source_id.count(":") >= 4 for source_id in text_sources["source_id"])
    assert not (release_dir / "indexes" / "visual.faiss").exists()
    assert not (release_dir / "db" / "app.sqlite").exists()
    assert not (release_dir / "tables" / "embeddings_meta.parquet").exists()
    assert structure_manifest.stat().st_mtime_ns == structure_before

def test_feature_batch_missing_structure_artifact_fails_clearly(tmp_path):
    output_dir = tmp_path / "output"
    invoke_app(["ingest", "--mode", "debug_small_sample", "--output", str(output_dir), "--input", "input"])
    invoke_app(["assign-batches", "--mode", "debug_small_sample", "--num-batches", "1", "--output", str(output_dir)])
    result = invoke_app(["feature-batch", "--batch-id", "batch_000", "--mode", "debug_small_sample", "--providers", "mock", "--output", str(output_dir), "--input", "input"])
    assert result.exit_code != 0


def test_worker_reports_include_phase_batch_worker_and_do_not_overwrite(tmp_path):
    output_dir = tmp_path / "output"
    invoke_app(["ingest", "--mode", "debug_small_sample", "--output", str(output_dir), "--input", "input"])
    invoke_app(["assign-batches", "--mode", "debug_small_sample", "--num-batches", "2", "--output", str(output_dir)])
    first = invoke_app(["process-batch", "--batch-id", "batch_000", "--worker-id", "worker_a", "--mode", "debug_small_sample", "--providers", "mock", "--output", str(output_dir), "--input", "input"])
    second = invoke_app(["process-batch", "--batch-id", "batch_001", "--worker-id", "worker_b", "--mode", "debug_small_sample", "--providers", "mock", "--output", str(output_dir), "--input", "input"])
    assert first.exit_code == 0, first.stdout
    assert second.exit_code == 0, second.stdout
    release_dir = output_dir / "competition_dataset_v001"
    report_a = release_dir / "manifests" / "worker_reports" / "structure_batch_000_worker_a.json"
    report_b = release_dir / "manifests" / "worker_reports" / "structure_batch_001_worker_b.json"
    assert report_a.exists()
    assert report_b.exists()
    payload_a = json.loads(report_a.read_text(encoding="utf-8"))
    payload_b = json.loads(report_b.read_text(encoding="utf-8"))
    assert payload_a["phase"] == "structure"
    assert payload_a["batch_id"] == "batch_000"
    assert payload_a["worker_id"] == "worker_a"
    assert payload_a["status"] == "completed"
    assert payload_a["videos_processed"] > 0
    assert payload_b["phase"] == "structure"
    assert payload_b["batch_id"] == "batch_001"
    assert payload_b["worker_id"] == "worker_b"


def test_feature_batch_restores_structure_from_zip_when_folder_missing(tmp_path):
    output_dir = tmp_path / "output"
    invoke_app(["ingest", "--mode", "debug_small_sample", "--output", str(output_dir), "--input", "input"])
    invoke_app(["assign-batches", "--mode", "debug_small_sample", "--num-batches", "1", "--output", str(output_dir)])
    invoke_app(["process-batch", "--batch-id", "batch_000", "--mode", "debug_small_sample", "--providers", "mock", "--output", str(output_dir), "--input", "input"])
    release_dir = output_dir / "competition_dataset_v001"
    shutil.rmtree(release_dir / "artifacts" / "structure" / "L21_V001")

    result = invoke_app(["feature-batch", "--batch-id", "batch_000", "--mode", "debug_small_sample", "--providers", "mock", "--output", str(output_dir), "--input", "input"])

    assert result.exit_code == 0, result.stdout
    extracted = release_dir / "staging" / "extracted_artifacts" / "structure" / "L21_V001"
    assert (extracted / "keyframes.parquet").exists()
    assert (release_dir / "artifacts" / "features" / "L21_V001_features.zip").exists()


def test_cli_merge_db_index_validate_smoke_runtime(tmp_path):
    output_dir = tmp_path / "output"
    commands = [
        ["ingest", "--mode", "debug_small_sample", "--output", str(output_dir), "--input", "input"],
        ["assign-batches", "--mode", "debug_small_sample", "--num-batches", "1", "--output", str(output_dir)],
        ["process-batch", "--batch-id", "batch_000", "--mode", "debug_small_sample", "--providers", "mock", "--output", str(output_dir), "--input", "input"],
        ["feature-batch", "--batch-id", "batch_000", "--mode", "debug_small_sample", "--providers", "mock", "--output", str(output_dir), "--input", "input"],
        ["merge", "--mode", "debug_small_sample", "--output", str(output_dir)],
    ]
    for command in commands:
        result = invoke_app(command)
        assert result.exit_code == 0, result.stdout
    release_dir = output_dir / "competition_dataset_v001"
    assert (release_dir / "tables" / "text_documents.parquet").exists()
    assert (release_dir / "manifests" / "artifact_manifest.parquet").exists()
    assert list((release_dir / "media" / "keyframes").rglob("*.jpg"))
    assert list((release_dir / "media" / "thumbnails").rglob("*.webp"))
    assert not (release_dir / "db" / "app.sqlite").exists()
    assert not (release_dir / "indexes" / "visual.faiss").exists()

    index = invoke_app(["build-index", "--mode", "debug_small_sample", "--output", str(output_dir)])
    db = invoke_app(["build-db", "--mode", "debug_small_sample", "--output", str(output_dir)])
    validate = invoke_app(["validate", "--mode", "debug_small_sample", "--output", str(output_dir)])
    smoke = invoke_app(["smoke-test", "--release", str(release_dir)])
    assert index.exit_code == 0, index.stdout
    assert db.exit_code == 0, db.stdout
    assert validate.exit_code == 0, validate.stdout
    assert smoke.exit_code == 0, smoke.stdout
    assert (release_dir / "db" / "app.sqlite").exists()
    assert (release_dir / "indexes" / "vector_map.parquet").exists()
    assert (release_dir / "indexes" / "visual.faiss").exists()
    vector_map = pd.read_parquet(release_dir / "indexes" / "vector_map.parquet")
    embeddings_meta = pd.read_parquet(release_dir / "tables" / "embeddings_meta.parquet")
    assert len(vector_map) == len(embeddings_meta)
    text_documents = pd.read_parquet(release_dir / "tables" / "text_documents.parquet")
    assert any(text_documents["normalized_text"] != text_documents["normalized_no_diacritics"])
    with sqlite3.connect(release_dir / "db" / "app.sqlite") as connection:
        refs = connection.execute("SELECT video_ref FROM videos").fetchall()
        media_refs = connection.execute("SELECT keyframe_ref, thumbnail_ref FROM keyframes LIMIT 1").fetchone()
        assert all(ref[0].startswith("media://") for ref in refs)
        assert not any(ref[0].startswith("/") for ref in refs)
        assert connection.execute("SELECT document_id FROM text_documents_fts WHERE text_documents_fts MATCH 'L21' LIMIT 1").fetchone()
    smoke_report = json.loads((release_dir / "manifests" / "smoke_test_report.json").read_text(encoding="utf-8"))
    assert smoke_report["media_resolved"] is True
    assert media_refs is not None


def test_merge_reads_zip_artifacts_when_extracted_folders_missing(tmp_path):
    output_dir = tmp_path / "output"
    release_dir = prepare_structure_and_feature_artifacts(output_dir)
    shutil.rmtree(release_dir / "artifacts" / "structure" / "L21_V001")
    shutil.rmtree(release_dir / "artifacts" / "features" / "L21_V001")

    result = invoke_app(["merge", "--mode", "debug_small_sample", "--output", str(output_dir)])

    assert result.exit_code == 0, result.stdout
    assert (release_dir / "staging" / "extracted_artifacts" / "merge" / "structure" / "L21_V001" / "shots.parquet").exists()
    assert (release_dir / "staging" / "extracted_artifacts" / "merge" / "features" / "L21_V001" / "embeddings_meta.parquet").exists()
    assert (release_dir / "tables" / "text_documents.parquet").exists()


def test_merge_fails_on_artifact_zip_checksum_mismatch(tmp_path):
    output_dir = tmp_path / "output"
    release_dir = prepare_structure_and_feature_artifacts(output_dir)
    structure_zip = release_dir / "artifacts" / "structure" / "L21_V001_structure.zip"

    def corrupt_first_checksum(payload: dict[str, object]) -> dict[str, object]:
        first_key = sorted(payload)[0]
        assert isinstance(payload[first_key], dict)
        payload[first_key]["sha256"] = "0" * 64
        return payload

    rewrite_zip_json_member(structure_zip, "L21_V001/checksums.json", corrupt_first_checksum)
    result = invoke_app(["merge", "--mode", "debug_small_sample", "--output", str(output_dir)])

    assert result.exit_code != 0
    assert result.exception is not None
    assert "checksum mismatch" in str(result.exception)


@pytest.mark.parametrize("member_name", ["L21_V001/artifact_manifest.json", "L21_V001/checksums.json"])
def test_merge_fails_on_artifact_zip_missing_package_metadata(tmp_path, member_name):
    output_dir = tmp_path / "output"
    release_dir = prepare_structure_and_feature_artifacts(output_dir)
    structure_zip = release_dir / "artifacts" / "structure" / "L21_V001_structure.zip"
    remove_zip_member(structure_zip, member_name)

    result = invoke_app(["merge", "--mode", "debug_small_sample", "--output", str(output_dir)])

    assert result.exit_code != 0
    assert result.exception is not None
    assert Path(member_name).name in str(result.exception)


def test_validate_fails_before_runtime_artifacts(tmp_path):
    output_dir = tmp_path / "output"
    result = invoke_app(["ingest", "--mode", "debug_small_sample", "--output", str(output_dir), "--input", "input"])
    assert result.exit_code == 0, result.stdout
    validate = invoke_app(["validate", "--mode", "debug_small_sample", "--output", str(output_dir)])
    assert validate.exit_code != 0

def test_build_mini_seed_command_is_removed_from_main_cli(tmp_path):
    output_dir = tmp_path / "output"
    result = runner.invoke(
        app,
        ["build-mini-seed", "--mode", "debug_small_sample", "--providers", "mock", "--output", str(output_dir), "--input", "input"],
    )
    assert result.exit_code != 0

    release_dir = run_phase_based_release(tmp_path, package=True)
    assert (release_dir / "manifests" / "smoke_test_report.json").exists()
    assert (output_dir / "competition_dataset_v001.zip").exists()


def test_cli_bronze_pipeline_end_to_end(tmp_path):
    output_dir = tmp_path / "output"
    commands = [
        ["ingest", "--mode", "bronze_fast", "--output", str(output_dir), "--input", "input"],
        ["assign-batches", "--mode", "bronze_fast", "--num-batches", "1", "--output", str(output_dir)],
        ["process-batch", "--batch-id", "batch_000", "--mode", "bronze_fast", "--providers", "mock", "--output", str(output_dir), "--input", "input"],
    ]
    for command in commands:
        result = invoke_app(command)
        assert result.exit_code == 0, result.stdout


def test_silver_balanced_outputs_asr_ocr_contracts(tmp_path):
    release_dir = run_phase_based_release(tmp_path, mode="silver_balanced")
    result = validate_release(release_dir)
    assert result.passed
    report = json.loads((release_dir / "manifests" / "validation_report.json").read_text(encoding="utf-8"))
    assert report["capabilities"]["asr"] == "pass"
    assert report["capabilities"]["ocr"] == "pass"
    assert (release_dir / "tables" / "asr_segments.parquet").exists()
    assert (release_dir / "tables" / "ocr.parquet").exists()


def test_real_provider_mode_fails_gracefully_with_degraded_asr_ocr(tmp_path):
    release_dir = run_phase_based_release(tmp_path, mode="silver_balanced", providers="real")
    result = validate_release(release_dir)
    assert result.passed
    report = json.loads((release_dir / "manifests" / "validation_report.json").read_text(encoding="utf-8"))
    assert report["capabilities"]["asr"] == "degraded"
    assert report["capabilities"]["ocr"] == "degraded"
    assert report["capabilities"]["visual_search"] == "degraded"
    assert report["release_usable"] is True


def test_gold_full_outputs_enrichment_and_phase_artifacts(tmp_path):
    release_dir = run_phase_based_release(tmp_path, mode="gold_full")
    report = json.loads((release_dir / "manifests" / "validation_report.json").read_text(encoding="utf-8"))
    assert report["capabilities"]["enrichment_overall"] == "pass"
    assert not (release_dir / "manifests" / "checkpoint_manifest.json").exists()
    assert list((release_dir / "artifacts" / "structure").glob("*_structure.zip"))
    assert list((release_dir / "artifacts" / "features").glob("*_features.zip"))
    for name in ["objects", "image_captions", "shot_captions", "scene_summaries", "scene_summaries_enriched"]:
        assert (release_dir / "tables" / f"{name}.parquet").exists()


def test_cli_gold_pipeline_end_to_end(tmp_path):
    output_dir = tmp_path / "output"
    commands = [
        ["ingest", "--mode", "gold_full", "--output", str(output_dir), "--input", "input"],
        ["assign-batches", "--mode", "gold_full", "--num-batches", "1", "--output", str(output_dir)],
        ["process-batch", "--batch-id", "batch_000", "--mode", "gold_full", "--providers", "mock", "--output", str(output_dir), "--input", "input"],
    ]
    for command in commands:
        result = invoke_app(command)
        assert result.exit_code == 0, result.stdout
    release_dir = output_dir / "competition_dataset_v001"
    assert list((release_dir / "artifacts" / "structure").glob("*_structure.zip"))
    assert not (release_dir / "artifacts" / "features").exists()


def test_provider_plan_supports_named_modes():
    plan = load_provider_plan(Path("configs"), "real")
    assert plan.asr == "whisper"
    assert plan.ocr == "paddleocr"
    assert plan.embedding == "openclip"
    assert plan.object_detection == "yolo"
    assert plan.image_caption == "blip"
    assert plan.shot_caption == "vlm"
    assert plan.scene_summary == "llm"


def test_worker_artifacts_and_runtime_reports_exist(tmp_path):
    release_dir = run_phase_based_release(tmp_path, mode="gold_full")
    assert (release_dir / "manifests" / "worker_reports" / "structure_batch_000_worker_000.json").exists()
    assert (release_dir / "manifests" / "worker_reports" / "features_batch_000_worker_000.json").exists()
    assert list((release_dir / "artifacts" / "structure").glob("*_structure.zip"))
    assert list((release_dir / "artifacts" / "features").glob("*_features.zip"))


def test_selective_provider_change_keeps_phase_contracts(tmp_path):
    release_dir = run_phase_based_release(tmp_path, mode="gold_full", providers="real")
    report = json.loads((release_dir / "manifests" / "validation_report.json").read_text(encoding="utf-8"))
    assert report["capabilities"]["asr"] == "degraded"
    assert report["capabilities"]["ocr"] == "degraded"
    assert report["capabilities"]["visual_search"] == "degraded"
    assert (release_dir / "tables" / "asr_segments.parquet").exists()
    assert (release_dir / "tables" / "ocr.parquet").exists()


def test_import_organizer_source_from_local_folder(tmp_path):
    source_root = tmp_path / "organizer_source"
    (source_root / "videos").mkdir(parents=True)
    (source_root / "metadata").mkdir(parents=True)
    sample_video = Path("input/raw_videos/L21_V001.mp4").resolve()
    sample_metadata = Path("input/metadata/L21_V001.json").resolve()
    shutil.copy2(sample_video, source_root / "videos" / "L21_V001.mp4")
    shutil.copy2(sample_metadata, source_root / "metadata" / "L21_V001.json")
    result = import_organizer_source(str(source_root), tmp_path / "drive_data")
    assert result.video_count == 1
    assert (tmp_path / "drive_data" / "raw_videos" / "L21_V001.mp4").exists()
    assert (tmp_path / "drive_data" / "metadata" / "L21_V001.json").exists()
    assert result.report_path.exists()


def test_import_organizer_source_resets_stale_data_root_content(tmp_path):
    source_root = tmp_path / "organizer_source"
    (source_root / "videos").mkdir(parents=True)
    sample_video = Path("input/raw_videos/L21_V001.mp4").resolve()
    shutil.copy2(sample_video, source_root / "videos" / "L21_V001.mp4")

    drive_data = tmp_path / "drive_data"
    stale_video = drive_data / "raw_videos" / "STALE.mp4"
    stale_metadata = drive_data / "metadata" / "STALE.json"
    stale_video.parent.mkdir(parents=True)
    stale_metadata.parent.mkdir(parents=True)
    stale_video.write_bytes(b"stale")
    stale_metadata.write_text("{}\n", encoding="utf-8")

    result = import_organizer_source(str(source_root), drive_data)

    assert result.video_count == 1
    assert not stale_video.exists()
    assert not stale_metadata.exists()
    assert (drive_data / "raw_videos" / "L21_V001.mp4").exists()
    assert (drive_data / "metadata" / "L21_V001.json").exists()


def test_import_organizer_source_rejects_duplicate_video_stems(tmp_path):
    source_root = tmp_path / "organizer_source"
    (source_root / "videos_a").mkdir(parents=True)
    (source_root / "videos_b").mkdir(parents=True)
    sample_video = Path("input/raw_videos/L21_V001.mp4").resolve()
    shutil.copy2(sample_video, source_root / "videos_a" / "L21_V001.mp4")
    shutil.copy2(sample_video, source_root / "videos_b" / "L21_V001.mkv")

    with pytest.raises(ValueError, match="duplicate video stem"):
        import_organizer_source(str(source_root), tmp_path / "drive_data")


def test_upload_standardized_raw_to_hf_uploads_versioned_standard_layout(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("AIC_VERBOSE", raising=False)
    source_root = tmp_path / "standardized"
    (source_root / "raw_videos").mkdir(parents=True)
    (source_root / "metadata").mkdir(parents=True)
    (source_root / "raw_videos" / "L21_V001.mp4").write_bytes(b"video-1")
    (source_root / "metadata" / "L21_V001.json").write_text('{"title":"sample 1"}\n', encoding="utf-8")
    (source_root / "raw_videos" / "L21_V002.mp4").write_bytes(b"video-2")
    (source_root / "metadata" / "L21_V002.json").write_text('{"title":"sample 2"}\n', encoding="utf-8")
    uploaded: dict[str, bytes] = {}
    commit_batches: list[list[str]] = []

    monkeypatch.setattr("system1.ingest.source_importer.HuggingFaceDatasetArtifactStore.list_files", lambda self, prefix="": [])

    def fake_upload_files(self, files, *, commit_message: str, num_threads: int = 2):
        commit_batches.append([str(relative_path) for _source, relative_path in files])
        for source, relative_path in files:
            uploaded[str(relative_path)] = source.read_bytes()
        return [Path("hf:/org/repo") / str(relative_path) for _source, relative_path in files]

    monkeypatch.setattr("system1.ingest.source_importer.HuggingFaceDatasetArtifactStore.upload_files", fake_upload_files)

    result = upload_standardized_raw_to_hf(
        source_root,
        repo_id="org/repo",
        raw_import_id="canonical_dataset_v001",
    )
    output = capsys.readouterr().out

    assert result.video_count == 2
    assert result.metadata_count == 2
    assert result.error_count == 0
    assert "canonical_dataset_v001/raw_videos/L21_V001.mp4" in uploaded
    assert "canonical_dataset_v001/raw_videos/L21_V002.mp4" in uploaded
    assert "canonical_dataset_v001/metadata/L21_V001.json" in uploaded
    assert "canonical_dataset_v001/metadata/L21_V002.json" in uploaded
    assert "canonical_dataset_v001/manifests/canonical_file_manifest.jsonl" in uploaded
    assert "canonical_dataset_v001/manifests/canonical_import_report.json" in uploaded
    assert "canonical_dataset_v001/manifests/canonical_video_inventory.parquet" in uploaded
    assert "canonical_dataset_v001/manifests/missing_metadata.json" in uploaded
    assert "canonical_dataset_v001/manifests/unmatched_metadata.json" in uploaded
    assert commit_batches == [
        [
            "canonical_dataset_v001/raw_videos/L21_V001.mp4",
            "canonical_dataset_v001/raw_videos/L21_V002.mp4",
        ],
        [
            "canonical_dataset_v001/metadata/L21_V001.json",
            "canonical_dataset_v001/metadata/L21_V002.json",
        ],
        [
            "canonical_dataset_v001/manifests/canonical_file_manifest.jsonl",
            "canonical_dataset_v001/manifests/canonical_import_report.json",
            "canonical_dataset_v001/manifests/canonical_video_inventory.parquet",
            "canonical_dataset_v001/manifests/missing_metadata.json",
            "canonical_dataset_v001/manifests/unmatched_metadata.json",
        ],
    ]
    manifest_row = json.loads(uploaded["canonical_dataset_v001/manifests/canonical_file_manifest.jsonl"].decode().splitlines()[0])
    inventory = pd.read_parquet(BytesIO(uploaded["canonical_dataset_v001/manifests/canonical_video_inventory.parquet"]))
    missing_audit = json.loads(uploaded["canonical_dataset_v001/manifests/missing_metadata.json"].decode())
    unmatched_audit = json.loads(uploaded["canonical_dataset_v001/manifests/unmatched_metadata.json"].decode())
    assert manifest_row["raw_repo_id"] == "org/repo"
    assert manifest_row["raw_import_id"] == "canonical_dataset_v001"
    assert manifest_row["video_path"] == "canonical_dataset_v001/raw_videos/L21_V001.mp4"
    assert manifest_row["video_upload_status"] == "uploaded"
    assert set(inventory.columns) == {
        "video_id",
        "video_filename",
        "metadata_filename",
        "video_size_bytes",
        "metadata_size_bytes",
        "canonical_backend",
        "canonical_repo_id",
        "canonical_repo_type",
        "canonical_revision",
        "canonical_prefix",
        "canonical_video_path",
        "canonical_metadata_path",
        "duration_sec",
        "fps",
        "frame_count",
        "file_size_bytes",
    }
    sorted_inventory = inventory.sort_values("video_id")
    assert sorted_inventory["canonical_prefix"].tolist() == [
        "canonical_dataset_v001",
        "canonical_dataset_v001",
    ]
    assert sorted_inventory["canonical_repo_id"].tolist() == ["org/repo", "org/repo"]
    assert sorted_inventory["canonical_video_path"].tolist() == [
        "canonical_dataset_v001/raw_videos/L21_V001.mp4",
        "canonical_dataset_v001/raw_videos/L21_V002.mp4",
    ]
    assert missing_audit["missing_metadata"] == []
    assert unmatched_audit["unmatched_metadata"] == []
    assert "kind=video index=" not in output
    assert "kind=metadata index=" not in output
    assert "Processing Files" not in output
    assert "New Data Upload" not in output
    assert "phase=scan repo_id=org/repo raw_import_id=canonical_dataset_v001" in output
    assert "phase=videos batch=1/1 uploaded=2 skipped=0 failed=0" in output
    assert "phase=metadata batch=1/1 uploaded=2 skipped=0 failed=0" in output
    assert "phase=manifests batch=1/1 uploaded=5 skipped=0 failed=0" in output
    assert "phase=done repo_id=org/repo raw_import_id=canonical_dataset_v001" in output
    assert "report_path=canonical_dataset_v001/manifests/canonical_import_report.json" in output


def test_upload_standardized_raw_to_hf_skips_existing_raw_files(monkeypatch, tmp_path):
    source_root = tmp_path / "standardized"
    (source_root / "raw_videos").mkdir(parents=True)
    (source_root / "metadata").mkdir(parents=True)
    (source_root / "raw_videos" / "A.mp4").write_bytes(b"video-a")
    (source_root / "metadata" / "A.json").write_text('{"title":"A"}\n', encoding="utf-8")
    (source_root / "raw_videos" / "B.mp4").write_bytes(b"video-b")
    (source_root / "metadata" / "B.json").write_text('{"title":"B"}\n', encoding="utf-8")
    existing = {
        Path("canonical_dataset_v001/raw_videos/A.mp4"),
        Path("canonical_dataset_v001/metadata/A.json"),
    }
    uploaded: list[str] = []

    monkeypatch.setattr("system1.ingest.source_importer.HuggingFaceDatasetArtifactStore.list_files", lambda self, prefix="": list(existing))

    def fake_upload_files(self, files, *, commit_message: str, num_threads: int = 2):
        for _source, relative_path in files:
            uploaded.append(str(relative_path))
        return [Path("hf:/org/repo") / str(relative_path) for _source, relative_path in files]

    monkeypatch.setattr("system1.ingest.source_importer.HuggingFaceDatasetArtifactStore.upload_files", fake_upload_files)

    result = upload_standardized_raw_to_hf(
        source_root,
        repo_id="org/repo",
        raw_import_id="canonical_dataset_v001",
    )

    assert result.error_count == 0
    assert "canonical_dataset_v001/raw_videos/A.mp4" not in uploaded
    assert "canonical_dataset_v001/metadata/A.json" not in uploaded
    assert "canonical_dataset_v001/raw_videos/B.mp4" in uploaded
    assert "canonical_dataset_v001/metadata/B.json" in uploaded
    assert "canonical_dataset_v001/manifests/canonical_file_manifest.jsonl" in uploaded
    assert "canonical_dataset_v001/manifests/canonical_import_report.json" in uploaded
    assert "canonical_dataset_v001/manifests/canonical_video_inventory.parquet" in uploaded
    assert "canonical_dataset_v001/manifests/missing_metadata.json" in uploaded
    assert "canonical_dataset_v001/manifests/unmatched_metadata.json" in uploaded


def test_upload_standardized_raw_to_hf_stages_drivefs_video_for_probe_and_upload(monkeypatch, tmp_path):
    monkeypatch.delenv("AIC_ALLOW_DRIVEFS_PROBE", raising=False)
    source_root = tmp_path / "standardized"
    scratch_root = tmp_path / "scratch"
    (source_root / "raw_videos").mkdir(parents=True)
    (source_root / "metadata").mkdir(parents=True)
    original_video = source_root / "raw_videos" / "A.mp4"
    original_video.write_bytes(b"video-a")
    (source_root / "metadata" / "A.json").write_text('{"title":"A"}\n', encoding="utf-8")
    staged_probe_paths: list[Path] = []
    staged_upload_paths: list[Path] = []

    monkeypatch.setattr(source_importer_module, "_is_drivefs_path", lambda path: Path(path).suffix == ".mp4")
    monkeypatch.setattr(source_importer_module, "_local_temp_parent", lambda: scratch_root)
    monkeypatch.setattr("system1.ingest.source_importer.HuggingFaceDatasetArtifactStore.list_files", lambda self, prefix="": [])

    def fake_probe(path: Path):
        staged_probe_paths.append(path)
        assert path != original_video
        assert scratch_root in path.parents
        return VideoProbe(25.0, "test", 25, False, "test", 1.0, 640, 360, False)

    def fake_upload_files(self, files, *, commit_message: str, num_threads: int = 2):
        for source, relative_path in files:
            if str(relative_path).endswith(".mp4"):
                staged_upload_paths.append(source)
                assert source != original_video
                assert scratch_root in source.parents
                assert source.exists()
        return [Path("hf:/org/repo") / str(relative_path) for _source, relative_path in files]

    monkeypatch.setattr(source_importer_module, "probe_video", fake_probe)
    monkeypatch.setattr("system1.ingest.source_importer.HuggingFaceDatasetArtifactStore.upload_files", fake_upload_files)

    result = upload_standardized_raw_to_hf(
        source_root,
        repo_id="org/repo",
        raw_import_id="canonical_dataset_v001",
    )

    assert result.error_count == 0
    assert staged_probe_paths
    assert staged_upload_paths
    assert all(not path.exists() for path in staged_probe_paths)
    assert all(not path.exists() for path in staged_upload_paths)


def test_drivefs_probe_stage_is_cleaned_when_probe_errors(monkeypatch, tmp_path):
    monkeypatch.delenv("AIC_ALLOW_DRIVEFS_PROBE", raising=False)
    scratch_root = tmp_path / "scratch"
    video_path = tmp_path / "drive" / "A.mp4"
    video_path.parent.mkdir(parents=True)
    video_path.write_bytes(b"video-a")
    staged_paths: list[Path] = []

    monkeypatch.setattr(source_importer_module, "_is_drivefs_path", lambda path: True)
    monkeypatch.setattr(source_importer_module, "_local_temp_parent", lambda: scratch_root)

    def fake_probe(path: Path):
        staged_paths.append(path)
        raise RuntimeError("probe failed")

    monkeypatch.setattr(source_importer_module, "probe_video", fake_probe)

    with pytest.raises(RuntimeError, match="probe failed"):
        source_importer_module._probe_video_drivefs_safe(video_path)

    assert staged_paths
    assert all(not path.exists() for path in staged_paths)
    assert not any(scratch_root.glob("system1_drivefs_probe_*"))


def test_upload_standardized_raw_to_hf_verbose_prints_file_detail(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("AIC_VERBOSE", "1")
    source_root = tmp_path / "standardized"
    (source_root / "raw_videos").mkdir(parents=True)
    (source_root / "metadata").mkdir(parents=True)
    (source_root / "raw_videos" / "A.mp4").write_bytes(b"video-a")
    (source_root / "metadata" / "A.json").write_text('{"title":"A"}\n', encoding="utf-8")

    monkeypatch.setattr("system1.ingest.source_importer.HuggingFaceDatasetArtifactStore.list_files", lambda self, prefix="": [])

    def fake_upload_files(self, files, *, commit_message: str, num_threads: int = 2):
        return [Path("hf:/org/repo") / str(relative_path) for _source, relative_path in files]

    monkeypatch.setattr("system1.ingest.source_importer.HuggingFaceDatasetArtifactStore.upload_files", fake_upload_files)

    result = upload_standardized_raw_to_hf(
        source_root,
        repo_id="org/repo",
        raw_import_id="canonical_dataset_v001",
    )
    output = capsys.readouterr().out

    assert result.error_count == 0
    assert "kind=video index=1/1 status=uploaded file=A.mp4" in output
    assert "kind=metadata index=1/1 status=uploaded file=A.json" in output


def test_stream_standardize_upload_raw_pairs_split_video_and_metadata_zips(monkeypatch, tmp_path):
    source_root = tmp_path / "raw_dataset"
    source_root.mkdir()
    video_zip_root = tmp_path / "video_zip_root"
    metadata_zip_root = tmp_path / "metadata_zip_root"
    (video_zip_root / "nested").mkdir(parents=True)
    (metadata_zip_root / "metadata").mkdir(parents=True)
    video_ids = [f"L21_V{index:03d}" for index in range(1, 12)]
    for video_id in video_ids:
        (video_zip_root / "nested" / f"{video_id}.mp4").write_bytes(f"video-{video_id}".encode())
    for video_id in video_ids[:-1]:
        (metadata_zip_root / "metadata" / f"{video_id}.json").write_text(
            json.dumps({"title": video_id}) + "\n",
            encoding="utf-8",
        )
    (metadata_zip_root / "metadata" / "orphan.json").write_text('{"title":"orphan"}\n', encoding="utf-8")
    shutil.make_archive(str(source_root / "Videos_L21_a"), "zip", video_zip_root)
    shutil.make_archive(str(source_root / "metadata-info-aic-b1"), "zip", metadata_zip_root)
    scratch_root = tmp_path / "scratch"
    progress_path = tmp_path / "progress" / "stream_progress.jsonl"
    uploaded: dict[str, bytes] = {}
    commit_batches: list[list[str]] = []
    probed_paths: list[Path] = []

    monkeypatch.setattr("system1.ingest.source_importer.HuggingFaceDatasetArtifactStore.list_files", lambda self, prefix="": [])

    def fake_probe(path: Path):
        probed_paths.append(path)
        assert scratch_root in path.parents
        return VideoProbe(30.0, "test", 300, False, "test", 10.0, 640, 360, False)

    def fake_upload_files(self, files, *, commit_message: str, num_threads: int = 2):
        commit_batches.append([str(relative_path) for _source, relative_path in files])
        for source, relative_path in files:
            uploaded[str(relative_path)] = source.read_bytes()
            if str(relative_path).endswith(".mp4"):
                assert scratch_root in source.parents
        return [Path("hf:/org/repo") / str(relative_path) for _source, relative_path in files]

    monkeypatch.setattr(source_importer_module, "probe_video", fake_probe)
    monkeypatch.setattr("system1.ingest.source_importer.HuggingFaceDatasetArtifactStore.upload_files", fake_upload_files)

    result = stream_standardize_upload_raw_to_hf(
        source_root,
        repo_id="org/repo",
        raw_import_id="canonical_dataset_v001",
        scratch_dir=scratch_root,
        progress_path=progress_path,
    )

    assert result.error_count == 0
    assert result.video_count == len(video_ids)
    for video_id in video_ids:
        assert f"canonical_dataset_v001/raw_videos/{video_id}.mp4" in uploaded
        assert f"canonical_dataset_v001/metadata/{video_id}.json" in uploaded
    assert json.loads(uploaded[f"canonical_dataset_v001/metadata/{video_ids[-1]}.json"])["metadata_missing"] is True
    assert "canonical_dataset_v001/manifests/canonical_file_manifest.jsonl" in uploaded
    assert "canonical_dataset_v001/manifests/canonical_import_report.json" in uploaded
    assert "canonical_dataset_v001/manifests/canonical_video_inventory.parquet" in uploaded
    missing_audit = json.loads(uploaded["canonical_dataset_v001/manifests/missing_metadata.json"].decode())
    unmatched_audit = json.loads(uploaded["canonical_dataset_v001/manifests/unmatched_metadata.json"].decode())
    assert missing_audit["missing_metadata"] == [video_ids[-1]]
    assert unmatched_audit["unmatched_metadata"] == ["orphan"]
    inventory = pd.read_parquet(BytesIO(uploaded["canonical_dataset_v001/manifests/canonical_video_inventory.parquet"]))
    assert inventory.sort_values("video_id")["video_id"].tolist() == video_ids
    assert all(not path.exists() for path in probed_paths)
    assert not any(scratch_root.glob("stream_pair_*"))
    progress_records = [json.loads(line) for line in progress_path.read_text(encoding="utf-8").splitlines()]
    assert [record["status"] for record in progress_records] == ["pass"] * len(video_ids)
    raw_pair_batches = [
        batch
        for batch in commit_batches
        if any(path.startswith("canonical_dataset_v001/raw_videos/") for path in batch)
    ]
    assert raw_pair_batches == [[
        path
        for video_id in video_ids
        for path in (
            f"canonical_dataset_v001/raw_videos/{video_id}.mp4",
            f"canonical_dataset_v001/metadata/{video_id}.json",
        )
    ]]


def test_upload_standardized_raw_rate_limit_helpers_parse_retry_after():
    class Response:
        status_code = 429
        headers = {"Retry-After": "7"}

    class RateLimitError(Exception):
        response = Response()

    error = RateLimitError("429 Too Many Requests. Retry after 7 seconds.")

    assert _is_hf_rate_limit_error(error) is True
    assert _hf_retry_sleep_seconds(error) == 7


def test_standardize_archive_source_flattens_zip_inputs(tmp_path):
    source_dir = tmp_path / "raw_dataset"
    source_dir.mkdir()
    archive_root = tmp_path / "archive_root"
    (archive_root / "nested").mkdir(parents=True)
    (archive_root / "nested" / "L21_V001.mp4").write_bytes(b"video")
    (archive_root / "nested" / "L21_V001.wav").write_bytes(b"audio")
    (archive_root / "nested" / "L21_V001.json").write_text('{"title":"sample"}\n', encoding="utf-8")
    archive_path = source_dir / "batch_a.zip"
    shutil.make_archive(str(archive_path.with_suffix("")), "zip", archive_root)

    result = standardize_archive_source(
        source_dir,
        tmp_path / "standardized",
        temp_dir=tmp_path / "temp_extract",
    )

    assert result.zip_count == 1
    assert result.video_count == 2
    assert result.metadata_count == 1
    assert (tmp_path / "standardized" / "raw_videos" / "L21_V001.mp4").exists()
    assert (tmp_path / "standardized" / "raw_videos" / "L21_V001.wav").exists()
    assert (tmp_path / "standardized" / "metadata" / "L21_V001.json").exists()
    report = json.loads(result.report_path.read_text(encoding="utf-8"))
    assert report["status"] == "pass"
    assert any(item.get("source_mode") == "zip" for item in report["items"])
    assert not any((tmp_path / "temp_extract").glob("member_stage_*"))

    rerun = standardize_archive_source(
        source_dir,
        tmp_path / "standardized",
        temp_dir=tmp_path / "temp_extract",
    )

    assert rerun.video_count == 0
    assert rerun.metadata_count == 0
    assert rerun.skipped_count == 3
    rerun_report = json.loads(rerun.report_path.read_text(encoding="utf-8"))
    assert rerun_report["status"] == "pass"
    assert {item["status"] for item in rerun_report["items"]} == {"skipped_completed"}


def test_standardize_archive_source_handles_layout_loose_duplicates_and_missing_metadata(tmp_path):
    source_dir = tmp_path / "source"
    (source_dir / "raw_videos").mkdir(parents=True)
    (source_dir / "metadata").mkdir(parents=True)
    (source_dir / "raw_videos" / "A.mp4").write_bytes(b"layout-video")
    (source_dir / "metadata" / "A.json").write_text('{"title":"layout"}\n', encoding="utf-8")
    (source_dir / "loose.mp4").write_bytes(b"loose-video")
    (source_dir / "loose.json").write_text('{"title":"loose"}\n', encoding="utf-8")
    (source_dir / "L21" / "V001.mp4").parent.mkdir(parents=True)
    (source_dir / "L21" / "V001.mp4").write_bytes(b"l21-video")
    (source_dir / "L21" / "V001.json").write_text('{"title":"l21"}\n', encoding="utf-8")
    (source_dir / "L22" / "V001.mp4").parent.mkdir(parents=True)
    (source_dir / "L22" / "V001.mp4").write_bytes(b"l22-video")
    (source_dir / "L22" / "V001.json").write_text('{"title":"l22"}\n', encoding="utf-8")
    (source_dir / "deep" / "A" / "L21").mkdir(parents=True)
    (source_dir / "deep" / "A" / "L21" / "V002.mp4").write_bytes(b"deep-a")
    (source_dir / "deep" / "B" / "L21").mkdir(parents=True)
    (source_dir / "deep" / "B" / "L21" / "V002.mp4").write_bytes(b"deep-b")
    (source_dir / "missing.mp4").write_bytes(b"missing-meta")
    (source_dir / "metadata" / "orphan.json").write_text('{"title":"orphan"}\n', encoding="utf-8")

    result = standardize_archive_source(source_dir, tmp_path / "standardized")

    assert result.error_count == 0
    for stem in ["A", "loose", "L21_V001", "L22_V001", "A_L21_V002", "B_L21_V002", "missing"]:
        assert (tmp_path / "standardized" / "raw_videos" / f"{stem}.mp4").exists()
        assert (tmp_path / "standardized" / "metadata" / f"{stem}.json").exists()
    report = json.loads(result.report_path.read_text(encoding="utf-8"))
    assert any(item.get("source_mode") == "existing_layout" for item in report["items"])
    assert any(item.get("source_mode") == "loose_files" for item in report["items"])
    assert any(item.get("kind") == "metadata_generated" and item.get("canonical_stem") == "missing" for item in report["items"])
    missing_metadata = json.loads((tmp_path / "standardized" / "missing_metadata.json").read_text(encoding="utf-8"))
    unmatched_metadata = json.loads((tmp_path / "standardized" / "unmatched_metadata.json").read_text(encoding="utf-8"))
    assert missing_metadata["source"] == "standardize_pairing_audit"
    assert missing_metadata["missing_metadata"] == ["A_L21_V002", "B_L21_V002", "missing"]
    assert unmatched_metadata["source"] == "standardize_pairing_audit"
    assert unmatched_metadata["unmatched_metadata"] == ["orphan"]


def test_standardize_archive_source_handles_mixed_zip_and_loose_inputs(tmp_path):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "loose.mp4").write_bytes(b"loose-video")
    (source_dir / "loose.json").write_text('{"title":"loose"}\n', encoding="utf-8")
    archive_root = tmp_path / "archive_root"
    archive_root.mkdir()
    (archive_root / "Z.mp4").write_bytes(b"zip-video")
    (archive_root / "Z.json").write_text('{"title":"zip"}\n', encoding="utf-8")
    shutil.make_archive(str(source_dir / "pack"), "zip", archive_root)

    result = standardize_archive_source(source_dir, tmp_path / "standardized")

    assert result.zip_count == 1
    assert result.error_count == 0
    for stem in ["loose", "Z"]:
        assert (tmp_path / "standardized" / "raw_videos" / f"{stem}.mp4").exists()
        assert (tmp_path / "standardized" / "metadata" / f"{stem}.json").exists()


def test_standardize_archive_source_resumes_completed_zip_items(tmp_path):
    source_dir = tmp_path / "raw_dataset"
    source_dir.mkdir()
    target_dir = tmp_path / "standardized"
    temp_dir = tmp_path / "temp_extract"

    def make_zip(stem: str, payload: bytes) -> Path:
        archive_root = tmp_path / f"{stem}_archive"
        if archive_root.exists():
            shutil.rmtree(archive_root)
        archive_root.mkdir()
        (archive_root / f"{stem}.mp4").write_bytes(payload)
        (archive_root / f"{stem}.json").write_text(f'{{"title":"{stem}"}}\n', encoding="utf-8")
        archive_path = source_dir / f"{stem}.zip"
        if archive_path.exists():
            archive_path.unlink()
        shutil.make_archive(str(archive_path.with_suffix("")), "zip", archive_root)
        return archive_path

    zip_a = make_zip("A", b"video-a")
    make_zip("B", b"video-b")

    first = standardize_archive_source(source_dir, target_dir, temp_dir=temp_dir, resume=True)
    assert first.zip_count == 2
    assert first.video_count == 2
    progress_path = target_dir / "standardize_progress.jsonl"
    records = [json.loads(line) for line in progress_path.read_text(encoding="utf-8").splitlines()]
    assert [record["status"] for record in records] == ["pass", "pass"]

    second = standardize_archive_source(source_dir, target_dir, temp_dir=temp_dir, resume=True)
    second_report = json.loads(second.report_path.read_text(encoding="utf-8"))
    assert second_report["processed_count"] == 0
    assert second_report["skipped_completed_count"] == 2

    (target_dir / "raw_videos" / "A.mp4").unlink()
    third = standardize_archive_source(source_dir, target_dir, temp_dir=temp_dir, resume=True)
    third_report = json.loads(third.report_path.read_text(encoding="utf-8"))
    assert third_report["processed_count"] == 1
    assert third_report["skipped_completed_count"] == 1
    assert (target_dir / "raw_videos" / "A.mp4").exists()

    make_zip("A", b"video-a-changed")
    os.utime(zip_a, None)
    fourth = standardize_archive_source(source_dir, target_dir, temp_dir=temp_dir, resume=True, overwrite=True)
    fourth_report = json.loads(fourth.report_path.read_text(encoding="utf-8"))
    assert fourth_report["processed_count"] == 1
    assert fourth_report["skipped_completed_count"] == 1
    assert (target_dir / "raw_videos" / "A.mp4").read_bytes() == b"video-a-changed"


def test_standardize_archives_cli_fails_on_partial_unless_allowed(tmp_path):
    source_dir = tmp_path / "raw_dataset"
    source_dir.mkdir()
    (source_dir / "broken.zip").write_text("not a zip", encoding="utf-8")
    target_dir = tmp_path / "standardized"

    result = runner.invoke(
        app,
        [
            "standardize-archives",
            "--source-dir",
            str(source_dir),
            "--target-dir",
            str(target_dir),
        ],
    )
    assert result.exit_code == 1
    assert "Archive standardization failed with errors" in result.output

    allowed = runner.invoke(
        app,
        [
            "standardize-archives",
            "--source-dir",
            str(source_dir),
            "--target-dir",
            str(target_dir),
            "--allow-partial",
        ],
    )
    assert allowed.exit_code == 0


def test_shadow_google_drive_folder_copies_nested_regular_files(tmp_path):
    class FakeExecute:
        def __init__(self, payload):
            self.payload = payload

        def execute(self):
            return self.payload

    class FakeFiles:
        def __init__(self):
            self.metadata = {
                "src": {"id": "src", "name": "source", "mimeType": "application/vnd.google-apps.folder"},
                "dest": {"id": "dest", "name": "destination", "mimeType": "application/vnd.google-apps.folder"},
            }
            self.children = {
                "src": [
                    {"id": "folder_a", "name": "folder_a", "mimeType": "application/vnd.google-apps.folder"},
                    {"id": "file_1", "name": "video.mp4", "mimeType": "video/mp4"},
                    {"id": "doc_1", "name": "notes", "mimeType": "application/vnd.google-apps.document"},
                ],
                "folder_a": [
                    {"id": "file_2", "name": "meta.json", "mimeType": "application/json"},
                ],
            }
            self.created: list[dict[str, object]] = []
            self.copied: list[tuple[str, dict[str, object]]] = []

        def get(self, fileId, fields, supportsAllDrives=False):
            assert supportsAllDrives is True
            return FakeExecute(self.metadata[fileId])

        def list(self, q, fields, pageToken=None, supportsAllDrives=False, includeItemsFromAllDrives=False, pageSize=None):
            assert supportsAllDrives is True
            assert includeItemsFromAllDrives is True
            assert pageSize == 1000
            assert "parents" in fields
            folder_id = q.split("'", 2)[1]
            return FakeExecute({"files": self.children.get(folder_id, [])})

        def create(self, body, fields, supportsAllDrives=False):
            assert supportsAllDrives is True
            new_id = f"new_{body['name']}"
            self.created.append(body)
            return FakeExecute({"id": new_id})

        def copy(self, fileId, body, supportsAllDrives=False):
            assert supportsAllDrives is True
            self.copied.append((fileId, body))
            return FakeExecute({"id": f"copy_{fileId}"})

    class FakeService:
        def __init__(self):
            self.fake_files = FakeFiles()

        def files(self):
            return self.fake_files

    service = FakeService()
    result = shadow_google_drive_folder(
        "src",
        "dest",
        report_path=tmp_path / "drive_shadow_report.json",
        service=service,
    )

    assert result.copied_files == 2
    assert result.created_folders == 1
    assert result.skipped_google_apps == 1
    assert service.fake_files.copied[0][0] == "file_2"
    assert service.fake_files.copied[1][0] == "file_1"
    report = json.loads(result.report_path.read_text(encoding="utf-8"))
    assert report["status"] == "pass"


def test_shadow_google_drive_folder_skips_existing_matching_targets(tmp_path):
    class FakeExecute:
        def __init__(self, payload):
            self.payload = payload

        def execute(self):
            return self.payload

    class FakeFiles:
        def __init__(self):
            self.metadata = {
                "src": {"id": "src", "name": "source", "mimeType": "application/vnd.google-apps.folder"},
                "dest": {"id": "dest", "name": "destination", "mimeType": "application/vnd.google-apps.folder"},
            }
            self.children = {
                "src": [
                    {"id": "folder_a", "name": "folder_a", "mimeType": "application/vnd.google-apps.folder"},
                    {"id": "file_1", "name": "video.mp4", "mimeType": "video/mp4", "size": "5"},
                ],
                "folder_a": [
                    {"id": "file_2", "name": "meta.json", "mimeType": "application/json", "size": "2"},
                ],
                "dest": [
                    {"id": "existing_folder_a", "name": "folder_a", "mimeType": "application/vnd.google-apps.folder"},
                    {"id": "existing_file_1", "name": "video.mp4", "mimeType": "video/mp4", "size": "5"},
                ],
                "existing_folder_a": [
                    {"id": "existing_file_2", "name": "meta.json", "mimeType": "application/json", "size": "2"},
                ],
            }
            self.created: list[dict[str, object]] = []
            self.copied: list[tuple[str, dict[str, object]]] = []

        def get(self, fileId, fields, supportsAllDrives=False):
            assert supportsAllDrives is True
            return FakeExecute(self.metadata[fileId])

        def list(self, q, fields, pageToken=None, supportsAllDrives=False, includeItemsFromAllDrives=False, pageSize=None):
            assert supportsAllDrives is True
            assert includeItemsFromAllDrives is True
            assert pageSize == 1000
            assert "parents" in fields
            folder_id = q.split("'", 2)[1]
            return FakeExecute({"files": self.children.get(folder_id, [])})

        def create(self, body, fields, supportsAllDrives=False):
            assert supportsAllDrives is True
            self.created.append(body)
            return FakeExecute({"id": f"new_{body['name']}"})

        def copy(self, fileId, body, supportsAllDrives=False):
            assert supportsAllDrives is True
            self.copied.append((fileId, body))
            return FakeExecute({"id": f"copy_{fileId}"})

    class FakeService:
        def __init__(self):
            self.fake_files = FakeFiles()

        def files(self):
            return self.fake_files

    service = FakeService()
    result = shadow_google_drive_folder(
        "src",
        "dest",
        report_path=tmp_path / "drive_shadow_report.json",
        service=service,
    )

    assert result.copied_files == 0
    assert result.created_folders == 0
    assert result.skipped_existing == 3
    assert result.error_count == 0
    assert service.fake_files.created == []
    assert service.fake_files.copied == []


def test_shadow_google_drive_folder_reports_empty_source_as_failure(tmp_path):
    class FakeExecute:
        def __init__(self, payload):
            self.payload = payload

        def execute(self):
            return self.payload

    class FakeFiles:
        def __init__(self):
            self.metadata = {
                "src": {"id": "src", "name": "source", "mimeType": "application/vnd.google-apps.folder"},
                "dest": {"id": "dest", "name": "destination", "mimeType": "application/vnd.google-apps.folder"},
            }
            self.children = {"src": [], "dest": []}

        def get(self, fileId, fields, supportsAllDrives=False):
            assert supportsAllDrives is True
            return FakeExecute(self.metadata[fileId])

        def list(self, q, fields, pageToken=None, supportsAllDrives=False, includeItemsFromAllDrives=False, pageSize=None):
            assert supportsAllDrives is True
            assert includeItemsFromAllDrives is True
            assert pageSize == 1000
            folder_id = q.split("'", 2)[1]
            return FakeExecute({"files": self.children.get(folder_id, [])})

    class FakeService:
        def __init__(self):
            self.fake_files = FakeFiles()

        def files(self):
            return self.fake_files

    result = shadow_google_drive_folder(
        "src",
        "dest",
        report_path=tmp_path / "drive_shadow_report.json",
        service=FakeService(),
    )

    assert result.copied_files == 0
    assert result.created_folders == 0
    assert result.skipped_existing == 0
    assert result.skipped_google_apps == 0
    assert result.error_count == 1
    report = json.loads(result.report_path.read_text(encoding="utf-8"))
    assert report["status"] == "fail"
    assert report["items"][0]["kind"] == "source_empty_or_not_listable"


def test_drive_shadow_cli_fails_on_partial_unless_allowed(monkeypatch, tmp_path):
    from system1.commands import imports as import_commands

    def fake_shadow_google_drive_folder(source_folder_id, dest_folder_id, *, report_path, service=None):
        Path(report_path).write_text('{"status":"partial"}\n', encoding="utf-8")
        return DriveShadowResult(
            source_folder_id=source_folder_id,
            dest_folder_id=dest_folder_id,
            copied_files=0,
            created_folders=0,
            skipped_google_apps=0,
            skipped_existing=0,
            error_count=1,
            report_path=Path(report_path),
        )

    monkeypatch.setattr(import_commands, "shadow_google_drive_folder", fake_shadow_google_drive_folder)

    report_path = tmp_path / "drive_shadow_report.json"
    result = runner.invoke(
        app,
        [
            "drive-shadow",
            "--source-folder-id",
            "src",
            "--dest-folder-id",
            "dest",
            "--report-path",
            str(report_path),
        ],
    )
    assert result.exit_code == 1
    assert "Drive shadow failed with errors" in result.output

    allowed = runner.invoke(
        app,
        [
            "drive-shadow",
            "--source-folder-id",
            "src",
            "--dest-folder-id",
            "dest",
            "--report-path",
            str(report_path),
            "--allow-partial",
        ],
    )
    assert allowed.exit_code == 0


def test_drive_shadow_cli_fails_when_no_actions(monkeypatch, tmp_path):
    from system1.commands import imports as import_commands

    def fake_shadow_google_drive_folder(source_folder_id, dest_folder_id, *, report_path, service=None):
        Path(report_path).write_text('{"status":"fail"}\n', encoding="utf-8")
        return DriveShadowResult(
            source_folder_id=source_folder_id,
            dest_folder_id=dest_folder_id,
            copied_files=0,
            created_folders=0,
            skipped_google_apps=0,
            skipped_existing=0,
            error_count=0,
            report_path=Path(report_path),
        )

    monkeypatch.setattr(import_commands, "shadow_google_drive_folder", fake_shadow_google_drive_folder)

    report_path = tmp_path / "drive_shadow_report.json"
    result = runner.invoke(
        app,
        [
            "drive-shadow",
            "--source-folder-id",
            "src",
            "--dest-folder-id",
            "dest",
            "--report-path",
            str(report_path),
        ],
    )
    assert result.exit_code == 1
    assert "Drive shadow made no changes or skips" in result.output

    allowed = runner.invoke(
        app,
        [
            "drive-shadow",
            "--source-folder-id",
            "src",
            "--dest-folder-id",
            "dest",
            "--report-path",
            str(report_path),
            "--allow-partial",
        ],
    )
    assert allowed.exit_code == 0


def test_ingest_from_canonical_hf_manifest(monkeypatch, tmp_path):
    from system1.ingest.pipeline import run_ingestion

    source_root = tmp_path / "canonical_repo"
    (source_root / "raw_videos").mkdir(parents=True)
    (source_root / "metadata").mkdir(parents=True)
    (source_root / "raw_videos" / "L21_V001.mp4").write_bytes(b"not-a-real-video")
    (source_root / "metadata" / "L21_V001.json").write_text('{"title":"sample"}\n', encoding="utf-8")
    manifest = {
        "video_id": "L21_V001",
        "video_filename": "L21_V001.mp4",
        "metadata_filename": "L21_V001.json",
        "video_path": "raw_videos/L21_V001.mp4",
        "metadata_path": "metadata/L21_V001.json",
        "video_size_bytes": (source_root / "raw_videos" / "L21_V001.mp4").stat().st_size,
        "metadata_size_bytes": (source_root / "metadata" / "L21_V001.json").stat().st_size,
        "status": "pass",
    }
    (source_root / "manifests").mkdir()
    (source_root / "manifests" / "canonical_file_manifest.jsonl").write_text(json.dumps(manifest) + "\n", encoding="utf-8")
    (source_root / "manifests" / "missing_metadata.json").write_text(
        json.dumps({"kind": "missing_metadata", "count": 0, "missing_metadata": []}) + "\n",
        encoding="utf-8",
    )
    (source_root / "manifests" / "unmatched_metadata.json").write_text(
        json.dumps({"kind": "unmatched_metadata", "count": 0, "unmatched_metadata": []}) + "\n",
        encoding="utf-8",
    )
    pd.DataFrame(
        [
            {
                "video_id": "L21_V001",
                "canonical_video_path": "raw_videos/L21_V001.mp4",
                "canonical_metadata_path": "metadata/L21_V001.json",
                "duration_sec": 12.5,
                "fps": 25.0,
                "frame_count": 313,
                "file_size_bytes": (source_root / "raw_videos" / "L21_V001.mp4").stat().st_size,
            }
        ]
    ).to_parquet(source_root / "manifests" / "canonical_video_inventory.parquet", index=False)
    download_calls: list[str] = []

    class FakeHFStore:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def download_file(self, relative_path, target: Path, *, cache_dir=None):
            download_calls.append(str(relative_path))
            source = source_root / str(relative_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            return target

    monkeypatch.setattr("system1.ingest.pipeline.HuggingFaceDatasetArtifactStore", FakeHFStore)

    report_path = run_ingestion(
        tmp_path / "output",
        mode="debug_small_sample",
        canonical_hf_repo_id="org/repo",
        canonical_hf_prefix="",
        canonical_staging_root=tmp_path / "staging",
    )
    release_dir = report_path.parent.parent
    videos = pd.read_parquet(release_dir / "tables" / "videos.parquet")
    mapping = pd.read_parquet(release_dir / "raw_mapping" / "media_store_manifest.parquet")

    assert videos["video_id"].tolist() == ["L21_V001"]
    assert videos.loc[0, "fps_detected"] == 25.0
    assert videos.loc[0, "duration_seconds"] == 12.5
    assert videos.loc[0, "frame_count"] == 313
    assert mapping.loc[0, "canonical_backend"] == "hf_dataset"
    assert mapping.loc[0, "canonical_repo_id"] == "org/repo"
    missing_audit = json.loads((release_dir / "manifests" / "missing_metadata.json").read_text(encoding="utf-8"))
    unmatched_audit = json.loads((release_dir / "manifests" / "unmatched_metadata.json").read_text(encoding="utf-8"))
    assert missing_audit["missing_metadata"] == []
    assert unmatched_audit["unmatched_metadata"] == []
    assert download_calls == [
        "manifests/canonical_file_manifest.jsonl",
        "manifests/canonical_video_inventory.parquet",
        "manifests/missing_metadata.json",
        "manifests/unmatched_metadata.json",
        "metadata/L21_V001.json",
    ]


def test_ingest_from_canonical_hf_manifest_strips_store_prefix(monkeypatch, tmp_path):
    from system1.ingest.pipeline import run_ingestion

    source_root = tmp_path / "canonical_repo"
    prefix = "canonical_dataset_v002"
    prefixed_root = source_root / prefix
    (prefixed_root / "raw_videos").mkdir(parents=True)
    (prefixed_root / "metadata").mkdir(parents=True)
    rows = [
        {
            "video_id": "L21_V001",
            "video_filename": "L21_V001.mp4",
            "metadata_filename": "L21_V001.json",
            "video_path": f"{prefix}/raw_videos/L21_V001.mp4",
            "metadata_path": f"{prefix}/metadata/L21_V001.json",
            "status": "pass",
        },
        {
            "video_id": "L21_V002",
            "video_filename": "L21_V002.mp4",
            "metadata_filename": "L21_V002.json",
            "video_path": "raw_videos/L21_V002.mp4",
            "metadata_path": "metadata/L21_V002.json",
            "status": "pass",
        },
    ]
    for row in rows:
        (prefixed_root / "raw_videos" / row["video_filename"]).write_bytes(b"not-a-real-video")
        (prefixed_root / "metadata" / row["metadata_filename"]).write_text(
            json.dumps({"title": row["video_id"]}) + "\n",
            encoding="utf-8",
        )
    (prefixed_root / "manifests").mkdir()
    (prefixed_root / "manifests" / "canonical_file_manifest.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )
    pd.DataFrame(
        [
            {
                "video_id": "L21_V001",
                "canonical_video_path": f"{prefix}/raw_videos/L21_V001.mp4",
                "canonical_metadata_path": f"{prefix}/metadata/L21_V001.json",
                "duration_sec": 10.0,
                "fps": 25.0,
                "frame_count": 250,
                "file_size_bytes": 1,
            },
            {
                "video_id": "L21_V002",
                "canonical_video_path": "raw_videos/L21_V002.mp4",
                "canonical_metadata_path": "metadata/L21_V002.json",
                "duration_sec": 20.0,
                "fps": 30.0,
                "frame_count": 600,
                "file_size_bytes": 1,
            },
        ]
    ).to_parquet(prefixed_root / "manifests" / "canonical_video_inventory.parquet", index=False)
    download_calls: list[str] = []

    class FakeHFStore:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def download_file(self, relative_path, target: Path, *, cache_dir=None):
            download_calls.append(str(relative_path))
            source = source_root / self.kwargs["prefix"] / str(relative_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            return target

    monkeypatch.setattr("system1.ingest.pipeline.HuggingFaceDatasetArtifactStore", FakeHFStore)

    report_path = run_ingestion(
        tmp_path / "output",
        mode="debug_small_sample",
        canonical_hf_repo_id="org/repo",
        canonical_hf_prefix=prefix,
        canonical_staging_root=tmp_path / "staging",
        max_workers=1,
    )
    release_dir = report_path.parent.parent
    mapping = pd.read_parquet(release_dir / "raw_mapping" / "media_store_manifest.parquet").sort_values("video_id")

    assert download_calls == [
        "manifests/canonical_file_manifest.jsonl",
        "manifests/canonical_video_inventory.parquet",
        "manifests/missing_metadata.json",
        "manifests/unmatched_metadata.json",
        "metadata/L21_V001.json",
        "metadata/L21_V002.json",
    ]
    assert mapping["canonical_video_path"].tolist() == ["raw_videos/L21_V001.mp4", "raw_videos/L21_V002.mp4"]
    assert mapping["canonical_metadata_path"].tolist() == ["metadata/L21_V001.json", "metadata/L21_V002.json"]


def test_ingest_from_canonical_hf_manifest_requires_inventory_unless_fallback_enabled(monkeypatch, tmp_path):
    from system1.ingest.pipeline import run_ingestion

    monkeypatch.delenv("AIC_ALLOW_HF_VIDEO_DOWNLOAD_FOR_PROBE", raising=False)
    manifest = {
        "video_id": "L21_V001",
        "video_filename": "L21_V001.mp4",
        "metadata_filename": "L21_V001.json",
        "video_path": "raw_videos/L21_V001.mp4",
        "metadata_path": "metadata/L21_V001.json",
        "status": "pass",
    }
    download_calls: list[str] = []

    class FakeHFStore:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def download_file(self, relative_path, target: Path, *, cache_dir=None):
            download_calls.append(str(relative_path))
            if str(relative_path).endswith("canonical_video_inventory.parquet"):
                raise FileNotFoundError(str(relative_path))
            target.parent.mkdir(parents=True, exist_ok=True)
            if str(relative_path).endswith("canonical_file_manifest.jsonl"):
                target.write_text(json.dumps(manifest) + "\n", encoding="utf-8")
            elif str(relative_path).endswith(".json"):
                target.write_text('{"title":"sample"}\n', encoding="utf-8")
            else:
                target.write_bytes(b"not-a-real-video")
            return target

    monkeypatch.setattr("system1.ingest.pipeline.HuggingFaceDatasetArtifactStore", FakeHFStore)

    with pytest.raises(FileNotFoundError, match="canonical_video_inventory.parquet"):
        run_ingestion(
            tmp_path / "output_fail",
            mode="debug_small_sample",
            canonical_hf_repo_id="org/repo",
            canonical_staging_root=tmp_path / "staging_fail",
            max_workers=1,
        )
    assert "raw_videos/L21_V001.mp4" not in download_calls

    download_calls.clear()
    monkeypatch.setenv("AIC_ALLOW_HF_VIDEO_DOWNLOAD_FOR_PROBE", "1")
    report_path = run_ingestion(
        tmp_path / "output_fallback",
        mode="debug_small_sample",
        canonical_hf_repo_id="org/repo",
        canonical_staging_root=tmp_path / "staging_fallback",
        max_workers=1,
    )

    assert report_path.exists()
    assert "raw_videos/L21_V001.mp4" in download_calls


def test_ingest_from_canonical_hf_manifest_cleans_staging_and_cache(monkeypatch, tmp_path):
    from system1.ingest.pipeline import run_ingestion

    monkeypatch.delenv("AIC_KEEP_CANONICAL_STAGING", raising=False)
    staging_root = tmp_path / "staging"
    manifest = {
        "video_id": "L21_V001",
        "video_filename": "L21_V001.mp4",
        "metadata_filename": "L21_V001.json",
        "video_path": "raw_videos/L21_V001.mp4",
        "metadata_path": "metadata/L21_V001.json",
        "status": "pass",
    }
    cache_dirs: list[Path] = []
    targets: list[Path] = []

    class FakeHFStore:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def download_file(self, relative_path, target: Path, *, cache_dir=None):
            if cache_dir is not None:
                cache_path = Path(cache_dir)
                cache_path.mkdir(parents=True, exist_ok=True)
                (cache_path / "cached.bin").write_bytes(b"cached")
                cache_dirs.append(cache_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            if str(relative_path).endswith("canonical_file_manifest.jsonl"):
                target.write_text(json.dumps(manifest) + "\n", encoding="utf-8")
            elif str(relative_path).endswith("canonical_video_inventory.parquet"):
                pd.DataFrame(
                    [
                        {
                            "video_id": "L21_V001",
                            "canonical_video_path": "raw_videos/L21_V001.mp4",
                            "canonical_metadata_path": "metadata/L21_V001.json",
                            "duration_sec": 1.0,
                            "fps": 25.0,
                            "frame_count": 25,
                            "file_size_bytes": 16,
                        }
                    ]
                ).to_parquet(target, index=False)
            elif str(relative_path).endswith(".json"):
                target.write_text('{"title":"sample"}\n', encoding="utf-8")
            else:
                target.write_bytes(b"not-a-real-video")
            targets.append(target)
            return target

    monkeypatch.setattr("system1.ingest.pipeline.HuggingFaceDatasetArtifactStore", FakeHFStore)

    report_path = run_ingestion(
        tmp_path / "output",
        mode="debug_small_sample",
        canonical_hf_repo_id="org/repo",
        canonical_staging_root=staging_root,
        max_workers=1,
    )

    assert report_path.exists()
    assert cache_dirs
    assert targets
    assert all(not path.exists() for path in cache_dirs)
    assert all(not path.exists() for path in targets)
    assert list(staging_root.iterdir()) == []


def test_ingest_from_canonical_hf_manifest_can_keep_staging_and_cache(monkeypatch, tmp_path):
    from system1.ingest.pipeline import run_ingestion

    monkeypatch.setenv("AIC_KEEP_CANONICAL_STAGING", "1")
    staging_root = tmp_path / "staging"
    manifest = {
        "video_id": "L21_V001",
        "video_filename": "L21_V001.mp4",
        "metadata_filename": "L21_V001.json",
        "video_path": "raw_videos/L21_V001.mp4",
        "metadata_path": "metadata/L21_V001.json",
        "status": "pass",
    }
    cache_dirs: list[Path] = []
    targets: list[Path] = []

    class FakeHFStore:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def download_file(self, relative_path, target: Path, *, cache_dir=None):
            if cache_dir is not None:
                cache_path = Path(cache_dir)
                cache_path.mkdir(parents=True, exist_ok=True)
                (cache_path / "cached.bin").write_bytes(b"cached")
                cache_dirs.append(cache_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            if str(relative_path).endswith("canonical_file_manifest.jsonl"):
                target.write_text(json.dumps(manifest) + "\n", encoding="utf-8")
            elif str(relative_path).endswith("canonical_video_inventory.parquet"):
                pd.DataFrame(
                    [
                        {
                            "video_id": "L21_V001",
                            "canonical_video_path": "raw_videos/L21_V001.mp4",
                            "canonical_metadata_path": "metadata/L21_V001.json",
                            "duration_sec": 1.0,
                            "fps": 25.0,
                            "frame_count": 25,
                            "file_size_bytes": 16,
                        }
                    ]
                ).to_parquet(target, index=False)
            elif str(relative_path).endswith(".json"):
                target.write_text('{"title":"sample"}\n', encoding="utf-8")
            else:
                target.write_bytes(b"not-a-real-video")
            targets.append(target)
            return target

    monkeypatch.setattr("system1.ingest.pipeline.HuggingFaceDatasetArtifactStore", FakeHFStore)

    report_path = run_ingestion(
        tmp_path / "output",
        mode="debug_small_sample",
        canonical_hf_repo_id="org/repo",
        canonical_staging_root=staging_root,
        max_workers=1,
    )

    assert report_path.exists()
    assert cache_dirs
    assert targets
    assert any(path.exists() for path in cache_dirs)
    assert any(path.name == "L21_V001.json" and path.exists() for path in targets)
    assert all(path.name != "L21_V001.mp4" for path in targets)
    assert any(staging_root.iterdir())


def test_release_sync_uploads_and_restores_release(monkeypatch, tmp_path):
    from system1.release.sync import download_release_from_hf, upload_release_to_hf

    release_dir = tmp_path / "output" / "competition_dataset_v001"
    (release_dir / "tables").mkdir(parents=True)
    (release_dir / "manifests").mkdir(parents=True)
    (release_dir / "tables" / "videos.parquet").write_bytes(b"videos")
    (release_dir / "manifests" / "dataset_report.json").write_text('{"ok": true}\n', encoding="utf-8")
    uploaded: dict[str, bytes] = {}

    class FakeHFStore:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def upload_file(self, source: Path, relative_path):
            uploaded[str(relative_path)] = source.read_bytes()
            return Path("hf:/org/repo") / str(relative_path)

        def list_files(self, prefix=""):
            return [Path(path) for path in uploaded if path.startswith(str(prefix))]

        def download_file(self, relative_path, target: Path, *, cache_dir=None):
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(uploaded[str(relative_path)])
            return target

    monkeypatch.setattr("system1.release.sync.HuggingFaceDatasetArtifactStore", FakeHFStore)

    upload = upload_release_to_hf(release_dir, repo_id="org/repo")
    restored_root = tmp_path / "restored"
    restore = download_release_from_hf(restored_root, release_id="competition_dataset_v001", repo_id="org/repo")

    assert upload.file_count == 2
    assert "releases/competition_dataset_v001/tables/videos.parquet" in uploaded
    assert "releases/competition_dataset_v001/manifests/dataset_report.json" in uploaded
    assert "releases/competition_dataset_v001/manifests/release_sync_manifest.json" in uploaded
    assert (restored_root / "competition_dataset_v001" / "tables" / "videos.parquet").read_bytes() == b"videos"
    assert restore.file_count == 3


def test_phase00_ingestion_sync_maps_legacy_release_layout(monkeypatch, tmp_path):
    from system1.release.sync import upload_phase00_ingestion_to_hf

    release_dir = tmp_path / "output" / "canonical_release_v003"
    (release_dir / "tables").mkdir(parents=True)
    (release_dir / "raw_mapping").mkdir(parents=True)
    (release_dir / "manifests").mkdir(parents=True)
    (release_dir / "tables" / "videos.parquet").write_bytes(b"videos")
    (release_dir / "raw_mapping" / "media_store_manifest.parquet").write_bytes(b"mapping")
    (release_dir / "frame_timeline").mkdir()
    (release_dir / "frame_timeline" / "L21_V001.parquet").write_bytes(b"timeline")
    (release_dir / "manifests" / "batch_manifest.csv").write_text("batch_id\n", encoding="utf-8")
    (release_dir / "manifests" / "batch_000.txt").write_text("L21_V001\n", encoding="utf-8")
    (release_dir / "manifests" / "dataset_report.json").write_text('{"ok": true}\n', encoding="utf-8")
    (release_dir / "manifests" / "ingestion_errors.jsonl").write_text("", encoding="utf-8")
    (release_dir / "manifests" / "missing_metadata.json").write_text('{"count": 0}\n', encoding="utf-8")
    (release_dir / "manifests" / "unmatched_metadata.json").write_text('{"count": 0}\n', encoding="utf-8")
    uploaded: dict[str, bytes] = {}

    class FakeHFStore:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def upload_file(self, source: Path, relative_path):
            uploaded[str(relative_path)] = source.read_bytes()
            return Path("hf:/org/repo") / str(relative_path)

    monkeypatch.setattr("system1.release.sync.HuggingFaceDatasetArtifactStore", FakeHFStore)

    result = upload_phase00_ingestion_to_hf(release_dir, repo_id="org/repo")

    assert result.file_count == 9
    assert "canonical_release_v003/phase00_ingestion/tables/videos.parquet" in uploaded
    assert "canonical_release_v003/phase00_ingestion/raw_mapping/media_store_manifest.parquet" in uploaded
    assert "canonical_release_v003/phase00_ingestion/frame_timeline/L21_V001.parquet" in uploaded
    assert "canonical_release_v003/phase00_ingestion/manifests/batch_manifest.csv" in uploaded
    assert "canonical_release_v003/phase00_ingestion/manifests/batch_000.txt" in uploaded
    assert "canonical_release_v003/phase00_ingestion/reports/dataset_report.json" in uploaded
    assert "canonical_release_v003/phase00_ingestion/reports/ingestion_errors.jsonl" in uploaded
    assert "canonical_release_v003/phase00_ingestion/reports/missing_metadata.json" in uploaded
    assert "canonical_release_v003/phase00_ingestion/reports/unmatched_metadata.json" in uploaded
    assert "canonical_release_v003/phase00_ingestion/reports/phase00_sync_manifest.json" in uploaded
    assert not any(path.startswith("releases/") for path in uploaded)


def test_phase00_ingestion_restore_materializes_active_layout(monkeypatch, tmp_path):
    from system1.release.sync import download_phase00_ingestion_from_hf

    uploaded = {
        "canonical_release_v003/phase00_ingestion/tables/videos.parquet": b"videos",
        "canonical_release_v003/phase00_ingestion/raw_mapping/media_store_manifest.parquet": b"mapping",
        "canonical_release_v003/phase00_ingestion/frame_timeline/L21_V001.parquet": b"timeline",
        "canonical_release_v003/phase00_ingestion/manifests/batch_manifest.csv": b"batch_id\n",
        "canonical_release_v003/phase00_ingestion/manifests/batch_000.txt": b"L21_V001\n",
        "canonical_release_v003/phase00_ingestion/reports/dataset_report.json": b'{"ok": true}\n',
    }

    class FakeHFStore:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def list_files(self, prefix=""):
            return [Path(path) for path in uploaded if path.startswith(str(prefix))]

        def download_file(self, relative_path, target: Path, *, cache_dir=None):
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(uploaded[str(relative_path)])
            return target

    monkeypatch.setattr("system1.release.sync.HuggingFaceDatasetArtifactStore", FakeHFStore)

    result = download_phase00_ingestion_from_hf(
        tmp_path / "output",
        release_id="canonical_release_v003",
        repo_id="org/repo",
    )
    release_dir = result.release_dir

    assert (release_dir / "phase00_ingestion" / "tables" / "videos.parquet").read_bytes() == b"videos"
    assert (release_dir / "phase00_ingestion" / "raw_mapping" / "media_store_manifest.parquet").read_bytes() == b"mapping"
    assert (release_dir / "phase00_ingestion" / "frame_timeline" / "L21_V001.parquet").read_bytes() == b"timeline"
    assert (release_dir / "phase00_ingestion" / "manifests" / "batch_000.txt").read_text(encoding="utf-8") == "L21_V001\n"
    assert (release_dir / "phase00_ingestion" / "reports" / "dataset_report.json").exists()
    assert (release_dir / "tables" / "videos.parquet").read_bytes() == b"videos"
    assert (release_dir / "raw_mapping" / "media_store_manifest.parquet").read_bytes() == b"mapping"
    assert (release_dir / "frame_timeline" / "L21_V001.parquet").read_bytes() == b"timeline"
    assert (release_dir / "manifests" / "batch_manifest.csv").read_text(encoding="utf-8") == "batch_id\n"
    assert (release_dir / "manifests" / "batch_000.txt").read_text(encoding="utf-8") == "L21_V001\n"
    assert not (release_dir / "reports" / "dataset_report.json").exists()


def test_phase00_ingestion_restore_no_overwrite_protects_active_layout(monkeypatch, tmp_path):
    from system1.release.sync import download_phase00_ingestion_from_hf

    uploaded = {
        "canonical_release_v003/phase00_ingestion/tables/videos.parquet": b"videos",
        "canonical_release_v003/phase00_ingestion/manifests/batch_000.txt": b"L21_V001\n",
    }

    class FakeHFStore:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def list_files(self, prefix=""):
            return [Path(path) for path in uploaded if path.startswith(str(prefix))]

        def download_file(self, relative_path, target: Path, *, cache_dir=None):
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(uploaded[str(relative_path)])
            return target

    output_dir = tmp_path / "output"
    active_batch = output_dir / "canonical_release_v003" / "manifests" / "batch_000.txt"
    active_batch.parent.mkdir(parents=True)
    active_batch.write_text("stale\n", encoding="utf-8")
    monkeypatch.setattr("system1.release.sync.HuggingFaceDatasetArtifactStore", FakeHFStore)

    with pytest.raises(FileExistsError, match="batch_000.txt"):
        download_phase00_ingestion_from_hf(
            output_dir,
            release_id="canonical_release_v003",
            repo_id="org/repo",
            overwrite=False,
        )

    assert active_batch.read_text(encoding="utf-8") == "stale\n"


def test_restore_phase00_ingestion_cli_unblocks_process_batch_manifest_check(monkeypatch, tmp_path):
    uploaded = {
        "canonical_release_v003/phase00_ingestion/tables/videos.parquet": b"videos",
        "canonical_release_v003/phase00_ingestion/raw_mapping/media_store_manifest.parquet": b"mapping",
        "canonical_release_v003/phase00_ingestion/manifests/batch_000.txt": b"L21_V001\n",
    }

    class FakeHFStore:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def list_files(self, prefix=""):
            return [Path(path) for path in uploaded if path.startswith(str(prefix))]

        def download_file(self, relative_path, target: Path, *, cache_dir=None):
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(uploaded[str(relative_path)])
            return target

    def fake_process_structure_batch(output, **kwargs):
        report_path = Path(output) / "canonical_release_v003" / "manifests" / "worker_reports" / "structure_batch_000_worker_000.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text('{"status": "completed"}\n', encoding="utf-8")
        return report_path

    monkeypatch.setenv("AIC_RELEASE_ID", "canonical_release_v003")
    monkeypatch.setattr("system1.release.sync.HuggingFaceDatasetArtifactStore", FakeHFStore)
    monkeypatch.setattr("system1.commands.pipeline.process_structure_batch", fake_process_structure_batch)

    restore = runner.invoke(
        app,
        [
            "restore-phase00-ingestion",
            "--output",
            str(tmp_path / "output"),
            "--release-id",
            "canonical_release_v003",
            "--hf-repo-id",
            "org/repo",
        ],
    )
    assert restore.exit_code == 0, restore.output

    process = invoke_app([
        "process-batch",
        "--batch-id",
        "batch_000",
        "--output",
        str(tmp_path / "output"),
    ])
    assert process.exit_code == 0, process.output
    assert "missing batch manifest" not in process.output
