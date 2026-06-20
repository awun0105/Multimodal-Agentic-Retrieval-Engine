from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from typing import Any

from system1.artifacts.hf_store import HuggingFaceDatasetArtifactStore

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".wav"}
METADATA_EXTENSIONS = {".json"}
VIDEO_DIR_NAMES = {"raw_videos", "videos", "video", "raw", "clips"}
METADATA_DIR_NAMES = {"metadata", "metadatas", "json", "annotations"}
GENERIC_CONTEXT_NAMES = VIDEO_DIR_NAMES | METADATA_DIR_NAMES | {"dataset", "train", "val", "test", "data"}
STANDARDIZE_TEMP_PREFIXES = ("member_stage_", "member_extract_", "archive_stage_", "source_stage_")
BYTES_PER_GB = 1024 ** 3
RAW_UPLOAD_BATCH_SIZE = 50
RAW_UPLOAD_MAX_RETRIES = 5
RAW_UPLOAD_RATE_LIMIT_DEFAULT_SLEEP_SECONDS = 120


@dataclass(frozen=True)
class SourceImportResult:
    video_count: int
    metadata_count: int
    report_path: Path


@dataclass(frozen=True)
class CanonicalRawUploadResult:
    video_count: int
    metadata_count: int
    error_count: int
    manifest_path: str
    report_path: str


@dataclass(frozen=True)
class DriveShadowResult:
    source_folder_id: str
    dest_folder_id: str
    copied_files: int
    created_folders: int
    skipped_google_apps: int
    skipped_existing: int
    error_count: int
    report_path: Path


@dataclass(frozen=True)
class ArchiveStandardizeResult:
    zip_count: int
    video_count: int
    metadata_count: int
    skipped_count: int
    error_count: int
    report_path: Path


@dataclass(frozen=True)
class _StandardizeCandidate:
    kind: str
    source_mode: str
    source_path: str
    actual_path: Path | None
    relative_path: Path
    original_stem: str
    extension: str
    context_parts: tuple[str, ...]
    group_key: tuple[str, ...]
    archive_stem: str | None = None
    zip_path: Path | None = None
    zip_member: str | None = None


@dataclass(frozen=True)
class _StandardizeSourceItem:
    source_id: str
    source_mode: str
    source_path: Path
    display_path: str
    candidates: tuple[_StandardizeCandidate, ...]
    skipped_rows: tuple[dict[str, Any], ...] = ()


@dataclass
class _RawUploadItem:
    kind: str
    video_id: str
    local_path: Path
    remote_path: str
    index: int
    total: int
    size_bytes: int
    status: str = "pending"
    error: str | None = None


def import_organizer_source(source_uri: str, data_root: Path | str) -> SourceImportResult:
    if not source_uri:
        raise ValueError("source_uri is required. Set AIC_ORGANIZER_SOURCE_URI before running notebook 00.")
    root = Path(data_root)
    raw_root = root / "raw_videos"
    metadata_root = root / "metadata"
    _reset_import_targets(root, raw_root, metadata_root)
    raw_root.mkdir(parents=True, exist_ok=True)
    metadata_root.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="system1_source_import_") as tmp:
        source_root = _materialize_source(source_uri, Path(tmp))
        video_files = _find_video_files(source_root)
        metadata_files = _find_metadata_files(source_root)
        video_by_stem = _index_unique_by_stem(video_files, kind="video")
        metadata_by_stem = _index_unique_by_stem(metadata_files, kind="metadata")
        imported: list[dict[str, str]] = []
        for video_id, video_path in video_by_stem.items():
            video_target = raw_root / video_path.name
            _copy_file(video_path, video_target)
            imported.append({"video_id": video_id, "kind": "video", "source": str(video_path), "target": str(video_target)})
            metadata_path = metadata_by_stem.get(video_id)
            metadata_target = metadata_root / f"{video_id}.json"
            if metadata_path:
                _copy_file(metadata_path, metadata_target)
                imported.append({"video_id": video_id, "kind": "metadata", "source": str(metadata_path), "target": str(metadata_target)})
            else:
                _write_minimal_metadata(metadata_target, video_id, source_uri)
                imported.append({"video_id": video_id, "kind": "metadata_generated", "source": source_uri, "target": str(metadata_target)})

    _validate_pairing(raw_root, metadata_root)
    report = {
        "status": "pass",
        "source_uri": source_uri,
        "data_root": str(root),
        "raw_videos": str(raw_root),
        "metadata": str(metadata_root),
        "imported": imported,
    }
    report_path = root / "organizer_import_report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return SourceImportResult(
        video_count=len(video_by_stem),
        metadata_count=len(list(metadata_root.glob("*.json"))),
        report_path=report_path,
    )


def shadow_google_drive_folder(
    source_folder_id: str,
    dest_folder_id: str,
    *,
    report_path: Path | str = "drive_shadow_report.json",
    service: Any | None = None,
) -> DriveShadowResult:
    """Copy regular files/folders from one Google Drive folder to another.

    Google-native Docs/Sheets/Slides files are skipped because the downstream
    dataset pipeline expects ordinary media/archive/JSON files.
    """
    if not source_folder_id:
        raise ValueError("source_folder_id is required")
    if not dest_folder_id:
        raise ValueError("dest_folder_id is required")

    resolved_report_path = Path(report_path).expanduser().resolve()
    rows: list[dict[str, Any]] = []
    counters = {
        "copied_files": 0,
        "created_folders": 0,
        "skipped_google_apps": 0,
        "skipped_existing": 0,
        "error_count": 0,
    }
    source_folder_name: str | None = None
    dest_folder_name: str | None = None
    fatal_error: str | None = None
    root_child_count: int | None = None

    print(
        "[drive-shadow] "
        f"source_folder_id={source_folder_id} dest_folder_id={dest_folder_id} "
        f"report_path={resolved_report_path}",
        flush=True,
    )

    def copy_folder_contents(source_id: str, target_id: str, logical_path: str = "") -> None:
        nonlocal root_child_count
        source_children = _list_drive_children(drive_service, source_id)
        if logical_path == "":
            root_child_count = len(source_children)
        print(f"[drive-shadow] listing path={logical_path or '/'} items={len(source_children)}", flush=True)
        source_children_by_name = _group_drive_children_by_name(source_children)
        target_children_by_name = _group_drive_children_by_name(_list_drive_children(drive_service, target_id))
        for item in source_children:
            item_name = str(item.get("name", ""))
            item_id = str(item.get("id", ""))
            mime_type = str(item.get("mimeType", ""))
            item_path = f"{logical_path}/{item_name}".strip("/")
            if len(source_children_by_name.get(item_name, [])) > 1:
                counters["error_count"] += 1
                rows.append({"kind": "source_conflict", "source_id": item_id, "name": item_name, "path": item_path, "status": "failed", "error": "multiple source entries with the same name"})
                continue
            existing_targets = target_children_by_name.get(item_name, [])
            if len(existing_targets) > 1:
                counters["error_count"] += 1
                rows.append({"kind": "target_conflict", "source_id": item_id, "name": item_name, "path": item_path, "status": "failed", "error": "multiple target entries with the same name"})
                continue
            existing_target = existing_targets[0] if existing_targets else None
            if mime_type == "application/vnd.google-apps.folder":
                if existing_target is not None:
                    if existing_target.get("mimeType") != "application/vnd.google-apps.folder":
                        counters["error_count"] += 1
                        rows.append({"kind": "folder", "source_id": item_id, "name": item_name, "path": item_path, "status": "failed", "error": "target entry exists with a non-folder mimeType"})
                        continue
                    counters["skipped_existing"] += 1
                    rows.append({"kind": "folder", "source_id": item_id, "target_id": existing_target.get("id"), "name": item_name, "path": item_path, "status": "skipped_existing"})
                    print(f"[drive-shadow] skipped existing: {item_path}", flush=True)
                    copy_folder_contents(item_id, str(existing_target["id"]), item_path)
                    continue
                folder_metadata = {
                    "name": item_name,
                    "mimeType": "application/vnd.google-apps.folder",
                    "parents": [target_id],
                }
                try:
                    new_folder = drive_service.files().create(
                        body=folder_metadata,
                        fields="id",
                        supportsAllDrives=True,
                    ).execute()
                    counters["created_folders"] += 1
                    rows.append({"kind": "folder", "source_id": item_id, "target_id": new_folder.get("id"), "name": item_name, "path": item_path, "status": "created"})
                    print(f"[drive-shadow] created folder: {item_path}", flush=True)
                    copy_folder_contents(item_id, str(new_folder["id"]), item_path)
                except Exception as exc:
                    counters["error_count"] += 1
                    rows.append({"kind": "folder", "source_id": item_id, "name": item_name, "path": item_path, "status": "failed", "error": str(exc)})
                    print(f"[drive-shadow] error creating folder: {item_path}: {exc}", flush=True)
                continue

            if mime_type.startswith("application/vnd.google-apps"):
                counters["skipped_google_apps"] += 1
                rows.append({"kind": "google_app", "source_id": item_id, "name": item_name, "path": item_path, "status": "skipped"})
                print(f"[drive-shadow] skipped google app: {item_path}", flush=True)
                continue

            if existing_target is not None:
                existing_mime_type = str(existing_target.get("mimeType", ""))
                if existing_mime_type == "application/vnd.google-apps.folder" or existing_mime_type.startswith("application/vnd.google-apps"):
                    counters["error_count"] += 1
                    rows.append({"kind": "file", "source_id": item_id, "name": item_name, "path": item_path, "status": "failed", "error": "target entry exists with an incompatible mimeType"})
                    continue
                if _drive_file_sizes_match(item, existing_target):
                    counters["skipped_existing"] += 1
                    rows.append({"kind": "file", "source_id": item_id, "target_id": existing_target.get("id"), "name": item_name, "path": item_path, "status": "skipped_existing"})
                    print(f"[drive-shadow] skipped existing: {item_path}", flush=True)
                    continue
                counters["error_count"] += 1
                rows.append({"kind": "file", "source_id": item_id, "name": item_name, "path": item_path, "status": "failed", "error": "target file exists but size does not match source"})
                continue

            copy_metadata = {"name": item_name, "parents": [target_id]}
            try:
                copied_file = drive_service.files().copy(
                    fileId=item_id,
                    body=copy_metadata,
                    supportsAllDrives=True,
                ).execute()
                counters["copied_files"] += 1
                rows.append({"kind": "file", "source_id": item_id, "target_id": copied_file.get("id"), "name": item_name, "path": item_path, "status": "copied"})
                print(f"[drive-shadow] copied: {item_path}", flush=True)
            except Exception as exc:
                counters["error_count"] += 1
                rows.append({"kind": "file", "source_id": item_id, "name": item_name, "path": item_path, "status": "failed", "error": str(exc)})
                print(f"[drive-shadow] error copying file: {item_path}: {exc}", flush=True)

    try:
        drive_service = service or _build_google_drive_service()
        source_metadata = _get_drive_folder_metadata(drive_service, source_folder_id, "source")
        dest_metadata = _get_drive_folder_metadata(drive_service, dest_folder_id, "destination")
        source_folder_name = str(source_metadata.get("name", ""))
        dest_folder_name = str(dest_metadata.get("name", ""))
        copy_folder_contents(source_folder_id, dest_folder_id)
    except Exception as exc:
        fatal_error = str(exc)
        counters["error_count"] += 1
        rows.append({"kind": "fatal_error", "status": "failed", "error": fatal_error})
        print(f"[drive-shadow] fatal error: {fatal_error}", flush=True)
    finally:
        action_count = (
            counters["copied_files"]
            + counters["created_folders"]
            + counters["skipped_existing"]
            + counters["skipped_google_apps"]
        )
        if root_child_count == 0:
            counters["error_count"] += 1
            rows.append(
                {
                    "kind": "source_empty_or_not_listable",
                    "status": "failed",
                    "error": "source folder has no visible children or cannot be listed",
                }
            )
        elif action_count == 0:
            counters["error_count"] += 1
            rows.append(
                {
                    "kind": "no_action",
                    "status": "failed",
                    "error": "drive shadow completed without copying, creating, skipping existing, or skipping google-app items",
                }
            )
        status = "pass" if counters["error_count"] == 0 else ("partial" if action_count > 0 else "fail")
        report = {
            "status": status,
            "source_folder_id": source_folder_id,
            "dest_folder_id": dest_folder_id,
            "source_folder_name": source_folder_name,
            "dest_folder_name": dest_folder_name,
            "fatal_error": fatal_error,
            **counters,
            "items": rows,
        }
        resolved_report_path.parent.mkdir(parents=True, exist_ok=True)
        resolved_report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(
            "[drive-shadow] completed "
            f"files_copied={counters['copied_files']} folders_created={counters['created_folders']} "
            f"skipped_existing={counters['skipped_existing']} skipped_google_apps={counters['skipped_google_apps']} "
            f"errors={counters['error_count']} report_path={resolved_report_path}",
            flush=True,
        )
    return DriveShadowResult(
        source_folder_id=source_folder_id,
        dest_folder_id=dest_folder_id,
        copied_files=counters["copied_files"],
        created_folders=counters["created_folders"],
        skipped_google_apps=counters["skipped_google_apps"],
        skipped_existing=counters["skipped_existing"],
        error_count=counters["error_count"],
        report_path=resolved_report_path,
    )


def standardize_archive_source(
    source_dir: Path | str,
    target_dir: Path | str,
    *,
    temp_dir: Path | str | None = None,
    media_extensions: set[str] | None = None,
    overwrite: bool = False,
    resume: bool = True,
    progress_path: Path | str | None = None,
    min_free_gb: float = 15.0,
    drive_sync_sleep_seconds: int = 30,
    cleanup_every_files: int = 1,
    cleanup_every_gb: float = 50.0,
) -> ArchiveStandardizeResult:
    """Normalize archives, existing layouts, and loose files into System 1 input layout."""
    source_root = Path(source_dir).expanduser().resolve()
    target_root = Path(target_dir).expanduser().resolve()
    if not source_root.exists() or not source_root.is_dir():
        raise FileNotFoundError(f"archive source directory does not exist: {source_root}")

    raw_root = target_root / "raw_videos"
    metadata_root = target_root / "metadata"
    temp_root = Path(temp_dir).expanduser().resolve() if temp_dir else target_root / ".tmp_archive_extract"
    if _is_colab_drive_path(temp_root):
        raise ValueError(
            "standardize temp_dir must be local scratch, not Google Drive mount: "
            f"{temp_root}. Use --temp-dir /content/aic_scratch on Colab."
        )
    resolved_progress_path = Path(progress_path).expanduser().resolve() if progress_path else target_root / "standardize_progress.jsonl"
    raw_root.mkdir(parents=True, exist_ok=True)
    metadata_root.mkdir(parents=True, exist_ok=True)
    temp_root.mkdir(parents=True, exist_ok=True)
    resolved_progress_path.parent.mkdir(parents=True, exist_ok=True)
    disk_manager = _StandardizeDiskManager(
        temp_root=temp_root,
        min_free_gb=min_free_gb,
        sleep_seconds=drive_sync_sleep_seconds,
        cleanup_every_files=cleanup_every_files,
        cleanup_every_gb=cleanup_every_gb,
    )

    accepted_media_extensions = {ext.lower() for ext in (media_extensions or VIDEO_EXTENSIONS)}
    rows: list[dict[str, Any]] = []
    counters = {
        "zip_count": 0,
        "video_count": 0,
        "metadata_count": 0,
        "skipped_count": 0,
        "error_count": 0,
    }
    resume_records = _read_standardize_progress(resolved_progress_path) if resume else {}
    progress_stats = {
        "source_item_count": 0,
        "processed_count": 0,
        "skipped_completed_count": 0,
        "failed_count": 0,
    }

    print(
        "[standardize] "
        f"source_dir={source_root} target_dir={target_root} temp_dir={temp_root} "
        f"overwrite={overwrite} resume={resume} progress_path={resolved_progress_path} "
        f"min_free_gb={min_free_gb} drive_sync_sleep_seconds={drive_sync_sleep_seconds} "
        f"cleanup_every_files={cleanup_every_files} cleanup_every_gb={cleanup_every_gb} "
        f"media_extensions={sorted(accepted_media_extensions)}",
        flush=True,
    )

    zip_paths, non_zip_candidates = _discover_standardize_files(
        source_root,
        target_root,
        temp_root,
        accepted_media_extensions,
    )
    counters["zip_count"] = len(zip_paths)
    print(f"[standardize] discovered zip_files={len(zip_paths)}", flush=True)
    print(
        "[standardize] discovered non_zip "
        f"media={sum(1 for candidate in non_zip_candidates if candidate.kind == 'media')} "
        f"metadata={sum(1 for candidate in non_zip_candidates if candidate.kind == 'metadata')}",
        flush=True,
    )

    zip_candidates: list[_StandardizeCandidate] = []
    zip_skipped_by_path: dict[Path, list[dict[str, Any]]] = {}
    discovery_failed_zip_paths: set[Path] = set()
    completed_zip_paths: set[Path] = set()
    for index, zip_path in enumerate(zip_paths, start=1):
        source_id = _standardize_source_id("zip", zip_path, source_root)
        completed_record = resume_records.get(source_id)
        if resume and _standardize_progress_record_completed(completed_record):
            targets = [target for target in completed_record.get("targets", []) if target]
            completed_zip_paths.add(zip_path)
            progress_stats["skipped_completed_count"] += 1
            counters["skipped_count"] += len(targets)
            rows.append(
                {
                    "kind": "source_item",
                    "source_mode": "zip",
                    "source": str(zip_path),
                    "source_id": source_id,
                    "status": "skipped_completed",
                    "targets": targets,
                }
            )
            print(f"[standardize] skipped completed zip from progress: {zip_path}", flush=True)
            continue
        print(f"[standardize] discovering zip [{index}/{len(zip_paths)}]: {zip_path}", flush=True)
        try:
            discovered, skipped = _discover_zip_candidates(zip_path, source_root, accepted_media_extensions)
            zip_candidates.extend(discovered)
            zip_skipped_by_path[zip_path] = skipped
        except (OSError, zipfile.BadZipFile, ValueError) as exc:
            discovery_failed_zip_paths.add(zip_path)
            counters["error_count"] += 1
            error_row = {"source_mode": "zip", "kind": "archive", "source": str(zip_path), "status": "failed", "error": str(exc)}
            rows.append(error_row)
            progress_stats["processed_count"] += 1
            progress_stats["failed_count"] += 1
            _append_standardize_progress(
                resolved_progress_path,
                _standardize_source_id("zip", zip_path, source_root),
                zip_path,
                "zip",
                "failed",
                [],
                {"error": f"{type(exc).__name__}: {exc}", "started_at": _utc_now_iso(), "finished_at": _utc_now_iso()},
            )

    candidates = [*non_zip_candidates, *zip_candidates]
    progress_stats["source_item_count"] = len(completed_zip_paths) + len(discovery_failed_zip_paths)
    try:
        canonical_by_group, rename_reason_by_group = _assign_canonical_stems(candidates)
    except ValueError as exc:
        counters["error_count"] += 1
        rows.append({"kind": "canonical_stem", "status": "failed", "error": str(exc)})
        canonical_by_group = {}
        rename_reason_by_group = {}

    if canonical_by_group:
        source_items = _build_standardize_source_items(
            zip_paths,
            zip_candidates,
            zip_skipped_by_path,
            non_zip_candidates,
            source_root,
            discovery_failed_zip_paths,
        )
        progress_stats["source_item_count"] = len(source_items) + len(discovery_failed_zip_paths) + len(completed_zip_paths)
        pending_count = 0
        for item in source_items:
            planned_targets = _planned_targets_for_source_item(item, raw_root, metadata_root, canonical_by_group)
            if resume and _standardize_item_completed(resume_records.get(item.source_id), planned_targets):
                progress_stats["skipped_completed_count"] += 1
                counters["skipped_count"] += len(planned_targets)
                rows.append(
                    {
                        "kind": "source_item",
                        "source_mode": item.source_mode,
                        "source": item.display_path,
                        "source_id": item.source_id,
                        "status": "skipped_completed",
                        "targets": [str(target) for target in planned_targets],
                    }
                )
                continue
            pending_count += 1
            progress_stats["processed_count"] += 1
            _process_standardize_source_item(
                item,
                raw_root,
                metadata_root,
                temp_root,
                canonical_by_group,
                rename_reason_by_group,
                overwrite,
                counters,
                rows,
                resolved_progress_path,
                disk_manager,
            )
            last_record = _read_standardize_progress(resolved_progress_path).get(item.source_id)
            if last_record and last_record.get("status") == "failed":
                progress_stats["failed_count"] += 1
        if pending_count == 0 and source_items:
            print("No pending source items. All source items already standardized.", flush=True)
    elif completed_zip_paths and counters["error_count"] == 0:
        print("No pending source items. All source items already standardized.", flush=True)

    _generate_missing_metadata(raw_root, metadata_root, source_root, counters, rows, accepted_media_extensions)
    _report_extra_metadata(raw_root, metadata_root, rows, accepted_media_extensions)
    validation_error: ValueError | None = None
    try:
        _validate_pairing(raw_root, metadata_root)
    except ValueError as exc:
        validation_error = exc
        counters["error_count"] += 1
        rows.append({"kind": "pairing_validation", "status": "failed", "error": str(exc)})

    report = {
        "status": "pass" if counters["error_count"] == 0 else "partial",
        "source_dir": str(source_root),
        "target_dir": str(target_root),
        "raw_videos": str(raw_root),
        "metadata": str(metadata_root),
        "media_extensions": sorted(accepted_media_extensions),
        "resume": resume,
        "progress_path": str(resolved_progress_path),
        "min_free_gb": min_free_gb,
        "drive_sync_sleep_seconds": drive_sync_sleep_seconds,
        "cleanup_every_files": cleanup_every_files,
        "cleanup_every_gb": cleanup_every_gb,
        **progress_stats,
        **counters,
        "items": rows,
    }
    report_path = target_root / "standardize_archives_report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        "[standardize] completed "
        f"video_count={counters['video_count']} metadata_count={counters['metadata_count']} "
        f"skipped_count={counters['skipped_count']} error_count={counters['error_count']} "
        f"report_path={report_path}",
        flush=True,
    )
    if temp_root.exists() and not temp_dir:
        shutil.rmtree(temp_root, ignore_errors=True)
    if validation_error is not None:
        raise ValueError(f"standardized input pairing validation failed: {validation_error}; report: {report_path}") from validation_error
    return ArchiveStandardizeResult(report_path=report_path, **counters)


def wait_for_drive_sync(
    *,
    min_free_gb: float = 15.0,
    sleep_seconds: int = 30,
    path: str | Path = "/",
) -> None:
    """
    Pause when free disk is low so DriveFS has time to upload and clear cache.
    Used on Google Colab when writing large files to /content/drive.
    """
    while True:
        _total, _used, free = shutil.disk_usage(str(path))
        free_gb = free / BYTES_PER_GB

        if free_gb >= min_free_gb:
            return

        print(
            f"[Drive Cache Manager] Free disk is low: "
            f"{free_gb:.2f}GB < {min_free_gb:.2f}GB. "
            f"Running sync and sleeping {sleep_seconds}s...",
            flush=True,
        )
        os.system("sync")
        time.sleep(sleep_seconds)


@dataclass
class _StandardizeDiskManager:
    temp_root: Path
    min_free_gb: float = 15.0
    sleep_seconds: int = 30
    cleanup_every_files: int = 1
    cleanup_every_gb: float = 50.0
    processed_files: int = 0
    processed_bytes: int = 0
    _since_cleanup_files: int = 0
    _since_cleanup_bytes: int = 0

    def before_file(self, size_bytes: int, label: str) -> None:
        wait_for_drive_sync(min_free_gb=self.min_free_gb, sleep_seconds=self.sleep_seconds, path=self.temp_root)
        _ensure_temp_disk_available(self.temp_root, size_bytes, self.min_free_gb, label)

    def after_file(self, size_bytes: int, *, reason: str) -> None:
        self.processed_files += 1
        self.processed_bytes += max(size_bytes, 0)
        self._since_cleanup_files += 1
        self._since_cleanup_bytes += max(size_bytes, 0)
        if self._cleanup_due():
            self.cleanup(reason=reason)
        wait_for_drive_sync(min_free_gb=self.min_free_gb, sleep_seconds=self.sleep_seconds, path="/")

    def cleanup(self, *, reason: str) -> None:
        removed = _cleanup_standardize_temp(self.temp_root)
        self._since_cleanup_files = 0
        self._since_cleanup_bytes = 0
        free_gb = shutil.disk_usage("/").free / BYTES_PER_GB
        temp_size_gb = _path_size_bytes(self.temp_root) / BYTES_PER_GB
        print(
            "[standardize] cleanup done "
            f"reason={reason} removed={removed} "
            f"processed_files={self.processed_files} "
            f"processed_gb={self.processed_bytes / BYTES_PER_GB:.3f} "
            f"free_disk_gb={free_gb:.2f} temp_dir_size_gb={temp_size_gb:.3f}",
            flush=True,
        )

    def _cleanup_due(self) -> bool:
        files_due = self.cleanup_every_files > 0 and self._since_cleanup_files >= self.cleanup_every_files
        gb_due = self.cleanup_every_gb > 0 and self._since_cleanup_bytes >= self.cleanup_every_gb * BYTES_PER_GB
        return files_due or gb_due


def _ensure_temp_disk_available(temp_root: Path, size_bytes: int, min_free_gb: float, label: str) -> None:
    free_bytes = shutil.disk_usage(str(temp_root)).free
    required_bytes = max(size_bytes, 0) + int(min_free_gb * BYTES_PER_GB)
    if free_bytes >= required_bytes:
        return
    raise RuntimeError(
        "not enough local runtime disk before staging "
        f"{label}: size={size_bytes / BYTES_PER_GB:.2f}GB "
        f"free={free_bytes / BYTES_PER_GB:.2f}GB "
        f"required={required_bytes / BYTES_PER_GB:.2f}GB. "
        "Increase Colab runtime disk, reduce batch/source size, or process fewer archives at a time."
    )


def _cleanup_standardize_temp(temp_root: Path) -> int:
    if not temp_root.exists() or not temp_root.is_dir():
        return 0
    removed = 0
    for child in temp_root.iterdir():
        if not child.name.startswith(STANDARDIZE_TEMP_PREFIXES):
            continue
        if child.is_dir():
            shutil.rmtree(child, ignore_errors=True)
        else:
            try:
                child.unlink()
            except FileNotFoundError:
                pass
        removed += 1
    return removed


def _path_size_bytes(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        return path.stat().st_size
    total = 0
    for child in path.rglob("*"):
        if child.is_file():
            try:
                total += child.stat().st_size
            except OSError:
                continue
    return total


def _is_colab_drive_path(path: Path) -> bool:
    parts = path.resolve().parts
    return len(parts) >= 3 and parts[0] == "/" and parts[1] == "content" and parts[2] == "drive"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read_standardize_progress(progress_path: Path) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    if not progress_path.exists():
        return records
    for line in progress_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        source_id = record.get("source_id")
        if isinstance(source_id, str):
            records[source_id] = record
    return records


def _append_standardize_progress(
    progress_path: Path,
    source_id: str,
    source_path: Path,
    source_mode: str,
    status: str,
    targets: list[Path],
    details: dict[str, Any],
) -> None:
    started_at = details.get("started_at") or _utc_now_iso()
    finished_at = details.get("finished_at") or _utc_now_iso()
    record = {
        "source_id": source_id,
        "source_path": str(source_path),
        "source_mode": source_mode,
        "status": status,
        "video_count": int(details.get("video_count", 0)),
        "metadata_count": int(details.get("metadata_count", 0)),
        "skipped_existing_count": int(details.get("skipped_existing_count", 0)),
        "error": str(details.get("error", "")),
        "started_at": started_at,
        "finished_at": finished_at,
        "targets": [str(target) for target in targets],
    }
    with progress_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _standardize_source_id(source_mode: str, path: Path, source_root: Path) -> str:
    stat = path.stat()
    try:
        relative = path.relative_to(source_root).as_posix()
    except ValueError:
        relative = path.name
    return f"{source_mode}:{relative}:{stat.st_size}"


def _standardize_group_source_id(
    source_mode: str,
    candidates: tuple[_StandardizeCandidate, ...],
    source_root: Path,
) -> str:
    actual_paths = sorted({candidate.actual_path for candidate in candidates if candidate.actual_path is not None})
    relative_parts = []
    size_total = 0
    for path in actual_paths:
        stat = path.stat()
        try:
            relative_parts.append(path.relative_to(source_root).as_posix())
        except ValueError:
            relative_parts.append(path.name)
        size_total += stat.st_size
    relative_key = "+".join(relative_parts) or "empty"
    return f"{source_mode}:{relative_key}:{size_total}"


def _build_standardize_source_items(
    zip_paths: list[Path],
    zip_candidates: list[_StandardizeCandidate],
    zip_skipped_by_path: dict[Path, list[dict[str, Any]]],
    non_zip_candidates: list[_StandardizeCandidate],
    source_root: Path,
    failed_zip_paths: set[Path],
) -> list[_StandardizeSourceItem]:
    items: list[_StandardizeSourceItem] = []
    by_zip: dict[Path, list[_StandardizeCandidate]] = {}
    for candidate in zip_candidates:
        if candidate.zip_path is not None:
            by_zip.setdefault(candidate.zip_path, []).append(candidate)
    for zip_path in zip_paths:
        if zip_path in failed_zip_paths:
            continue
        candidates = tuple(by_zip.get(zip_path, []))
        skipped = tuple(zip_skipped_by_path.get(zip_path, []))
        if not candidates and not skipped:
            continue
        items.append(
            _StandardizeSourceItem(
                source_id=_standardize_source_id("zip", zip_path, source_root),
                source_mode="zip",
                source_path=zip_path,
                display_path=str(zip_path),
                candidates=candidates,
                skipped_rows=skipped,
            )
        )

    by_group: dict[tuple[str, ...], list[_StandardizeCandidate]] = {}
    for candidate in non_zip_candidates:
        by_group.setdefault(candidate.group_key, []).append(candidate)
    for group_key in sorted(by_group):
        candidates_tuple = tuple(sorted(by_group[group_key], key=lambda candidate: candidate.source_path))
        source_mode = candidates_tuple[0].source_mode
        source_path = candidates_tuple[0].actual_path or Path(candidates_tuple[0].source_path)
        items.append(
            _StandardizeSourceItem(
                source_id=_standardize_group_source_id(source_mode, candidates_tuple, source_root),
                source_mode=source_mode,
                source_path=source_path,
                display_path=", ".join(candidate.source_path for candidate in candidates_tuple),
                candidates=candidates_tuple,
            )
        )
    return items


def _planned_targets_for_source_item(
    item: _StandardizeSourceItem,
    raw_root: Path,
    metadata_root: Path,
    canonical_by_group: dict[tuple[str, ...], str],
) -> list[Path]:
    targets = []
    for candidate in item.candidates:
        canonical_stem = canonical_by_group.get(candidate.group_key)
        if canonical_stem:
            targets.append(_target_for_candidate(candidate, raw_root, metadata_root, canonical_stem))
    return sorted(set(targets))


def _standardize_item_completed(record: dict[str, Any] | None, planned_targets: list[Path]) -> bool:
    if not record or record.get("status") != "pass":
        return False
    recorded_targets = [Path(target) for target in record.get("targets", []) if target]
    targets = recorded_targets or planned_targets
    return bool(targets) and all(target.exists() for target in targets)


def _standardize_progress_record_completed(record: dict[str, Any] | None) -> bool:
    if not record or record.get("status") != "pass":
        return False
    targets = [Path(target) for target in record.get("targets", []) if target]
    return bool(targets) and all(target.exists() for target in targets)


def _process_standardize_source_item(
    item: _StandardizeSourceItem,
    raw_root: Path,
    metadata_root: Path,
    temp_root: Path,
    canonical_by_group: dict[tuple[str, ...], str],
    rename_reason_by_group: dict[tuple[str, ...], str],
    overwrite: bool,
    counters: dict[str, int],
    rows: list[dict[str, Any]],
    progress_path: Path,
    disk_manager: _StandardizeDiskManager,
) -> None:
    started_at = _utc_now_iso()
    before = dict(counters)
    targets = _planned_targets_for_source_item(item, raw_root, metadata_root, canonical_by_group)
    item_errors: list[str] = []
    try:
        if item.source_mode == "zip":
            _process_zip_source_item(item, raw_root, metadata_root, temp_root, canonical_by_group, rename_reason_by_group, overwrite, counters, rows, item_errors, disk_manager)
        else:
            _process_non_zip_source_item(item, raw_root, metadata_root, canonical_by_group, rename_reason_by_group, overwrite, counters, rows, item_errors, disk_manager)
    except Exception as exc:
        counters["error_count"] += 1
        item_errors.append(f"{type(exc).__name__}: {exc}")
        rows.append({"kind": "source_item", "source_mode": item.source_mode, "source": item.display_path, "source_id": item.source_id, "status": "failed", "error": str(exc)})
    finally:
        disk_manager.cleanup(reason=f"source_complete source_id={item.source_id}")

    failed = counters["error_count"] > before["error_count"]
    _append_standardize_progress(
        progress_path,
        item.source_id,
        item.source_path,
        item.source_mode,
        "failed" if failed else "pass",
        targets,
        {
            "video_count": counters["video_count"] - before["video_count"],
            "metadata_count": counters["metadata_count"] - before["metadata_count"],
            "skipped_existing_count": counters["skipped_count"] - before["skipped_count"],
            "error": "; ".join(item_errors),
            "started_at": started_at,
            "finished_at": _utc_now_iso(),
        },
    )


def _process_non_zip_source_item(
    item: _StandardizeSourceItem,
    raw_root: Path,
    metadata_root: Path,
    canonical_by_group: dict[tuple[str, ...], str],
    rename_reason_by_group: dict[tuple[str, ...], str],
    overwrite: bool,
    counters: dict[str, int],
    rows: list[dict[str, Any]],
    item_errors: list[str],
    disk_manager: _StandardizeDiskManager,
) -> None:
    for candidate in item.candidates:
        if candidate.actual_path is None:
            continue
        target = _target_for_candidate(candidate, raw_root, metadata_root, canonical_by_group[candidate.group_key])
        try:
            size_bytes = candidate.actual_path.stat().st_size
            disk_manager.before_file(size_bytes, candidate.source_path)
            status = _copy_standardized_file(candidate.actual_path, target, overwrite=overwrite)
            if status != "skipped_existing":
                disk_manager.after_file(size_bytes, reason=f"file_complete source={candidate.source_path}")
            _update_standardize_counters(candidate, status, counters)
            rows.append(_candidate_report_item(candidate, target, canonical_by_group, rename_reason_by_group, status))
        except (OSError, RuntimeError) as exc:
            counters["error_count"] += 1
            item_errors.append(f"{type(exc).__name__}: {exc}")
            rows.append(_candidate_report_item(candidate, target, canonical_by_group, rename_reason_by_group, "failed", error=str(exc)))
            print(f"[standardize] error source={candidate.source_path} target={target}: {exc}", flush=True)


def _process_zip_source_item(
    item: _StandardizeSourceItem,
    raw_root: Path,
    metadata_root: Path,
    temp_root: Path,
    canonical_by_group: dict[tuple[str, ...], str],
    rename_reason_by_group: dict[tuple[str, ...], str],
    overwrite: bool,
    counters: dict[str, int],
    rows: list[dict[str, Any]],
    item_errors: list[str],
    disk_manager: _StandardizeDiskManager,
) -> None:
    rows.extend(item.skipped_rows)
    counters["skipped_count"] += len(item.skipped_rows)
    with zipfile.ZipFile(item.source_path, "r") as archive:
        for candidate in item.candidates:
            target = _target_for_candidate(candidate, raw_root, metadata_root, canonical_by_group[candidate.group_key])
            try:
                member_info = archive.getinfo(candidate.zip_member or "")
                if target.exists() and not overwrite:
                    if target.stat().st_size == member_info.file_size:
                        status = "skipped_existing"
                        _update_standardize_counters(candidate, status, counters)
                        rows.append(_candidate_report_item(candidate, target, canonical_by_group, rename_reason_by_group, status))
                        continue
                    raise FileExistsError(f"target already exists with different size: {target}")
                disk_manager.before_file(member_info.file_size, candidate.source_path)
                extracted_file = _extract_zip_candidate_member(archive, candidate, temp_root)
                stage_dir = extracted_file.parent
                try:
                    status = _move_flattened_file(extracted_file, target, overwrite=overwrite)
                finally:
                    if stage_dir.name.startswith("member_stage_"):
                        shutil.rmtree(stage_dir, ignore_errors=True)
                if status != "skipped_existing":
                    disk_manager.after_file(member_info.file_size, reason=f"member_complete source={candidate.source_path}")
                _update_standardize_counters(candidate, status, counters)
                rows.append(_candidate_report_item(candidate, target, canonical_by_group, rename_reason_by_group, status))
            except (OSError, RuntimeError, ValueError, KeyError) as exc:
                counters["error_count"] += 1
                item_errors.append(f"{type(exc).__name__}: {exc}")
                rows.append(_candidate_report_item(candidate, target, canonical_by_group, rename_reason_by_group, "failed", error=str(exc)))
                print(f"[standardize] error source={candidate.source_path} target={target}: {exc}", flush=True)


def _discover_standardize_files(
    source_root: Path,
    target_root: Path,
    temp_root: Path,
    accepted_media_extensions: set[str],
) -> tuple[list[Path], list[_StandardizeCandidate]]:
    zip_paths: list[Path] = []
    candidates: list[_StandardizeCandidate] = []
    skip_roots = [target_root, temp_root]
    for path in sorted(source_root.rglob("*")):
        resolved = path.resolve()
        if _should_skip_standardize_path(resolved, skip_roots):
            continue
        if not path.is_file() or path.name in {"standardize_archives_report.json", "standardize_progress.jsonl"}:
            continue
        suffix = path.suffix.lower()
        if suffix == ".zip":
            zip_paths.append(resolved)
            continue
        if suffix not in accepted_media_extensions and suffix not in METADATA_EXTENSIONS:
            continue
        kind = "media" if suffix in accepted_media_extensions else "metadata"
        relative_path = resolved.relative_to(source_root)
        context_parts = _meaningful_context(relative_path.parent.parts)
        source_mode = "existing_layout" if _has_layout_context(relative_path.parent.parts) else "loose_files"
        group_key = (*context_parts, path.stem)
        candidates.append(
            _StandardizeCandidate(
                kind=kind,
                source_mode=source_mode,
                source_path=str(resolved),
                actual_path=resolved,
                relative_path=relative_path,
                original_stem=path.stem,
                extension=path.suffix,
                context_parts=context_parts,
                group_key=group_key,
            )
        )
    return zip_paths, candidates


def _discover_zip_candidates(
    zip_path: Path,
    source_root: Path,
    accepted_media_extensions: set[str],
) -> tuple[list[_StandardizeCandidate], list[dict[str, Any]]]:
    candidates: list[_StandardizeCandidate] = []
    skipped: list[dict[str, Any]] = []
    archive_stem = zip_path.stem
    with zipfile.ZipFile(zip_path, "r") as archive:
        for member in archive.infolist():
            member_path = Path(member.filename)
            _validate_zip_member_path(member_path)
            if member.is_dir():
                continue
            suffix = member_path.suffix.lower()
            is_media = suffix in accepted_media_extensions
            is_metadata = suffix in METADATA_EXTENSIONS
            if not is_media and not is_metadata:
                skipped.append(
                    {
                        "source_mode": "zip",
                        "kind": "unsupported",
                        "source": f"{zip_path}::{member.filename}",
                        "status": "skipped",
                        "archive_stem": archive_stem,
                        "source_inner_path": member.filename,
                    }
                )
                continue
            kind = "media" if is_media else "metadata"
            try:
                zip_relative = zip_path.relative_to(source_root)
            except ValueError:
                zip_relative = Path(zip_path.name)
            context_parts = (archive_stem, *_meaningful_context(member_path.parent.parts))
            group_key = (*context_parts, member_path.stem)
            candidates.append(
                _StandardizeCandidate(
                    kind=kind,
                    source_mode="zip",
                    source_path=f"{zip_path}::{member.filename}",
                    actual_path=None,
                    relative_path=zip_relative / member_path,
                    original_stem=member_path.stem,
                    extension=member_path.suffix,
                    context_parts=context_parts,
                    group_key=group_key,
                    archive_stem=archive_stem,
                    zip_path=zip_path,
                    zip_member=member.filename,
                )
            )
    return candidates, skipped


def _should_skip_standardize_path(path: Path, skip_roots: list[Path]) -> bool:
    if ".tmp_archive_extract" in path.parts:
        return True
    return any(path == root or root in path.parents for root in skip_roots)


def _has_layout_context(parts: tuple[str, ...]) -> bool:
    names = {part.lower() for part in parts}
    return bool(names & (VIDEO_DIR_NAMES | METADATA_DIR_NAMES))


def _meaningful_context(parts: tuple[str, ...]) -> tuple[str, ...]:
    context = []
    for part in parts:
        if part.lower() in GENERIC_CONTEXT_NAMES:
            continue
        sanitized = _sanitize_stem(part)
        if sanitized:
            context.append(sanitized)
    return tuple(context)


def _assign_canonical_stems(
    candidates: list[_StandardizeCandidate],
) -> tuple[dict[tuple[str, ...], str], dict[tuple[str, ...], str]]:
    grouped: dict[tuple[str, ...], list[_StandardizeCandidate]] = {}
    for candidate in candidates:
        grouped.setdefault(candidate.group_key, []).append(candidate)
    media_groups = {
        group_key
        for group_key, group_candidates in grouped.items()
        if any(candidate.kind == "media" for candidate in group_candidates)
    }
    original_media_counts: dict[str, int] = {}
    for group_key in media_groups:
        original = grouped[group_key][0].original_stem
        original_media_counts[original] = original_media_counts.get(original, 0) + 1

    assigned: dict[tuple[str, ...], str] = {}
    reasons: dict[tuple[str, ...], str] = {}
    media_depths: dict[tuple[str, ...], int] = {}
    for group_key in media_groups:
        representative = grouped[group_key][0]
        original_is_unique = original_media_counts.get(representative.original_stem, 0) <= 1
        media_depths[group_key] = 0 if original_is_unique else 1
    while media_depths:
        stems_by_group = {
            group_key: _stem_for_context_depth(grouped[group_key][0], depth)
            for group_key, depth in media_depths.items()
        }
        groups_by_stem: dict[str, list[tuple[str, ...]]] = {}
        for group_key, stem in stems_by_group.items():
            groups_by_stem.setdefault(stem, []).append(group_key)
        duplicates = [group_keys for group_keys in groups_by_stem.values() if len(group_keys) > 1]
        if not duplicates:
            break
        progressed = False
        for duplicate_group_keys in duplicates:
            for group_key in duplicate_group_keys:
                representative = grouped[group_key][0]
                if media_depths[group_key] >= len(representative.context_parts):
                    continue
                media_depths[group_key] += 1
                progressed = True
        if not progressed:
            example = duplicates[0][0]
            representative = grouped[example][0]
            raise ValueError(
                "unable to assign unique canonical stem for duplicate media groups "
                f"original_stem={representative.original_stem!r}"
            )
    used: set[str] = set()
    for group_key in sorted(media_groups):
        depth = media_depths[group_key]
        stem = _stem_for_context_depth(grouped[group_key][0], depth)
        assigned[group_key] = stem
        reasons[group_key] = "original_unique" if depth == 0 else "context_disambiguation"
        used.add(stem)
    for group_key in sorted(set(grouped) - media_groups):
        representative = grouped[group_key][0]
        stem, reason = _choose_canonical_stem(representative, used, allow_original=True)
        assigned[group_key] = stem
        reasons[group_key] = reason
        used.add(stem)
    return assigned, reasons


def _stem_for_context_depth(candidate: _StandardizeCandidate, depth: int) -> str:
    if depth <= 0:
        return _sanitize_stem(candidate.original_stem)
    context = list(candidate.context_parts)[-depth:]
    return _sanitize_stem("_".join([*context, candidate.original_stem]))


def _choose_canonical_stem(candidate: _StandardizeCandidate, used: set[str], *, allow_original: bool) -> tuple[str, str]:
    original = _sanitize_stem(candidate.original_stem)
    if allow_original and original and original not in used:
        return original, "original_unique"
    context_parts = list(candidate.context_parts)
    for depth in range(1, len(context_parts) + 1):
        context = context_parts[-depth:]
        stem = _sanitize_stem("_".join([*context, candidate.original_stem]))
        if stem and stem not in used:
            return stem, "context_disambiguation"
    if original and original not in used:
        return original, "metadata_only_original"
    raise ValueError(
        "unable to assign unique canonical stem for "
        f"source={candidate.source_path} original_stem={candidate.original_stem!r} "
        f"context={list(candidate.context_parts)}"
    )


def _copy_non_zip_candidates(
    candidates: list[_StandardizeCandidate],
    raw_root: Path,
    metadata_root: Path,
    canonical_by_group: dict[tuple[str, ...], str],
    rename_reason_by_group: dict[tuple[str, ...], str],
    overwrite: bool,
    counters: dict[str, int],
    rows: list[dict[str, Any]],
) -> None:
    for candidate in candidates:
        if candidate.actual_path is None:
            continue
        target = _target_for_candidate(candidate, raw_root, metadata_root, canonical_by_group[candidate.group_key])
        try:
            status = _copy_standardized_file(candidate.actual_path, target, overwrite=overwrite)
            _update_standardize_counters(candidate, status, counters)
            rows.append(_candidate_report_item(candidate, target, canonical_by_group, rename_reason_by_group, status))
        except OSError as exc:
            counters["error_count"] += 1
            rows.append(_candidate_report_item(candidate, target, canonical_by_group, rename_reason_by_group, "failed", error=str(exc)))
            print(f"[standardize] error source={candidate.source_path} target={target}: {exc}", flush=True)
    print(f"[standardize] after non_zip counters={counters}", flush=True)


def _process_zip_candidates(
    zip_paths: list[Path],
    candidates: list[_StandardizeCandidate],
    raw_root: Path,
    metadata_root: Path,
    temp_root: Path,
    canonical_by_group: dict[tuple[str, ...], str],
    rename_reason_by_group: dict[tuple[str, ...], str],
    overwrite: bool,
    counters: dict[str, int],
    rows: list[dict[str, Any]],
) -> None:
    by_zip: dict[Path, list[_StandardizeCandidate]] = {}
    for candidate in candidates:
        if candidate.zip_path is not None:
            by_zip.setdefault(candidate.zip_path, []).append(candidate)
    for index, zip_path in enumerate(zip_paths, start=1):
        zip_candidates = by_zip.get(zip_path, [])
        if not zip_candidates:
            continue
        print(f"[standardize] processing zip [{index}/{len(zip_paths)}]: {zip_path}", flush=True)
        try:
            with zipfile.ZipFile(zip_path, "r") as archive:
                for candidate in zip_candidates:
                    target = _target_for_candidate(candidate, raw_root, metadata_root, canonical_by_group[candidate.group_key])
                    try:
                        member_info = archive.getinfo(candidate.zip_member or "")
                        if target.exists() and not overwrite:
                            if target.stat().st_size == member_info.file_size:
                                status = "skipped_existing"
                                _update_standardize_counters(candidate, status, counters)
                                rows.append(_candidate_report_item(candidate, target, canonical_by_group, rename_reason_by_group, status))
                                continue
                            raise FileExistsError(f"target already exists with different size: {target}")
                        extracted_file = _extract_zip_candidate_member(archive, candidate, temp_root)
                        status = _move_flattened_file(extracted_file, target, overwrite=overwrite)
                        _update_standardize_counters(candidate, status, counters)
                        rows.append(_candidate_report_item(candidate, target, canonical_by_group, rename_reason_by_group, status))
                    except (OSError, ValueError, KeyError) as exc:
                        counters["error_count"] += 1
                        rows.append(_candidate_report_item(candidate, target, canonical_by_group, rename_reason_by_group, "failed", error=str(exc)))
                        print(f"[standardize] error source={candidate.source_path} target={target}: {exc}", flush=True)
        except (OSError, zipfile.BadZipFile) as exc:
            counters["error_count"] += 1
            rows.append({"source_mode": "zip", "kind": "archive", "source": str(zip_path), "status": "failed", "error": str(exc)})
        print(f"[standardize] after zip [{index}/{len(zip_paths)}] counters={counters}", flush=True)


def _extract_zip_candidate_member(archive: zipfile.ZipFile, candidate: _StandardizeCandidate, temp_root: Path) -> Path:
    if candidate.zip_member is None:
        raise ValueError("zip candidate missing member path")
    member = archive.getinfo(candidate.zip_member)
    member_path = Path(member.filename)
    _validate_zip_member_path(member_path)
    with tempfile.TemporaryDirectory(prefix="member_extract_", dir=temp_root) as clean_tmp:
        clean_tmp_path = Path(clean_tmp).resolve()
        destination = (clean_tmp_path / member_path).resolve()
        try:
            destination.relative_to(clean_tmp_path)
        except ValueError as exc:
            raise ValueError(f"archive member escapes target directory: {member.filename}") from exc
        archive.extract(member, path=clean_tmp_path)
        extracted_file = clean_tmp_path / member.filename
        if not extracted_file.is_file():
            raise FileNotFoundError(f"extracted zip member is not a file: {member.filename}")
        stable_dir = Path(tempfile.mkdtemp(prefix="member_stage_", dir=temp_root))
        stable_temp = stable_dir / extracted_file.name
        shutil.move(str(extracted_file), str(stable_temp))
        return stable_temp


def _validate_zip_member_path(member_path: Path) -> None:
    if member_path.is_absolute():
        raise ValueError(f"archive member must be relative: {member_path}")
    if any(part == ".." for part in member_path.parts):
        raise ValueError(f"archive member escapes target directory: {member_path}")


def _target_for_candidate(candidate: _StandardizeCandidate, raw_root: Path, metadata_root: Path, canonical_stem: str) -> Path:
    if candidate.kind == "media":
        return raw_root / f"{canonical_stem}{candidate.extension}"
    return metadata_root / f"{canonical_stem}.json"


def _update_standardize_counters(candidate: _StandardizeCandidate, status: str, counters: dict[str, int]) -> None:
    if status in {"copied", "moved"}:
        if candidate.kind == "media":
            counters["video_count"] += 1
        else:
            counters["metadata_count"] += 1
    elif status == "skipped_existing":
        counters["skipped_count"] += 1


def _candidate_report_item(
    candidate: _StandardizeCandidate,
    target: Path,
    canonical_by_group: dict[tuple[str, ...], str],
    rename_reason_by_group: dict[tuple[str, ...], str],
    status: str,
    *,
    error: str | None = None,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "source_mode": candidate.source_mode,
        "kind": candidate.kind,
        "source": candidate.source_path,
        "target": str(target),
        "status": status,
        "original_stem": candidate.original_stem,
        "canonical_stem": canonical_by_group.get(candidate.group_key),
        "context": list(candidate.context_parts),
        "rename_reason": rename_reason_by_group.get(candidate.group_key),
    }
    if candidate.archive_stem is not None:
        item["archive_stem"] = candidate.archive_stem
    if candidate.zip_member is not None:
        item["source_inner_path"] = candidate.zip_member
    if error is not None:
        item["error"] = error
    return item


def _copy_standardized_file(source: Path, target: Path, *, overwrite: bool) -> str:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if not overwrite and target.stat().st_size == source.stat().st_size:
            return "skipped_existing"
        if not overwrite:
            raise FileExistsError(f"target already exists with different size: {target}")
        target.unlink()
    shutil.copy2(source, target)
    return "copied"


def _generate_missing_metadata(
    raw_root: Path,
    metadata_root: Path,
    source_root: Path,
    counters: dict[str, int],
    rows: list[dict[str, Any]],
    accepted_media_extensions: set[str],
) -> None:
    for video_path in sorted(raw_root.iterdir()):
        if not video_path.is_file() or video_path.suffix.lower() not in accepted_media_extensions:
            continue
        metadata_path = metadata_root / f"{video_path.stem}.json"
        if metadata_path.exists():
            continue
        _write_minimal_metadata(metadata_path, video_path.stem, str(source_root))
        counters["metadata_count"] += 1
        rows.append(
            {
                "kind": "metadata_generated",
                "status": "generated",
                "canonical_stem": video_path.stem,
                "target": str(metadata_path),
                "source_mode": "generated",
            }
        )


def _report_extra_metadata(
    raw_root: Path,
    metadata_root: Path,
    rows: list[dict[str, Any]],
    accepted_media_extensions: set[str],
) -> None:
    video_stems = {
        path.stem
        for path in raw_root.iterdir()
        if path.is_file() and path.suffix.lower() in accepted_media_extensions
    }
    for metadata_path in sorted(metadata_root.glob("*.json")):
        if metadata_path.stem in video_stems:
            continue
        rows.append(
            {
                "kind": "metadata",
                "status": "warning_extra_metadata",
                "canonical_stem": metadata_path.stem,
                "target": str(metadata_path),
            }
        )


def _sanitize_stem(value: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "_", value)
    sanitized = re.sub(r"_+", "_", sanitized)
    return sanitized.strip("_") or "item"


def upload_standardized_raw_to_hf(
    source_dir: Path | str,
    *,
    repo_id: str,
    raw_import_id: str,
    repo_type: str = "dataset",
    revision: str = "main",
    token: str | None = None,
    progress_path: Path | str | None = None,
) -> CanonicalRawUploadResult:
    """Upload a standardized raw_videos/metadata layout into a versioned HF raw repo prefix."""
    source_root = Path(source_dir).expanduser().resolve()
    raw_root = source_root / "raw_videos"
    metadata_root = source_root / "metadata"
    if not source_root.exists() or not source_root.is_dir():
        raise FileNotFoundError(f"standardized source directory does not exist: {source_root}")
    if not raw_root.exists() or not raw_root.is_dir():
        raise FileNotFoundError(f"standardized source is missing raw_videos/: {raw_root}")
    if not metadata_root.exists() or not metadata_root.is_dir():
        raise FileNotFoundError(f"standardized source is missing metadata/: {metadata_root}")
    if not repo_id:
        raise ValueError("repo_id is required")
    normalized_import_id = _normalize_raw_import_id(raw_import_id)

    store = HuggingFaceDatasetArtifactStore(
        repo_id=repo_id,
        repo_type=repo_type,
        revision=revision,
        token=token or os.environ.get("AIC_HF_TOKEN") or os.environ.get("HF_TOKEN"),
        prefix="",
    )

    existing_files = {path.as_posix() for path in store.list_files("")}
    video_files = [
        path
        for path in sorted(raw_root.iterdir())
        if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS and not _exclude_raw_upload_file(path)
    ]
    metadata_files = [
        path
        for path in sorted(metadata_root.iterdir())
        if path.is_file() and path.suffix.lower() in METADATA_EXTENSIONS and not _exclude_raw_upload_file(path)
    ]
    video_by_stem = _index_unique_by_stem(video_files, kind="video")
    metadata_by_stem = _index_unique_by_stem(metadata_files, kind="metadata")
    errors: list[dict[str, Any]] = []
    resolved_progress_path = Path(progress_path).expanduser() if progress_path is not None else None
    pair_records: list[dict[str, Any]] = []
    pending_by_phase: dict[str, list[_RawUploadItem]] = {"raw_videos": [], "metadata": []}
    skipped_by_phase: dict[str, int] = {"raw_videos": 0, "metadata": 0, "manifests": 0}

    print(
        "[upload-standardized-raw] "
        f"phase=start repo_id={repo_id} raw_import_id={normalized_import_id} "
        f"video_count={len(video_by_stem)} metadata_source_count={len(metadata_by_stem)} "
        f"existing_remote_count={len(existing_files)} batch_size={RAW_UPLOAD_BATCH_SIZE}",
        flush=True,
    )

    with tempfile.TemporaryDirectory(prefix="system1_raw_upload_metadata_") as tmp:
        temp_root = Path(tmp)
        total_files = len(video_by_stem)
        for index, video_id in enumerate(sorted(video_by_stem), start=1):
            video_path = video_by_stem[video_id]
            metadata_path = metadata_by_stem.get(video_id)
            generated_metadata_path: Path | None = None
            if metadata_path is None:
                generated_metadata_path = temp_root / "generated_metadata" / f"{video_id}.json"
                generated_metadata_path.parent.mkdir(parents=True, exist_ok=True)
                _write_minimal_metadata(generated_metadata_path, video_id, str(source_root))
                metadata_path = generated_metadata_path

            video_remote_path = _raw_upload_remote_path(normalized_import_id, "raw_videos", video_path.name)
            metadata_filename = f"{video_id}.json"
            metadata_remote_path = _raw_upload_remote_path(normalized_import_id, "metadata", metadata_filename)
            video_status = "skipped_existing"
            metadata_status = "skipped_existing"
            video_item = _RawUploadItem(
                kind="video",
                video_id=video_id,
                local_path=video_path,
                remote_path=video_remote_path,
                index=index,
                total=total_files,
                size_bytes=video_path.stat().st_size,
            )
            metadata_item = _RawUploadItem(
                kind="metadata",
                video_id=video_id,
                local_path=metadata_path,
                remote_path=metadata_remote_path,
                index=index,
                total=total_files,
                size_bytes=metadata_path.stat().st_size,
            )
            pair_records.append(
                {
                    "video_id": video_id,
                    "video_filename": video_path.name,
                    "metadata_filename": metadata_filename,
                    "video_path": video_remote_path,
                    "metadata_path": metadata_remote_path,
                    "video_size_bytes": video_item.size_bytes,
                    "metadata_size_bytes": metadata_item.size_bytes,
                    "metadata_generated": generated_metadata_path is not None,
                    "raw_repo_id": repo_id,
                    "raw_import_id": normalized_import_id,
                    "video_item": video_item,
                    "metadata_item": metadata_item,
                }
            )
            if video_remote_path in existing_files:
                video_item.status = video_status
                skipped_by_phase["raw_videos"] += 1
                _log_standardized_raw_upload_progress(video_item)
                _append_raw_upload_progress(resolved_progress_path, video_item)
            else:
                pending_by_phase["raw_videos"].append(video_item)

            if metadata_remote_path in existing_files:
                metadata_item.status = metadata_status
                skipped_by_phase["metadata"] += 1
                _log_standardized_raw_upload_progress(metadata_item)
                _append_raw_upload_progress(resolved_progress_path, metadata_item)
            else:
                pending_by_phase["metadata"].append(metadata_item)

        for phase in ("raw_videos", "metadata"):
            phase_errors = _upload_raw_phase_batches(
                store,
                phase=phase,
                items=pending_by_phase[phase],
                skipped_count=skipped_by_phase[phase],
                existing_files=existing_files,
                progress_path=resolved_progress_path,
                repo_id=repo_id,
                raw_import_id=normalized_import_id,
            )
            errors.extend(phase_errors)

        manifest_rows: list[dict[str, Any]] = []
        for record in pair_records:
            video_item = record["video_item"]
            metadata_item = record["metadata_item"]
            row = {
                "video_id": record["video_id"],
                "video_filename": record["video_filename"],
                "metadata_filename": record["metadata_filename"],
                "video_path": record["video_path"],
                "metadata_path": record["metadata_path"],
                "video_size_bytes": record["video_size_bytes"],
                "metadata_size_bytes": record["metadata_size_bytes"],
                "metadata_generated": record["metadata_generated"],
                "raw_repo_id": record["raw_repo_id"],
                "raw_import_id": record["raw_import_id"],
                "video_upload_status": video_item.status,
                "metadata_upload_status": metadata_item.status,
                "status": "pass",
            }
            if video_item.status == "failed" or metadata_item.status == "failed":
                row["status"] = "failed"
                if video_item.error is not None:
                    row["video_error"] = video_item.error
                if metadata_item.error is not None:
                    row["metadata_error"] = metadata_item.error
                row["error"] = video_item.error or metadata_item.error or "upload failed"
            manifest_rows.append(row)

        report = {
            "status": "pass" if not errors else "partial",
            "raw_repo_id": repo_id,
            "raw_import_id": normalized_import_id,
            "source_dir": str(source_root),
            "repo_type": repo_type,
            "revision": revision,
            "video_count": len(video_by_stem),
            "metadata_count": len(manifest_rows),
            "uploaded_pair_count": len([row for row in manifest_rows if row["status"] == "pass"]),
            "error_count": len(errors),
            "errors": errors,
            "upload_method": "create_commit_batch",
            "batch_size": RAW_UPLOAD_BATCH_SIZE,
        }
        manifest_remote_path = _raw_upload_remote_path(normalized_import_id, "manifests", "canonical_file_manifest.jsonl")
        report_remote_path = _raw_upload_remote_path(normalized_import_id, "manifests", "canonical_import_report.json")
        manifest_text = "".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in manifest_rows)
        with tempfile.TemporaryDirectory(prefix="system1_raw_upload_manifest_") as manifest_tmp:
            tmp_path = Path(manifest_tmp)
            manifest_path = tmp_path / "canonical_file_manifest.jsonl"
            report_path = tmp_path / "canonical_import_report.json"
            manifest_path.write_text(manifest_text, encoding="utf-8")
            report_path.write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
            manifest_items = [
                _RawUploadItem(
                    kind="manifest",
                    video_id="",
                    local_path=manifest_path,
                    remote_path=manifest_remote_path,
                    index=1,
                    total=2,
                    size_bytes=manifest_path.stat().st_size,
                ),
                _RawUploadItem(
                    kind="manifest",
                    video_id="",
                    local_path=report_path,
                    remote_path=report_remote_path,
                    index=2,
                    total=2,
                    size_bytes=report_path.stat().st_size,
                ),
            ]
            manifest_errors = _upload_raw_phase_batches(
                store,
                phase="manifests",
                items=manifest_items,
                skipped_count=0,
                existing_files=existing_files,
                progress_path=resolved_progress_path,
                repo_id=repo_id,
                raw_import_id=normalized_import_id,
            )
            errors.extend(manifest_errors)
        if errors:
            report["status"] = "partial"
            report["error_count"] = len(errors)
            report["errors"] = errors

    print("[upload-standardized-raw] phase=done", flush=True)
    return CanonicalRawUploadResult(
        video_count=int(report["video_count"]),
        metadata_count=int(report["metadata_count"]),
        error_count=len(errors),
        manifest_path=manifest_remote_path,
        report_path=report_remote_path,
    )


RAW_UPLOAD_EXCLUDED_NAMES = {
    "standardize_archives_report.json",
    "standardize_progress.jsonl",
    "batch_manifest.csv",
    "videos.parquet",
    "media_store_manifest.parquet",
    "drive_shadow_report.json",
}


def _normalize_raw_import_id(raw_import_id: str) -> str:
    normalized = raw_import_id.strip().strip("/")
    if not normalized:
        raise ValueError("raw_import_id is required")
    parts = normalized.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError(f"raw_import_id must be a relative repo prefix: {raw_import_id}")
    return "/".join(parts)


def _raw_upload_remote_path(raw_import_id: str, *parts: str) -> str:
    return "/".join([raw_import_id, *parts])


def _exclude_raw_upload_file(path: Path) -> bool:
    return path.name in RAW_UPLOAD_EXCLUDED_NAMES or (path.name.startswith("batch_") and path.suffix == ".txt")


def _upload_raw_phase_batches(
    store: HuggingFaceDatasetArtifactStore,
    *,
    phase: str,
    items: list[_RawUploadItem],
    skipped_count: int,
    existing_files: set[str],
    progress_path: Path | None,
    repo_id: str,
    raw_import_id: str,
) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    batches = list(_chunked_raw_upload_items(items, RAW_UPLOAD_BATCH_SIZE))
    if not batches:
        print(
            f"[upload-standardized-raw] phase={phase} uploaded_batch=0/0 "
            f"file_count=0 skipped_existing={skipped_count}",
            flush=True,
        )
        return errors

    for batch_index, batch in enumerate(batches, start=1):
        try:
            _upload_raw_batch_with_retry(
                store,
                batch,
                phase=phase,
                batch_index=batch_index,
                batch_total=len(batches),
                repo_id=repo_id,
                raw_import_id=raw_import_id,
            )
        except Exception as exc:
            message = str(exc)
            for item in batch:
                item.status = "failed"
                item.error = message
                _log_standardized_raw_upload_progress(item)
                _append_raw_upload_progress(progress_path, item)
                errors.append({"video_id": item.video_id, "kind": item.kind, "remote_path": item.remote_path, "message": message})
            print(
                f"[upload-standardized-raw] phase={phase} uploaded_batch={batch_index}/{len(batches)} "
                f"file_count={len(batch)} skipped_existing={skipped_count} status=failed",
                flush=True,
            )
            continue

        for item in batch:
            item.status = "uploaded"
            item.error = None
            existing_files.add(item.remote_path)
            _log_standardized_raw_upload_progress(item)
            _append_raw_upload_progress(progress_path, item)
        print(
            f"[upload-standardized-raw] phase={phase} uploaded_batch={batch_index}/{len(batches)} "
            f"file_count={len(batch)} skipped_existing={skipped_count}",
            flush=True,
        )
    return errors


def _upload_raw_batch_with_retry(
    store: HuggingFaceDatasetArtifactStore,
    batch: list[_RawUploadItem],
    *,
    phase: str,
    batch_index: int,
    batch_total: int,
    repo_id: str,
    raw_import_id: str,
) -> None:
    files = [(item.local_path, item.remote_path) for item in batch]
    commit_message = (
        f"Upload standardized raw {raw_import_id} {phase} "
        f"batch {batch_index}/{batch_total}"
    )
    for retry_index in range(0, RAW_UPLOAD_MAX_RETRIES + 1):
        try:
            store.upload_files(files, commit_message=commit_message, num_threads=2)
            return
        except Exception as exc:
            if not _is_hf_rate_limit_error(exc) or retry_index >= RAW_UPLOAD_MAX_RETRIES:
                raise
            sleep_seconds = _hf_retry_sleep_seconds(exc)
            print(
                f"[upload-standardized-raw] rate limited, sleep_seconds={sleep_seconds}, "
                f"retry={retry_index + 1}/{RAW_UPLOAD_MAX_RETRIES}",
                flush=True,
            )
            time.sleep(sleep_seconds)
    raise RuntimeError(f"failed to upload batch to {repo_id}/{raw_import_id}: phase={phase}")


def _chunked_raw_upload_items(items: list[_RawUploadItem], size: int) -> list[list[_RawUploadItem]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def _is_hf_rate_limit_error(exc: Exception) -> bool:
    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", None)
    if status_code == 429:
        return True
    message = str(exc).lower()
    return "429" in message or "too many requests" in message or "rate limit" in message


def _hf_retry_sleep_seconds(exc: Exception) -> int:
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if headers:
        retry_after = headers.get("Retry-After") or headers.get("retry-after")
        if retry_after:
            try:
                return max(1, int(float(retry_after)))
            except ValueError:
                pass
    message = str(exc)
    match = re.search(r"retry after\s+(\d+(?:\.\d+)?)\s*seconds", message, flags=re.IGNORECASE)
    if match:
        return max(1, int(float(match.group(1))))
    return RAW_UPLOAD_RATE_LIMIT_DEFAULT_SLEEP_SECONDS


def _log_standardized_raw_upload_progress(item: _RawUploadItem) -> None:
    size_mb = item.size_bytes / (1024 ** 2)
    print(
        f"[upload-standardized-raw] kind={item.kind} index={item.index}/{item.total} "
        f"status={item.status} file={item.local_path.name} size_mb={size_mb:.2f} "
        f"remote={item.remote_path}",
        flush=True,
    )


def _append_raw_upload_progress(progress_path: Path | None, item: _RawUploadItem) -> None:
    _append_jsonl_record(
        progress_path,
        {
            "kind": item.kind,
            "local_path": str(item.local_path),
            "remote_path": item.remote_path,
            "status": item.status,
            "size_bytes": item.size_bytes,
            "error": item.error,
        },
    )


def _append_jsonl_record(progress_path: Path | None, record: dict[str, Any]) -> None:
    if progress_path is None:
        return
    progress_path.parent.mkdir(parents=True, exist_ok=True)
    with progress_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")
        handle.flush()


def _reset_import_targets(root: Path, raw_root: Path, metadata_root: Path) -> None:
    root = root.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    for target in (raw_root, metadata_root):
        if target.exists():
            _safe_remove_tree(target, root)
    report_path = root / "organizer_import_report.json"
    if report_path.exists():
        report_path.unlink()


def _safe_remove_tree(target: Path, root: Path) -> None:
    target = target.expanduser().resolve()
    if target == root or root not in target.parents:
        raise ValueError(f"refusing to delete path outside data_root: {target}")
    shutil.rmtree(target)


def _index_unique_by_stem(paths: list[Path], *, kind: str) -> dict[str, Path]:
    indexed: dict[str, Path] = {}
    for path in paths:
        existing = indexed.get(path.stem)
        if existing is not None:
            raise ValueError(f"duplicate {kind} stem '{path.stem}' found: {existing} and {path}")
        indexed[path.stem] = path
    return indexed


def _materialize_source(source_uri: str, tmp_root: Path) -> Path:
    parsed = urlparse(source_uri)
    if parsed.scheme in {"", "file"}:
        path = Path(parsed.path if parsed.scheme == "file" else source_uri).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"organizer source does not exist: {path}")
        return path
    if "drive.google.com" in parsed.netloc:
        target = tmp_root / "drive_source"
        target.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.run(["gdown", "--folder", source_uri, "-O", str(target), "--fuzzy"], check=True)
        except (FileNotFoundError, subprocess.CalledProcessError) as exc:
            raise RuntimeError("Google Drive folder import requires gdown installed in the notebook runtime") from exc
        return target
    raise ValueError(f"unsupported organizer source URI: {source_uri}")


def _find_video_files(source_root: Path) -> list[Path]:
    preferred_dirs = [path for path in source_root.rglob("*") if path.is_dir() and path.name.lower() in VIDEO_DIR_NAMES]
    search_roots = preferred_dirs or [source_root]
    files = sorted({file for root in search_roots for file in root.rglob("*") if file.is_file() and file.suffix.lower() in VIDEO_EXTENSIONS})
    if not files:
        raise FileNotFoundError(f"no video files found under organizer source: {source_root}")
    return files


def _find_metadata_files(source_root: Path) -> list[Path]:
    preferred_dirs = [path for path in source_root.rglob("*") if path.is_dir() and path.name.lower() in METADATA_DIR_NAMES]
    search_roots = preferred_dirs or [source_root]
    return sorted({file for root in search_roots for file in root.rglob("*") if file.is_file() and file.suffix.lower() in METADATA_EXTENSIONS})


def _copy_file(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and target.stat().st_size == source.stat().st_size:
        return
    shutil.copy2(source, target)


def _move_flattened_file(source: Path, target: Path, *, overwrite: bool) -> str:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if not overwrite and target.stat().st_size == source.stat().st_size:
            return "skipped_existing"
        if not overwrite:
            raise FileExistsError(f"target already exists with different size: {target}")
        target.unlink()
    shutil.move(str(source), str(target))
    return "moved"


def _safe_extract_zip(zip_path: Path, target_dir: Path) -> None:
    target_root = target_dir.resolve()
    with zipfile.ZipFile(zip_path, "r") as archive:
        for member in archive.infolist():
            member_path = Path(member.filename)
            if member_path.is_absolute():
                raise ValueError(f"archive member must be relative: {member.filename}")
            destination = (target_root / member_path).resolve()
            try:
                destination.relative_to(target_root)
            except ValueError as exc:
                raise ValueError(f"archive member escapes target directory: {member.filename}") from exc
        archive.extractall(target_root)


def _build_google_drive_service():
    try:
        import google.auth
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise RuntimeError(
            "Google Drive shadow copy requires google-api-python-client and google-auth. "
            "In Colab, run auth.authenticate_user() before this command."
        ) from exc
    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/drive"])
    return build("drive", "v3", credentials=credentials)


def _get_drive_folder_metadata(service: Any, folder_id: str, label: str) -> dict[str, Any]:
    try:
        metadata = service.files().get(
            fileId=folder_id,
            fields="id, name, mimeType",
            supportsAllDrives=True,
        ).execute()
    except Exception as exc:
        raise RuntimeError(f"{label} folder is not accessible: folder_id={folder_id}: {exc}") from exc
    mime_type = str(metadata.get("mimeType", ""))
    if mime_type != "application/vnd.google-apps.folder":
        raise ValueError(
            f"{label} ID is not a Google Drive folder: "
            f"folder_id={folder_id} name={metadata.get('name')} mimeType={mime_type}"
        )
    print(f"[drive-shadow] {label} folder: {metadata.get('name')} ({metadata.get('id')})", flush=True)
    return metadata


def _list_drive_children(service: Any, folder_id: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    page_token: str | None = None
    while True:
        try:
            result = service.files().list(
                q=f"'{folder_id}' in parents and trashed=false",
                fields="nextPageToken, files(id, name, mimeType, size, parents)",
                pageToken=page_token,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
                pageSize=1000,
            ).execute()
        except Exception as exc:
            raise RuntimeError(f"failed to list Google Drive folder children: folder_id={folder_id}: {exc}") from exc
        items.extend(result.get("files", []))
        page_token = result.get("nextPageToken")
        if not page_token:
            return items


def _group_drive_children_by_name(items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        grouped.setdefault(str(item.get("name", "")), []).append(item)
    return grouped


def _drive_file_sizes_match(source: dict[str, Any], target: dict[str, Any]) -> bool:
    source_size = source.get("size")
    target_size = target.get("size")
    return source_size is not None and target_size is not None and str(source_size) == str(target_size)


def _write_minimal_metadata(target: Path, video_id: str, source_uri: str) -> None:
    payload = {
        "video_id": video_id,
        "title": video_id,
        "description": "",
        "watch_url": source_uri,
        "source": "organizer_source_auto_import",
    }
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _validate_pairing(raw_root: Path, metadata_root: Path) -> None:
    video_stems = {path.stem for path in raw_root.iterdir() if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS}
    metadata_stems = {path.stem for path in metadata_root.glob("*.json")}
    missing = sorted(video_stems - metadata_stems)
    if missing:
        raise ValueError(f"metadata pairing failed after import, missing metadata for: {missing}")
