from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

import pandas as pd

from system1.artifacts.package import write_artifact_zip
from system1.artifacts.reports import utc_now, write_worker_report
from system1.artifacts.hf_store import HuggingFaceDatasetArtifactStore
from system1.features.providers import MockTextProvider, RealProviderUnavailable
from system1.ingest.discovery import read_metadata
from system1.keyframes.extractor import extract_keyframe_and_thumbnail
from system1.release.types import release_root
from system1.text.builder import metadata_text

STRUCTURE_PARQUET_FILES = (
    "asr_segments.parquet",
    "shots.parquet",
    "scenes.parquet",
    "keyframes.parquet",
    "shot_transcript_links.parquet",
    "scene_transcript_links.parquet",
    "scene_summaries_initial.parquet",
)


def process_structure_batch(
    output_dir: Path | str,
    *,
    input_dir: Path | str | None = None,
    batch_id: str,
    mode: str = "debug_small_sample",
    providers: str = "mock",
    worker_id: str = "worker_000",
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
        video_errors, video_tables = _write_video_structure_artifact(
            artifact_dir=artifact_dir,
            video=video,
            mapping=mapping,
            input_dir=input_dir,
            mode=mode,
            providers=providers,
            batch_id=batch_id,
            worker_id=worker_id,
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
    video: dict[str, Any],
    mapping: dict[str, Any],
    input_dir: Path | str | None,
    mode: str,
    providers: str,
    batch_id: str,
    worker_id: str,
) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    video_id = str(video["video_id"])
    errors: list[dict[str, Any]] = []
    canonical_cache_dir = artifact_dir / "_canonical_cache"
    video_path = _resolve_video_path(mapping, input_dir, canonical_cache_dir)
    metadata_path = _resolve_metadata_path(mapping, input_dir, canonical_cache_dir)
    metadata = _read_metadata_or_empty(metadata_path, errors, video_id)
    normalized_text = metadata_text(video_id, metadata)
    frame_id = 0
    frame_id_method = "first_frame_extraction_assumed_frame_0"
    frame_count = _int_or_none(video.get("frame_count"))
    end_frame = frame_count if frame_count and frame_count > 0 else 1
    duration_seconds = _float_or_zero(video.get("duration_seconds"))

    asr_text = _transcribe(video_path, providers, errors, video_id)
    asr_status = "empty" if not asr_text else "pass"
    asr_segment_id = f"{video_id}_ASR00000"
    shot_id = f"{video_id}_SH00000"
    scene_id = f"{video_id}_SC00000"
    keyframe_id = f"{video_id}:{frame_id}"
    keyframe_filename = f"{video_id}_f{frame_id:07d}.jpg"
    thumbnail_filename = f"{video_id}_f{frame_id:07d}.webp"
    keyframe_path = artifact_dir / "keyframes" / keyframe_filename
    thumbnail_path = artifact_dir / "thumbnails" / thumbnail_filename
    selection_method = _extract_media(video_path, keyframe_path, thumbnail_path, errors, video_id)
    keyframe_ref = f"media://keyframes/{video_id}/{keyframe_filename}"
    thumbnail_ref = f"media://thumbnails/{video_id}/{thumbnail_filename}"

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
        "asr_segments": [{
            "asr_segment_id": asr_segment_id,
            "video_id": video_id,
            "start_seconds": 0.0,
            "end_seconds": duration_seconds,
            "text": asr_text,
            "provider": providers,
            "status": asr_status,
        }],
        "shots": [{
            "shot_id": shot_id,
            "video_id": video_id,
            "start_frame": 0,
            "end_frame": end_frame,
            "start_seconds": 0.0,
            "end_seconds": duration_seconds,
            "boundary_convention": "[start_frame, end_frame)",
            "detection_method": "fallback_full_video",
        }],
        "scenes": [{
            "scene_id": scene_id,
            "video_id": video_id,
            "start_frame": 0,
            "end_frame": end_frame,
            "start_seconds": 0.0,
            "end_seconds": duration_seconds,
            "shot_ids": [shot_id],
            "boundary_convention": "[start_frame, end_frame)",
            "construction_method": "fallback_scene_from_full_video_shot",
        }],
        "keyframes": [{
            "keyframe_id": keyframe_id,
            "video_id": video_id,
            "frame_id": frame_id,
            "frame_id_method": frame_id_method,
            "time_seconds": 0.0,
            "shot_id": shot_id,
            "scene_id": scene_id,
            "keyframe_ref": keyframe_ref,
            "thumbnail_ref": thumbnail_ref,
            "selection_method": selection_method,
        }],
        "shot_transcript_links": [{
            "shot_id": shot_id,
            "asr_segment_id": asr_segment_id,
            "video_id": video_id,
            "coverage": 1.0,
        }],
        "scene_transcript_links": [{
            "scene_id": scene_id,
            "asr_segment_id": asr_segment_id,
            "video_id": video_id,
            "coverage": 1.0,
        }],
        "scene_summaries_initial": [{
            "scene_id": scene_id,
            "video_id": video_id,
            "summary": normalized_text,
            "provider": "metadata_fallback",
            "status": "pass" if normalized_text else "empty",
        }],
    }
    for table_name, rows in tables.items():
        _write_parquet(artifact_dir / f"{table_name}.parquet", rows)
    _write_errors(artifact_dir / "errors.jsonl", errors)
    _write_json_artifact(
        artifact_dir / "manifest.json",
        {
            "video_id": video_id,
            "status": "pass" if not errors else "partial",
            "counts": {name.replace(".parquet", ""): 1 for name in STRUCTURE_PARQUET_FILES},
            "provider": providers,
            "mode": mode,
            "batch_id": batch_id,
            "worker_id": worker_id,
            "created_at": "1970-01-01T00:00:00Z" if providers == "mock" else "runtime",
            "errors": errors,
            "artifact_media": {
                "keyframe_path": str((artifact_dir / "keyframes" / keyframe_filename).relative_to(artifact_dir)),
                "thumbnail_path": str((artifact_dir / "thumbnails" / thumbnail_filename).relative_to(artifact_dir)),
            },
        },
    )
    return errors, tables


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


def _transcribe(video_path: Path, providers: str, errors: list[dict[str, Any]], video_id: str) -> str:
    provider = MockTextProvider() if providers == "mock" else RealProviderUnavailable(providers)
    try:
        return provider.transcribe(video_path)
    except Exception as exc:  # pragma: no cover
        errors.append({"video_id": video_id, "level": "warning", "kind": "asr_failed", "message": str(exc)})
        return ""


def _extract_media(video_path: Path, keyframe_path: Path, thumbnail_path: Path, errors: list[dict[str, Any]], video_id: str) -> str:
    try:
        return extract_keyframe_and_thumbnail(video_path, keyframe_path, thumbnail_path)
    except Exception as exc:  # pragma: no cover
        errors.append({"video_id": video_id, "level": "warning", "kind": "keyframe_extract_failed", "message": str(exc)})
        return "missing_after_extract_failure"


def _write_parquet(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(path, index=False)


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
