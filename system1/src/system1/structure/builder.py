from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

import pandas as pd

from system1.artifacts.hf_store import HuggingFaceDatasetArtifactStore
from system1.artifacts.package import write_artifact_zip
from system1.artifacts.reports import utc_now, write_worker_report
from system1.config import ProviderPlan, load_provider_plan
from system1.features.providers import MockTextProvider, RealProviderUnavailable
from system1.ingest.discovery import read_metadata
from system1.keyframes.extractor import extract_keyframe_and_thumbnail
from system1.release.types import config_dir, release_root
from system1.structure.providers import (
    TimelineAwareFallbackProvider,
    TimelineContext,
    TimelineFrame,
)
from system1.text.builder import metadata_text

STRUCTURE_PARQUET_FILES = (
    "asr_segments.parquet",
    "asr_words.parquet",
    "shots.parquet",
    "scenes.parquet",
    "keyframes.parquet",
    "ocr.parquet",
    "shot_captions.parquet",
    "shot_transcript_links.parquet",
    "scene_transcript_links.parquet",
    "scene_summaries.parquet",
)

PARQUET_COLUMNS: dict[str, list[str]] = {
    "asr_segments": [
        "asr_segment_id",
        "video_id",
        "start_sec",
        "end_sec",
        "start_frame",
        "end_frame",
        "text",
        "language",
        "confidence",
        "avg_logprob",
        "no_speech_prob",
        "provider",
        "model_name",
        "model_version",
        "status",
    ],
    "asr_words": [
        "asr_word_id", "asr_segment_id", "video_id", "word_index", "text",
        "start_sec", "end_sec", "start_frame", "end_frame", "confidence",
        "alignment_method", "alignment_version", "provider", "model_name",
        "model_version", "status",
    ],
    "shot_transcript_links": [
        "video_id", "shot_id", "asr_segment_id", "overlap_start_sec",
        "overlap_end_sec", "overlap_sec", "segment_coverage", "entity_coverage",
        "coverage", "assigned_word_count",
    ],
    "scene_transcript_links": [
        "video_id", "scene_id", "asr_segment_id", "overlap_start_sec",
        "overlap_end_sec", "overlap_sec", "segment_coverage", "entity_coverage",
        "coverage", "assigned_word_count",
    ],
    "ocr": [
        "ocr_id",
        "video_id",
        "keyframe_id",
        "shot_id",
        "frame_id",
        "text",
        "raw_text",
        "provider",
        "model_name",
        "model_version",
        "language",
        "confidence",
        "status",
    ],
}


def process_structure_batch(
    output_dir: Path | str,
    *,
    input_dir: Path | str | None = None,
    batch_id: str,
    providers: str = "mock",
    worker_id: str = "worker_000",
    require_frame_timeline: bool = False,
) -> Path:
    started_at = utc_now()
    release_dir = release_root(output_dir)
    videos_path = release_dir / "tables" / "videos.parquet"
    media_manifest_path = release_dir / "raw_mapping" / "media_store_manifest.parquet"
    batch_path = release_dir / "manifests" / f"{batch_id}.txt"
    if not videos_path.exists():
        raise FileNotFoundError(f"missing ingestion output: {videos_path}")
    if not media_manifest_path.exists():
        raise FileNotFoundError(f"missing media mapping output: {media_manifest_path}")
    if not batch_path.exists():
        raise FileNotFoundError(f"missing batch manifest: {batch_path}")

    batch_video_ids = [line.strip() for line in batch_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    videos = pd.read_parquet(videos_path)
    media_manifest = pd.read_parquet(media_manifest_path)
    video_rows = videos[videos["video_id"].isin(batch_video_ids)].sort_values("video_id")
    missing = sorted(set(batch_video_ids) - set(video_rows["video_id"].astype(str)))
    if missing:
        raise ValueError(f"batch references missing videos: {missing}")

    mapping_by_video = {str(row["video_id"]): row for row in media_manifest.to_dict("records")}
    provider_plan = load_provider_plan(config_dir(), providers)
    artifact_paths: list[str] = []
    errors: list[dict[str, Any]] = []
    batch_debug_dir = release_dir / "artifacts" / "structure_batches" / batch_id
    if batch_debug_dir.exists():
        shutil.rmtree(batch_debug_dir)
    batch_debug_dir.mkdir(parents=True, exist_ok=True)

    for video in video_rows.to_dict("records"):
        video_id = str(video["video_id"])
        mapping = mapping_by_video.get(video_id)
        if mapping is None:
            raise ValueError(f"missing media mapping for video_id={video_id}")
        artifact_dir = release_dir / "artifacts" / "structure" / video_id
        if artifact_dir.exists():
            shutil.rmtree(artifact_dir)
        artifact_dir.mkdir(parents=True, exist_ok=True)
        scratch_dir = release_dir / "staging" / "phase01_scratch" / batch_id / video_id
        if scratch_dir.exists():
            shutil.rmtree(scratch_dir)
        scratch_dir.mkdir(parents=True, exist_ok=True)
        try:
            video_errors, video_tables = _write_video_structure_artifact(
                artifact_dir=artifact_dir,
                release_dir=release_dir,
                scratch_dir=scratch_dir,
                video=video,
                mapping=mapping,
                input_dir=input_dir,
                providers=providers,
                provider_plan=provider_plan,
                batch_id=batch_id,
                worker_id=worker_id,
                require_frame_timeline=require_frame_timeline,
            )
            errors.extend(video_errors)
            _write_batch_debug_copy(batch_debug_dir / f"{video_id}.json", video_id=video_id, tables=video_tables)
            archive_path = write_artifact_zip(
                artifact_dir=artifact_dir,
                zip_path=release_dir / "artifacts" / "structure" / f"{video_id}_structure.zip",
                video_id=video_id,
                artifact_type="structure",
                batch_id=batch_id,
                worker_id=worker_id,
                status="complete" if not video_errors else "partial",
            )
        finally:
            shutil.rmtree(scratch_dir, ignore_errors=True)
        artifact_paths.append(str(archive_path.relative_to(release_dir)))

    finished_at = utc_now()
    report_path = write_worker_report(
        release_dir,
        phase="structure",
        batch_id=batch_id,
        worker_id=worker_id,
        started_at=started_at,
        finished_at=finished_at,
        videos_processed=int(len(video_rows)),
        videos_failed=len({str(error.get("video_id")) for error in errors if error.get("video_id")}),
        payload={
            "legacy_status": "pass" if not errors else "partial",
            "artifact_paths": artifact_paths,
            "video_count": int(len(video_rows)),
            "error_count": len(errors),
            "batch_debug_dir": str(batch_debug_dir.relative_to(release_dir)),
        },
    )
    return report_path


def _write_video_structure_artifact(
    *,
    artifact_dir: Path,
    release_dir: Path,
    scratch_dir: Path,
    video: dict[str, Any],
    mapping: dict[str, Any],
    input_dir: Path | str | None,
    providers: str,
    provider_plan: ProviderPlan,
    batch_id: str,
    worker_id: str,
    require_frame_timeline: bool,
) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    video_id = str(video["video_id"])
    errors: list[dict[str, Any]] = []
    canonical_cache_dir = scratch_dir / "canonical_cache"
    video_path = _resolve_video_path(mapping, input_dir, canonical_cache_dir)
    metadata_path = _resolve_metadata_path(mapping, input_dir, canonical_cache_dir)
    metadata = _read_metadata_or_empty(metadata_path, errors, video_id)
    normalized_text = metadata_text(video_id, metadata)
    text_provider = _text_provider_for_plan(provider_plan)
    timeline, timeline_errors = _load_timeline_context(release_dir, video)
    if require_frame_timeline and not timeline.available:
        details = timeline_errors[0]["message"] if timeline_errors else "timeline is empty"
        raise ValueError(
            f"decoded frame timeline is required for production video_id={video_id}: {details}"
        )
    errors.extend(timeline_errors)
    structure_provider = TimelineAwareFallbackProvider()
    frame_count = _int_or_none(video.get("frame_count"))
    duration_seconds = _float_or_zero(video.get("duration_seconds"))
    shots = structure_provider.detect_shots(
        video_id=video_id,
        timeline=timeline,
        frame_count=frame_count,
        duration_seconds=duration_seconds,
    )
    scenes = structure_provider.construct_scenes(video_id=video_id, timeline=timeline, shots=shots)
    keyframe_selections = structure_provider.select_keyframes(
        video_id=video_id,
        timeline=timeline,
        shots=shots,
        scene_id=scenes[0].scene_id,
    )
    shot = shots[0]
    scene = scenes[0]
    keyframe_selection = keyframe_selections[0]

    asr_text = _transcribe(video_path, text_provider, provider_plan, errors, video_id)
    asr_segment_id = f"{video_id}_ASR00000"
    shot_id = shot.shot_id
    scene_id = scene.scene_id
    frame_id = keyframe_selection.frame_id
    keyframe_id = keyframe_selection.keyframe_id
    keyframe_filename = f"{video_id}_f{frame_id:07d}.jpg"
    thumbnail_filename = f"{video_id}_f{frame_id:07d}.webp"
    keyframe_path = artifact_dir / "keyframes" / keyframe_filename
    thumbnail_path = artifact_dir / "thumbnails" / thumbnail_filename
    selection_method = _extract_media(video_path, keyframe_path, thumbnail_path, errors, video_id)
    keyframe_ref = f"media://keyframes/{video_id}/{keyframe_filename}"
    thumbnail_ref = f"media://thumbnails/{video_id}/{thumbnail_filename}"
    ocr_text = text_provider.read_text(keyframe_path)
    ocr_status = "empty" if not ocr_text else "pass"
    shot_caption_text = _caption_keyframe(keyframe_path, normalized_text, text_provider, provider_plan, errors, video_id)
    shot_caption_status = "empty" if not shot_caption_text else "pass"
    scene_summary_text = _summarize_scene(
        scene_id,
        _join_text([normalized_text, asr_text, shot_caption_text]),
        text_provider,
        provider_plan,
        errors,
        video_id,
    )
    scene_summary_status = "empty" if not scene_summary_text else "pass"
    asr_rows = _legacy_asr_rows(
        video_id=video_id,
        asr_segment_id=asr_segment_id,
        text=asr_text,
        end_sec=shot.end_seconds,
        end_frame=shot.end_frame,
        provider=provider_plan.asr,
    )
    legacy_link = {
        "video_id": video_id,
        "asr_segment_id": asr_segment_id,
        "overlap_start_sec": float(shot.start_seconds),
        "overlap_end_sec": float(shot.end_seconds),
        "overlap_sec": float(shot.end_seconds - shot.start_seconds),
        "segment_coverage": 1.0,
        "entity_coverage": 1.0,
        "coverage": 1.0,
        "assigned_word_count": 0,
    }
    shot_transcript_links = (
        [{**legacy_link, "shot_id": shot_id}]
        if asr_rows
        else []
    )
    scene_transcript_links = (
        [{**legacy_link, "scene_id": scene_id}]
        if asr_rows
        else []
    )

    _write_json_artifact(
        artifact_dir / "metadata_normalized.json",
        {
            "video_id": video_id,
            "video_ref": video.get("video_ref"),
            "metadata_ref": video.get("metadata_ref"),
            "normalized_text": normalized_text,
            "metadata": metadata,
        },
    )
    tables = {
        "asr_segments": asr_rows,
        # This legacy/debug builder has no acoustic alignment evidence. It emits
        # an explicitly empty sibling table instead of fabricating word timing.
        "asr_words": [],
        "shots": [{
            "shot_id": shot_id,
            "video_id": video_id,
            "scene_id": scene_id,
            "shot_index": 0,
            "start_frame": shot.start_frame,
            "end_frame": shot.end_frame,
            "start_sec": shot.start_seconds,
            "end_sec": shot.end_seconds,
            "start_seconds": shot.start_seconds,
            "end_seconds": shot.end_seconds,
            "duration_sec": max(0.0, shot.end_seconds - shot.start_seconds),
            "frame_count": max(0, shot.end_frame - shot.start_frame),
            "boundary_convention": "[start_frame, end_frame)",
            "detection_method": shot.detection_method,
            "provider": "ShotDetectionProvider",
            "status": shot.status,
        }],
        "scenes": [{
            "scene_id": scene_id,
            "video_id": video_id,
            "scene_index": 0,
            "start_shot_id": shot_id,
            "end_shot_id": shot_id,
            "start_frame": scene.start_frame,
            "end_frame": scene.end_frame,
            "start_sec": scene.start_seconds,
            "end_sec": scene.end_seconds,
            "start_seconds": scene.start_seconds,
            "end_seconds": scene.end_seconds,
            "duration_sec": max(0.0, scene.end_seconds - scene.start_seconds),
            "frame_count": max(0, scene.end_frame - scene.start_frame),
            "shot_count": len(scene.shot_ids),
            "keyframe_count": 1,
            "scene_type": "semantic",
            "shot_ids": list(scene.shot_ids),
            "boundary_convention": "[start_frame, end_frame)",
            "construction_method": scene.construction_method,
            "grouping_method": scene.construction_method,
            "grouping_version": "debug_v1",
            "confidence": 0.0,
            "provider": "SceneConstructionProvider",
            "status": scene.status,
        }],
        "keyframes": [{
            "keyframe_id": keyframe_id,
            "video_id": video_id,
            "frame_id": frame_id,
            "frame_id_method": keyframe_selection.frame_id_method,
            "timestamp_sec": keyframe_selection.time_seconds,
            "time_seconds": keyframe_selection.time_seconds,
            "pts_time": keyframe_selection.time_seconds,
            "duration_time": timeline.duration_for_frame(frame_id),
            "shot_id": shot_id,
            "scene_id": scene_id,
            "keyframe_ref": keyframe_ref,
            "thumbnail_ref": thumbnail_ref,
            "keyframe_role": "middle",
            "quality_score": 0.0,
            "is_representative": True,
            "selection_reason": "debug_single_keyframe",
            "selection_method": f"{keyframe_selection.selection_method}:{selection_method}",
            "provider": "KeyframeSelectionProvider",
            "status": keyframe_selection.status if keyframe_path.exists() and thumbnail_path.exists() else "degraded",
        }],
        "ocr": [{
            "ocr_id": f"{keyframe_id}:ocr",
            "video_id": video_id,
            "keyframe_id": keyframe_id,
            "shot_id": shot_id,
            "frame_id": frame_id,
            "text": ocr_text,
            "raw_text": ocr_text,
            "provider": provider_plan.ocr,
            "model_name": provider_plan.ocr,
            "model_version": "debug",
            "language": "vi",
            "confidence": None,
            "status": ocr_status,
        }],
        "shot_captions": [{
            "shot_caption_id": f"{shot_id}_caption",
            "video_id": video_id,
            "scene_id": scene_id,
            "shot_id": shot_id,
            "representative_keyframe_id": keyframe_id,
            "representative_timestamp_sec": keyframe_selection.time_seconds,
            "caption_vi": shot_caption_text,
            "caption_en": shot_caption_text,
            "objects_vi": [],
            "objects_en": [],
            "actions_vi": [],
            "actions_en": [],
            "visible_text_summary_vi": ocr_text,
            "visible_text_summary_en": ocr_text,
            "provider": provider_plan.shot_caption,
            "caption_model": provider_plan.shot_caption,
            "model_name": provider_plan.shot_caption,
            "model_version": "debug",
            "prompt_version": "debug_shot_caption_v2",
            "schema_version": "shot_caption_response_v3",
            "confidence": 0.0,
            "status": shot_caption_status,
        }],
        "shot_transcript_links": shot_transcript_links,
        "scene_transcript_links": scene_transcript_links,
        "scene_summaries": [{
            "scene_id": scene_id,
            "video_id": video_id,
            "summary_vi": scene_summary_text,
            "summary_en": scene_summary_text,
            "provider": provider_plan.scene_summary,
            "model_name": provider_plan.scene_summary,
            "model_version": "debug",
            "prompt_version": "debug_scene_summary_v1",
            "schema_version": "1.0.0",
            "confidence": 0.0,
            "status": scene_summary_status,
        }],
    }
    for table_name, rows in tables.items():
        _write_parquet(
            artifact_dir / f"{table_name}.parquet",
            rows,
            columns=PARQUET_COLUMNS.get(table_name),
        )
    _write_errors(artifact_dir / "errors.jsonl", errors)
    _write_json_artifact(
        artifact_dir / "manifest.json",
        {
            "video_id": video_id,
            "status": "pass" if not errors else "partial",
            "counts": {name.replace(".parquet", ""): 1 for name in STRUCTURE_PARQUET_FILES},
            "provider": providers,
            "provider_plan": provider_plan.__dict__,
            "batch_id": batch_id,
            "worker_id": worker_id,
            "created_at": "1970-01-01T00:00:00Z" if providers == "mock" else "runtime",
            "errors": errors,
            "artifact_media": {
                "keyframe_path": str((artifact_dir / "keyframes" / keyframe_filename).relative_to(artifact_dir)),
                "thumbnail_path": str((artifact_dir / "thumbnails" / thumbnail_filename).relative_to(artifact_dir)),
            },
            "phase01_contract": {
                "semantic_level": "semantic_light",
                "uses_phase00_video_facts": True,
                "uses_phase00_frame_timeline": timeline.available,
                "frame_timeline_ref": timeline.source_ref,
                "canonical_shot_captions": True,
                "bilingual_shot_captions": True,
                "shot_caption_table": "shot_captions.parquet",
                "bilingual_scene_summaries": True,
                "scene_summary_table": "scene_summaries.parquet",
            },
        },
    )
    return errors, tables


def _load_timeline_context(release_dir: Path, video: dict[str, Any]) -> tuple[TimelineContext, list[dict[str, Any]]]:
    video_id = str(video["video_id"])
    errors: list[dict[str, Any]] = []
    timeline_ref = video.get("frame_timeline_ref")
    timeline_path = release_dir / str(timeline_ref) if timeline_ref else release_dir / "frame_timeline" / f"{video_id}.parquet"
    if not timeline_path.exists():
        errors.append({
            "video_id": video_id,
            "level": "warning",
            "kind": "frame_timeline_unavailable",
            "message": f"phase00 frame timeline unavailable at {timeline_path}; exact timestamp/frame mapping is degraded",
        })
        return TimelineContext(video_id=video_id, frames=(), source_ref=str(timeline_ref) if timeline_ref else None), errors
    try:
        frame_df = pd.read_parquet(timeline_path, columns=["frame_id", "pts_time", "duration_time"])
    except Exception as exc:
        errors.append({
            "video_id": video_id,
            "level": "warning",
            "kind": "frame_timeline_read_failed",
            "message": str(exc),
        })
        return TimelineContext(video_id=video_id, frames=(), source_ref=str(timeline_ref) if timeline_ref else timeline_path.relative_to(release_dir).as_posix()), errors
    frames = tuple(
        TimelineFrame(
            frame_id=int(row["frame_id"]),
            pts_time=float(row["pts_time"]),
            duration_time=None if pd.isna(row.get("duration_time")) else float(row["duration_time"]),
        )
        for row in frame_df.sort_values("frame_id").to_dict("records")
        if row.get("frame_id") is not None and row.get("pts_time") is not None and not pd.isna(row.get("pts_time"))
    )
    return TimelineContext(
        video_id=video_id,
        frames=frames,
        source_ref=str(timeline_ref) if timeline_ref else timeline_path.relative_to(release_dir).as_posix(),
    ), errors


def _write_batch_debug_copy(path: Path, *, video_id: str, tables: dict[str, list[dict[str, Any]]]) -> None:
    payload = {"video_id": video_id, "tables": tables}
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _resolve_video_path(mapping: dict[str, Any], input_dir: Path | str | None, cache_dir: Path | None = None) -> Path:
    for key in ("video_local_path", "debug_video_local_path", "source_video_path"):
        value = mapping.get(key)
        if value:
            return Path(str(value))
    canonical = _download_canonical(mapping, "canonical_video_path", cache_dir)
    if canonical is not None:
        return canonical
    filename = mapping.get("video_filename") or Path(str(mapping.get("video_ref", ""))).name
    if input_dir and filename:
        return Path(input_dir) / "raw_videos" / str(filename)
    raise FileNotFoundError("media mapping has no video debug/source path")


def _resolve_metadata_path(mapping: dict[str, Any], input_dir: Path | str | None, cache_dir: Path | None = None) -> Path | None:
    for key in ("metadata_local_path", "debug_metadata_local_path", "source_metadata_path"):
        value = mapping.get(key)
        if value:
            return Path(str(value))
    canonical = _download_canonical(mapping, "canonical_metadata_path", cache_dir)
    if canonical is not None:
        return canonical
    filename = mapping.get("metadata_filename") or Path(str(mapping.get("metadata_ref", ""))).name
    if input_dir and filename:
        return Path(input_dir) / "metadata" / str(filename)
    return None


def _download_canonical(mapping: dict[str, Any], path_key: str, cache_dir: Path | None) -> Path | None:
    if mapping.get("canonical_backend") != "hf_dataset":
        return None
    relative_path = mapping.get(path_key)
    repo_id = mapping.get("canonical_repo_id")
    if not relative_path or not repo_id:
        return None
    if cache_dir is None:
        raise FileNotFoundError("canonical media requires a cache directory")
    target = cache_dir / Path(str(relative_path)).name
    if target.exists():
        return target
    store = HuggingFaceDatasetArtifactStore(
        repo_id=str(repo_id),
        repo_type=str(mapping.get("canonical_repo_type") or "dataset"),
        revision=str(mapping.get("canonical_revision") or "main"),
        token=os.environ.get("AIC_HF_TOKEN") or os.environ.get("HF_TOKEN"),
        prefix=str(mapping.get("canonical_prefix") or ""),
    )
    return store.download_file(str(relative_path), target)


def _read_metadata_or_empty(path: Path | None, errors: list[dict[str, Any]], video_id: str) -> dict[str, Any]:
    if path is None or not path.exists():
        errors.append({"video_id": video_id, "level": "warning", "kind": "metadata_missing", "message": "metadata file unavailable"})
        return {}
    try:
        return read_metadata(path)
    except (OSError, json.JSONDecodeError) as exc:
        errors.append({"video_id": video_id, "level": "warning", "kind": "metadata_read_failed", "message": str(exc)})
        return {}


def _text_provider_for_plan(provider_plan: ProviderPlan) -> MockTextProvider | RealProviderUnavailable:
    if provider_plan.uses_only_mock_providers:
        return MockTextProvider()
    return RealProviderUnavailable("mixed_real_unavailable")


def _transcribe(
    video_path: Path,
    provider: MockTextProvider | RealProviderUnavailable,
    provider_plan: ProviderPlan,
    errors: list[dict[str, Any]],
    video_id: str,
) -> str:
    try:
        return provider.transcribe(video_path)
    except Exception as exc:  # pragma: no cover
        errors.append({
            "video_id": video_id,
            "level": "warning",
            "kind": "asr_failed",
            "provider": provider_plan.asr,
            "message": str(exc),
        })
        return ""


def _legacy_asr_rows(
    *,
    video_id: str,
    asr_segment_id: str,
    text: str,
    end_sec: float,
    end_frame: int,
    provider: str,
) -> list[dict[str, Any]]:
    stripped = text.strip()
    if not stripped:
        return []
    canonical_provider = provider if provider in {"faster_whisper", "nemo"} else "faster_whisper"
    return [
        {
            "asr_segment_id": asr_segment_id,
            "video_id": video_id,
            "start_sec": 0.0,
            "end_sec": float(end_sec),
            "start_frame": 0,
            "end_frame": int(end_frame),
            "text": stripped,
            "language": None,
            "confidence": None,
            "avg_logprob": None,
            "no_speech_prob": None,
            "provider": canonical_provider,
            "model_name": canonical_provider,
            "model_version": "legacy-debug",
            "status": "pass",
        }
    ]


def _caption_keyframe(
    keyframe_path: Path,
    fallback_text: str,
    provider: MockTextProvider | RealProviderUnavailable,
    provider_plan: ProviderPlan,
    errors: list[dict[str, Any]],
    video_id: str,
) -> str:
    try:
        return provider.caption_image(keyframe_path, fallback_text)
    except Exception as exc:  # pragma: no cover
        errors.append({
            "video_id": video_id,
            "level": "warning",
            "kind": "keyframe_caption_failed",
            "provider": provider_plan.shot_caption,
            "message": str(exc),
        })
        return fallback_text


def _summarize_scene(
    scene_id: str,
    fallback_text: str,
    provider: MockTextProvider | RealProviderUnavailable,
    provider_plan: ProviderPlan,
    errors: list[dict[str, Any]],
    video_id: str,
) -> str:
    try:
        return provider.summarize_scene(scene_id, fallback_text)
    except Exception as exc:  # pragma: no cover
        errors.append({
            "video_id": video_id,
            "level": "warning",
            "kind": "scene_summary_failed",
            "provider": provider_plan.scene_summary,
            "message": str(exc),
        })
        return fallback_text


def _join_text(values: list[str]) -> str:
    return "\n".join(value for value in values if value)


def _extract_media(video_path: Path, keyframe_path: Path, thumbnail_path: Path, errors: list[dict[str, Any]], video_id: str) -> str:
    try:
        return extract_keyframe_and_thumbnail(video_path, keyframe_path, thumbnail_path)
    except Exception as exc:  # pragma: no cover
        errors.append({"video_id": video_id, "level": "warning", "kind": "keyframe_extract_failed", "message": str(exc)})
        return "missing_after_extract_failure"


def _write_parquet(
    path: Path,
    rows: list[dict[str, Any]],
    *,
    columns: list[str] | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=columns if not rows and columns else None).to_parquet(
        path,
        index=False,
    )


def _write_json_artifact(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_errors(path: Path, errors: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(error, ensure_ascii=False) + "\n" for error in errors), encoding="utf-8")


def _int_or_none(value: object) -> int | None:
    try:
        if value is None or pd.isna(value):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_or_zero(value: object) -> float:
    try:
        if value is None or pd.isna(value):
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0
