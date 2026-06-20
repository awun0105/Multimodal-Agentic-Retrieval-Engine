import shutil
import json
import sqlite3
import csv
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import numpy as np
import pytest
from typer.testing import CliRunner

from system1.cli import app
from system1.config import REQUIRED_CONFIGS, load_configs, load_provider_plan
from system1.ingest.discovery import discover_media_inputs_tolerant, discover_paired_inputs
from system1.ingest.source_importer import (
    ArchiveStandardizeResult,
    DriveShadowResult,
    _hf_retry_sleep_seconds,
    _is_hf_rate_limit_error,
    import_organizer_source,
    shadow_google_drive_folder,
    standardize_archive_source,
    upload_standardized_raw_to_hf,
)
from system1.release.artifacts import write_worker_artifacts
from system1.release.mini_seed import build_mini_seed
from system1.validation.release_validator import validate_release

runner = CliRunner()


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
        "00_master_ingestion_and_assignment.ipynb": [
            "drive-shadow",
            "standardize-archives",
            "ingest",
            "assign-batches",
            "sync-release",
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
        if path.name != "00_master_ingestion_and_assignment.ipynb":
            assert "worker_id" in joined
            assert "batch_id" in joined
            assert "provider_mode" in joined
        assert "run_cli" in joined
        for command in expected_commands[path.name]:
            assert command in joined

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
    release_dir = build_mini_seed(tmp_path, input_dir="input")
    sqlite_path = release_dir / "db" / "app.sqlite"
    with sqlite3.connect(sqlite_path) as connection:
        row = connection.execute("SELECT document_id FROM text_documents_fts WHERE text_documents_fts MATCH ? LIMIT 1", ("L21",)).fetchone()
        count = connection.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
    assert row is not None
    assert count == 3
    result = validate_release(release_dir)
    assert result.passed
    assert any("visual_search" in degraded for degraded in result.degraded)


def test_bronze_fast_generates_real_media_files(tmp_path):
    release_dir = build_mini_seed(tmp_path, input_dir="input", mode="bronze_fast")
    result = validate_release(release_dir)
    assert result.passed
    manifest = json.loads((release_dir / "manifests" / "dataset_manifest.json").read_text(encoding="utf-8"))
    assert manifest["capabilities"]["core_runtime"] == "pass"
    assert manifest["capabilities"]["visual_search"] == "pass"
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
        result = runner.invoke(app, command)
        assert result.exit_code == 0, result.stdout
    release_dir = output_dir / "competition_dataset_v001"
    assert (release_dir / "manifests" / "dataset_report.json").exists()
    assert (release_dir / "manifests" / "batch_000.txt").exists()
    assert (release_dir / "manifests" / "worker_runtime_report_structure.json").exists()
    assert not (release_dir / "manifests" / "merge_report.json").exists()
    assert not (release_dir / "db" / "app.sqlite").exists()
    assert not (release_dir / "indexes" / "visual.faiss").exists()

def test_ingest_creates_only_ingestion_artifacts_and_is_idempotent(tmp_path):
    output_dir = tmp_path / "output"
    command = ["ingest", "--mode", "debug_small_sample", "--output", str(output_dir), "--input", "input"]
    first = runner.invoke(app, command)
    second = runner.invoke(app, command)
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
    ingest = runner.invoke(app, ["ingest", "--mode", "debug_small_sample", "--output", str(output_dir), "--input", "input"])
    assigned = runner.invoke(app, ["assign-batches", "--mode", "debug_small_sample", "--num-batches", "2", "--output", str(output_dir)])
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
    runner.invoke(app, ["ingest", "--mode", "debug_small_sample", "--output", str(output_dir), "--input", "input"])
    runner.invoke(app, ["assign-batches", "--mode", "debug_small_sample", "--num-batches", "1", "--output", str(output_dir)])
    release_dir = output_dir / "competition_dataset_v001"
    videos_before = (release_dir / "tables" / "videos.parquet").stat().st_mtime_ns
    result = runner.invoke(app, ["process-batch", "--batch-id", "batch_000", "--mode", "debug_small_sample", "--providers", "mock", "--output", str(output_dir), "--input", "input"])
    assert result.exit_code == 0, result.stdout
    artifact_dir = release_dir / "artifacts" / "structure" / "L21_V001"
    assert artifact_dir.exists()
    for name in [
        "metadata_normalized.json",
        "asr_segments.parquet",
        "shots.parquet",
        "scenes.parquet",
        "keyframes.parquet",
        "shot_transcript_links.parquet",
        "scene_transcript_links.parquet",
        "scene_summaries_initial.parquet",
        "manifest.json",
        "errors.jsonl",
    ]:
        assert (artifact_dir / name).exists()
    assert (artifact_dir / "keyframes").exists()
    assert (artifact_dir / "thumbnails").exists()
    assert not (artifact_dir / "L21_V001").exists()
    assert list((release_dir / "artifacts" / "structure").glob("*_structure.zip"))
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
        "shot_transcript_links.parquet",
        "scene_transcript_links.parquet",
        "scene_summaries_initial.parquet",
    ]:
        assert not (release_dir / "tables" / name).exists()
    keyframes = pd.read_parquet(artifact_dir / "keyframes.parquet")
    assert keyframes.iloc[0]["keyframe_ref"] == "media://keyframes/L21_V001/L21_V001_f0000000.jpg"
    assert keyframes.iloc[0]["thumbnail_ref"] == "media://thumbnails/L21_V001/L21_V001_f0000000.webp"
    assert keyframes.iloc[0]["frame_id_method"] == "first_frame_extraction_assumed_frame_0"
    assert str(keyframes.iloc[0]["thumbnail_ref"]).endswith(".webp")
    shots = pd.read_parquet(artifact_dir / "shots.parquet")
    assert shots.iloc[0]["boundary_convention"] == "[start_frame, end_frame)"

def test_process_batch_ffmpeg_failure_writes_valid_placeholder_images(tmp_path):
    output_dir = tmp_path / "output"
    runner.invoke(app, ["ingest", "--mode", "debug_small_sample", "--output", str(output_dir), "--input", "input"])
    runner.invoke(app, ["assign-batches", "--mode", "debug_small_sample", "--num-batches", "1", "--output", str(output_dir)])
    with patch("subprocess.run", side_effect=__import__("subprocess").CalledProcessError(1, "ffmpeg")):
        result = runner.invoke(app, ["process-batch", "--batch-id", "batch_000", "--mode", "debug_small_sample", "--providers", "mock", "--output", str(output_dir), "--input", "input"])
    assert result.exit_code == 0, result.stdout
    artifact_dir = output_dir / "competition_dataset_v001" / "artifacts" / "structure" / "L21_V001"
    jpg = next((artifact_dir / "keyframes").glob("*.jpg"))
    webp = next((artifact_dir / "thumbnails").glob("*.webp"))
    assert jpg.read_bytes().startswith(b"\xff\xd8\xff")
    assert webp.read_bytes().startswith(b"RIFF")
    assert b"WEBP" in webp.read_bytes()[:16]

def test_process_batch_missing_batch_file_fails_clearly(tmp_path):
    output_dir = tmp_path / "output"
    runner.invoke(app, ["ingest", "--mode", "debug_small_sample", "--output", str(output_dir), "--input", "input"])
    result = runner.invoke(app, ["process-batch", "--batch-id", "batch_999", "--mode", "debug_small_sample", "--providers", "mock", "--output", str(output_dir), "--input", "input"])
    assert result.exit_code != 0

def test_feature_batch_creates_only_feature_artifacts_from_structure(tmp_path):
    output_dir = tmp_path / "output"
    runner.invoke(app, ["ingest", "--mode", "debug_small_sample", "--output", str(output_dir), "--input", "input"])
    runner.invoke(app, ["assign-batches", "--mode", "debug_small_sample", "--num-batches", "1", "--output", str(output_dir)])
    runner.invoke(app, ["process-batch", "--batch-id", "batch_000", "--mode", "debug_small_sample", "--providers", "mock", "--output", str(output_dir), "--input", "input"])
    release_dir = output_dir / "competition_dataset_v001"
    structure_manifest = release_dir / "artifacts" / "structure" / "L21_V001" / "manifest.json"
    structure_before = structure_manifest.stat().st_mtime_ns
    result = runner.invoke(app, ["feature-batch", "--batch-id", "batch_000", "--mode", "debug_small_sample", "--providers", "mock", "--output", str(output_dir), "--input", "input"])
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
    assert list((release_dir / "artifacts" / "features").glob("*_features.zip"))
    assert (release_dir / "manifests" / "worker_runtime_report_features.json").exists()
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
    runner.invoke(app, ["ingest", "--mode", "debug_small_sample", "--output", str(output_dir), "--input", "input"])
    runner.invoke(app, ["assign-batches", "--mode", "debug_small_sample", "--num-batches", "1", "--output", str(output_dir)])
    result = runner.invoke(app, ["feature-batch", "--batch-id", "batch_000", "--mode", "debug_small_sample", "--providers", "mock", "--output", str(output_dir), "--input", "input"])
    assert result.exit_code != 0

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
        result = runner.invoke(app, command)
        assert result.exit_code == 0, result.stdout
    release_dir = output_dir / "competition_dataset_v001"
    assert (release_dir / "tables" / "text_documents.parquet").exists()
    assert (release_dir / "manifests" / "artifact_manifest.parquet").exists()
    assert list((release_dir / "media" / "keyframes").rglob("*.jpg"))
    assert list((release_dir / "media" / "thumbnails").rglob("*.webp"))
    assert not (release_dir / "db" / "app.sqlite").exists()
    assert not (release_dir / "indexes" / "visual.faiss").exists()

    index = runner.invoke(app, ["build-index", "--mode", "debug_small_sample", "--output", str(output_dir)])
    db = runner.invoke(app, ["build-db", "--mode", "debug_small_sample", "--output", str(output_dir)])
    validate = runner.invoke(app, ["validate", "--mode", "debug_small_sample", "--output", str(output_dir)])
    smoke = runner.invoke(app, ["smoke-test", "--release", str(release_dir)])
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

def test_validate_fails_before_runtime_artifacts(tmp_path):
    output_dir = tmp_path / "output"
    result = runner.invoke(app, ["ingest", "--mode", "debug_small_sample", "--output", str(output_dir), "--input", "input"])
    assert result.exit_code == 0, result.stdout
    validate = runner.invoke(app, ["validate", "--mode", "debug_small_sample", "--output", str(output_dir)])
    assert validate.exit_code != 0

def test_build_mini_seed_command_keeps_dev_helper_path(tmp_path):
    output_dir = tmp_path / "output"
    result = runner.invoke(
        app,
        ["build-mini-seed", "--mode", "debug_small_sample", "--providers", "mock", "--output", str(output_dir), "--input", "input"],
    )
    assert result.exit_code == 0, result.stdout
    release_dir = output_dir / "competition_dataset_v001"
    validate = runner.invoke(app, ["validate", "--mode", "debug_small_sample", "--output", str(output_dir)])
    assert validate.exit_code == 0, validate.stdout
    smoke = runner.invoke(app, ["smoke-test", "--release", str(release_dir)])
    assert smoke.exit_code == 0, smoke.stdout
    packaged = runner.invoke(app, ["release", "--mode", "debug_small_sample", "--output", str(output_dir)])
    assert packaged.exit_code == 0, packaged.stdout
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
        result = runner.invoke(app, command)
        assert result.exit_code == 0, result.stdout


def test_silver_balanced_outputs_asr_ocr_contracts(tmp_path):
    release_dir = build_mini_seed(tmp_path, input_dir="input", mode="silver_balanced")
    result = validate_release(release_dir)
    assert result.passed
    report = json.loads((release_dir / "manifests" / "validation_report.json").read_text(encoding="utf-8"))
    assert report["capabilities"]["asr"] == "pass"
    assert report["capabilities"]["ocr"] == "pass"
    assert (release_dir / "tables" / "asr_segments.parquet").exists()
    assert (release_dir / "tables" / "ocr.parquet").exists()


def test_real_provider_mode_fails_gracefully_with_degraded_asr_ocr(tmp_path):
    release_dir = build_mini_seed(tmp_path, input_dir="input", mode="silver_balanced", providers="real")
    result = validate_release(release_dir)
    assert result.passed
    report = json.loads((release_dir / "manifests" / "validation_report.json").read_text(encoding="utf-8"))
    assert report["capabilities"]["asr"] == "degraded"
    assert report["capabilities"]["ocr"] == "degraded"
    assert report["capabilities"]["visual_search"] == "degraded"
    assert report["release_usable"] is True


def test_gold_full_outputs_enrichment_and_reuse_checkpoint(tmp_path):
    release_dir = build_mini_seed(tmp_path, input_dir="input", mode="gold_full")
    first_checkpoint = json.loads((release_dir / "manifests" / "checkpoint_manifest.json").read_text(encoding="utf-8"))
    index_path = release_dir / "indexes" / "visual.faiss"
    first_mtime = index_path.stat().st_mtime_ns
    release_dir = build_mini_seed(tmp_path, input_dir="input", mode="gold_full")
    report = json.loads((release_dir / "manifests" / "validation_report.json").read_text(encoding="utf-8"))
    second_checkpoint = json.loads((release_dir / "manifests" / "checkpoint_manifest.json").read_text(encoding="utf-8"))
    second_mtime = index_path.stat().st_mtime_ns
    assert report["capabilities"]["enrichment_overall"] == "pass"
    assert report["capabilities"]["incremental_reuse"] == "pass"
    assert first_checkpoint["rules"]["skip_keyframe_if_input_config_schema_unchanged"] is True
    assert second_checkpoint["videos"]
    assert all(video["media_reused"] for video in second_checkpoint["videos"].values())
    assert second_checkpoint["embeddings_hash"] == first_checkpoint["embeddings_hash"]
    assert second_mtime == first_mtime
    for name in ["objects", "image_captions", "shot_captions", "scene_summaries_initial", "scene_summaries_enriched"]:
        assert (release_dir / "tables" / f"{name}.parquet").exists()


def test_cli_gold_pipeline_end_to_end(tmp_path):
    output_dir = tmp_path / "output"
    commands = [
        ["ingest", "--mode", "gold_full", "--output", str(output_dir), "--input", "input"],
        ["assign-batches", "--mode", "gold_full", "--num-batches", "1", "--output", str(output_dir)],
        ["process-batch", "--batch-id", "batch_000", "--mode", "gold_full", "--providers", "mock", "--output", str(output_dir), "--input", "input"],
    ]
    for command in commands:
        result = runner.invoke(app, command)
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
    release_dir = build_mini_seed(tmp_path, input_dir="input", mode="gold_full")
    structure_report = write_worker_artifacts(release_dir, batch_id="batch_000", phase="structure")
    features_report = write_worker_artifacts(release_dir, batch_id="batch_000", phase="features")
    assert structure_report.exists()
    assert features_report.exists()
    assert list((release_dir / "artifacts" / "structure").glob("*_structure.zip"))
    assert list((release_dir / "artifacts" / "features").glob("*_features.zip"))


def test_selective_rebuild_proof_embedding_change_keeps_asr_ocr_contracts(tmp_path):
    release_dir = build_mini_seed(tmp_path, input_dir="input", mode="gold_full", providers="mock")
    first_checkpoint = json.loads((release_dir / "manifests" / "checkpoint_manifest.json").read_text(encoding="utf-8"))
    release_dir = build_mini_seed(tmp_path, input_dir="input", mode="gold_full", providers="real")
    second_checkpoint = json.loads((release_dir / "manifests" / "checkpoint_manifest.json").read_text(encoding="utf-8"))
    report = json.loads((release_dir / "manifests" / "validation_report.json").read_text(encoding="utf-8"))
    assert first_checkpoint["videos"].keys() == second_checkpoint["videos"].keys()
    assert all(video["media_reused"] for video in second_checkpoint["videos"].values())
    assert report["capabilities"]["asr"] == "degraded"
    assert report["capabilities"]["ocr"] == "degraded"
    assert report["capabilities"]["visual_search"] == "degraded"


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
        ],
    ]
    manifest_row = json.loads(uploaded["canonical_dataset_v001/manifests/canonical_file_manifest.jsonl"].decode().splitlines()[0])
    assert manifest_row["raw_repo_id"] == "org/repo"
    assert manifest_row["raw_import_id"] == "canonical_dataset_v001"
    assert manifest_row["video_path"] == "canonical_dataset_v001/raw_videos/L21_V001.mp4"
    assert manifest_row["video_upload_status"] == "uploaded"
    assert "kind=video index=" not in output
    assert "kind=metadata index=" not in output
    assert "Processing Files" not in output
    assert "New Data Upload" not in output
    assert "phase=scan repo_id=org/repo raw_import_id=canonical_dataset_v001" in output
    assert "phase=videos batch=1/1 uploaded=2 skipped=0 failed=0" in output
    assert "phase=metadata batch=1/1 uploaded=2 skipped=0 failed=0" in output
    assert "phase=manifests batch=1/1 uploaded=2 skipped=0 failed=0" in output
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

    result = standardize_archive_source(source_dir, tmp_path / "standardized")

    assert result.error_count == 0
    for stem in ["A", "loose", "L21_V001", "L22_V001", "A_L21_V002", "B_L21_V002", "missing"]:
        assert (tmp_path / "standardized" / "raw_videos" / f"{stem}.mp4").exists()
        assert (tmp_path / "standardized" / "metadata" / f"{stem}.json").exists()
    report = json.loads(result.report_path.read_text(encoding="utf-8"))
    assert any(item.get("source_mode") == "existing_layout" for item in report["items"])
    assert any(item.get("source_mode") == "loose_files" for item in report["items"])
    assert any(item.get("kind") == "metadata_generated" and item.get("canonical_stem") == "missing" for item in report["items"])


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
    shutil.copy2(Path("input/raw_videos/L21_V001.mp4").resolve(), source_root / "raw_videos" / "L21_V001.mp4")
    shutil.copy2(Path("input/metadata/L21_V001.json").resolve(), source_root / "metadata" / "L21_V001.json")
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

    class FakeHFStore:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def download_file(self, relative_path, target: Path):
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
    assert mapping.loc[0, "canonical_backend"] == "hf_dataset"
    assert mapping.loc[0, "canonical_repo_id"] == "org/repo"


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
    download_calls: list[str] = []

    class FakeHFStore:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def download_file(self, relative_path, target: Path):
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
        "raw_videos/L21_V001.mp4",
        "metadata/L21_V001.json",
        "raw_videos/L21_V002.mp4",
        "metadata/L21_V002.json",
    ]
    assert mapping["canonical_video_path"].tolist() == ["raw_videos/L21_V001.mp4", "raw_videos/L21_V002.mp4"]
    assert mapping["canonical_metadata_path"].tolist() == ["metadata/L21_V001.json", "metadata/L21_V002.json"]


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

        def download_file(self, relative_path, target: Path):
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
