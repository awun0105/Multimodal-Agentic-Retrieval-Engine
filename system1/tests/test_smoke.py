import shutil
import json
import sqlite3
import csv
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import numpy as np
import pytest
from typer.testing import CliRunner

from system1.cli import app
from system1.config import REQUIRED_CONFIGS, load_configs, load_provider_plan
from system1.ingest.discovery import discover_paired_inputs
from system1.ingest.source_importer import import_organizer_source
from system1.release.artifacts import write_worker_artifacts
from system1.release.mini_seed import build_mini_seed
from system1.validation.release_validator import validate_release

runner = CliRunner()


def test_system1_package_imports():
    import system1

    assert system1 is not None

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
        "00_master_ingestion_and_assignment.ipynb": ["import-source", "ingest", "assign-batches"],
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
        assert "worker_id" in joined
        assert "batch_id" in joined
        assert "execution_mode" in joined
        assert "provider_mode" in joined
        assert "run_cli" in joined
        for command in expected_commands[path.name]:
            assert command in joined

def test_input_discovery_pairs_real_subset():
    pairs = discover_paired_inputs("input")
    assert [pair["video_id"] for pair in pairs] == ["L21_V001", "L21_V002", "L21_V003"]


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
