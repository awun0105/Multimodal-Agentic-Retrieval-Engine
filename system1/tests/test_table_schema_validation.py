from __future__ import annotations

from pathlib import Path

import pandas as pd

from system1.validation.table_schema import validate_release_tables


def write_table(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(path, index=False)


def write_valid_schema_release(release_dir: Path) -> None:
    write_table(
        release_dir / "tables" / "videos.parquet",
        [
            {
                "video_id": "L21_V001",
                "video_ref": "media://raw_videos/L21_V001.mp4",
                "frame_count": 1,
                "frame_count_method": "decoded_frame_timeline",
                "has_frame_timeline": True,
            }
        ],
    )
    write_table(
        release_dir / "tables" / "keyframes.parquet",
        [
            {
                "keyframe_id": "L21_V001:0",
                "video_id": "L21_V001",
                "frame_id": 0,
                "shot_id": "L21_V001_SH00000",
                "scene_id": "L21_V001_SC00000",
                "keyframe_role": "representative",
                "is_representative": True,
                "keyframe_ref": "media://keyframes/L21_V001/L21_V001_f0000000.jpg",
                "thumbnail_ref": "media://thumbnails/L21_V001/L21_V001_f0000000.webp",
            }
        ],
    )
    write_table(
        release_dir / "tables" / "shots.parquet",
        [{
            "shot_id": "L21_V001_SH00000",
            "video_id": "L21_V001",
            "scene_id": "L21_V001_SC00000",
            "start_frame": 0,
            "end_frame": 1,
            "start_sec": 0.0,
            "end_sec": 0.04,
            "detection_method": "transnet_v2_no_cut",
            "status": "pass",
        }],
    )
    write_table(
        release_dir / "tables" / "scenes.parquet",
        [{
            "scene_id": "L21_V001_SC00000",
            "video_id": "L21_V001",
            "start_shot_id": "L21_V001_SH00000",
            "end_shot_id": "L21_V001_SH00000",
            "start_frame": 0,
            "end_frame": 1,
            "start_sec": 0.0,
            "end_sec": 0.04,
            "shot_count": 1,
            "grouping_method": "multimodal_context_focus",
            "grouping_version": "scene_grouping_v1",
            "status": "pass",
        }],
    )
    write_table(
        release_dir / "tables" / "asr_segments.parquet",
        [{"asr_segment_id": "L21_V001_ASR00000", "video_id": "L21_V001", "start_sec": 0.0, "end_sec": 0.04, "text": "sample transcript"}],
    )
    write_table(
        release_dir / "tables" / "shot_transcript_links.parquet",
        [{"shot_id": "L21_V001_SH00000", "asr_segment_id": "L21_V001_ASR00000", "video_id": "L21_V001", "coverage": 1.0}],
    )
    write_table(
        release_dir / "tables" / "scene_transcript_links.parquet",
        [{"scene_id": "L21_V001_SC00000", "asr_segment_id": "L21_V001_ASR00000", "video_id": "L21_V001", "coverage": 1.0}],
    )
    write_table(
        release_dir / "tables" / "shot_captions.parquet",
        [
            {
                "shot_caption_id": "L21_V001_SH00000_caption",
                "shot_id": "L21_V001_SH00000",
                "video_id": "L21_V001",
                "representative_keyframe_id": "L21_V001:0",
                "representative_timestamp_sec": 0.0,
                "caption_vi": "mô tả cảnh quay mẫu",
                "caption_en": "sample shot caption",
                "provider": "gemini",
                "model_name": "fixture-gemini",
                "model_version": "fixture",
                "prompt_version": "shot_caption_v1",
                "schema_version": "1.0.0",
                "status": "pass",
            }
        ],
    )
    write_table(
        release_dir / "tables" / "scene_summaries.parquet",
        [{
            "scene_id": "L21_V001_SC00000",
            "video_id": "L21_V001",
            "summary_vi": "tóm tắt cảnh mẫu",
            "summary_en": "sample scene summary",
            "provider": "gemini",
            "model_name": "fixture-gemini",
            "model_version": "fixture",
            "prompt_version": "scene_summary_v1",
            "schema_version": "1.0.0",
            "status": "pass",
        }],
    )
    write_table(
        release_dir / "tables" / "embeddings_meta.parquet",
        [{"embedding_id": "L21_V001:0_mock", "keyframe_id": "L21_V001:0", "video_id": "L21_V001"}],
    )
    write_table(
        release_dir / "tables" / "text_sources.parquet",
        [{
            "source_id": "L21_V001:video:metadata:fixture:0001",
            "video_id": "L21_V001",
            "entity_type": "video",
            "entity_id": "L21_V001",
            "source_type": "metadata",
            "raw_text": "sample text",
            "normalized_text": "sample text",
            "language": "und",
            "provider": "fixture",
            "status": "pass",
        }],
    )
    write_table(
        release_dir / "tables" / "text_documents.parquet",
        [
            {
                "doc_id": "doc:L21_V001:video:L21_V001",
                "document_id": "doc:L21_V001:video:L21_V001",
                "video_id": "L21_V001",
                "source_type": "metadata",
                "normalized_text": "sample text",
                "language": "und",
            }
        ],
    )
    write_table(
        release_dir / "indexes" / "vector_map.parquet",
        [{"index_name": "visual", "vector_id": 0, "keyframe_id": "L21_V001:0", "video_id": "L21_V001"}],
    )
    write_table(
        release_dir / "tables" / "feature_availability.parquet",
        [{"entity_type": "keyframe", "entity_id": "L21_V001:0", "video_id": "L21_V001", "status": "pass"}],
    )


def test_schema_validation_passes_with_required_tables_and_skips_missing_optional(tmp_path):
    release_dir = tmp_path / "release"
    write_valid_schema_release(release_dir)

    result = validate_release_tables(release_dir)

    assert result.status == "pass"
    assert not result.errors
    assert any("missing optional table" in warning for warning in result.warnings)
    assert result.tables["keyframes"]["status"] == "pass"
    assert result.tables["text_documents"]["resolved_columns"]["doc_id or document_id"] == "doc_id"
    assert result.tables["feature_availability"]["resolved_columns"]["entity_level or entity_type"] == "entity_type"


def test_schema_validation_catches_missing_required_column(tmp_path):
    release_dir = tmp_path / "release"
    write_valid_schema_release(release_dir)
    keyframes = pd.read_parquet(release_dir / "tables" / "keyframes.parquet").drop(columns=["thumbnail_ref"])
    keyframes.to_parquet(release_dir / "tables" / "keyframes.parquet", index=False)

    result = validate_release_tables(release_dir)

    assert result.status == "fail"
    assert any("keyframes missing required column: thumbnail_ref" in error for error in result.errors)


def test_schema_validation_catches_duplicate_keyframe_id(tmp_path):
    release_dir = tmp_path / "release"
    write_valid_schema_release(release_dir)
    keyframes = pd.read_parquet(release_dir / "tables" / "keyframes.parquet")
    pd.concat([keyframes, keyframes], ignore_index=True).to_parquet(
        release_dir / "tables" / "keyframes.parquet",
        index=False,
    )

    result = validate_release_tables(release_dir)

    assert result.status == "fail"
    assert any("keyframes duplicate primary key keyframe_id" in error for error in result.errors)


def test_schema_validation_catches_null_id_column(tmp_path):
    release_dir = tmp_path / "release"
    write_valid_schema_release(release_dir)
    videos = pd.read_parquet(release_dir / "tables" / "videos.parquet")
    videos.loc[0, "video_id"] = None
    videos.to_parquet(release_dir / "tables" / "videos.parquet", index=False)

    result = validate_release_tables(release_dir)

    assert result.status == "fail"
    assert any("videos.video_id has 1 null values" in error for error in result.errors)


def test_schema_validation_catches_missing_required_table(tmp_path):
    release_dir = tmp_path / "release"
    write_valid_schema_release(release_dir)
    (release_dir / "tables" / "keyframes.parquet").unlink()

    result = validate_release_tables(release_dir)

    assert result.status == "fail"
    assert any("missing required table: tables/keyframes.parquet" in error for error in result.errors)


def test_schema_validation_catches_duplicate_caption_for_shot(tmp_path):
    release_dir = tmp_path / "release"
    write_valid_schema_release(release_dir)
    captions = pd.read_parquet(release_dir / "tables" / "shot_captions.parquet")
    duplicate = captions.copy()
    duplicate.loc[0, "shot_caption_id"] = "duplicate-caption-id"
    pd.concat([captions, duplicate], ignore_index=True).to_parquet(
        release_dir / "tables" / "shot_captions.parquet",
        index=False,
    )

    result = validate_release_tables(release_dir)

    assert result.status == "fail"
    assert any("shot_captions duplicate primary key shot_id" in error for error in result.errors)


def test_schema_validation_catches_empty_bilingual_text(tmp_path):
    release_dir = tmp_path / "release"
    write_valid_schema_release(release_dir)
    summaries = pd.read_parquet(release_dir / "tables" / "scene_summaries.parquet")
    summaries.loc[0, "summary_en"] = "   "
    summaries.to_parquet(release_dir / "tables" / "scene_summaries.parquet", index=False)

    result = validate_release_tables(release_dir)

    assert result.status == "fail"
    assert any("scene_summaries.summary_en has 1 empty text values" in error for error in result.errors)
