from __future__ import annotations

import copy
import gc
import io
import json
import shutil
import threading
import time
import traceback
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

import pandas as pd

from system1.artifacts.checkpoint import sha256_file
from system1.artifacts.hf_store import HuggingFaceDatasetArtifactStore
from system1.artifacts.package import validate_artifact_zip
from system1.artifacts.reports import utc_now
from system1.config import (
    ResolvedPhase01Config,
    load_configs,
    persist_resolved_phase01_config,
    rebuild_resolved_phase01_config,
    require_phase01_production_ready,
    resolve_phase01_config,
)
from system1.phase01.model_artifacts import materialize_transnet_artifact
from system1.phase01.phase00 import discover_phase00_candidates, resolve_phase00_release
from system1.phase01.preflight import (
    RuntimePreflightResult,
    run_phase01_preflight,
    run_phase01_runtime_preflight,
)
from system1.phase01.production import process_production_batch
from system1.phase01.runner import (
    _git_identity,
    _hf_store,
    _scratch_root,
)
from system1.phase01_qualification import new_run_id, sanitize_payload, write_json_atomic
from system1.release.sync import phase00_ingestion_remote_prefix


_REQUIRED_STAGES = (
    "shots",
    "keyframes",
    "asr",
    "ocr",
    "shot_captions",
    "shot_transcript_links",
    "scenes",
    "scene_summaries",
    "package",
    "sync",
)


class Phase01SmokeError(RuntimeError):
    """The optional real-provider smoke run failed."""

    def __init__(self, message: str, *, report_path: Path) -> None:
        super().__init__(message)
        self.report_path = report_path


@dataclass(frozen=True)
class Phase01SmokeResult:
    run_id: str
    ready_for_full_run: bool
    report_path: Path
    remote_report_path: str | None


def run_phase01_smoke(
    *,
    config_dir: Path,
    output_root: Path,
    user_settings: Mapping[str, Any],
    run_id: str | None = None,
    keep_remote_artifacts: bool | None = None,
    cleanup_local: bool | None = None,
) -> Phase01SmokeResult:
    """Execute one isolated video through the unmodified production core."""

    started_at = utc_now()
    started_monotonic = time.monotonic()
    effective_run_id = str(run_id or new_run_id())
    _validate_run_id(effective_run_id)
    configs = load_configs(config_dir)
    smoke_policy = _smoke_policy(configs)
    video_id = str(smoke_policy["video_id"])
    namespace = _smoke_namespace(smoke_policy, effective_run_id)
    batch_id = f"smoke_{effective_run_id}"
    worker_id = f"smoke_{effective_run_id}"
    smoke_root = output_root.resolve() / ".phase01_smoke" / effective_run_id
    release_id = str(smoke_policy["source_release"]["release_id"])
    release_dir = smoke_root / release_id
    report_path = output_root.resolve() / "smoke_reports" / f"{effective_run_id}.json"
    keep_artifacts = (
        bool(smoke_policy["keep_remote_artifacts"])
        if keep_remote_artifacts is None
        else keep_remote_artifacts
    )
    cleanup_enabled = (
        bool(smoke_policy["cleanup_local"])
        if cleanup_local is None
        else cleanup_local
    )
    report: dict[str, Any] = {
        "schema_version": "phase01_real_smoke_report_v1",
        "run_id": effective_run_id,
        "status": "fail",
        "ready_for_full_run": False,
        "started_at": started_at,
        "finished_at": None,
        "elapsed_seconds": None,
        "video_id": video_id,
        "namespace": namespace,
        "fixture": copy.deepcopy(smoke_policy),
        "runtime": {},
        "git": _git_identity(),
        "config": {},
        "stage_sources": {},
        "package": {},
        "resources": {},
        "cleanup": {
            "local": "pending",
            "model_cache": "kept",
            "remote_artifacts": "kept" if keep_artifacts else "pending",
        },
        "failed_stage": None,
        "error": None,
    }
    remote_report_path: str | None = None
    output_store: HuggingFaceDatasetArtifactStore | None = None
    checkpoint_store: HuggingFaceDatasetArtifactStore | None = None
    scratch_root: Path | None = None
    sampler = _ResourceSampler()
    try:
        resolved = _resolve_smoke_config(
            config_dir=config_dir,
            production_user_settings=user_settings,
            smoke_policy=smoke_policy,
            namespace=namespace,
            batch_id=batch_id,
            worker_id=worker_id,
        )
        require_phase01_production_ready(resolved)
        scratch_root = _scratch_root(resolved.payload["storage"], smoke_root)
        report["config"] = {
            "config_hash": resolved.config_hash,
            "stage_config_hashes": dict(resolved.stage_config_hashes),
            "pipeline_id": resolved.payload["phase01"]["pipeline_id"],
            "providers": _provider_identity(resolved),
        }
        output_store = _hf_store(
            resolved.payload["storage"]["release"],
            cache_dir=scratch_root / ".hf_cache" / "smoke_output",
        )
        checkpoint_store = _hf_store(
            resolved.payload["storage"]["checkpoint"],
            cache_dir=scratch_root / ".hf_cache" / "smoke_checkpoint",
        )
        _assert_empty_smoke_namespace(output_store, effective_run_id, smoke_policy)
        _assert_empty_smoke_namespace(checkpoint_store, effective_run_id, smoke_policy)

        runtime = run_phase01_runtime_preflight(resolved, scratch_root=scratch_root)
        report["runtime"] = _runtime_payload(runtime)
        fixture_evidence = _prepare_smoke_fixture(
            release_dir=release_dir,
            batch_id=batch_id,
            policy=smoke_policy,
            scratch_root=scratch_root,
        )
        report["fixture_evidence"] = fixture_evidence
        resolved_path = persist_resolved_phase01_config(
            resolved,
            release_dir / "manifests" / "phase01" / "resolved_config.json",
        )
        report["config"]["resolved_config_path"] = str(resolved_path)
        transnet = materialize_transnet_artifact(
            model_config=resolved.payload["models"]["shot_detection"],
            storage_config=resolved.payload["storage"]["model_artifacts"],
            cache_root=scratch_root / "model_artifacts",
        )
        run_phase01_preflight(
            resolved,
            release_dir=release_dir,
            transnet_artifact_dir=transnet.root,
            scratch_root=scratch_root,
            validate_remote=True,
            runtime_result=runtime,
        )

        sampler.start()
        worker_report_path = process_production_batch(
            release_dir=release_dir,
            config=resolved,
            scratch_root=scratch_root,
            transnet_artifact_dir=transnet.root,
            sync_release=True,
        )
        sampler.stop()
        worker_report = json.loads(worker_report_path.read_text(encoding="utf-8"))
        video_result = _single_video_result(worker_report, video_id)
        sources = dict(video_result.get("stage_sources", {}))
        required_sources = dict(smoke_policy["required_stage_sources"])
        if tuple(required_sources) != _REQUIRED_STAGES:
            raise ValueError("smoke required_stage_sources does not match Phase01 stage order")
        if sources != required_sources:
            raise RuntimeError(
                "smoke did not compute every required stage: "
                f"expected={required_sources}, actual={sources}"
            )
        report["stage_sources"] = sources
        artifact_path = Path(str(video_result["artifact"]))
        report["package"] = _inspect_smoke_package(
            artifact_path,
            video_id=video_id,
            require_non_empty_asr=bool(
                smoke_policy["speech"].get("require_non_empty_asr", True)
            ),
        )
        report["worker_report"] = sanitize_payload(worker_report)
        report["status"] = "pass"
        report["ready_for_full_run"] = True
    except Exception as exc:  # noqa: BLE001 - preserve complete smoke evidence
        sampler.stop()
        recovered_worker_report = _recover_worker_report(release_dir, video_id)
        if recovered_worker_report is not None:
            report["worker_report"] = sanitize_payload(recovered_worker_report)
        report["failed_stage"] = _failure_stage(exc, report)
        report["error"] = sanitize_payload(
            {
                "error_type": type(exc).__name__,
                "message": str(exc),
                "traceback": traceback.format_exc(),
            }
        )
    finally:
        sampler.stop()
        report["resources"] = sampler.payload()
        try:
            report["resources"]["gpu_cleanup"] = _release_and_measure_gpu(
                smoke_policy["gpu_cleanup"], sampler.gpu_baseline
            )
        except Exception as exc:  # noqa: BLE001 - cleanup is part of readiness
            report["cleanup"]["gpu"] = "failed"
            report["error"] = report["error"] or sanitize_payload(
                {
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                    "traceback": traceback.format_exc(),
                }
            )
            report["failed_stage"] = report["failed_stage"] or "gpu_cleanup"
            report["status"] = "fail"
            report["ready_for_full_run"] = False
        else:
            report["cleanup"]["gpu"] = "pass"

        if not keep_artifacts:
            try:
                if output_store is not None:
                    _delete_smoke_files(
                        output_store,
                        configured_repo=str(smoke_policy["output_release"]["repo_id"]),
                        run_id=effective_run_id,
                    )
                if checkpoint_store is not None:
                    _delete_smoke_files(
                        checkpoint_store,
                        configured_repo=str(smoke_policy["checkpoint"]["repo_id"]),
                        run_id=effective_run_id,
                    )
                report["cleanup"]["remote_artifacts"] = "removed"
            except Exception as exc:  # noqa: BLE001 - requested cleanup must be safe/complete
                report["cleanup"]["remote_artifacts"] = "failed"
                report["error"] = report["error"] or sanitize_payload(
                    {"error_type": type(exc).__name__, "message": str(exc)}
                )
                report["failed_stage"] = report["failed_stage"] or "remote_cleanup"
                report["status"] = "fail"
                report["ready_for_full_run"] = False

        if cleanup_enabled:
            shutil.rmtree(smoke_root, ignore_errors=True)
            if scratch_root is not None:
                shutil.rmtree(scratch_root / release_id / batch_id, ignore_errors=True)
                for cache_name in (
                    "smoke_output",
                    "smoke_checkpoint",
                    "smoke_fixture_release",
                    "smoke_fixture_raw",
                ):
                    shutil.rmtree(
                        scratch_root / ".hf_cache" / cache_name,
                        ignore_errors=True,
                    )
            report["cleanup"]["local"] = "removed"
        else:
            report["cleanup"]["local"] = "kept"
        report["finished_at"] = utc_now()
        report["elapsed_seconds"] = round(time.monotonic() - started_monotonic, 3)
        write_json_atomic(report_path, report)
        if bool(smoke_policy.get("keep_remote_report", True)) and output_store is not None:
            try:
                remote = output_store.upload_file(
                    report_path,
                    "reports/phase01_smoke_report_v1.json",
                )
                remote_report_path = str(remote)
            except Exception as exc:  # noqa: BLE001 - report upload is evidence, not execution
                report["cleanup"]["remote_report"] = "upload_failed"
                report["remote_report_error"] = sanitize_payload(str(exc))
                write_json_atomic(report_path, report)
        _print_smoke_report(report, report_path, remote_report_path)

    result = Phase01SmokeResult(
        run_id=effective_run_id,
        ready_for_full_run=bool(report["ready_for_full_run"]),
        report_path=report_path,
        remote_report_path=remote_report_path,
    )
    if not result.ready_for_full_run:
        raise Phase01SmokeError(
            f"Phase01 smoke failed; full batch was not started. report={report_path}",
            report_path=report_path,
        )
    return result


def _smoke_policy(configs: Mapping[str, Any]) -> dict[str, Any]:
    value = configs["phase01"].get("smoke")
    if not isinstance(value, dict):
        raise ValueError("phase01.yaml is missing smoke policy")
    if value.get("schema_version") != "phase01_real_smoke_config_v1":
        raise ValueError("unsupported Phase01 smoke policy")
    required = set(_REQUIRED_STAGES)
    configured = set(dict(value.get("required_stage_sources", {})))
    if configured != required:
        raise ValueError(
            "smoke required_stage_sources mismatch: "
            f"missing={sorted(required - configured)}, extra={sorted(configured - required)}"
        )
    return copy.deepcopy(value)


def _resolve_smoke_config(
    *,
    config_dir: Path,
    production_user_settings: Mapping[str, Any],
    smoke_policy: Mapping[str, Any],
    namespace: str,
    batch_id: str,
    worker_id: str,
) -> ResolvedPhase01Config:
    source_release_id = str(smoke_policy["source_release"]["release_id"])
    production = resolve_phase01_config(
        config_dir,
        user_settings=dict(production_user_settings),
        phase00_release_id=source_release_id,
    )
    smoke_settings: dict[str, Any] = {
        "batch_id": batch_id,
        "worker_id": worker_id,
        "release_id_override": source_release_id,
        "hf_release_repo": smoke_policy["output_release"]["repo_id"],
        "hf_repo_type": smoke_policy["output_release"].get("repo_type", "dataset"),
        "hf_release_revision": smoke_policy["output_release"].get("revision", "main"),
        "hf_release_prefix": namespace,
        "hf_checkpoint_repo": smoke_policy["checkpoint"]["repo_id"],
        "checkpoint_revision": smoke_policy["checkpoint"].get("revision", "main"),
        "checkpoint_prefix": namespace,
    }
    for key in ("asr_provider", "scratch_dir"):
        if production_user_settings.get(key) is not None:
            smoke_settings[key] = production_user_settings[key]
    resolved = resolve_phase01_config(
        config_dir,
        user_settings=smoke_settings,
        phase00_release_id=source_release_id,
    )
    payload = copy.deepcopy(resolved.payload)
    payload["storage"]["model_artifacts"] = copy.deepcopy(
        production.payload["storage"]["model_artifacts"]
    )
    return rebuild_resolved_phase01_config(payload)


def _prepare_smoke_fixture(
    *,
    release_dir: Path,
    batch_id: str,
    policy: Mapping[str, Any],
    scratch_root: Path,
) -> dict[str, Any]:
    video_id = str(policy["video_id"])
    release_storage = dict(policy["source_release"])
    release_id = str(release_storage.pop("release_id"))
    source_store = _hf_store(
        release_storage,
        cache_dir=scratch_root / ".hf_cache" / "smoke_fixture_release",
    )
    selected = resolve_phase00_release(
        discover_phase00_candidates(source_store),
        release_id_override=release_id,
    )
    remote_root = phase00_ingestion_remote_prefix(release_id)
    checksums = {
        str(row["relative_path"]): str(row["sha256"])
        for row in selected.manifest.get("files", [])
        if isinstance(row, dict) and row.get("relative_path") and row.get("sha256")
    }
    relative_paths = (
        "tables/videos.parquet",
        "raw_mapping/media_store_manifest.parquet",
        str(policy["timeline"]["relative_path"]),
    )
    for relative in relative_paths:
        _download_checked(
            source_store,
            f"{remote_root}/{relative}",
            release_dir / relative,
            checksums.get(relative),
        )
    videos_path = release_dir / "tables" / "videos.parquet"
    media_path = release_dir / "raw_mapping" / "media_store_manifest.parquet"
    videos = pd.read_parquet(videos_path)
    media = pd.read_parquet(media_path)
    selected_videos = videos[videos["video_id"].astype(str) == video_id].copy()
    selected_media = media[media["video_id"].astype(str) == video_id].copy()
    if len(selected_videos) != 1 or len(selected_media) != 1:
        raise RuntimeError(
            f"smoke fixture requires exactly one mapping row for {video_id}: "
            f"videos={len(selected_videos)}, media={len(selected_media)}"
        )
    mapping_revision = _validate_mapping(
        selected_media.iloc[0].to_dict(), policy["source_raw"]
    )
    # The Phase00 test release may record the moving branch used at ingestion.
    # The isolated fixture intentionally rewrites only its local one-row clone
    # to the content-addressed raw revision qualified below.
    selected_media.loc[:, "canonical_revision"] = str(
        policy["source_raw"]["revision"]
    )
    raw_store = HuggingFaceDatasetArtifactStore(
        repo_id=str(policy["source_raw"]["repo_id"]),
        repo_type=str(policy["source_raw"].get("repo_type", "dataset")),
        revision=str(policy["source_raw"]["revision"]),
        token=source_store.token,
        prefix="",
        cache_dir=scratch_root / ".hf_cache" / "smoke_fixture_raw",
    )
    local_source = release_dir / ".smoke_sources"
    video_path = _download_checked(
        raw_store,
        str(policy["source_raw"]["video_path"]),
        local_source / f"{video_id}.mp4",
        str(policy["source_raw"]["video_sha256"]),
    )
    metadata_path = _download_checked(
        raw_store,
        str(policy["source_raw"]["metadata_path"]),
        local_source / f"{video_id}.json",
        str(policy["source_raw"]["metadata_sha256"]),
    )
    selected_media.loc[:, "video_local_path"] = str(video_path)
    selected_media.loc[:, "metadata_local_path"] = str(metadata_path)
    selected_videos.to_parquet(videos_path, index=False)
    selected_media.to_parquet(media_path, index=False)
    timeline_path = release_dir / str(policy["timeline"]["relative_path"])
    expected_timeline = str(policy["timeline"]["sha256"])
    if sha256_file(timeline_path) != expected_timeline:
        raise ValueError("smoke timeline checksum does not match the pinned fixture")
    timeline = pd.read_parquet(timeline_path)
    frame_id = int(policy["timeline"]["vlm_frame_id"])
    pts_time = float(policy["timeline"]["vlm_pts_time"])
    rows = timeline[timeline["frame_id"].astype(int) == frame_id]
    if len(rows) != 1 or abs(float(rows.iloc[0]["pts_time"]) - pts_time) > 1e-6:
        raise RuntimeError("smoke timeline does not contain the pinned VLM frame/timestamp")
    manifest_path = release_dir / "manifests" / f"{batch_id}.txt"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(f"{video_id}\n", encoding="utf-8")
    return {
        "release_revision": release_storage["revision"],
        "release_manifest_path": selected.manifest_path,
        "mapping_revision": mapping_revision,
        "execution_raw_revision": str(policy["source_raw"]["revision"]),
        "video_sha256": sha256_file(video_path),
        "metadata_sha256": sha256_file(metadata_path),
        "timeline_sha256": sha256_file(timeline_path),
        "timeline_rows": len(timeline),
        "vlm_frame_id": frame_id,
        "vlm_pts_time": pts_time,
        "speech_start_sec": float(policy["speech"]["start_sec"]),
        "speech_end_sec": float(policy["speech"]["end_sec"]),
    }


def _download_checked(
    store: HuggingFaceDatasetArtifactStore,
    remote_path: str,
    target: Path,
    expected_sha256: str | None,
) -> Path:
    store.download_file(remote_path, target)
    if expected_sha256 and sha256_file(target) != expected_sha256:
        raise ValueError(f"smoke fixture checksum mismatch: {remote_path}")
    return target


def _validate_mapping(mapping: Mapping[str, Any], raw: Mapping[str, Any]) -> str:
    if str(mapping.get("canonical_repo_id")) != str(raw["repo_id"]):
        raise RuntimeError("smoke mapping points at an unexpected raw repository")
    mapping_revision = str(mapping.get("canonical_revision") or "").strip()
    if not mapping_revision:
        raise RuntimeError("smoke mapping has no canonical raw revision")
    prefix = str(mapping.get("canonical_prefix") or "").strip("/")
    video = str(mapping.get("canonical_video_path") or "").strip("/")
    metadata = str(mapping.get("canonical_metadata_path") or "").strip("/")
    joined_video = "/".join(value for value in (prefix, video) if value)
    joined_metadata = "/".join(value for value in (prefix, metadata) if value)
    if joined_video != str(raw["video_path"]).strip("/"):
        raise RuntimeError("smoke mapping points at an unexpected canonical video")
    if joined_metadata != str(raw["metadata_path"]).strip("/"):
        raise RuntimeError("smoke mapping points at unexpected canonical metadata")
    return mapping_revision


def _inspect_smoke_package(
    artifact_path: Path,
    *,
    video_id: str,
    require_non_empty_asr: bool,
) -> dict[str, Any]:
    artifact_manifest = validate_artifact_zip(artifact_path)
    with zipfile.ZipFile(artifact_path) as archive:
        manifest = json.loads(archive.read(f"{video_id}/manifest.json"))
        counts = {str(key): int(value) for key, value in manifest["counts"].items()}
        required_non_empty = {
            "shots",
            "keyframes",
            "ocr",
            "shot_captions",
            "shot_transcript_links",
            "scenes",
            "scene_summaries",
        }
        if require_non_empty_asr:
            required_non_empty.add("asr_segments")
        empty = sorted(name for name in required_non_empty if counts.get(name, 0) < 1)
        if empty:
            raise RuntimeError(f"smoke package has empty required outputs: {empty}")
        samples = {
            "asr": _parquet_sample(
                archive,
                video_id,
                "asr_segments.parquet",
                preferred_text_fields=("text",),
                require_text=require_non_empty_asr,
            ),
            "ocr": _parquet_sample(
                archive,
                video_id,
                "ocr.parquet",
                preferred_text_fields=("text", "raw_text"),
                require_text=True,
            ),
            "shot_caption": _parquet_sample(
                archive,
                video_id,
                "shot_captions.parquet",
                preferred_text_fields=("caption_vi", "caption_en"),
                require_text=True,
            ),
            "scene_summary": _parquet_sample(
                archive,
                video_id,
                "scene_summaries.parquet",
                preferred_text_fields=("summary_vi", "summary_en"),
                require_text=True,
            ),
        }
    return {
        "path": str(artifact_path),
        "sha256": sha256_file(artifact_path),
        "size_bytes": artifact_path.stat().st_size,
        "validation": "pass",
        "artifact_manifest": artifact_manifest,
        "row_counts": counts,
        "samples": samples,
        "remote_checksum": "pass",
    }


def _parquet_sample(
    archive: zipfile.ZipFile,
    video_id: str,
    filename: str,
    *,
    preferred_text_fields: tuple[str, ...] = (),
    require_text: bool = False,
) -> dict[str, Any] | None:
    frame = pd.read_parquet(io.BytesIO(archive.read(f"{video_id}/{filename}")))
    if frame.empty:
        return None
    records = frame.to_dict("records")
    row = records[0]
    if preferred_text_fields:
        selected = next(
            (
                candidate
                for candidate in records
                if any(
                    str(candidate.get(field) or "").strip()
                    for field in preferred_text_fields
                )
            ),
            None,
        )
        if selected is None:
            if require_text:
                raise RuntimeError(
                    f"smoke output {filename} has no non-empty model text"
                )
        else:
            row = selected
    return sanitize_payload(
        {
            str(key): _json_scalar(value)
            for key, value in row.items()
            if not isinstance(value, (bytes, bytearray))
        }
    )


def _single_video_result(worker_report: Mapping[str, Any], video_id: str) -> dict[str, Any]:
    videos = worker_report.get("videos", [])
    matches = [row for row in videos if str(row.get("video_id")) == video_id]
    if len(matches) != 1:
        raise RuntimeError("smoke worker report does not contain exactly one video")
    result = dict(matches[0])
    if str(result.get("status")) != "complete":
        raise RuntimeError(f"smoke video did not complete: {result}")
    return result


def _recover_worker_report(
    release_dir: Path, video_id: str
) -> dict[str, Any] | None:
    report_root = release_dir / "manifests" / "worker_reports"
    if not report_root.is_dir():
        return None
    candidates = sorted(
        report_root.glob("structure_smoke_*.json"),
        key=lambda path: path.stat().st_mtime_ns,
        reverse=True,
    )
    for path in candidates:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        videos = payload.get("videos", [])
        if any(str(row.get("video_id")) == video_id for row in videos):
            return payload
    return None


def _assert_empty_smoke_namespace(
    store: HuggingFaceDatasetArtifactStore,
    run_id: str,
    policy: Mapping[str, Any],
) -> None:
    expected = _smoke_namespace(policy, run_id)
    if store.prefix != expected:
        raise ValueError(f"unsafe smoke prefix: {store.prefix!r} != {expected!r}")
    existing = store.list_files("")
    if existing:
        raise RuntimeError(
            f"smoke namespace collision at {store.repo_id}/{store.prefix}: {existing[:10]}"
        )


def _delete_smoke_files(
    store: HuggingFaceDatasetArtifactStore,
    *,
    configured_repo: str,
    run_id: str,
) -> None:
    expected_prefix = f"_smoke/{run_id}"
    if not run_id or store.repo_id != configured_repo or store.prefix != expected_prefix:
        raise ValueError("refusing unsafe remote smoke deletion")
    files = store.list_files("")
    exact: list[str] = []
    for path in files:
        normalized = PurePosixPath(path.as_posix())
        if normalized.is_absolute() or ".." in normalized.parts or not normalized.parts:
            raise ValueError(f"refusing unsafe remote smoke path: {path}")
        exact.append(normalized.as_posix())
    if exact:
        store.sync_files(
            [],
            delete_paths=exact,
            commit_message=f"Delete isolated Phase01 smoke artifacts {run_id}",
            num_threads=2,
        )


def _smoke_namespace(policy: Mapping[str, Any], run_id: str) -> str:
    root = str(policy.get("namespace_root", "_smoke")).strip("/")
    if root != "_smoke":
        raise ValueError("Phase01 smoke namespace_root must be _smoke")
    return f"{root}/{run_id}"


def _validate_run_id(value: str) -> None:
    if (
        not value
        or value != value.strip()
        or value in {".", ".."}
        or any(separator in value for separator in ("/", "\\"))
        or any(ord(character) < 32 for character in value)
    ):
        raise ValueError("smoke run_id must be a non-empty path-safe identifier")


def _runtime_payload(result: RuntimePreflightResult) -> dict[str, Any]:
    return {
        "environment": result.environment,
        "python": result.versions.get("python"),
        "cuda_available": result.cuda_available,
        "scratch_free_gb": result.scratch_free_gb,
        "model_cache_free_gb": result.model_cache_free_gb,
        "versions": dict(result.versions),
    }


def _provider_identity(config: ResolvedPhase01Config) -> dict[str, Any]:
    models = config.payload["models"]
    return {
        key: {
            "provider": value.get("provider"),
            "model_id": value.get("model_id"),
            "model_revision": value.get("model_revision"),
        }
        for key, value in models.items()
        if isinstance(value, dict) and value.get("provider")
    }


def _failure_stage(exc: Exception, report: Mapping[str, Any]) -> str:
    worker = report.get("worker_report")
    if isinstance(worker, Mapping):
        videos = worker.get("videos")
        if isinstance(videos, list) and videos:
            value = videos[0].get("failed_stage")
            if value:
                return str(value)
    if isinstance(exc, (FileNotFoundError, ValueError)):
        return "fixture_or_preflight"
    return "smoke_execution"


def _release_and_measure_gpu(
    policy: Mapping[str, Any], baseline: Mapping[str, int] | None
) -> dict[str, Any]:
    gc.collect()
    try:
        import torch
    except ImportError:
        return {"available": False, "status": "not_applicable"}
    if not torch.cuda.is_available():
        return {"available": False, "status": "not_applicable"}
    torch.cuda.empty_cache()
    ipc_collect = getattr(torch.cuda, "ipc_collect", None)
    if callable(ipc_collect):
        ipc_collect()
    post = {
        "allocated_bytes": int(torch.cuda.memory_allocated()),
        "reserved_bytes": int(torch.cuda.memory_reserved()),
    }
    base = dict(baseline or {"allocated_bytes": 0, "reserved_bytes": 0})
    limits = {
        "allocated_bytes": int(base.get("allocated_bytes", 0))
        + int(policy["allocated_tolerance_bytes"]),
        "reserved_bytes": int(base.get("reserved_bytes", 0))
        + int(policy["reserved_tolerance_bytes"]),
    }
    if post["allocated_bytes"] > limits["allocated_bytes"]:
        raise RuntimeError(f"GPU allocated memory remained above cleanup tolerance: {post}")
    if post["reserved_bytes"] > limits["reserved_bytes"]:
        raise RuntimeError(f"GPU reserved memory remained above cleanup tolerance: {post}")
    return {"available": True, "status": "pass", "baseline": base, "post": post, "limits": limits}


class _ResourceSampler:
    def __init__(self) -> None:
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.peak_ram_bytes = 0
        self.peak_vram_allocated_bytes = 0
        self.peak_vram_reserved_bytes = 0
        self.gpu_baseline: dict[str, int] | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self.gpu_baseline = self._gpu()
        self._sample()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None
        self._sample()

    def _run(self) -> None:
        while not self._stop.wait(0.5):
            self._sample()

    def _sample(self) -> None:
        try:
            import psutil

            self.peak_ram_bytes = max(
                self.peak_ram_bytes,
                int(psutil.Process().memory_info().rss),
            )
        except (ImportError, OSError):
            pass
        gpu = self._gpu()
        if gpu is not None:
            self.peak_vram_allocated_bytes = max(
                self.peak_vram_allocated_bytes, gpu["allocated_bytes"]
            )
            self.peak_vram_reserved_bytes = max(
                self.peak_vram_reserved_bytes, gpu["reserved_bytes"]
            )

    @staticmethod
    def _gpu() -> dict[str, int] | None:
        try:
            import torch
        except ImportError:
            return None
        if not torch.cuda.is_available():
            return None
        return {
            "allocated_bytes": int(torch.cuda.memory_allocated()),
            "reserved_bytes": int(torch.cuda.memory_reserved()),
        }

    def payload(self) -> dict[str, Any]:
        return {
            "peak_ram_bytes": self.peak_ram_bytes,
            "peak_vram_allocated_bytes": self.peak_vram_allocated_bytes,
            "peak_vram_reserved_bytes": self.peak_vram_reserved_bytes,
        }


def _json_scalar(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, Mapping):
        return {
            str(key): _json_scalar(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_json_scalar(item) for item in value]
    to_list = getattr(value, "tolist", None)
    if callable(to_list):
        converted = to_list()
        if converted is not value:
            return _json_scalar(converted)
    item = getattr(value, "item", None)
    if callable(item):
        value = item()
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def _print_smoke_report(
    report: Mapping[str, Any],
    report_path: Path,
    remote_report_path: str | None,
) -> None:
    sources = report.get("stage_sources", {})
    print("=" * 60)
    print("PHASE01 REAL PROVIDER SMOKE")
    print("=" * 60)
    print(f"video_id: {report.get('video_id')}")
    print(f"run_id: {report.get('run_id')}")
    runtime = report.get("runtime", {})
    print(f"python: {runtime.get('python')}")
    print(f"cuda: {'PASS' if runtime.get('cuda_available') else 'FAIL'}")
    for stage in _REQUIRED_STAGES:
        source = sources.get(stage, "missing")
        print(f"{stage:28} {'PASS' if source == 'computed' else 'FAIL'} ({source})")
    package = report.get("package", {})
    print(f"package validation: {str(package.get('validation', 'fail')).upper()}")
    print(f"local report: {report_path}")
    if remote_report_path:
        print(f"remote report: {remote_report_path}")
    print(f"READY FOR FULL RUN: {'YES' if report.get('ready_for_full_run') else 'NO'}")
    if report.get("error"):
        error = report["error"]
        if isinstance(error, Mapping):
            print(f"error: {error.get('error_type')}: {error.get('message')}")
        else:
            print(f"error: {error}")
    print("=" * 60, flush=True)
