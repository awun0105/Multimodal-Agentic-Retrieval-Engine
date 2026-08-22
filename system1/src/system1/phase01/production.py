from __future__ import annotations

import json
import os
import shutil
import tempfile
import zipfile
from collections.abc import Mapping
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path
from typing import Any

import pandas as pd

from system1.artifacts.checkpoint import sha256_file
from system1.artifacts.hf_store import HuggingFaceDatasetArtifactStore
from system1.artifacts.package import validate_artifact_zip, write_artifact_zip
from system1.artifacts.reports import utc_now, write_worker_report
from system1.artifacts.store import ArtifactStore
from system1.asr import build_shot_transcript_links, transcribe_video
from system1.config import ResolvedPhase01Config, persist_resolved_phase01_config
from system1.gemini import GeminiRequest, GeminiStructuredClient
from system1.ingest.discovery import read_metadata
from system1.keyframes import (
    candidate_frame_ids_for_shot,
    iter_decode_frame_groups,
    select_keyframes_for_shot,
    write_keyframe_images,
)
from system1.phase01.checkpoint import CheckpointManager, compute_fingerprint
from system1.phase01.qa import write_manual_review_report
from system1.phase01.validation import validate_phase01_package, validate_rows
from system1.scenes import group_scenes
from system1.scenes.gemini_judge import GeminiSceneBoundaryJudge
from system1.shots import (
    detect_shot_scenes,
    load_transnet_artifact,
    scenes_to_shot_rows,
)

PARQUET_COLUMNS: dict[str, list[str]] = {
    "asr_segments": [
        "asr_segment_id", "video_id", "start_sec", "end_sec", "start_frame", "end_frame",
        "text", "language", "confidence", "avg_logprob", "no_speech_prob", "provider",
        "model_name", "model_version", "status",
    ],
    "shot_transcript_links": ["video_id", "shot_id", "asr_segment_id", "coverage"],
    "scene_transcript_links": ["video_id", "scene_id", "asr_segment_id", "coverage"],
}


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
    videos = pd.read_parquet(release_dir / "tables" / "videos.parquet")
    media = pd.read_parquet(release_dir / "raw_mapping" / "media_store_manifest.parquet")
    videos_by_id = {str(row["video_id"]): row for row in videos.to_dict("records")}
    media_by_id = {str(row["video_id"]): row for row in media.to_dict("records")}
    checkpoint_store = _hf_store(config.payload["storage"]["checkpoint"])
    release_store = _hf_store(config.payload["storage"]["release"])
    results: list[dict[str, Any]] = []
    scratch_root.mkdir(parents=True, exist_ok=True)

    for video_id in video_ids:
        video_scratch = scratch_root / release_id / batch_id / video_id
        if video_scratch.exists():
            shutil.rmtree(video_scratch)
        video_scratch.mkdir(parents=True)
        manager = CheckpointManager(
            checkpoint_store,
            release_id=release_id,
            video_id=video_id,
            config_hash=config.config_hash,
            stage_config_hashes=config.stage_config_hashes,
            verify_remote_checksum=bool(
                config.payload["storage"]["checkpoint"].get("verify_remote_checksum", True)
            ),
            root_template=str(config.payload["artifact"]["checkpoint"]["root"]),
            state_filename=str(
                config.payload["artifact"]["checkpoint"]["state_filename"]
            ),
        )
        try:
            if video_id not in videos_by_id or video_id not in media_by_id:
                raise ValueError(f"Phase00 batch references unknown video_id={video_id}")
            result = _process_video(
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
            )
        except Exception as exc:  # noqa: BLE001 - isolate failures per video
            retryable = _retryable_video_error(exc)
            checkpoint_error: str | None = None
            try:
                failed_stage = manager.active_stage
                manager.mark_failed(
                    failed_stage,
                    input_fingerprint=None,
                    retryable=retryable,
                    error={
                        "error_type": type(exc).__name__,
                        "message": str(exc),
                        "failed_at": utc_now(),
                    },
                )
            except Exception as checkpoint_exc:  # noqa: BLE001 - retain original error
                failed_stage = "unknown"
                checkpoint_error = str(checkpoint_exc)
            result = {
                "video_id": video_id,
                "status": "failed_retryable" if retryable else "failed_terminal",
                "failed_stage": failed_stage,
                "error_type": type(exc).__name__,
                "error": str(exc),
                "checkpoint_error": checkpoint_error,
            }
        finally:
            shutil.rmtree(video_scratch, ignore_errors=True)
        results.append(result)

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
    if failed:
        raise RuntimeError(
            f"Phase01 batch completed with {len(failed)} failed video(s); report={report}"
        )
    return report


def _process_video(
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
) -> dict[str, Any]:
    manager.active_stage = "shots"
    stage_dir = scratch / "stages"
    stage_dir.mkdir()
    # API responses only need request-level reuse while the current atomic
    # stage is running. Completed canonical tables are the persistent cache via
    # the stage checkpoint, so avoid one HF commit per Gemini request.
    api_cache = ArtifactStore(scratch / "api_cache")
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
    media_config = config.payload["media"]

    shots_path = stage_dir / "shots.parquet"
    shots_fingerprint = compute_fingerprint(
        video_timeline_fingerprint, config.stage_config_hashes["shots"]
    )
    if not _restore_if_reusable(manager, "shots", shots_fingerprint, stage_dir):
        artifact = load_transnet_artifact(
            transnet_artifact_dir,
            expected_commit=str(models["shot_detection"]["model_revision"]),
            expected_source_sha256=str(
                models["shot_detection"]["source_sha256"]
            ),
            expected_weights_sha256=str(models["shot_detection"]["weights_sha256"]),
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
    shots = pd.read_parquet(shots_path).to_dict("records")
    shots_output_fingerprint = manager.stage_output_fingerprint("shots")

    manager.active_stage = "keyframes"
    keyframes_path = stage_dir / "keyframes.parquet"
    keyframes_bundle = stage_dir / "keyframes.zip"
    keyframes_fingerprint = _stage_fingerprint(
        manager, "keyframes", shots_output_fingerprint
    )
    if not _restore_keyframes_if_reusable(manager, keyframes_fingerprint, stage_dir):
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
    keyframes = pd.read_parquet(keyframes_path).to_dict("records")
    keyframes_output_fingerprint = manager.stage_output_fingerprint("keyframes")

    manager.active_stage = "asr"
    asr_path = stage_dir / "asr_segments.parquet"
    asr_status_path = stage_dir / "asr_status.json"
    asr_fingerprint = compute_fingerprint(
        video_timeline_fingerprint, config.stage_config_hashes["asr"]
    )
    if not _restore_if_reusable(manager, "asr", asr_fingerprint, stage_dir):
        asr_config = {**models["asr"], "total_attempts": phase01["retry"]["local_model_total_attempts"]}
        result = transcribe_video(
            video_path,
            video_id=video_id,
            frame_timeline=timeline,
            config=asr_config,
        )
        _write_parquet(asr_path, result.rows, empty_columns=PARQUET_COLUMNS["asr_segments"])
        _write_json(asr_status_path, {
            "status": result.status,
            "compute_type": result.compute_type,
            "attempts": result.attempts,
            "detected_language": result.detected_language,
        })
        manager.promote_stage(
            "asr",
            input_fingerprint=asr_fingerprint,
            outputs=[asr_path, asr_status_path],
            model=models["asr"],
            schema_version=phase01["schemas"]["asr_segments"],
        )
    asr_rows = pd.read_parquet(asr_path).to_dict("records")
    asr_output_fingerprint = manager.stage_output_fingerprint("asr")

    manager.active_stage = "shot_captions"
    gemini_client = GeminiStructuredClient(
        model_id=str(models["shot_caption"]["model_id"]),
        api_config={
            **phase01["api"],
            "schema_repair_attempts": phase01["retry"]["schema_repair_attempts"],
            "thinking_level": models["shot_caption"]["thinking_level"],
        },
        cache=api_cache,
        cache_prefix="gemini",
    )
    captions_path = stage_dir / "shot_captions.parquet"
    captions_fingerprint = _stage_fingerprint(
        manager, "shot_captions", keyframes_output_fingerprint
    )
    if not _restore_if_reusable(manager, "shot_captions", captions_fingerprint, stage_dir):
        caption_rows = _build_captions(
            video_id=video_id,
            shots=shots,
            keyframes=keyframes,
            stage_dir=stage_dir,
            client=gemini_client,
            model_config=models["shot_caption"],
            max_concurrency=int(phase01["api"]["max_concurrency_per_video"]),
        )
        _write_parquet(captions_path, caption_rows)
        manager.promote_stage(
            "shot_captions",
            input_fingerprint=captions_fingerprint,
            outputs=[captions_path],
            model=models["shot_caption"],
            prompt_version=models["shot_caption"]["prompt_version"],
            schema_version=phase01["schemas"]["shot_captions"],
        )
    captions = pd.read_parquet(captions_path).to_dict("records")
    captions_output_fingerprint = manager.stage_output_fingerprint("shot_captions")

    manager.active_stage = "shot_transcript_links"
    links_path = stage_dir / "shot_transcript_links.parquet"
    links_fingerprint = compute_fingerprint(
        shots_output_fingerprint,
        asr_output_fingerprint,
        config.stage_config_hashes["shot_transcript_links"],
    )
    if not _restore_if_reusable(manager, "shot_transcript_links", links_fingerprint, stage_dir):
        links = build_shot_transcript_links(shots, asr_rows)
        _write_parquet(links_path, links, empty_columns=PARQUET_COLUMNS["shot_transcript_links"])
        manager.promote_stage(
            "shot_transcript_links",
            input_fingerprint=links_fingerprint,
            outputs=[links_path],
            schema_version=phase01["schemas"]["shot_transcript_links"],
        )
    links = pd.read_parquet(links_path).to_dict("records")
    links_output_fingerprint = manager.stage_output_fingerprint(
        "shot_transcript_links"
    )

    manager.active_stage = "scenes"
    scenes_path = stage_dir / "scenes.parquet"
    scene_links_path = stage_dir / "scene_transcript_links.parquet"
    scene_diagnostics_path = stage_dir / "scene_boundary_diagnostics.jsonl"
    scenes_fingerprint = compute_fingerprint(
        shots_output_fingerprint,
        keyframes_output_fingerprint,
        captions_output_fingerprint,
        asr_output_fingerprint,
        links_output_fingerprint,
        config.stage_config_hashes["scenes"],
    )
    if not _restore_if_reusable(manager, "scenes", scenes_fingerprint, stage_dir):
        evidence = _build_scene_evidence(shots, keyframes, captions, asr_rows, links, stage_dir)
        boundary_client = GeminiStructuredClient(
            model_id=str(models["scene_boundary"]["model_id"]),
            api_config={
                **phase01["api"],
                "schema_repair_attempts": phase01["retry"]["schema_repair_attempts"],
                "thinking_level": models["scene_boundary"]["thinking_level"],
            },
            cache=api_cache,
            cache_prefix="gemini",
        )
        judge = GeminiSceneBoundaryJudge(
            boundary_client,
            video_id=video_id,
            prompt_dir=_prompt_dir(),
            diagnostics_dir=stage_dir / "diagnostics" / "scene_requests",
            model_config=models["scene_boundary"],
        )
        scenes, decisions = group_scenes(
            video_id=video_id,
            shots=shots,
            evidence=evidence,
            judge=judge,
            config=phase01["scene_grouping"],
        )
        _write_parquet(scenes_path, scenes)
        scene_links = _build_scene_transcript_links(scenes, asr_rows)
        _write_parquet(
            scene_links_path,
            scene_links,
            empty_columns=PARQUET_COLUMNS["scene_transcript_links"],
        )
        _write_jsonl(scene_diagnostics_path, [decision.__dict__ for decision in decisions])
        manager.promote_stage(
            "scenes",
            input_fingerprint=scenes_fingerprint,
            outputs=[scenes_path, scene_links_path, scene_diagnostics_path],
            model=models["scene_boundary"],
            prompt_version=models["scene_boundary"]["prompt_version"],
            schema_version=phase01["schemas"]["scenes"],
        )
    scenes = pd.read_parquet(scenes_path).to_dict("records")
    scene_links = pd.read_parquet(scene_links_path).to_dict("records")
    scenes_output_fingerprint = manager.stage_output_fingerprint("scenes")

    manager.active_stage = "scene_summaries"
    summaries_path = stage_dir / "scene_summaries.parquet"
    summaries_fingerprint = compute_fingerprint(
        scenes_output_fingerprint,
        keyframes_output_fingerprint,
        asr_output_fingerprint,
        captions_output_fingerprint,
        links_output_fingerprint,
        config.stage_config_hashes["scene_summaries"],
    )
    if not _restore_if_reusable(manager, "scene_summaries", summaries_fingerprint, stage_dir):
        summary_client = GeminiStructuredClient(
            model_id=str(models["scene_summary"]["model_id"]),
            api_config={
                **phase01["api"],
                "schema_repair_attempts": phase01["retry"]["schema_repair_attempts"],
                "thinking_level": models["scene_summary"]["thinking_level"],
            },
            cache=api_cache,
            cache_prefix="gemini",
        )
        summary_rows = _build_scene_summaries(
            video_id=video_id,
            scenes=scenes,
            shots=shots,
            keyframes=keyframes,
            captions=captions,
            asr_rows=asr_rows,
            scene_links=scene_links,
            stage_dir=stage_dir,
            client=summary_client,
            model_config=models["scene_summary"],
            summary_config=phase01["scene_summary"],
        )
        _write_parquet(summaries_path, summary_rows)
        manager.promote_stage(
            "scene_summaries",
            input_fingerprint=summaries_fingerprint,
            outputs=[summaries_path],
            model=models["scene_summary"],
            prompt_version=models["scene_summary"]["prompt_version"],
            schema_version=phase01["schemas"]["scene_summaries"],
        )
    summaries_output_fingerprint = manager.stage_output_fingerprint("scene_summaries")

    manager.active_stage = "package"
    package_fingerprint = compute_fingerprint(
        metadata_fingerprint,
        shots_output_fingerprint,
        keyframes_output_fingerprint,
        asr_output_fingerprint,
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
    if not _restore_if_reusable(manager, "package", package_fingerprint, stage_dir):
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

    local_artifact = release_dir / "artifacts" / "structure" / package_filename
    local_artifact.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(package_path, local_artifact)
    if not sync_release:
        return {"video_id": video_id, "status": "complete_local", "artifact": str(local_artifact)}

    manager.active_stage = "sync"
    sync_fingerprint = compute_fingerprint(
        package_fingerprint, sha256_file(package_path), config.stage_config_hashes["sync"]
    )
    if not manager.is_reusable("sync", input_fingerprint=sync_fingerprint):
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
    candidate_groups = []
    for shot in shots:
        by_role = candidate_frame_ids_for_shot(shot, keyframe_config)
        candidate_groups.append(
            {frame_id for role_ids in by_role.values() for frame_id in role_ids}
        )
    timeline_by_frame = {int(row["frame_id"]): row for row in timeline}
    rows: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    decoded_groups = iter_decode_frame_groups(video_path, candidate_groups)
    for shot, decoded in zip(shots, decoded_groups, strict=True):
        selected, candidate_diagnostics = select_keyframes_for_shot(shot, decoded, keyframe_config)
        diagnostics.extend({"shot_id": shot["shot_id"], **item.__dict__} for item in candidate_diagnostics)
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


def _build_captions(
    *, video_id: str, shots: list[dict[str, Any]], keyframes: list[dict[str, Any]],
    stage_dir: Path, client: GeminiStructuredClient, model_config: Mapping[str, Any],
    max_concurrency: int,
) -> list[dict[str, Any]]:
    if max_concurrency < 1:
        raise ValueError("Gemini max_concurrency must be positive")
    representative = {str(row["shot_id"]): row for row in keyframes if row["is_representative"]}
    prompt = (_prompt_dir() / f"{model_config['prompt_version']}.txt").read_text(encoding="utf-8")
    schema = {
        "type": "object",
        "properties": {"caption_vi": {"type": "string", "minLength": 1}, "caption_en": {"type": "string", "minLength": 1}},
        "required": ["caption_vi", "caption_en"],
        "additionalProperties": False,
    }
    def build(shot: dict[str, Any]) -> dict[str, Any]:
        keyframe = representative[str(shot["shot_id"])]
        image = stage_dir / "keyframes" / Path(str(keyframe["keyframe_ref"])).name
        response = client.request(GeminiRequest(
            request_kind="shot_caption", video_id=video_id, prompt=prompt,
            prompt_version=str(model_config["prompt_version"]),
            response_schema_version=str(model_config["response_schema_version"]),
            response_schema=schema, image_paths=(image,), identity={"shot_id": shot["shot_id"]},
        ))
        caption_vi = _required_text(response, "caption_vi")
        caption_en = _required_text(response, "caption_en")
        return {
            "shot_caption_id": f"{shot['shot_id']}_caption", "video_id": video_id,
            "shot_id": shot["shot_id"], "representative_keyframe_id": keyframe["keyframe_id"],
            "representative_timestamp_sec": keyframe["timestamp_sec"],
            "caption_vi": caption_vi, "caption_en": caption_en,
            "provider": "gemini", "model_name": model_config["model_id"],
            "model_version": model_config["model_revision"], "prompt_version": model_config["prompt_version"],
            "schema_version": model_config["response_schema_version"], "confidence": None, "status": "pass",
        }
    rows: list[dict[str, Any]] = []
    shot_iterator = iter(shots)
    executor = ThreadPoolExecutor(max_workers=max_concurrency)
    pending = {
        executor.submit(build, shot)
        for shot in [item for _, item in zip(range(max_concurrency), shot_iterator)]
    }
    try:
        while pending:
            completed, pending = wait(pending, return_when=FIRST_COMPLETED)
            for future in completed:
                rows.append(future.result())
                next_shot = next(shot_iterator, None)
                if next_shot is not None:
                    pending.add(executor.submit(build, next_shot))
    except Exception:
        for future in pending:
            future.cancel()
        raise
    finally:
        executor.shutdown(wait=True, cancel_futures=True)
    return sorted(rows, key=lambda row: str(row["shot_id"]))


def _build_scene_evidence(shots, keyframes, captions, asr_rows, links, stage_dir):
    by_shot_keyframes: dict[str, list[dict[str, Any]]] = {}
    for row in keyframes:
        by_shot_keyframes.setdefault(str(row["shot_id"]), []).append(row)
    caption_by_shot = {str(row["shot_id"]): row for row in captions}
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
        }
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
        evidence.append({
            "shot_id": shot_id, "start_sec": shot["start_sec"], "end_sec": shot["end_sec"],
            "representative_path": stage_dir
            / "keyframes"
            / Path(str(representative["keyframe_ref"])).name,
            "early_path": role_paths.get("early"), "late_path": role_paths.get("late"),
            "caption_vi": caption["caption_vi"], "caption_en": caption["caption_en"], "transcript": transcript,
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


def _build_scene_summaries(*, video_id, scenes, shots, keyframes, captions, asr_rows, scene_links, stage_dir, client, model_config, summary_config):
    prompt_base = (_prompt_dir() / f"{model_config['prompt_version']}.txt").read_text(encoding="utf-8")
    schema = {"type": "object", "properties": {"summary_vi": {"type": "string", "minLength": 1}, "summary_en": {"type": "string", "minLength": 1}}, "required": ["summary_vi", "summary_en"], "additionalProperties": False}
    captions_by_shot = {str(row["shot_id"]): row for row in captions}
    representative = {str(row["shot_id"]): row for row in keyframes if row["is_representative"]}
    asr_by_id = {str(row["asr_segment_id"]): row for row in asr_rows}
    links_by_scene: dict[str, list[dict[str, Any]]] = {}
    for link in scene_links: links_by_scene.setdefault(str(link["scene_id"]), []).append(link)
    rows = []
    for scene in scenes:
        scene_shots = [shot for shot in shots if float(shot["start_sec"]) >= float(scene["start_sec"]) and float(shot["end_sec"]) <= float(scene["end_sec"]) + 1e-6]
        sampled_shots = _evenly_sample(
            scene_shots, int(summary_config["max_representative_images"])
        )
        image_paths = tuple(
            stage_dir
            / "keyframes"
            / Path(str(representative[str(shot["shot_id"])]["keyframe_ref"])).name
            for shot in sampled_shots
        )
        evidence = {"shots": [{"shot_id": shot["shot_id"], "caption_vi": captions_by_shot[str(shot["shot_id"])]["caption_vi"], "caption_en": captions_by_shot[str(shot["shot_id"])]["caption_en"]} for shot in scene_shots], "transcript": [asr_by_id[str(link["asr_segment_id"])]["text"] for link in links_by_scene.get(str(scene["scene_id"]), [])], "timeline": [scene["start_sec"], scene["end_sec"]]}
        response = client.request(GeminiRequest(request_kind="scene_summary", video_id=video_id, prompt=prompt_base + "\n\nSCENE EVIDENCE:\n" + json.dumps(evidence, ensure_ascii=False), prompt_version=str(model_config["prompt_version"]), response_schema_version=str(model_config["response_schema_version"]), response_schema=schema, image_paths=image_paths, identity={"scene_id": scene["scene_id"]}))
        rows.append({"scene_id": scene["scene_id"], "video_id": video_id, "summary_vi": _required_text(response, "summary_vi"), "summary_en": _required_text(response, "summary_en"), "provider": "gemini", "model_name": model_config["model_id"], "model_version": model_config["model_revision"], "prompt_version": model_config["prompt_version"], "schema_version": model_config["response_schema_version"], "confidence": None, "status": "pass"})
    return rows


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
    for name in ("shots.parquet", "keyframes.parquet", "asr_segments.parquet", "shot_captions.parquet", "shot_transcript_links.parquet", "scenes.parquet", "scene_transcript_links.parquet", "scene_summaries.parquet"):
        shutil.copy2(stage_dir / name, artifact_dir / name)
    shutil.copytree(stage_dir / "keyframes", artifact_dir / "keyframes")
    shutil.copytree(stage_dir / "thumbnails", artifact_dir / "thumbnails")
    diagnostics = artifact_dir / "diagnostics"; diagnostics.mkdir()
    for name in ("keyframe_diagnostics.jsonl", "scene_boundary_diagnostics.jsonl", "transnet_predictions.json", "asr_status.json"):
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
    return manager.is_reusable(
        stage,
        input_fingerprint=fingerprint,
        restore_dir=target_dir,
    )


def _restore_keyframes_if_reusable(manager, fingerprint, target_dir):
    if not manager.is_reusable(
        "keyframes", input_fingerprint=fingerprint, restore_dir=target_dir
    ):
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


def _hf_store(config):
    return HuggingFaceDatasetArtifactStore(repo_id=str(config["repo_id"]), repo_type=str(config.get("repo_type", "dataset")), revision=str(config.get("revision", "main")), token=os.environ.get("AIC_HF_TOKEN") or os.environ.get("HF_TOKEN"), prefix=str(config.get("prefix", "")))


def _materialize_canonical(mapping, key, target_dir):
    local_keys = ("video_local_path", "debug_video_local_path", "source_video_path") if "video" in key else ("metadata_local_path", "debug_metadata_local_path", "source_metadata_path")
    for local_key in local_keys:
        value = mapping.get(local_key)
        if _present_scalar(value) and Path(str(value)).is_file(): return Path(str(value))
    target_dir.mkdir(parents=True, exist_ok=True)
    remote_path = str(mapping[key]); target = target_dir / Path(remote_path).name
    store = HuggingFaceDatasetArtifactStore(repo_id=str(mapping["canonical_repo_id"]), repo_type=str(mapping.get("canonical_repo_type")) if _present_scalar(mapping.get("canonical_repo_type")) else "dataset", revision=str(mapping.get("canonical_revision")) if _present_scalar(mapping.get("canonical_revision")) else "main", token=os.environ.get("AIC_HF_TOKEN") or os.environ.get("HF_TOKEN"), prefix=str(mapping.get("canonical_prefix")) if _present_scalar(mapping.get("canonical_prefix")) else "")
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
        raise ValueError(f"Gemini structured field must contain non-whitespace text: {key}")
    return value


def _retryable_video_error(exc):
    message = str(exc).lower()
    return any(marker in message for marker in ("timeout", "timed out", "429", "500", "502", "503", "504", "out of memory", "temporarily unavailable", "connection reset", "decode", "i/o"))
