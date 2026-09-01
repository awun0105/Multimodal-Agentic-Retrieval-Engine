from __future__ import annotations

import gc
import json
import os
import re
import shutil
import tempfile
import time
import weakref
import zipfile
from collections.abc import Callable, Generator, Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import psutil
from PIL import Image, ImageDraw, ImageOps

from system1.artifacts.checkpoint import sha256_file
from system1.artifacts.hf_store import HuggingFaceDatasetArtifactStore
from system1.artifacts.package import validate_artifact_zip, write_artifact_zip
from system1.artifacts.reports import utc_now, write_worker_report
from system1.artifacts.store import ArtifactStore
from system1.asr import AsrResourceError, build_shot_transcript_links, transcribe_video
from system1.config import ResolvedPhase01Config, persist_resolved_phase01_config
from system1.ingest.discovery import read_metadata
from system1.keyframes import (
    candidate_frame_ids_for_shot,
    iter_decode_frame_groups,
    select_keyframes_for_shot,
    select_supplemental_keyframes,
    temporal_probe_plan_for_shot,
    text_presence_gate,
    write_keyframe_images,
)
from system1.phase01.checkpoint import CheckpointManager, compute_fingerprint
from system1.phase01.qa import write_manual_review_report
from system1.phase01.scheduler import plan_runtime_chunks
from system1.phase01.validation import validate_phase01_package, validate_rows
from system1.scenes import (
    SceneGroupingResult,
    ScenePartitionQualityError,
    group_scenes,
)
from system1.scenes.vlm_judge import SemanticSceneBoundaryJudge
from system1.shots import (
    detect_shot_scenes,
    load_transnet_artifact,
    scenes_to_shot_rows,
)
from system1.vlm import (
    TEXT_RESPONSE_SCHEMA,
    BatchRequestError,
    ExclusiveLocalFallbackClient,
    LocalVisionStructuredClient,
    ModelRequest,
    SystemicProviderError,
    build_text_prompt,
)

SHOT_CAPTION_FIELDS = (
    "caption_vi",
    "caption_en",
    "objects_vi",
    "objects_en",
    "actions_vi",
    "actions_en",
    "visible_text_summary_vi",
    "visible_text_summary_en",
)

SHOT_CAPTION_FIELD_KIND = {
    "caption_vi": "required_text",
    "caption_en": "required_text",
    "objects_vi": "line_list",
    "objects_en": "line_list",
    "actions_vi": "line_list",
    "actions_en": "line_list",
    "visible_text_summary_vi": "optional_text",
    "visible_text_summary_en": "optional_text",
}

PARQUET_COLUMNS: dict[str, list[str]] = {
    "asr_segments": [
        "asr_segment_id", "video_id", "start_sec", "end_sec", "start_frame", "end_frame",
        "text", "language", "confidence", "avg_logprob", "no_speech_prob", "provider",
        "model_name", "model_version", "status",
    ],
    "shot_transcript_links": ["video_id", "shot_id", "asr_segment_id", "coverage"],
    "scene_transcript_links": ["video_id", "scene_id", "asr_segment_id", "coverage"],
    "ocr": [
        "ocr_id", "video_id", "keyframe_id", "shot_id", "frame_id", "text", "raw_text",
        "provider", "model_name", "model_version", "language", "confidence", "status",
    ],
}


@dataclass
class _VideoFlow:
    video_id: str
    video_index: int
    scratch: Path
    manager: CheckpointManager
    pipeline: Generator[str, Any, dict[str, Any]]


class InsufficientMemoryError(RuntimeError):
    """Retryable host-memory pressure that blocks a heavy model load."""


_MANAGER_RUNTIME_CONTEXT: weakref.WeakKeyDictionary[
    CheckpointManager, dict[str, Any]
] = weakref.WeakKeyDictionary()
_STAGE_TIMERS: dict[tuple[int, str], float] = {}


def process_production_batch(
    *,
    release_dir: Path,
    config: ResolvedPhase01Config,
    scratch_root: Path,
    transnet_artifact_dir: Path,
    sync_release: bool = True,
) -> Path:
    runtime = config.payload["runtime"]
    release_id = str(runtime["release_id"])
    batch_id = str(runtime["batch_id"])
    worker_id = str(runtime["worker_id"])
    started_at = utc_now()
    batch_path = release_dir / "manifests" / f"{batch_id}.txt"
    video_ids = [line.strip() for line in batch_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    duplicate_video_ids = sorted(
        video_id for video_id in set(video_ids) if video_ids.count(video_id) > 1
    )
    if duplicate_video_ids:
        raise ValueError(
            "Phase01 batch manifest contains duplicate video IDs: "
            + ", ".join(duplicate_video_ids)
        )
    videos = pd.read_parquet(release_dir / "tables" / "videos.parquet")
    media = pd.read_parquet(release_dir / "raw_mapping" / "media_store_manifest.parquet")
    videos_by_id = {str(row["video_id"]): row for row in videos.to_dict("records")}
    media_by_id = {str(row["video_id"]): row for row in media.to_dict("records")}
    del videos, media
    result_slots: list[dict[str, Any] | None] = [None] * len(video_ids)
    scratch_root.mkdir(parents=True, exist_ok=True)
    _emit_progress(
        event="batch",
        status="start",
        scratch=scratch_root,
        release_id=release_id,
        batch_id=batch_id,
        video_count=len(video_ids),
    )

    raw_bytes_by_video = {
        video_id: _mapping_raw_bytes(mapping)
        for video_id, mapping in media_by_id.items()
    }
    pending = list(video_ids)
    video_offsets = {video_id: index for index, video_id in enumerate(video_ids)}
    chunk_index = 0
    scheduler_policy = config.payload["phase01"]["execution"]["chunk_scheduler"]
    while pending:
        planned = plan_runtime_chunks(
            pending,
            raw_bytes_by_video=raw_bytes_by_video,
            free_disk_gb=_scratch_free_gb(scratch_root),
            available_ram_gb=_available_ram_gb(),
            policy=scheduler_policy,
        )[0]
        chunk_index += 1
        chunk_video_ids = list(planned.video_ids)
        pending = pending[len(chunk_video_ids) :]
        chunk_size = len(chunk_video_ids)
        chunk_scratch = (
            scratch_root
            / release_id
            / batch_id
            / ".runtime_chunks"
            / f"chunk_{chunk_index:04d}"
        )
        shutil.rmtree(chunk_scratch, ignore_errors=True)
        chunk_scratch.mkdir(parents=True)
        _emit_progress(
            event="chunk",
            status="start",
            scratch=scratch_root,
            release_id=release_id,
            batch_id=batch_id,
            chunk_index=chunk_index,
            chunk_size=chunk_size,
            chunk_raw_bytes=planned.raw_bytes,
        )
        _emit_progress(
            event="memory",
            status="chunk_start",
            scratch=scratch_root,
            release_id=release_id,
            batch_id=batch_id,
            chunk_index=chunk_index,
            chunk_size=chunk_size,
            chunk_raw_bytes=planned.raw_bytes,
        )
        asr_pre_load_callback = _heavy_model_memory_guard(
            scratch_root=scratch_root,
            release_id=release_id,
            batch_id=batch_id,
            chunk_index=chunk_index,
            chunk_size=chunk_size,
            policy=scheduler_policy["ram"],
        )

        active: list[_VideoFlow] = []
        for video_id in chunk_video_ids:
            video_index = video_offsets[video_id] + 1
            video_scratch = scratch_root / release_id / batch_id / video_id
            shutil.rmtree(video_scratch, ignore_errors=True)
            video_scratch.mkdir(parents=True)
            checkpoint_store = _hf_store(
                config.payload["storage"]["checkpoint"],
                cache_dir=video_scratch / "hf_cache" / "checkpoint",
            )
            release_store = _hf_store(
                config.payload["storage"]["release"],
                cache_dir=video_scratch / "hf_cache" / "release",
            )
            manager = CheckpointManager(
                checkpoint_store,
                release_id=release_id,
                video_id=video_id,
                config_hash=config.config_hash,
                stage_config_hashes=config.stage_config_hashes,
                verify_remote_checksum=bool(
                    config.payload["storage"]["checkpoint"].get(
                        "verify_remote_checksum", True
                    )
                ),
                root_template=str(
                    config.payload["artifact"]["checkpoint"]["root"]
                ),
                state_filename=str(
                    config.payload["artifact"]["checkpoint"]["state_filename"]
                ),
            )
            _MANAGER_RUNTIME_CONTEXT[manager] = {
                "chunk_index": chunk_index,
                "chunk_size": chunk_size,
                "stage_sources": {},
            }
            _emit_progress(
                event="video",
                status="start",
                scratch=scratch_root,
                release_id=release_id,
                batch_id=batch_id,
                video_id=video_id,
                video_index=video_index,
                video_count=len(video_ids),
                chunk_index=chunk_index,
                chunk_size=chunk_size,
            )
            flow: _VideoFlow | None = None
            try:
                if video_id not in videos_by_id or video_id not in media_by_id:
                    raise ValueError(
                        f"Phase00 batch references unknown video_id={video_id}"
                    )
                pipeline = _process_video_flow(
                    video_id=video_id,
                    video_row=videos_by_id[video_id],
                    mapping=media_by_id[video_id],
                    release_dir=release_dir,
                    scratch=video_scratch,
                    manager=manager,
                    config=config,
                    transnet_artifact_dir=transnet_artifact_dir,
                    release_store=release_store,
                    sync_release=sync_release,
                    asr_pre_load_callback=asr_pre_load_callback,
                )
                flow = _VideoFlow(
                    video_id=video_id,
                    video_index=video_index,
                    scratch=video_scratch,
                    manager=manager,
                    pipeline=pipeline,
                )
                yielded = next(pipeline)
                if yielded != "ocr":
                    raise RuntimeError(
                        f"Phase01 video flow expected ocr, received {yielded!r}"
                    )
                active.append(flow)
            except Exception as exc:  # noqa: BLE001 - isolate failures per video
                if flow is None:
                    flow = _VideoFlow(
                        video_id=video_id,
                        video_index=video_index,
                        scratch=video_scratch,
                        manager=manager,
                        pipeline=_empty_video_flow(),
                    )
                _finish_failed_video(
                    flow,
                    exc,
                    result_slots=result_slots,
                    scratch_root=scratch_root,
                    release_id=release_id,
                    batch_id=batch_id,
                    video_count=len(video_ids),
                )

        active = _run_chunk_client_phase(
            active,
            model_config=config.payload["models"]["ocr"],
            phase01=config.payload["phase01"],
            cache=ArtifactStore(chunk_scratch / "ocr_api_cache"),
            cache_prefix="ocr",
            expected_yields=("shot_captions",),
            model_role="ocr",
            result_slots=result_slots,
            scratch_root=scratch_root,
            release_id=release_id,
            batch_id=batch_id,
            video_count=len(video_ids),
            chunk_index=chunk_index,
            chunk_size=chunk_size,
        )
        active = _run_chunk_client_phase(
            active,
            model_config=config.payload["models"]["shot_caption"],
            phase01=config.payload["phase01"],
            cache=ArtifactStore(chunk_scratch / "caption_api_cache"),
            cache_prefix="shot_caption",
            expected_yields=("scenes", "scene_summaries", "finalize"),
            model_role="semantic",
            result_slots=result_slots,
            scratch_root=scratch_root,
            release_id=release_id,
            batch_id=batch_id,
            video_count=len(video_ids),
            chunk_index=chunk_index,
            chunk_size=chunk_size,
        )
        for flow in active:
            try:
                yielded = next(flow.pipeline)
            except StopIteration as completed:
                result = completed.value
                if not isinstance(result, dict):
                    _finish_failed_video(
                        flow,
                        RuntimeError("Phase01 video flow returned an invalid result"),
                        result_slots=result_slots,
                        scratch_root=scratch_root,
                        release_id=release_id,
                        batch_id=batch_id,
                        video_count=len(video_ids),
                    )
                    continue
                _finish_video(
                    flow,
                    result,
                    result_slots=result_slots,
                    scratch_root=scratch_root,
                    release_id=release_id,
                    batch_id=batch_id,
                    video_count=len(video_ids),
                )
            except Exception as exc:  # noqa: BLE001 - isolate failures per video
                _finish_failed_video(
                    flow,
                    exc,
                    result_slots=result_slots,
                    scratch_root=scratch_root,
                    release_id=release_id,
                    batch_id=batch_id,
                    video_count=len(video_ids),
                )
            else:
                _finish_failed_video(
                    flow,
                    RuntimeError(
                        "Phase01 video flow yielded unexpectedly during finalize: "
                        f"{yielded!r}"
                    ),
                    result_slots=result_slots,
                    scratch_root=scratch_root,
                    release_id=release_id,
                    batch_id=batch_id,
                    video_count=len(video_ids),
                )
        active.clear()
        flow = None
        pipeline = None
        manager = None
        checkpoint_store = None
        release_store = None
        shutil.rmtree(chunk_scratch, ignore_errors=True)
        _cleanup_runtime_resources()
        _emit_progress(
            event="memory",
            status="chunk_end",
            scratch=scratch_root,
            release_id=release_id,
            batch_id=batch_id,
            chunk_index=chunk_index,
            chunk_size=chunk_size,
            chunk_raw_bytes=planned.raw_bytes,
        )
        _emit_progress(
            event="chunk",
            status="complete",
            scratch=scratch_root,
            release_id=release_id,
            batch_id=batch_id,
            chunk_index=chunk_index,
            chunk_size=chunk_size,
            chunk_raw_bytes=planned.raw_bytes,
        )

    shutil.rmtree(
        scratch_root / release_id / batch_id / ".runtime_chunks",
        ignore_errors=True,
    )
    if any(result is None for result in result_slots):
        raise RuntimeError("Phase01 scheduler finished without a result for every video")
    results = [result for result in result_slots if result is not None]

    failed = [row for row in results if not row["status"].startswith("complete")]
    manual_review_path = write_manual_review_report(
        release_dir=release_dir,
        batch_id=batch_id,
        worker_id=worker_id,
        video_results=results,
        sample_size=int(config.payload["phase01"]["manual_review"]["sample_size"]),
    )
    report = write_worker_report(
        release_dir,
        phase="structure",
        batch_id=batch_id,
        worker_id=worker_id,
        started_at=started_at,
        finished_at=utc_now(),
        videos_processed=len(results),
        videos_failed=len(failed),
        payload={
            "schema_version": "phase01_worker_report_v2",
            "release_id": release_id,
            "config_hash": config.config_hash,
            "manual_review": {
                "status": "pending_manual_review",
                "path": str(manual_review_path),
            },
            "counts": {
                "complete": sum(row["status"] == "complete" for row in results),
                "complete_local": sum(row["status"] == "complete_local" for row in results),
                "failed_retryable": sum(row["status"] == "failed_retryable" for row in results),
                "failed_terminal": sum(row["status"] == "failed_terminal" for row in results),
            },
            "videos": results,
        },
    )
    errors_path = release_dir / "manifests" / "phase01" / f"errors_{batch_id}_{worker_id}.jsonl"
    _write_jsonl(errors_path, failed)
    if sync_release:
        release_store = _hf_store(config.payload["storage"]["release"])
        remote_root = f"{release_id}/phase01_structure"
        release_store.upload_files(
            [
                (report, f"{remote_root}/worker_reports/{report.name}"),
                (errors_path, f"{remote_root}/worker_reports/{errors_path.name}"),
                (
                    manual_review_path,
                    f"{remote_root}/worker_reports/{manual_review_path.name}",
                ),
            ],
            commit_message=f"Upload Phase01 worker report {batch_id}/{worker_id}",
            num_threads=2,
        )
    _emit_progress(
        event="batch",
        status="complete" if not failed else "failed",
        scratch=scratch_root,
        release_id=release_id,
        batch_id=batch_id,
        video_count=len(video_ids),
        failed_count=len(failed),
    )
    if failed:
        raise RuntimeError(
            f"Phase01 batch completed with {len(failed)} failed video(s); report={report}"
        )
    return report


def _run_chunk_client_phase(
    flows: list[_VideoFlow],
    *,
    model_config: Mapping[str, Any],
    phase01: Mapping[str, Any],
    cache: ArtifactStore,
    cache_prefix: str,
    expected_yields: tuple[str, ...],
    model_role: str,
    result_slots: list[dict[str, Any] | None],
    scratch_root: Path,
    release_id: str,
    batch_id: str,
    video_count: int,
    chunk_index: int,
    chunk_size: int,
) -> list[_VideoFlow]:
    if not flows:
        return []
    if model_role not in {"ocr", "semantic"}:
        raise ValueError(f"Unsupported chunk model role: {model_role}")
    if not expected_yields:
        raise ValueError("Chunk client phase requires at least one expected yield")

    stage = "shot_captions" if model_role == "semantic" else "ocr"
    lifecycle_callback = _model_lifecycle_callback(
        scratch_root=scratch_root,
        release_id=release_id,
        batch_id=batch_id,
        chunk_index=chunk_index,
        chunk_size=chunk_size,
        stage=stage,
    )
    pre_load_callback = _heavy_model_memory_guard(
        scratch_root=scratch_root,
        release_id=release_id,
        batch_id=batch_id,
        chunk_index=chunk_index,
        chunk_size=chunk_size,
        policy=phase01["execution"]["chunk_scheduler"]["ram"],
    )
    try:
        if model_role == "semantic":
            client = _caption_client_for_model(
                model_config,
                phase01=phase01,
                cache=cache,
                lifecycle_callback=lifecycle_callback,
                pre_load_callback=pre_load_callback,
            )
        else:
            client = _structured_client_for_model(
                model_config,
                phase01=phase01,
                cache=cache,
                cache_prefix=cache_prefix,
                lifecycle_callback=lifecycle_callback,
                pre_load_callback=pre_load_callback,
            )
    except Exception as exc:  # noqa: BLE001 - fail only this chunk stage
        for flow in flows:
            flow.manager.active_stage = stage
            _emit_stage_progress(
                flow.manager, stage, scratch_root, status="start"
            )
            _finish_failed_video(
                flow,
                exc,
                result_slots=result_slots,
                scratch_root=scratch_root,
                release_id=release_id,
                batch_id=batch_id,
                video_count=video_count,
            )
        return []

    survivors = list(flows)
    try:
        for step_index, expected_yield in enumerate(expected_yields):
            next_survivors: list[_VideoFlow] = []
            for flow in survivors:
                try:
                    yielded = flow.pipeline.send(client if step_index == 0 else None)
                    if yielded != expected_yield:
                        raise RuntimeError(
                            "Phase01 video flow expected "
                            f"{expected_yield}, received {yielded!r}"
                        )
                    next_survivors.append(flow)
                except Exception as exc:  # noqa: BLE001 - isolate failures per video
                    _finish_failed_video(
                        flow,
                        exc,
                        result_slots=result_slots,
                        scratch_root=scratch_root,
                        release_id=release_id,
                        batch_id=batch_id,
                        video_count=video_count,
                    )
            survivors = next_survivors
            if not survivors:
                break
            if model_role == "semantic":
                milestone = {
                    "scenes": "after_captions",
                    "scene_summaries": "after_scenes",
                    "finalize": "after_summaries",
                }[expected_yield]
                _emit_progress(
                    event="memory",
                    status=milestone,
                    scratch=scratch_root,
                    release_id=release_id,
                    batch_id=batch_id,
                    chunk_index=chunk_index,
                    chunk_size=chunk_size,
                    active_video_count=len(survivors),
                )
    finally:
        _release_structured_client(client)
        client = None
        if model_role == "ocr":
            _emit_progress(
                event="memory",
                status="after_ocr",
                scratch=scratch_root,
                release_id=release_id,
                batch_id=batch_id,
                chunk_index=chunk_index,
                chunk_size=chunk_size,
                active_video_count=len(survivors),
            )
        else:
            _emit_progress(
                event="memory",
                status="semantic_models_unloaded",
                scratch=scratch_root,
                release_id=release_id,
                batch_id=batch_id,
                chunk_index=chunk_index,
                chunk_size=chunk_size,
                active_video_count=len(survivors),
            )
    return survivors


def _finish_failed_video(
    flow: _VideoFlow,
    exc: Exception,
    *,
    result_slots: list[dict[str, Any] | None],
    scratch_root: Path,
    release_id: str,
    batch_id: str,
    video_count: int,
) -> None:
    retryable = _retryable_video_error(exc)
    checkpoint_error: str | None = None
    failed_stage = flow.manager.active_stage
    error_payload = _checkpoint_error_payload(exc)
    _emit_stage_progress(
        flow.manager,
        failed_stage,
        scratch_root,
        status="failed_retryable" if retryable else "failed_terminal",
    )
    try:
        flow.manager.mark_failed(
            failed_stage,
            input_fingerprint=None,
            retryable=retryable,
            error=error_payload,
        )
    except Exception as checkpoint_exc:  # noqa: BLE001 - retain original error
        failed_stage = "unknown"
        checkpoint_error = str(checkpoint_exc)
    result = {
        "video_id": flow.video_id,
        "status": "failed_retryable" if retryable else "failed_terminal",
        "failed_stage": failed_stage,
        "error_type": type(exc).__name__,
        "error": str(exc),
        "error_details": error_payload.get("details"),
        "checkpoint_error": checkpoint_error,
    }
    flow.pipeline.close()
    _finish_video(
        flow,
        result,
        result_slots=result_slots,
        scratch_root=scratch_root,
        release_id=release_id,
        batch_id=batch_id,
        video_count=video_count,
    )


def _finish_video(
    flow: _VideoFlow,
    result: dict[str, Any],
    *,
    result_slots: list[dict[str, Any] | None],
    scratch_root: Path,
    release_id: str,
    batch_id: str,
    video_count: int,
) -> None:
    runtime_context = _MANAGER_RUNTIME_CONTEXT.get(flow.manager, {})
    result.setdefault(
        "stage_sources",
        dict(runtime_context.get("stage_sources", {})),
    )
    result_slots[flow.video_index - 1] = result
    shutil.rmtree(flow.scratch, ignore_errors=True)
    _emit_progress(
        event="video_cache_cleanup",
        status="complete",
        scratch=scratch_root,
        release_id=release_id,
        batch_id=batch_id,
        video_id=flow.video_id,
        **runtime_context,
    )
    result_progress = {
        key: result[key]
        for key in ("failed_stage", "error_type")
        if result.get(key) is not None
    }
    _emit_progress(
        event="video",
        status=str(result["status"]),
        scratch=scratch_root,
        release_id=release_id,
        batch_id=batch_id,
        video_id=flow.video_id,
        video_index=flow.video_index,
        video_count=video_count,
        **runtime_context,
        **result_progress,
    )
    _MANAGER_RUNTIME_CONTEXT.pop(flow.manager, None)


def _empty_video_flow() -> Generator[str, Any, dict[str, Any]]:
    if False:  # pragma: no cover - typed empty generator
        yield ""
    return {}


def _process_video_flow(
    *,
    video_id: str,
    video_row: dict[str, Any],
    mapping: dict[str, Any],
    release_dir: Path,
    scratch: Path,
    manager: CheckpointManager,
    config: ResolvedPhase01Config,
    transnet_artifact_dir: Path,
    release_store: HuggingFaceDatasetArtifactStore,
    sync_release: bool,
    asr_pre_load_callback: Callable[[str], None] | None = None,
) -> Generator[str, Any, dict[str, Any]]:
    manager.active_stage = "shots"
    _emit_stage_progress(manager, "shots", scratch, status="start")
    stage_dir = scratch / "stages"
    stage_dir.mkdir(exist_ok=True)
    video_path = _materialize_canonical(mapping, "canonical_video_path", scratch / "source")
    metadata_path = _materialize_canonical(mapping, "canonical_metadata_path", scratch / "source")
    timeline_path = _timeline_path(release_dir, video_id, video_row)
    timeline = pd.read_parquet(timeline_path).sort_values("frame_id").to_dict("records")
    if not timeline:
        raise ValueError(f"Phase00 frame timeline is empty for {video_id}")
    video_timeline_fingerprint = compute_fingerprint(
        _stable_video_identity(mapping),
        sha256_file(video_path),
        sha256_file(timeline_path),
        len(timeline),
    )
    metadata_fingerprint = compute_fingerprint(
        _stable_metadata_identity(mapping),
        sha256_file(metadata_path),
    )
    models = config.payload["models"]
    phase01 = config.payload["phase01"]
    scene_boundary_model = _semantic_model_config(models, "scene_boundary")
    scene_summary_model = _semantic_model_config(models, "scene_summary")
    media_config = config.payload["media"]

    shots_path = stage_dir / "shots.parquet"
    shots_fingerprint = compute_fingerprint(
        video_timeline_fingerprint, config.stage_config_hashes["shots"]
    )
    shots_reused = _restore_if_reusable(manager, "shots", shots_fingerprint, stage_dir)
    if not shots_reused:
        artifact = load_transnet_artifact(
            transnet_artifact_dir,
            expected_commit=str(models["shot_detection"]["model_revision"]),
            expected_source_sha256=str(
                models["shot_detection"]["source_sha256"]
            ),
            expected_weights_sha256=str(models["shot_detection"]["weights_sha256"]),
            expected_conversion_verified=bool(
                models["shot_detection"].get("conversion_verified", True)
            ),
        )
        prediction_path = stage_dir / "transnet_predictions.json"
        predictions = detect_shot_scenes(
            video_path,
            artifact=artifact,
            output_path=prediction_path,
            threshold=float(models["shot_detection"]["threshold"]),
            transition_run_boundary=str(
                models["shot_detection"]["transition_run_boundary"]
            ),
            expected_frame_count=len(timeline),
            total_attempts=int(phase01["retry"]["local_model_total_attempts"]),
        )
        shots = scenes_to_shot_rows(
            video_id=video_id,
            scenes_inclusive=predictions["scenes_inclusive"],
            frame_timeline=timeline,
        )
        _write_parquet(shots_path, shots)
        manager.promote_stage(
            "shots",
            input_fingerprint=shots_fingerprint,
            outputs=[shots_path, prediction_path],
            model=models["shot_detection"],
            schema_version=phase01["schemas"]["shots"],
        )
    _emit_stage_progress(
        manager, "shots", scratch, status="complete", reused=shots_reused
    )
    shots = pd.read_parquet(shots_path).to_dict("records")
    shots_output_fingerprint = manager.stage_output_fingerprint("shots")

    manager.active_stage = "keyframes"
    _emit_stage_progress(manager, "keyframes", scratch, status="start")
    keyframes_path = stage_dir / "keyframes.parquet"
    keyframes_bundle = stage_dir / "keyframes.zip"
    keyframes_fingerprint = _stage_fingerprint(
        manager, "keyframes", shots_output_fingerprint
    )
    keyframes_reused = _restore_keyframes_if_reusable(
        manager, keyframes_fingerprint, stage_dir
    )
    if not keyframes_reused:
        _build_keyframes(
            video_id=video_id,
            video_path=video_path,
            shots=shots,
            timeline=timeline,
            output_dir=stage_dir,
            config=media_config,
        )
        _write_directory_zip(stage_dir, keyframes_bundle, ("keyframes.parquet", "keyframes", "thumbnails", "keyframe_diagnostics.jsonl"))
        manager.promote_stage(
            "keyframes",
            input_fingerprint=keyframes_fingerprint,
            outputs=[keyframes_bundle],
            schema_version=phase01["schemas"]["keyframes"],
        )
    _emit_stage_progress(
        manager, "keyframes", scratch, status="complete", reused=keyframes_reused
    )
    keyframes = pd.read_parquet(keyframes_path).to_dict("records")
    keyframes_output_fingerprint = manager.stage_output_fingerprint("keyframes")

    manager.active_stage = "asr"
    _emit_stage_progress(manager, "asr", scratch, status="start")
    asr_path = stage_dir / "asr_segments.parquet"
    asr_status_path = stage_dir / "asr_status.json"
    asr_diagnostics_path = stage_dir / "asr_diagnostics.jsonl"
    asr_fingerprint = compute_fingerprint(
        video_timeline_fingerprint, config.stage_config_hashes["asr"]
    )
    asr_reused = _restore_if_reusable(manager, "asr", asr_fingerprint, stage_dir)
    if not asr_reused:
        asr_config = {**models["asr"], "total_attempts": phase01["retry"]["local_model_total_attempts"]}
        result = transcribe_video(
            video_path,
            video_id=video_id,
            frame_timeline=timeline,
            config=asr_config,
            pre_load_callback=asr_pre_load_callback,
        )
        _write_parquet(asr_path, result.rows, empty_columns=PARQUET_COLUMNS["asr_segments"])
        _write_jsonl(asr_diagnostics_path, result.diagnostics)
        _write_json(asr_status_path, {
            "status": result.status,
            "compute_type": result.compute_type,
            "attempts": result.attempts,
            "detected_language": result.detected_language,
            **result.status_details,
        })
        manager.promote_stage(
            "asr",
            input_fingerprint=asr_fingerprint,
            outputs=[asr_path, asr_status_path, asr_diagnostics_path],
            model=models["asr"],
            schema_version=phase01["schemas"]["asr_segments"],
        )
    _emit_stage_progress(
        manager, "asr", scratch, status="complete", reused=asr_reused
    )
    asr_rows = pd.read_parquet(asr_path).to_dict("records")
    asr_output_fingerprint = manager.stage_output_fingerprint("asr")

    # The decoded Phase00 timeline can be very large. Release it before this
    # prepared video waits for the other videos in its runtime chunk.
    timeline = []
    ocr_client = yield "ocr"
    manager.active_stage = "ocr"
    _emit_stage_progress(manager, "ocr", scratch, status="start")
    ocr_path = stage_dir / "ocr.parquet"
    ocr_status_path = stage_dir / "ocr_status.json"
    ocr_fingerprint = _stage_fingerprint(manager, "ocr", keyframes_output_fingerprint)
    ocr_reused = _restore_if_reusable(manager, "ocr", ocr_fingerprint, stage_dir)
    if not ocr_reused:
        if ocr_client is None:
            raise RuntimeError("Phase01 OCR stage requires a structured client")
        try:
            ocr_gate_counts: dict[str, int] = {}
            ocr_rows = _build_ocr(
                video_id=video_id,
                keyframes=keyframes,
                stage_dir=stage_dir,
                client=ocr_client,
                model_config=models["ocr"],
                ocr_config=phase01["ocr"],
                diagnostics=ocr_gate_counts,
            )
            _write_parquet(ocr_path, ocr_rows, empty_columns=PARQUET_COLUMNS["ocr"])
            status_counts: dict[str, int] = {}
            for row in ocr_rows:
                status = str(row["status"])
                status_counts[status] = status_counts.get(status, 0) + 1
            ocr_status = _ocr_stage_status(status_counts, ocr_gate_counts)
            _write_json(ocr_status_path, {
                "status": ocr_status,
                "provider": models["ocr"]["provider"],
                "model_id": models["ocr"]["model_id"],
                "status_counts": status_counts,
                **ocr_gate_counts,
            })
            _emit_progress(
                event="ocr_gate",
                status="complete",
                scratch=scratch,
                release_id=manager.release_id,
                video_id=video_id,
                **_MANAGER_RUNTIME_CONTEXT.get(manager, {}),
                **ocr_gate_counts,
            )
            if ocr_status == "failed":
                raise RuntimeError(
                    "Phase01 OCR failed for every Vintern request: "
                    f"video_id={video_id}, "
                    f"failed={status_counts.get('failed', 0)}, "
                    "vintern_processed="
                    f"{ocr_gate_counts.get('vintern_processed', 0)}"
                )
            manager.promote_stage(
                "ocr",
                input_fingerprint=ocr_fingerprint,
                outputs=[ocr_path, ocr_status_path],
                model=models["ocr"],
                prompt_version=models["ocr"]["prompt_version"],
                schema_version=phase01["schemas"]["ocr"],
            )
        finally:
            pass  # The chunk scheduler owns the shared client lifecycle.
    _emit_stage_progress(manager, "ocr", scratch, status="complete", reused=ocr_reused)
    ocr_rows = pd.read_parquet(ocr_path).to_dict("records")
    ocr_output_fingerprint = manager.stage_output_fingerprint("ocr")

    caption_client = yield "shot_captions"
    manager.active_stage = "shot_captions"
    _emit_stage_progress(manager, "shot_captions", scratch, status="start")
    captions_path = stage_dir / "shot_captions.parquet"
    captions_fingerprint = _stage_fingerprint(
        manager, "shot_captions", compute_fingerprint(keyframes_output_fingerprint, ocr_output_fingerprint)
    )
    captions_reused = _restore_if_reusable(
        manager, "shot_captions", captions_fingerprint, stage_dir
    )
    if not captions_reused:
        if caption_client is None:
            raise RuntimeError(
                "Phase01 shot_captions stage requires a structured client"
            )
        try:
            caption_rows = _build_captions(
                video_id=video_id,
                shots=shots,
                keyframes=keyframes,
                ocr_rows=ocr_rows,
                stage_dir=stage_dir,
                client=caption_client,
                model_config=models["shot_caption"],
            )
            _write_parquet(captions_path, caption_rows)
            caption_provenance = stage_dir / "shot_caption_field_provenance.jsonl"
            manager.promote_stage(
                "shot_captions",
                input_fingerprint=captions_fingerprint,
                outputs=[captions_path, caption_provenance],
                model=models["shot_caption"],
                prompt_version=models["shot_caption"]["prompt_bundle_version"],
                schema_version=phase01["schemas"]["shot_captions"],
            )
            del caption_rows
        finally:
            pass  # The chunk scheduler owns the shared client lifecycle.
    _emit_stage_progress(
        manager,
        "shot_captions",
        scratch,
        status="complete",
        reused=captions_reused,
    )
    captions = pd.read_parquet(captions_path).to_dict("records")
    captions_output_fingerprint = manager.stage_output_fingerprint("shot_captions")

    manager.active_stage = "shot_transcript_links"
    _emit_stage_progress(manager, "shot_transcript_links", scratch, status="start")
    links_path = stage_dir / "shot_transcript_links.parquet"
    links_fingerprint = compute_fingerprint(
        shots_output_fingerprint,
        asr_output_fingerprint,
        config.stage_config_hashes["shot_transcript_links"],
    )
    links_reused = _restore_if_reusable(
        manager, "shot_transcript_links", links_fingerprint, stage_dir
    )
    if not links_reused:
        links = build_shot_transcript_links(shots, asr_rows)
        _write_parquet(links_path, links, empty_columns=PARQUET_COLUMNS["shot_transcript_links"])
        manager.promote_stage(
            "shot_transcript_links",
            input_fingerprint=links_fingerprint,
            outputs=[links_path],
            schema_version=phase01["schemas"]["shot_transcript_links"],
        )
    _emit_stage_progress(
        manager,
        "shot_transcript_links",
        scratch,
        status="complete",
        reused=links_reused,
    )
    links = pd.read_parquet(links_path).to_dict("records")
    links_output_fingerprint = manager.stage_output_fingerprint(
        "shot_transcript_links"
    )

    yield "scenes"

    manager.active_stage = "scenes"
    _emit_stage_progress(manager, "scenes", scratch, status="start")
    scenes_path = stage_dir / "scenes.parquet"
    scene_links_path = stage_dir / "scene_transcript_links.parquet"
    scene_diagnostics_path = stage_dir / "scene_boundary_diagnostics.jsonl"
    scene_quality_path = stage_dir / "scene_partition_quality.json"
    scenes_fingerprint = compute_fingerprint(
        shots_output_fingerprint,
        keyframes_output_fingerprint,
        ocr_output_fingerprint,
        captions_output_fingerprint,
        asr_output_fingerprint,
        links_output_fingerprint,
        config.stage_config_hashes["scenes"],
    )
    scenes_reused = _restore_if_reusable(
        manager, "scenes", scenes_fingerprint, stage_dir
    )
    if not scenes_reused:
        evidence = _build_scene_evidence(shots, keyframes, ocr_rows, captions, asr_rows, links, stage_dir)
        judge = SemanticSceneBoundaryJudge(
            caption_client,
            video_id=video_id,
            prompt_dir=_prompt_dir(),
            diagnostics_dir=stage_dir / "diagnostics" / "scene_requests",
            model_config=scene_boundary_model,
            focused_keyframe_roles=tuple(
                str(role)
                for role in phase01["scene_grouping"][
                    "focused_review_keyframe_roles"
                ]
            ),
            max_ocr_chars_per_shot=int(
                phase01["scene_grouping"]["max_ocr_chars_per_shot"]
            ),
            max_transcript_chars_per_shot=int(
                phase01["scene_grouping"]["max_transcript_chars_per_shot"]
            ),
        )
        grouping_result = group_scenes(
            video_id=video_id,
            shots=shots,
            evidence=evidence,
            judge=judge,
            config=phase01["scene_grouping"],
        )
        quality_payload = _scene_partition_quality_payload(
            video_id=video_id,
            result=grouping_result,
            policy=phase01["scene_grouping"]["quality_guard"],
        )
        _write_json(scene_quality_path, quality_payload)
        _write_jsonl(
            scene_diagnostics_path,
            [asdict(decision) for decision in grouping_result.decisions],
        )
        _emit_scene_partition_quality(
            manager=manager,
            scratch=scratch,
            payload=quality_payload,
        )
        _require_scene_partition_quality(
            video_id=video_id,
            result=grouping_result,
            payload=quality_payload,
        )
        scenes = grouping_result.scenes
        decisions = grouping_result.decisions
        _write_parquet(scenes_path, scenes)
        scene_links = _build_scene_transcript_links(scenes, asr_rows)
        _write_parquet(
            scene_links_path,
            scene_links,
            empty_columns=PARQUET_COLUMNS["scene_transcript_links"],
        )
        manager.promote_stage(
            "scenes",
            input_fingerprint=scenes_fingerprint,
            outputs=[
                scenes_path,
                scene_links_path,
                scene_diagnostics_path,
                scene_quality_path,
            ],
            model=scene_boundary_model,
            prompt_version=scene_boundary_model["prompt_version"],
            schema_version=phase01["schemas"]["scenes"],
        )
        del decisions, evidence, grouping_result, judge
    _emit_stage_progress(
        manager, "scenes", scratch, status="complete", reused=scenes_reused
    )
    scenes = pd.read_parquet(scenes_path).to_dict("records")
    scene_links = pd.read_parquet(scene_links_path).to_dict("records")
    scenes_output_fingerprint = manager.stage_output_fingerprint("scenes")

    yield "scene_summaries"

    manager.active_stage = "scene_summaries"
    _emit_stage_progress(manager, "scene_summaries", scratch, status="start")
    summaries_path = stage_dir / "scene_summaries.parquet"
    summaries_fingerprint = compute_fingerprint(
        scenes_output_fingerprint,
        keyframes_output_fingerprint,
        ocr_output_fingerprint,
        asr_output_fingerprint,
        captions_output_fingerprint,
        links_output_fingerprint,
        config.stage_config_hashes["scene_summaries"],
    )
    summaries_reused = _restore_if_reusable(
        manager, "scene_summaries", summaries_fingerprint, stage_dir
    )
    if not summaries_reused:
        summary_rows = _build_scene_summaries(
            video_id=video_id,
            scenes=scenes,
            shots=shots,
            keyframes=keyframes,
            ocr_rows=ocr_rows,
            captions=captions,
            asr_rows=asr_rows,
            scene_links=scene_links,
            stage_dir=stage_dir,
            client=caption_client,
            model_config=scene_summary_model,
            summary_config=phase01["scene_summary"],
        )
        summary_provenance = stage_dir / "scene_summary_field_provenance.jsonl"
        _write_parquet(summaries_path, summary_rows)
        manager.promote_stage(
            "scene_summaries",
            input_fingerprint=summaries_fingerprint,
            outputs=[summaries_path, summary_provenance],
            model=scene_summary_model,
            prompt_version=scene_summary_model["prompt_bundle_version"],
            schema_version=phase01["schemas"]["scene_summaries"],
        )
        del summary_rows
    _emit_stage_progress(
        manager,
        "scene_summaries",
        scratch,
        status="complete",
        reused=summaries_reused,
    )
    summaries_output_fingerprint = manager.stage_output_fingerprint("scene_summaries")

    # Package/sync read stage artifacts from disk. Drop semantic runtime and
    # table references before the chunk owner closes Qwen and resumes this flow.
    caption_client = None
    shots = []
    keyframes = []
    asr_rows = []
    ocr_rows = []
    captions = []
    links = []
    scenes = []
    scene_links = []
    yield "finalize"

    manager.active_stage = "package"
    _emit_stage_progress(manager, "package", scratch, status="start")
    package_fingerprint = compute_fingerprint(
        metadata_fingerprint,
        shots_output_fingerprint,
        keyframes_output_fingerprint,
        asr_output_fingerprint,
        ocr_output_fingerprint,
        captions_output_fingerprint,
        links_output_fingerprint,
        scenes_output_fingerprint,
        summaries_output_fingerprint,
        config.stage_config_hashes["package"],
    )
    package_config = config.payload["artifact"]["package"]
    package_filename = str(package_config["filename"]).format(video_id=video_id)
    if Path(package_filename).name != package_filename:
        raise ValueError("Phase01 package filename must resolve to a basename")
    package_path = stage_dir / package_filename
    package_reused = _restore_if_reusable(
        manager, "package", package_fingerprint, stage_dir
    )
    if not package_reused:
        artifact_dir = stage_dir / "package" / video_id
        _assemble_package(
            artifact_dir=artifact_dir,
            video_id=video_id,
            metadata_path=metadata_path,
            stage_dir=stage_dir,
            config=config,
        )
        write_artifact_zip(
            artifact_dir=artifact_dir,
            zip_path=package_path,
            video_id=video_id,
            artifact_type="structure",
            batch_id=str(config.payload["runtime"]["batch_id"]),
            worker_id=str(config.payload["runtime"]["worker_id"]),
            status="complete",
            schema_version="phase01_structure_v2",
        )
        validate_artifact_zip(package_path)
        manager.promote_stage(
            "package",
            input_fingerprint=package_fingerprint,
            outputs=[package_path],
            schema_version="phase01_structure_v2",
        )
    _emit_stage_progress(
        manager, "package", scratch, status="complete", reused=package_reused
    )

    local_artifact = release_dir / "artifacts" / "structure" / package_filename
    local_artifact.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(package_path, local_artifact)
    if not sync_release:
        return {"video_id": video_id, "status": "complete_local", "artifact": str(local_artifact)}

    manager.active_stage = "sync"
    _emit_stage_progress(manager, "sync", scratch, status="start")
    sync_fingerprint = compute_fingerprint(
        package_fingerprint, sha256_file(package_path), config.stage_config_hashes["sync"]
    )
    sync_reused = manager.is_reusable("sync", input_fingerprint=sync_fingerprint)
    _record_stage_source(manager, "sync", reused=sync_reused)
    if not sync_reused:
        remote_root = str(package_config["root"]).format(
            release_id=config.payload["runtime"]["release_id"],
            batch_id=config.payload["runtime"]["batch_id"],
            video_id=video_id,
        ).strip("/")
        remote_path = f"{remote_root}/{package_filename}"
        release_store.upload_file(package_path, remote_path)
        with tempfile.TemporaryDirectory(prefix="phase01_sync_verify_") as tmp:
            verified = Path(tmp) / package_path.name
            release_store.download_file(remote_path, verified)
            if sha256_file(verified) != sha256_file(package_path):
                raise ValueError(f"Release artifact remote checksum mismatch: {remote_path}")
        receipt_path = stage_dir / "sync_receipt.json"
        _write_json(receipt_path, {
            "repo_id": release_store.repo_id,
            "remote_path": remote_path,
            "sha256": sha256_file(package_path),
            "synced_at": utc_now(),
        })
        manager.promote_stage(
            "sync",
            input_fingerprint=sync_fingerprint,
            outputs=[receipt_path],
            schema_version="phase01_sync_receipt_v1",
        )
    _emit_stage_progress(
        manager, "sync", scratch, status="complete", reused=sync_reused
    )
    return {"video_id": video_id, "status": "complete", "artifact": str(local_artifact)}


def _build_keyframes(
    *,
    video_id: str,
    video_path: Path,
    shots: list[dict[str, Any]],
    timeline: list[dict[str, Any]],
    output_dir: Path,
    config: Mapping[str, Any],
) -> None:
    keyframe_config = config["keyframe"]
    timeline_by_frame = {int(row["frame_id"]): row for row in timeline}
    timestamp_by_frame = {
        frame_id: float(row["pts_time"])
        for frame_id, row in timeline_by_frame.items()
    }
    candidate_groups = []
    probe_plans = []
    for shot in shots:
        by_role = candidate_frame_ids_for_shot(shot, keyframe_config)
        shot_timeline = [
            timeline_by_frame[frame_id]
            for frame_id in range(
                int(shot["start_frame"]), int(shot["end_frame"])
            )
            if frame_id in timeline_by_frame
        ]
        probe_plan = temporal_probe_plan_for_shot(
            shot, shot_timeline, keyframe_config
        )
        probe_plans.append(probe_plan)
        candidate_groups.append(
            {
                *(
                    frame_id
                    for role_ids in by_role.values()
                    for frame_id in role_ids
                ),
                *(probe.frame_id for probe in probe_plan.semantic_candidates),
            }
        )
    rows: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    decoded_groups = iter_decode_frame_groups(video_path, candidate_groups)
    for shot, decoded, probe_plan in zip(
        shots, decoded_groups, probe_plans, strict=True
    ):
        anchors, candidate_diagnostics = select_keyframes_for_shot(
            shot, decoded, keyframe_config
        )
        supplemental, supplemental_diagnostics = select_supplemental_keyframes(
            shot=shot,
            anchors=anchors,
            probe_plan=probe_plan,
            decoded_frames=decoded,
            timestamp_by_frame=timestamp_by_frame,
            config=keyframe_config,
        )
        selected = sorted(
            [*anchors, *supplemental], key=lambda item: item.frame_id
        )
        selected_roles = sorted(item.role for item in selected)
        selected_frame_ids = sorted(item.frame_id for item in selected)
        selected_identity = {
            (item.frame_id, item.role): item for item in selected
        }
        shot_frame_span = int(shot["end_frame"]) - int(shot["start_frame"])
        shot_duration_sec = float(shot["end_sec"]) - float(shot["start_sec"])
        diagnostic_counts = _keyframe_diagnostic_counts(
            candidate_diagnostics,
            supplemental_diagnostics,
        )
        diagnostics.extend(
            {
                "shot_id": shot["shot_id"],
                "shot_frame_span": shot_frame_span,
                "shot_duration_sec": shot_duration_sec,
                "selected_roles": selected_roles,
                "selected_frame_ids": selected_frame_ids,
                **diagnostic_counts,
                "long_shot_coverage_warning": shot_duration_sec > 10.0 and len(anchors) < 3,
                "candidate_source": f"anchor_{item.role}_search_band",
                "timestamp_sec": (
                    float(timeline_by_frame[item.frame_id]["pts_time"])
                    if item.frame_id in timeline_by_frame
                    else None
                ),
                "temporal_gap_sec": None,
                "visual_novelty_score": None,
                "text_present": None,
                "text_change_score": None,
                "visual_trigger": False,
                "text_trigger": False,
                "triggered_signal_count": 0,
                "max_triggered_signal_score": None,
                "keep": (item.frame_id, item.role) in selected_identity,
                "decision_reason": (
                    selected_identity[(item.frame_id, item.role)].selection_reason
                    if (item.frame_id, item.role) in selected_identity
                    else item.invalid_reason or "lower_quality_in_role"
                ),
                "dedup_target_frame_id": None,
                "distance_to_nearest_actual_anchor_sec": None,
                "coverage_cap_reached": probe_plan.coverage_cap_reached,
                "remaining_max_probe_gap_seconds": (
                    probe_plan.remaining_max_probe_gap_seconds
                ),
                "signal_errors": [],
                **item.__dict__,
            }
            for item in candidate_diagnostics
        )
        diagnostics.extend(
            {
                **item,
                "shot_frame_span": shot_frame_span,
                "shot_duration_sec": shot_duration_sec,
                "selected_roles": selected_roles,
                "selected_frame_ids": selected_frame_ids,
                **diagnostic_counts,
                "long_shot_coverage_warning": (
                    shot_duration_sec > 10.0 and len(anchors) < 3
                ),
            }
            for item in supplemental_diagnostics
        )
        for item in selected:
            frame = decoded[item.frame_id]
            keyframe_id = f"{video_id}:{item.frame_id}"
            media_stem = f"{video_id}_f{item.frame_id:07d}"
            filename = f"{media_stem}.jpg"
            thumbnail_name = f"{media_stem}.webp"
            write_keyframe_images(
                frame,
                keyframe_path=output_dir / "keyframes" / filename,
                thumbnail_path=output_dir / "thumbnails" / thumbnail_name,
                keyframe_long_side=int(keyframe_config["encoding"]["long_side"]),
                jpeg_quality=int(keyframe_config["encoding"]["jpeg_quality"]),
                thumbnail_width=int(config["thumbnail"]["width"]),
                webp_quality=int(config["thumbnail"]["encoding"]["webp_quality"]),
            )
            timeline_row = timeline_by_frame[item.frame_id]
            rows.append({
                "keyframe_id": keyframe_id,
                "video_id": video_id,
                "frame_id": item.frame_id,
                "timestamp_sec": float(timeline_row["pts_time"]),
                "shot_id": str(shot["shot_id"]),
                "scene_id": None,
                "keyframe_role": item.role,
                "quality_score": item.quality_score,
                "is_representative": item.is_representative,
                "selection_reason": item.selection_reason,
                "keyframe_ref": f"media://keyframes/{video_id}/{filename}",
                "thumbnail_ref": f"media://thumbnails/{video_id}/{thumbnail_name}",
                "status": "pass",
            })
    _validate_keyframe_rows(shots, rows)
    _write_parquet(output_dir / "keyframes.parquet", rows)
    _write_jsonl(output_dir / "keyframe_diagnostics.jsonl", diagnostics)


def _keyframe_diagnostic_counts(
    anchor_diagnostics: list[Any],
    semantic_diagnostics: list[dict[str, Any]],
) -> dict[str, int]:
    candidate_frame_ids = {
        int(item.frame_id) for item in anchor_diagnostics
    } | {int(item["frame_id"]) for item in semantic_diagnostics}
    valid_candidate_frame_ids = {
        int(item.frame_id) for item in anchor_diagnostics if item.valid
    } | {
        int(item["frame_id"])
        for item in semantic_diagnostics
        if item.get("valid")
    }
    return {
        "candidate_count": len(candidate_frame_ids),
        "valid_candidate_count": len(valid_candidate_frame_ids),
        "evaluation_count": len(anchor_diagnostics) + len(semantic_diagnostics),
        "valid_evaluation_count": sum(
            1 for item in anchor_diagnostics if item.valid
        )
        + sum(1 for item in semantic_diagnostics if item.get("valid")),
    }


def _caption_client_for_model(
    model_config: Mapping[str, Any],
    *,
    phase01: Mapping[str, Any],
    cache: ArtifactStore,
    lifecycle_callback=None,
    pre_load_callback=None,
):
    fallbacks = list(model_config.get("fallbacks", []))
    if len(fallbacks) > 1:
        raise ValueError("Phase01 semantic runtime supports exactly one local fallback")

    primary = _structured_client_for_model(
        model_config,
        phase01=phase01,
        cache=cache,
        cache_prefix=f"{model_config['provider']}/shot_caption",
        lifecycle_callback=lifecycle_callback,
        pre_load_callback=pre_load_callback,
    )

    if not fallbacks:
        return primary

    fallback = _structured_client_for_model(
        fallbacks[0],
        phase01=phase01,
        cache=cache,
        cache_prefix=f"{fallbacks[0]['provider']}/shot_caption",
        lifecycle_callback=lifecycle_callback,
        pre_load_callback=pre_load_callback,
    )

    return ExclusiveLocalFallbackClient(
        primary=primary,
        fallback=fallback,
        telemetry_callback=lifecycle_callback,
    )


def _semantic_model_config(
    models: Mapping[str, Any], stage_key: str
) -> dict[str, Any]:
    stage_config = dict(models[stage_key])
    model_key = stage_config.pop("model_key", None)
    if not model_key:
        return stage_config
    if str(model_key) not in models:
        raise ValueError(
            f"Phase01 semantic model_key does not exist: {model_key}"
        )
    return {**dict(models[str(model_key)]), **stage_config}


def _structured_client_for_model(
    model_config: Mapping[str, Any],
    *,
    phase01: Mapping[str, Any],
    cache: ArtifactStore,
    cache_prefix: str,
    lifecycle_callback=None,
    pre_load_callback=None,
):
    provider = str(model_config["provider"])

    local_providers = {
        "qwen_local",
        "vintern_local",
        "vintern_reasoning_local",
    }

    if provider in local_providers:
        if provider == "vintern_reasoning_local":
            inference_batch_size = 1
        else:
            inference_stage = (
                "shot_captions" if "shot_caption" in cache_prefix else "ocr"
            )
            inference_batch_size = phase01["execution"]["inference_batch_size"][inference_stage]

        return LocalVisionStructuredClient(
            model_config={
                **model_config,
                "total_attempts": phase01["retry"]["local_model_total_attempts"],
                "inference_batch_size": inference_batch_size,
            },
            cache=cache,
            cache_prefix=f"local_vlm/{cache_prefix}",
            lifecycle_callback=lifecycle_callback,
            pre_load_callback=pre_load_callback,
        )
    raise RuntimeError(f"Unsupported structured provider: {provider}")


def _build_ocr(
    *,
    video_id: str,
    keyframes: list[dict[str, Any]],
    stage_dir: Path,
    client,
    model_config: Mapping[str, Any],
    ocr_config: Mapping[str, Any],
    diagnostics: dict[str, int] | None = None,
) -> list[dict[str, Any]]:
    prompt = (_prompt_dir() / f"{model_config['prompt_version']}.txt").read_text(encoding="utf-8")
    schema = {
        "type": "object",
        "properties": {
            "full_text": {"type": "string"},
            "ocr_blocks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "confidence": {"type": ["number", "null"]},
                    },
                    "required": ["text"],
                    "additionalProperties": True,
                },
            },
            "language": {"type": "string"},
            "confidence": {"type": ["number", "null"]},
        },
        "required": ["full_text", "ocr_blocks"],
        "additionalProperties": False,
    }
    allowed_roles = {str(role) for role in ocr_config.get("run_on_keyframe_roles", [])}
    selected_keyframes = sorted(
        [
        keyframe
        for keyframe in keyframes
        if not allowed_roles or str(keyframe.get("keyframe_role")) in allowed_roles
        ],
        key=lambda row: (str(row["shot_id"]), int(row["frame_id"])),
    )
    gate_config = ocr_config.get("text_presence_filter", {})
    gate_enabled = bool(
        isinstance(gate_config, Mapping) and gate_config.get("enabled", False)
    )
    counts = {
        "gate_checked": 0,
        "gate_no_text": 0,
        "gate_failures": 0,
        "vintern_processed": 0,
        "vintern_failed": 0,
    }
    rows_by_keyframe: dict[str, dict[str, Any]] = {}
    requests: list[ModelRequest] = []
    request_keyframes: list[dict[str, Any]] = []
    for keyframe in selected_keyframes:
        keyframe_id = str(keyframe["keyframe_id"])
        image = stage_dir / "keyframes" / Path(str(keyframe["keyframe_ref"])).name
        gate_decision = "uncertain"
        if gate_enabled:
            counts["gate_checked"] += 1
            try:
                gate_decision = _text_presence_gate(image, gate_config)
            except Exception:  # noqa: BLE001 - gate failure must run Vintern
                gate_decision = "error"
                counts["gate_failures"] += 1
        if gate_decision == "no_text":
            counts["gate_no_text"] += 1
            rows_by_keyframe[keyframe_id] = _ocr_row(
                video_id=video_id,
                keyframe=keyframe,
                text="",
                provider="opencv_text_gate",
                model_name="opencv_mser_canny",
                model_version="text_presence_gate_v1",
                language="vi",
                confidence=None,
                status="empty",
            )
            continue
        requests.append(
            ModelRequest(
                request_kind="keyframe_ocr",
                video_id=video_id,
                prompt=prompt,
                prompt_version=str(model_config["prompt_version"]),
                response_schema_version=str(model_config["response_schema_version"]),
                response_schema=schema,
                image_paths=(image,),
                identity={"keyframe_id": keyframe_id},
            )
        )
        request_keyframes.append(keyframe)

    counts["vintern_processed"] = len(requests)
    responses: list[dict[str, Any] | None] = [None] * len(requests)
    errors: dict[int, Exception] = {}
    if requests:
        try:
            responses = list(client.request_many(requests))
        except BatchRequestError as exc:
            if any(
                isinstance(error, SystemicProviderError)
                for error in exc.errors.values()
            ):
                raise
            responses = list(exc.results)
            errors = dict(exc.errors)
        except InsufficientMemoryError:
            raise
        except Exception as exc:  # noqa: BLE001 - preserve per-keyframe degradation
            errors = {index: exc for index in range(len(requests))}

    for index, keyframe in enumerate(request_keyframes):
        keyframe_id = str(keyframe["keyframe_id"])
        response = responses[index] if index < len(responses) else None
        try:
            if index in errors:
                raise errors[index]
            if response is None:
                raise RuntimeError("OCR request returned no response")
            text = _ocr_text(response)
            status = "pass" if text else "empty"
            provider = str(response.get("__provider", model_config["provider"]))
            model_name = str(response.get("__model_id", model_config["model_id"]))
            model_version = str(response.get("__model_revision", model_config["model_revision"]))
            confidence = _nullable_confidence(response.get("confidence"))
            language = str(response.get("language") or "vi")
        except Exception:  # noqa: BLE001 - preserve per-keyframe degradation
            counts["vintern_failed"] += 1
            text = ""
            status = "failed"
            provider = str(model_config["provider"])
            model_name = str(model_config["model_id"])
            model_version = str(model_config["model_revision"])
            confidence = None
            language = "vi"
        rows_by_keyframe[keyframe_id] = _ocr_row(
            video_id=video_id,
            keyframe=keyframe,
            text=text,
            provider=provider,
            model_name=model_name,
            model_version=model_version,
            language=language,
            confidence=confidence,
            status=status,
        )
    if diagnostics is not None:
        diagnostics.update(counts)
    return [rows_by_keyframe[str(row["keyframe_id"])] for row in selected_keyframes]


def _ocr_stage_status(
    status_counts: Mapping[str, int],
    diagnostics: Mapping[str, int],
) -> str:
    """Classify OCR stage health from actual Vintern requests."""

    failed_count = int(status_counts.get("failed", 0))
    vintern_processed = int(diagnostics.get("vintern_processed", 0))
    if vintern_processed > 0 and failed_count == vintern_processed:
        return "failed"
    if failed_count > 0:
        return "partial"
    return "pass"


def _ocr_row(
    *,
    video_id: str,
    keyframe: Mapping[str, Any],
    text: str,
    provider: str,
    model_name: str,
    model_version: str,
    language: str,
    confidence: float | None,
    status: str,
) -> dict[str, Any]:
    keyframe_id = str(keyframe["keyframe_id"])
    return {
        "ocr_id": f"{keyframe_id}:ocr",
        "video_id": video_id,
        "keyframe_id": keyframe_id,
        "shot_id": str(keyframe["shot_id"]),
        "frame_id": int(keyframe["frame_id"]),
        "text": text,
        "raw_text": text,
        "provider": provider,
        "model_name": model_name,
        "model_version": model_version,
        "language": language,
        "confidence": confidence,
        "status": status,
    }


def _text_presence_gate(
    image_path: Path, config: Mapping[str, Any]
) -> str:
    return text_presence_gate(image_path, config)


def _ocr_text(payload: Mapping[str, Any]) -> str:
    full_text = str(payload.get("full_text", "")).strip()
    if full_text:
        return full_text
    blocks = payload.get("ocr_blocks", [])
    if not isinstance(blocks, list):
        return ""
    return " ".join(
        str(block.get("text", "")).strip()
        for block in blocks
        if isinstance(block, Mapping) and str(block.get("text", "")).strip()
    )


def _ocr_text_by_keyframe(rows: list[dict[str, Any]]) -> dict[str, str]:
    output: dict[str, str] = {}
    for row in rows:
        if str(row.get("status")) == "failed":
            continue
        text = str(row.get("text") or row.get("raw_text") or "").strip()
        if text:
            output[str(row["keyframe_id"])] = text
    return output


def _nullable_confidence(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return min(1.0, max(0.0, number))


def _string_list(payload: Mapping[str, Any], key: str) -> list[str]:
    value = payload.get(key, [])
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if not isinstance(value, (list, tuple)):
        if hasattr(value, "tolist"):
            value = value.tolist()
        else:
            return []
    if not isinstance(value, (list, tuple)):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _configured_prompt_versions(
    model_config: Mapping[str, Any],
    *,
    expected_fields: set[str],
    bundle_version: str,
) -> dict[str, str]:
    configured = model_config.get("prompt_versions")
    if not isinstance(configured, Mapping):
        raise TypeError(
            f"Invalid prompt_versions for {bundle_version}: expected a mapping"
        )
    bundle = {str(field): str(version) for field, version in configured.items()}
    if set(bundle) != expected_fields or any(
        not version.strip() for version in bundle.values()
    ):
        raise ValueError(
            f"Invalid prompt bundle {bundle_version}: expected {sorted(expected_fields)}"
        )
    return bundle


def _build_captions(
    *,
    video_id: str,
    shots: list[dict[str, Any]],
    keyframes: list[dict[str, Any]],
    ocr_rows: list[dict[str, Any]],
    stage_dir: Path,
    client,
    model_config: Mapping[str, Any],
) -> list[dict[str, Any]]:
    representative = {
        str(row["shot_id"]): row
        for row in keyframes
        if row["is_representative"]
    }
    bundle_version = str(model_config["prompt_bundle_version"])
    bundle = _configured_prompt_versions(
        model_config,
        expected_fields=set(SHOT_CAPTION_FIELDS),
        bundle_version=bundle_version,
    )

    ocr_by_keyframe = _ocr_text_by_keyframe(ocr_rows)
    ordered_shots = sorted(shots, key=lambda row: str(row["shot_id"]))
    requests: list[ModelRequest] = []
    request_context: list[tuple[dict[str, Any], dict[str, Any], str]] = []

    for shot in ordered_shots:
        shot_id = str(shot["shot_id"])
        if shot_id not in representative:
            raise ValueError(f"Shot has no representative keyframe: {shot_id}")
        keyframe = representative[shot_id]
        keyframe_id = str(keyframe["keyframe_id"])
        image = stage_dir / "keyframes" / Path(str(keyframe["keyframe_ref"])).name
        ocr_text = ocr_by_keyframe.get(keyframe_id, "")

        for field in SHOT_CAPTION_FIELDS:
            prompt_version = str(bundle[field])
            prompt = (
                build_text_prompt(prompt_version)
                + "\n\nBEGIN_EVIDENCE\n"
                + "OCR_EVIDENCE:\n"
                + (ocr_text if ocr_text else "<NONE>")
                + "\nEND_EVIDENCE"
            )
            requests.append(
                ModelRequest(
                    request_kind=f"shot_caption_{field}",
                    video_id=video_id,
                    prompt=prompt,
                    prompt_version=prompt_version,
                    response_schema_version="plain_text_response_v1",
                    response_schema=TEXT_RESPONSE_SCHEMA,
                    image_paths=(image,),
                    identity={
                        "shot_id": shot_id,
                        "keyframe_id": keyframe_id,
                        "field": field,
                    },
                    response_mode="text",
                )
            )
            request_context.append((shot, keyframe, field))

    responses = client.request_many(requests)
    if len(responses) != len(request_context):
        raise ValueError(
            "caption client returned a different number of responses than requests"
        )

    grouped: dict[str, dict[str, Any]] = {}
    field_metadata: dict[str, list[tuple[str, str, str]]] = {}
    provenance_rows: list[dict[str, Any]] = []
    for response, context in zip(responses, request_context, strict=True):
        shot, keyframe, field = context
        shot_id = str(shot["shot_id"])
        if shot_id not in grouped:
            grouped[shot_id] = {
                "shot_caption_id": f"{shot_id}_caption",
                "video_id": video_id,
                "shot_id": shot_id,
                "representative_keyframe_id": str(keyframe["keyframe_id"]),
                "representative_timestamp_sec": float(keyframe["timestamp_sec"]),
                "prompt_version": bundle_version,
                "schema_version": str(model_config["response_schema_version"]),
                "confidence": None,
                "status": "pass",
            }
            field_metadata[shot_id] = []

        raw_text = str(response.get("text", ""))
        field_kind = SHOT_CAPTION_FIELD_KIND[field]
        if field_kind == "required_text":
            grouped[shot_id][field] = _normalize_required_text(raw_text)
        elif field_kind == "optional_text":
            grouped[shot_id][field] = _normalize_optional_text(raw_text)
        else:
            grouped[shot_id][field] = _normalize_line_list(raw_text)

        metadata = _response_model_identity(response, model_config)
        field_metadata[shot_id].append(metadata)
        provenance_rows.append(
            {
                "video_id": video_id,
                "shot_id": shot_id,
                "field": field,
                "provider": metadata[0],
                "model_id": metadata[1],
                "model_revision": metadata[2],
                "prompt_version": str(bundle[field]),
            }
        )

    for shot_id, row in grouped.items():
        provider, model_name, model_version = _aggregate_model_identity(
            field_metadata[shot_id]
        )
        row.update(
            {
                "provider": provider,
                "model_name": model_name,
                "model_version": model_version,
            }
        )

    rows = [grouped[str(shot["shot_id"])] for shot in ordered_shots]
    validate_rows("shot_captions", rows)
    _write_jsonl(stage_dir / "shot_caption_field_provenance.jsonl", provenance_rows)
    return rows


def _normalize_required_text(raw: str) -> str:
    text = raw.strip()
    if not text or text.upper() == "<NONE>":
        raise ValueError("required semantic text is empty")
    return " ".join(line.strip() for line in text.splitlines() if line.strip())


def _normalize_optional_text(raw: str) -> str:
    text = raw.strip()
    if not text or text.upper() == "<NONE>":
        return ""
    return " ".join(line.strip() for line in text.splitlines() if line.strip())


def _normalize_line_list(raw: str) -> list[str]:
    text = raw.strip()
    if not text or text.upper() == "<NONE>":
        return []

    output: list[str] = []
    seen: set[str] = set()
    for raw_line in text.splitlines():
        line = re.sub(
            r"^(?:[-*]|\u2022|\d+[.)])\s*", "", raw_line.strip()
        ).strip()
        if not line or line.upper() == "<NONE>":
            continue
        identity = line.casefold()
        if identity in seen:
            continue
        seen.add(identity)
        output.append(line)
    return output


def _response_model_identity(
    response: Mapping[str, Any], model_config: Mapping[str, Any]
) -> tuple[str, str, str]:
    provider = response.get("__provider") or model_config.get("provider")
    model_id = response.get("__model_id") or model_config.get("model_id")
    model_revision = response.get("__model_revision") or model_config.get(
        "model_revision"
    )
    values = (provider, model_id, model_revision)
    if any(value in (None, "") for value in values):
        raise ValueError("semantic response is missing model identity metadata")
    return str(provider), str(model_id), str(model_revision)


def _aggregate_model_identity(
    identities: list[tuple[str, str, str]],
) -> tuple[str, str, str]:
    unique = set(identities)
    if len(unique) == 1:
        return next(iter(unique))
    return "mixed", "mixed", "mixed"


def _build_scene_evidence(shots, keyframes, ocr_rows, captions, asr_rows, links, stage_dir):
    by_shot_keyframes: dict[str, list[dict[str, Any]]] = {}
    for row in keyframes:
        by_shot_keyframes.setdefault(str(row["shot_id"]), []).append(row)
    caption_by_shot = {str(row["shot_id"]): row for row in captions}
    ocr_by_keyframe = _ocr_text_by_keyframe(ocr_rows)
    asr_by_id = {str(row["asr_segment_id"]): row for row in asr_rows}
    links_by_shot: dict[str, list[dict[str, Any]]] = {}
    for row in links:
        links_by_shot.setdefault(str(row["shot_id"]), []).append(row)
    evidence = []
    for shot in shots:
        shot_id = str(shot["shot_id"])
        frames = by_shot_keyframes[shot_id]
        representative = next(row for row in frames if row["is_representative"])
        role_paths = {
            str(row["keyframe_role"]): stage_dir
            / "keyframes"
            / Path(str(row["keyframe_ref"])).name
            for row in frames
            if str(row["keyframe_role"]) != "supplemental"
        }
        supplemental_paths = [
            stage_dir / "keyframes" / Path(str(row["keyframe_ref"])).name
            for row in sorted(frames, key=lambda value: int(value["frame_id"]))
            if str(row["keyframe_role"]) == "supplemental"
        ]
        linked_ids = {
            str(link["asr_segment_id"])
            for link in links_by_shot.get(shot_id, [])
            if str(link["asr_segment_id"]) in asr_by_id
        }
        ordered_segments = sorted(
            (asr_by_id[segment_id] for segment_id in linked_ids),
            key=lambda row: (
                float(row["start_sec"]),
                float(row["end_sec"]),
                str(row["asr_segment_id"]),
            ),
        )
        transcript = " ".join(
            str(row["text"]).strip()
            for row in ordered_segments
            if str(row["text"]).strip()
        )
        caption = caption_by_shot[shot_id]
        shot_ocr = [
            ocr_by_keyframe[str(row["keyframe_id"])]
            for row in frames
            if ocr_by_keyframe.get(str(row["keyframe_id"]))
        ]
        evidence.append({
            "shot_id": shot_id, "start_sec": shot["start_sec"], "end_sec": shot["end_sec"],
            "representative_path": stage_dir
            / "keyframes"
            / Path(str(representative["keyframe_ref"])).name,
            "early_path": role_paths.get("early"), "late_path": role_paths.get("late"),
            "supplemental_paths": supplemental_paths,
            "caption_vi": caption["caption_vi"], "caption_en": caption["caption_en"],
            "objects_vi": _string_list(caption, "objects_vi"), "objects_en": _string_list(caption, "objects_en"),
            "actions_vi": _string_list(caption, "actions_vi"), "actions_en": _string_list(caption, "actions_en"),
            "visible_text_summary_vi": caption.get("visible_text_summary_vi", ""),
            "visible_text_summary_en": caption.get("visible_text_summary_en", ""),
            "ocr_text": shot_ocr, "transcript": transcript,
        })
    return evidence


def _build_scene_transcript_links(scenes, asr_rows):
    rows = []
    for scene in scenes:
        for segment in asr_rows:
            overlap = min(float(scene["end_sec"]), float(segment["end_sec"])) - max(float(scene["start_sec"]), float(segment["start_sec"]))
            if overlap > 0:
                duration = float(segment["end_sec"]) - float(segment["start_sec"])
                if duration <= 0:
                    raise ValueError("ASR segment duration must be positive")
                rows.append({"video_id": scene["video_id"], "scene_id": scene["scene_id"], "asr_segment_id": segment["asr_segment_id"], "coverage": min(1.0, max(0.0, overlap / duration))})
    return rows


def _build_scene_summaries(
    *,
    video_id,
    scenes,
    shots,
    keyframes,
    ocr_rows,
    captions,
    asr_rows,
    scene_links,
    stage_dir,
    client,
    model_config,
    summary_config,
):
    bundle_version = str(model_config["prompt_bundle_version"])
    bundle = _configured_prompt_versions(
        model_config,
        expected_fields={"summary_vi", "summary_en"},
        bundle_version=bundle_version,
    )

    captions_by_shot = {str(row["shot_id"]): row for row in captions}
    ocr_by_keyframe = _ocr_text_by_keyframe(ocr_rows)
    representative = {
        str(row["shot_id"]): row
        for row in keyframes
        if row["is_representative"]
    }
    keyframes_by_shot: dict[str, list[dict[str, Any]]] = {}
    for row in keyframes:
        keyframes_by_shot.setdefault(str(row["shot_id"]), []).append(row)
    asr_by_id = {str(row["asr_segment_id"]): row for row in asr_rows}
    links_by_scene: dict[str, list[dict[str, Any]]] = {}
    for link in scene_links:
        links_by_scene.setdefault(str(link["scene_id"]), []).append(link)

    contexts: list[dict[str, Any]] = []
    for scene in scenes:
        scene_id = str(scene["scene_id"])
        scene_shots = _shots_for_scene(scene, shots)
        image_shots = _evenly_sample(
            scene_shots,
            int(summary_config["max_representative_images"]),
        )
        image_paths = tuple(
            stage_dir
            / "keyframes"
            / Path(str(representative[str(shot["shot_id"])]["keyframe_ref"])).name
            for shot in image_shots
        )

        evidence_blocks: list[str] = []
        for shot in _evenly_sample(
            scene_shots,
            int(summary_config["max_shot_evidence_items"]),
        ):
            shot_id = str(shot["shot_id"])
            caption = captions_by_shot[shot_id]
            ocr_texts = [
                ocr_by_keyframe[str(row["keyframe_id"])]
                for row in keyframes_by_shot.get(shot_id, [])
                if ocr_by_keyframe.get(str(row["keyframe_id"]))
            ]
            evidence_blocks.append(
                _render_summary_shot_evidence(
                    shot,
                    caption,
                    ocr_text=" ".join(ocr_texts),
                    max_ocr_chars=int(summary_config["max_ocr_chars_per_shot"]),
                )
            )

        segment_ids = {
            str(link["asr_segment_id"])
            for link in links_by_scene.get(scene_id, [])
            if str(link["asr_segment_id"]) in asr_by_id
        }
        transcript = " ".join(
            str(segment["text"]).strip()
            for segment in sorted(
                (asr_by_id[segment_id] for segment_id in segment_ids),
                key=lambda row: (
                    float(row["start_sec"]),
                    float(row["end_sec"]),
                    str(row["asr_segment_id"]),
                ),
            )
            if str(segment["text"]).strip()
        )
        transcript = _bounded_text(
            transcript,
            max_chars=int(summary_config["max_transcript_chars"]),
        )
        evidence_body = (
            f"SCENE_ID: {scene_id}\n"
            f"TIME: {float(scene['start_sec']):.3f}-{float(scene['end_sec']):.3f}\n\n"
            + "\n\n".join(evidence_blocks)
            + "\n\nSCENE_TRANSCRIPT:\n"
            + (transcript or "<NONE>")
        )
        evidence_body = _bounded_text(
            evidence_body,
            max_chars=int(summary_config["max_total_evidence_chars"]),
        )

        fallback_sheet = (
            stage_dir
            / "diagnostics"
            / "scene_summary_requests"
            / f"{scene_id}_fallback.jpg"
        )
        _write_scene_summary_contact_sheet(
            image_shots,
            representative=representative,
            stage_dir=stage_dir,
            output=fallback_sheet,
        )
        contexts.append(
            {
                "scene": scene,
                "image_paths": image_paths,
                "fallback_sheet": fallback_sheet,
                "evidence": evidence_body,
            }
        )

    vi_requests = [
        _scene_summary_request(
            video_id=video_id,
            context=context,
            field="summary_vi",
            prompt_version=str(bundle["summary_vi"]),
        )
        for context in contexts
    ]
    vi_responses = client.request_many(vi_requests)
    if len(vi_responses) != len(contexts):
        raise ValueError("scene summary client returned an invalid VI batch size")

    vi_by_scene: dict[str, str] = {}
    response_by_scene: dict[str, dict[str, Mapping[str, Any]]] = {}
    provenance_rows: list[dict[str, Any]] = []
    for context, response in zip(contexts, vi_responses, strict=True):
        scene_id = str(context["scene"]["scene_id"])
        vi_by_scene[scene_id] = _normalize_required_text(str(response.get("text", "")))
        response_by_scene[scene_id] = {"summary_vi": response}
        provenance_rows.append(
            _summary_provenance_row(
                video_id=video_id,
                scene_id=scene_id,
                field="summary_vi",
                response=response,
                model_config=model_config,
                prompt_version=str(bundle["summary_vi"]),
            )
        )

    en_requests = [
        _scene_summary_request(
            video_id=video_id,
            context=context,
            field="summary_en",
            prompt_version=str(bundle["summary_en"]),
            vi_summary=vi_by_scene[str(context["scene"]["scene_id"])],
        )
        for context in contexts
    ]
    en_responses = client.request_many(en_requests)
    if len(en_responses) != len(contexts):
        raise ValueError("scene summary client returned an invalid EN batch size")

    rows: list[dict[str, Any]] = []
    for context, response in zip(contexts, en_responses, strict=True):
        scene = context["scene"]
        scene_id = str(scene["scene_id"])
        response_by_scene[scene_id]["summary_en"] = response
        provenance_rows.append(
            _summary_provenance_row(
                video_id=video_id,
                scene_id=scene_id,
                field="summary_en",
                response=response,
                model_config=model_config,
                prompt_version=str(bundle["summary_en"]),
            )
        )
        identities = [
            _response_model_identity(field_response, model_config)
            for field_response in response_by_scene[scene_id].values()
        ]
        provider, model_name, model_version = _aggregate_model_identity(identities)
        rows.append(
            {
                "scene_id": scene_id,
                "video_id": video_id,
                "summary_vi": vi_by_scene[scene_id],
                "summary_en": _normalize_required_text(
                    str(response.get("text", ""))
                ),
                "provider": provider,
                "model_name": model_name,
                "model_version": model_version,
                "prompt_version": bundle_version,
                "schema_version": str(model_config["response_schema_version"]),
                "confidence": None,
                "status": "pass",
            }
        )

    validate_rows("scene_summaries", rows)
    _write_jsonl(stage_dir / "scene_summary_field_provenance.jsonl", provenance_rows)
    return rows


def _shots_for_scene(
    scene: Mapping[str, Any], shots: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    by_id = {str(shot["shot_id"]): index for index, shot in enumerate(shots)}
    start_id = str(scene["start_shot_id"])
    end_id = str(scene["end_shot_id"])
    if start_id not in by_id or end_id not in by_id or by_id[start_id] > by_id[end_id]:
        raise ValueError(f"Scene has invalid shot range: {scene['scene_id']}")
    return shots[by_id[start_id] : by_id[end_id] + 1]


def _scene_partition_quality_payload(
    *,
    video_id: str,
    result: SceneGroupingResult,
    policy: Mapping[str, Any],
) -> dict[str, Any]:
    if result.final_quality.suspicious:
        status = "failed_quality_gate"
    elif result.degenerate_review_triggered:
        status = "pass_after_review"
    else:
        status = "pass"
    return {
        "schema_version": "scene_partition_quality_v1",
        "video_id": video_id,
        "status": status,
        "guard_enabled": bool(policy["enabled"]),
        "consistency_review_rounds_run": result.consistency_review_rounds_run,
        "degenerate_review_triggered": result.degenerate_review_triggered,
        "degenerate_review_rounds_run": result.degenerate_review_rounds_run,
        "policy": {
            "min_shot_count": int(policy["min_shot_count"]),
            "suspicious_boundary_density": float(
                policy["suspicious_boundary_density"]
            ),
            "suspicious_one_shot_scene_rate": float(
                policy["suspicious_one_shot_scene_rate"]
            ),
            "unresolved_action": str(policy["unresolved_action"]),
        },
        "initial": asdict(result.initial_quality),
        "final": asdict(result.final_quality),
    }


def _require_scene_partition_quality(
    *,
    video_id: str,
    result: SceneGroupingResult,
    payload: Mapping[str, Any],
) -> None:
    if not result.final_quality.suspicious:
        return
    raise ScenePartitionQualityError(
        video_id=video_id,
        details={
            "quality_contract": "scene_partition_quality_v1",
            "manual_review_required": True,
            "initial": dict(payload["initial"]),
            "final": dict(payload["final"]),
            "degenerate_review_triggered": result.degenerate_review_triggered,
        },
    )


def _emit_scene_partition_quality(
    *,
    manager: CheckpointManager,
    scratch: Path,
    payload: Mapping[str, Any],
) -> None:
    final = payload["final"]
    runtime = {
        key: value
        for key, value in _MANAGER_RUNTIME_CONTEXT.get(manager, {}).items()
        if key != "stage_sources"
    }
    _emit_progress(
        event="scene_partition_quality",
        status=str(payload["status"]),
        scratch=scratch,
        release_id=manager.release_id,
        video_id=manager.video_id,
        shot_count=int(final["shot_count"]),
        scene_count=int(final["scene_count"]),
        boundary_density=float(final["boundary_density"]),
        one_shot_scene_rate=float(final["one_shot_scene_rate"]),
        degenerate_review_triggered=bool(payload["degenerate_review_triggered"]),
        **runtime,
    )


def _bounded_text(value: Any, *, max_chars: int) -> str:
    if max_chars < 1:
        raise ValueError("text evidence limit must be positive")
    text = str(value or "").strip()
    if len(text) <= max_chars:
        return text
    marker = "\n[TRUNCATED]"
    return text[: max(0, max_chars - len(marker))].rstrip() + marker


def _render_summary_shot_evidence(
    shot: Mapping[str, Any],
    caption: Mapping[str, Any],
    *,
    ocr_text: str,
    max_ocr_chars: int,
) -> str:
    return "\n".join(
        (
            "--- SHOT ---",
            f"SHOT_ID: {shot['shot_id']}",
            f"TIME: {float(shot['start_sec']):.3f}-{float(shot['end_sec']):.3f}",
            f"CAPTION_VI: {caption['caption_vi']}",
            f"CAPTION_EN: {caption['caption_en']}",
            "OBJECTS_VI: " + " | ".join(_string_list(caption, "objects_vi")),
            "OBJECTS_EN: " + " | ".join(_string_list(caption, "objects_en")),
            "ACTIONS_VI: " + " | ".join(_string_list(caption, "actions_vi")),
            "ACTIONS_EN: " + " | ".join(_string_list(caption, "actions_en")),
            "VISIBLE_TEXT_VI: "
            + str(caption.get("visible_text_summary_vi", "")),
            "VISIBLE_TEXT_EN: "
            + str(caption.get("visible_text_summary_en", "")),
            "OCR: " + (_bounded_text(ocr_text, max_chars=max_ocr_chars) or "<NONE>"),
        )
    )


def _scene_summary_request(
    *,
    video_id: str,
    context: Mapping[str, Any],
    field: str,
    prompt_version: str,
    vi_summary: str | None = None,
) -> ModelRequest:
    scene = context["scene"]
    prompt = build_text_prompt(prompt_version)
    if vi_summary is not None:
        prompt += "\n\nVIETNAMESE_SUMMARY_REFERENCE:\n" + vi_summary
    prompt += "\n\nBEGIN_EVIDENCE\n" + str(context["evidence"]) + "\nEND_EVIDENCE"
    return ModelRequest(
        request_kind=f"scene_{field}",
        video_id=video_id,
        prompt=prompt,
        prompt_version=prompt_version,
        response_schema_version="plain_text_response_v1",
        response_schema=TEXT_RESPONSE_SCHEMA,
        image_paths=tuple(context["image_paths"]),
        fallback_image_paths=(Path(context["fallback_sheet"]),),
        identity={"scene_id": str(scene["scene_id"]), "field": field},
        response_mode="text",
    )


def _summary_provenance_row(
    *,
    video_id: str,
    scene_id: str,
    field: str,
    response: Mapping[str, Any],
    model_config: Mapping[str, Any],
    prompt_version: str,
) -> dict[str, Any]:
    provider, model_id, model_revision = _response_model_identity(
        response, model_config
    )
    return {
        "video_id": video_id,
        "scene_id": scene_id,
        "field": field,
        "provider": provider,
        "model_id": model_id,
        "model_revision": model_revision,
        "prompt_version": prompt_version,
    }


def _write_scene_summary_contact_sheet(
    shots: list[dict[str, Any]],
    *,
    representative: Mapping[str, Mapping[str, Any]],
    stage_dir: Path,
    output: Path,
) -> None:
    tile_width, tile_height, label_height, columns = 320, 180, 32, 4
    rows = max(1, (len(shots) + columns - 1) // columns)
    sheet = Image.new(
        "RGB",
        (columns * tile_width, rows * (tile_height + label_height)),
        "black",
    )
    draw = ImageDraw.Draw(sheet)
    for index, shot in enumerate(shots):
        shot_id = str(shot["shot_id"])
        keyframe = representative[shot_id]
        image_path = (
            stage_dir
            / "keyframes"
            / Path(str(keyframe["keyframe_ref"])).name
        )
        with Image.open(image_path) as opened:
            tile = ImageOps.fit(
                opened.convert("RGB"),
                (tile_width, tile_height),
                method=Image.Resampling.LANCZOS,
            )
        x = (index % columns) * tile_width
        y = (index // columns) * (tile_height + label_height)
        sheet.paste(tile, (x, y))
        label = f"{shot_id} {float(keyframe['timestamp_sec']):.3f}s"
        draw.text((x + 4, y + tile_height + 6), label, fill="white")
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output, format="JPEG", quality=90, subsampling=0)


def _evenly_sample(rows: list[dict[str, Any]], maximum: int) -> list[dict[str, Any]]:
    if maximum < 1:
        raise ValueError("Scene summary image limit must be positive")
    if len(rows) <= maximum:
        return rows
    indices = sorted(
        {
            round(position * (len(rows) - 1) / (maximum - 1))
            for position in range(maximum)
        }
    ) if maximum > 1 else [len(rows) // 2]
    return [rows[index] for index in indices]


def _assemble_package(*, artifact_dir: Path, video_id: str, metadata_path: Path, stage_dir: Path, config: ResolvedPhase01Config):
    if artifact_dir.exists(): shutil.rmtree(artifact_dir)
    artifact_dir.mkdir(parents=True)
    metadata = read_metadata(metadata_path)
    _write_json(artifact_dir / "metadata_normalized.json", metadata)
    for name in ("shots.parquet", "keyframes.parquet", "asr_segments.parquet", "ocr.parquet", "shot_captions.parquet", "shot_transcript_links.parquet", "scenes.parquet", "scene_transcript_links.parquet", "scene_summaries.parquet"):
        shutil.copy2(stage_dir / name, artifact_dir / name)
    shutil.copytree(stage_dir / "keyframes", artifact_dir / "keyframes")
    shutil.copytree(stage_dir / "thumbnails", artifact_dir / "thumbnails")
    diagnostics = artifact_dir / "diagnostics"; diagnostics.mkdir()
    for name in (
        "keyframe_diagnostics.jsonl",
        "scene_boundary_diagnostics.jsonl",
        "scene_partition_quality.json",
        "shot_caption_field_provenance.jsonl",
        "scene_summary_field_provenance.jsonl",
        "transnet_predictions.json",
        "asr_status.json",
        "asr_diagnostics.jsonl",
        "ocr_status.json",
    ):
        source = stage_dir / name
        if source.exists(): shutil.copy2(source, diagnostics / name)
    # A complete per-video package has no item-level errors, but retains the
    # canonical file so downstream readers never need layout-specific logic.
    _write_jsonl(artifact_dir / "errors.jsonl", [])
    _backfill_scene_ids(artifact_dir)
    persist_resolved_phase01_config(config, artifact_dir / "resolved_config.json")
    counts = {path.stem: len(pd.read_parquet(path)) for path in artifact_dir.glob("*.parquet")}
    _validate_package_invariants(artifact_dir, counts)
    _write_json(artifact_dir / "manifest.json", {"schema_version": "phase01_video_manifest_v2", "video_id": video_id, "status": "complete", "config_hash": config.config_hash, "stage_config_hashes": config.stage_config_hashes, "counts": counts, "created_at": utc_now()})


def _backfill_scene_ids(artifact_dir: Path):
    shots = pd.read_parquet(artifact_dir / "shots.parquet")
    keyframes = pd.read_parquet(artifact_dir / "keyframes.parquet")
    scenes = pd.read_parquet(artifact_dir / "scenes.parquet")
    mapping = {}
    shot_rows = shots.sort_values("shot_index").to_dict("records")
    for scene in scenes.to_dict("records"):
        start = next(i for i,row in enumerate(shot_rows) if row["shot_id"] == scene["start_shot_id"])
        end = next(i for i,row in enumerate(shot_rows) if row["shot_id"] == scene["end_shot_id"])
        for row in shot_rows[start:end+1]: mapping[str(row["shot_id"])] = str(scene["scene_id"])
    shots["scene_id"] = shots["shot_id"].astype(str).map(mapping)
    keyframes["scene_id"] = keyframes["shot_id"].astype(str).map(mapping)
    keyframe_counts = keyframes.groupby("scene_id").size().to_dict()
    scenes["keyframe_count"] = scenes["scene_id"].map(keyframe_counts).fillna(0).astype(int)
    shots.to_parquet(artifact_dir / "shots.parquet", index=False)
    keyframes.to_parquet(artifact_dir / "keyframes.parquet", index=False)
    scenes.to_parquet(artifact_dir / "scenes.parquet", index=False)


def _validate_package_invariants(artifact_dir: Path, counts: Mapping[str, int]):
    validate_phase01_package(artifact_dir)


def _restore_if_reusable(manager, stage, fingerprint, target_dir):
    reused = manager.is_reusable(
        stage,
        input_fingerprint=fingerprint,
        restore_dir=target_dir,
    )
    _record_stage_source(manager, stage, reused=reused)
    return reused


def _restore_keyframes_if_reusable(manager, fingerprint, target_dir):
    reused = manager.is_reusable(
        "keyframes", input_fingerprint=fingerprint, restore_dir=target_dir
    )
    _record_stage_source(manager, "keyframes", reused=reused)
    if not reused:
        return False
    bundle = target_dir / "keyframes.zip"
    _safe_extract_zip(bundle, target_dir)
    return True


def _stage_fingerprint(manager, stage, upstream): return compute_fingerprint(upstream, manager.stage_config_hashes[stage])


def _write_directory_zip(root, output, members):
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for member in members:
            path = root / member
            if path.is_file(): archive.write(path, path.relative_to(root))
            elif path.is_dir():
                for child in sorted(path.rglob("*")):
                    if child.is_file(): archive.write(child, child.relative_to(root))


def _safe_extract_zip(bundle: Path, target_dir: Path) -> None:
    root = target_dir.resolve()
    with zipfile.ZipFile(bundle) as archive:
        for member in archive.infolist():
            if member.is_dir():
                continue
            target = (root / member.filename).resolve()
            target.relative_to(root)
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)


def _emit_progress(
    *,
    event: str,
    status: str,
    scratch: Path,
    **details: Any,
) -> None:
    payload = {
        "event": event,
        "status": status,
        **_resource_snapshot(scratch),
        **details,
    }
    print(f"[phase01] {json.dumps(payload, ensure_ascii=False, sort_keys=True)}", flush=True)


def _emit_stage_progress(
    manager: CheckpointManager,
    stage: str,
    scratch: Path,
    *,
    status: str,
    reused: bool | None = None,
) -> None:
    timer_key = (id(manager), stage)
    details: dict[str, Any] = {
        "release_id": manager.release_id,
        "video_id": manager.video_id,
        "stage": stage,
        **{
            key: value
            for key, value in _MANAGER_RUNTIME_CONTEXT.get(manager, {}).items()
            if key != "stage_sources"
        },
    }
    if status == "start":
        _STAGE_TIMERS[timer_key] = time.monotonic()
    else:
        started = _STAGE_TIMERS.pop(timer_key, None)
        if started is not None:
            details["elapsed_seconds"] = round(time.monotonic() - started, 3)
    if reused is not None:
        details["source"] = "restored" if reused else "computed"
    _emit_progress(event="stage", status=status, scratch=scratch, **details)


def _record_stage_source(
    manager: CheckpointManager,
    stage: str,
    *,
    reused: bool,
) -> None:
    context = _MANAGER_RUNTIME_CONTEXT.setdefault(manager, {})
    sources = context.setdefault("stage_sources", {})
    source = "restored" if reused else "computed"
    previous = sources.get(stage)
    if previous is not None and previous != source:
        raise RuntimeError(
            "Phase01 stage source changed during one execution: "
            f"stage={stage}, previous={previous}, current={source}"
        )
    sources[stage] = source


def _model_lifecycle_callback(
    *,
    scratch_root: Path,
    release_id: str,
    batch_id: str,
    chunk_index: int,
    chunk_size: int,
    stage: str,
):
    def emit(payload: Mapping[str, Any]) -> None:
        details = dict(payload)
        status = str(details.pop("status"))
        if "load_seconds" in details:
            details.setdefault("elapsed_seconds", details["load_seconds"])
        _emit_progress(
            event="model",
            status=status,
            scratch=scratch_root,
            release_id=release_id,
            batch_id=batch_id,
            stage=stage,
            chunk_index=chunk_index,
            chunk_size=chunk_size,
            **details,
        )

    return emit


def _heavy_model_memory_guard(
    *,
    scratch_root: Path,
    release_id: str,
    batch_id: str,
    chunk_index: int,
    chunk_size: int,
    policy: Mapping[str, Any],
):
    try:
        minimum_available_gb = float(policy["minimum_available_gb"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(
            "Phase01 RAM guard minimum_available_gb must be configured"
        ) from exc
    if minimum_available_gb < 0:
        raise ValueError("Phase01 RAM guard minimum_available_gb must be non-negative")

    def guard(provider: str) -> None:
        before_cleanup_gb = _available_ram_gb()
        _cleanup_runtime_resources()
        available_gb = _available_ram_gb()
        _emit_progress(
            event="memory_guard",
            status="pass" if available_gb >= minimum_available_gb else "blocked",
            scratch=scratch_root,
            release_id=release_id,
            batch_id=batch_id,
            chunk_index=chunk_index,
            chunk_size=chunk_size,
            provider=provider,
            ram_available_before_cleanup_gb=before_cleanup_gb,
            ram_available_after_cleanup_gb=available_gb,
            minimum_available_gb=minimum_available_gb,
        )
        if available_gb < minimum_available_gb:
            raise InsufficientMemoryError(
                "insufficient RAM for heavy model load: "
                f"available={available_gb:.3f} GiB, "
                f"minimum={minimum_available_gb:.3f} GiB, provider={provider}"
            )

    return guard


def _resource_snapshot(scratch: Path) -> dict[str, float | None]:
    snapshot: dict[str, float | None] = {
        "scratch_free_gb": None,
        "ram_used_gb": None,
        "ram_available_gb": None,
        "process_rss_gb": None,
        "gpu_allocated_gb": None,
        "gpu_reserved_gb": None,
        "gpu_peak_allocated_gb": None,
    }
    try:
        snapshot["scratch_free_gb"] = _bytes_to_gb(shutil.disk_usage(scratch).free)
    except (FileNotFoundError, OSError):
        pass
    try:
        memory = psutil.virtual_memory()
        snapshot["ram_available_gb"] = _bytes_to_gb(memory.available)
        snapshot["ram_used_gb"] = _bytes_to_gb(memory.total - memory.available)
        snapshot["process_rss_gb"] = _bytes_to_gb(
            psutil.Process().memory_info().rss
        )
    except (OSError, TypeError, ValueError):
        pass
    try:
        import torch
    except ImportError:
        return snapshot
    try:
        if torch.cuda.is_available():
            snapshot["gpu_allocated_gb"] = _bytes_to_gb(
                torch.cuda.memory_allocated()
            )
            snapshot["gpu_reserved_gb"] = _bytes_to_gb(
                torch.cuda.memory_reserved()
            )
            snapshot["gpu_peak_allocated_gb"] = _bytes_to_gb(
                torch.cuda.max_memory_allocated()
            )
    except (RuntimeError, TypeError, ValueError):
        pass
    return snapshot


def _bytes_to_gb(value: float) -> float:
    return round(float(value) / (1024**3), 3)


def _scratch_free_gb(scratch: Path) -> float:
    return float(shutil.disk_usage(scratch).free) / (1024**3)


def _available_ram_gb() -> float:
    return float(psutil.virtual_memory().available) / (1024**3)


def _mapping_raw_bytes(mapping: Mapping[str, Any]) -> int | None:
    value = mapping.get("video_size_bytes")
    if _present_scalar(value):
        try:
            size = int(value)
        except (TypeError, ValueError):
            size = -1
        if size >= 0:
            return size
    for key in ("video_local_path", "debug_video_local_path", "source_video_path"):
        path_value = mapping.get(key)
        if _present_scalar(path_value):
            path = Path(str(path_value))
            if path.is_file():
                return path.stat().st_size
    return None


def _hf_store(config, *, cache_dir: Path | str | None = None):
    return HuggingFaceDatasetArtifactStore(
        repo_id=str(config["repo_id"]),
        repo_type=str(config.get("repo_type", "dataset")),
        revision=str(config.get("revision", "main")),
        token=os.environ.get("AIC_HF_TOKEN") or os.environ.get("HF_TOKEN"),
        prefix=str(config.get("prefix", "")),
        cache_dir=cache_dir,
    )


def _release_structured_client(client: Any) -> None:
    close = getattr(client, "close", None)
    if callable(close):
        close()
    _cleanup_runtime_resources()


def _cleanup_runtime_resources() -> None:
    # Third-party wrappers do not consistently release cyclic references or
    # CUDA caches even after their close hook returns.
    gc.collect()
    try:
        import torch
    except ImportError:
        return
    try:
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            ipc_collect = getattr(torch.cuda, "ipc_collect", None)
            if callable(ipc_collect):
                ipc_collect()
    except RuntimeError:
        pass


def _materialize_canonical(mapping, key, target_dir):
    local_keys = ("video_local_path", "debug_video_local_path", "source_video_path") if "video" in key else ("metadata_local_path", "debug_metadata_local_path", "source_metadata_path")
    for local_key in local_keys:
        value = mapping.get(local_key)
        if _present_scalar(value) and Path(str(value)).is_file(): return Path(str(value))
    target_dir.mkdir(parents=True, exist_ok=True)
    remote_path = str(mapping[key]); target = target_dir / Path(remote_path).name
    store = HuggingFaceDatasetArtifactStore(
        repo_id=str(mapping["canonical_repo_id"]),
        repo_type=(
            str(mapping.get("canonical_repo_type"))
            if _present_scalar(mapping.get("canonical_repo_type"))
            else "dataset"
        ),
        revision=(
            str(mapping.get("canonical_revision"))
            if _present_scalar(mapping.get("canonical_revision"))
            else "main"
        ),
        token=os.environ.get("AIC_HF_TOKEN") or os.environ.get("HF_TOKEN"),
        prefix=(
            str(mapping.get("canonical_prefix"))
            if _present_scalar(mapping.get("canonical_prefix"))
            else ""
        ),
        cache_dir=target_dir / ".hf_cache",
    )
    return store.download_file(remote_path, target)


def _timeline_path(release_dir, video_id, video_row):
    candidate = video_row.get("frame_timeline_ref")
    ref = candidate if _present_scalar(candidate) else f"frame_timeline/{video_id}.parquet"
    path = release_dir / str(ref)
    if not path.is_file(): raise FileNotFoundError(path)
    return path


def _stable_video_identity(mapping):
    return {key: _json_scalar(mapping.get(key)) for key in ("canonical_repo_id", "canonical_revision", "canonical_prefix", "canonical_video_path", "video_size_bytes")}


def _stable_metadata_identity(mapping):
    return {
        key: _json_scalar(mapping.get(key))
        for key in (
            "canonical_repo_id",
            "canonical_revision",
            "canonical_prefix",
            "canonical_metadata_path",
            "metadata_size_bytes",
            "metadata_schema_version",
        )
    }


def _present_scalar(value: Any) -> bool:
    if value is None:
        return False
    try:
        if bool(pd.isna(value)):
            return False
    except (TypeError, ValueError):
        pass
    return bool(str(value).strip())


def _json_scalar(value: Any) -> Any:
    if not _present_scalar(value):
        return None
    item = getattr(value, "item", None)
    return item() if callable(item) else value


def _validate_keyframe_rows(shots, rows):
    for shot in shots:
        members = [row for row in rows if row["shot_id"] == shot["shot_id"]]
        if not members or sum(row["is_representative"] for row in members) != 1: raise ValueError(f"Invalid keyframe selection for {shot['shot_id']}")
        if any(
            row["keyframe_role"] == "supplemental" and row["is_representative"]
            for row in members
        ):
            raise ValueError("Supplemental keyframes cannot be representative")
        if any(not (shot["start_frame"] <= row["frame_id"] < shot["end_frame"]) for row in members): raise ValueError("Keyframe lies outside its shot")


def _write_parquet(path, rows, empty_columns=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    schema_path = Path(__file__).resolve().parents[3] / "schemas" / f"{path.stem}.schema.json"
    if schema_path.is_file():
        validate_rows(path.stem, rows)
    pd.DataFrame(rows, columns=empty_columns if not rows and empty_columns else None).to_parquet(path, index=False)


def _write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True); path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def _prompt_dir(): return Path(__file__).resolve().parents[3] / "prompts"


def _required_text(payload: Mapping[str, Any], key: str) -> str:
    value = str(payload[key]).strip()
    if not value:
        raise ValueError(
            f"Structured field must contain non-whitespace text: {key}"
        )
    return value


def _retryable_video_error(exc):
    if isinstance(exc, ScenePartitionQualityError):
        return False
    if isinstance(exc, (AsrResourceError, InsufficientMemoryError)):
        return True
    message = str(exc).lower()
    return any(marker in message for marker in ("timeout", "timed out", "429", "500", "502", "503", "504", "out of memory", "insufficient ram", "temporarily unavailable", "connection reset", "decode", "i/o"))


def _checkpoint_error_payload(exc: Exception) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "error_type": type(exc).__name__,
        "message": str(exc),
        "failed_at": utc_now(),
    }
    details = getattr(exc, "details", None)
    if isinstance(details, Mapping):
        payload["details"] = dict(details)
    return payload
