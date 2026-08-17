from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from system1.artifacts.hf_store import HuggingFaceDatasetArtifactStore
from system1.artifacts.reports import utc_now


@dataclass(frozen=True)
class ReleaseSyncResult:
    release_dir: Path
    repo_id: str
    prefix: str
    file_count: int
    manifest_path: Path | str


PHASE00_INGESTION = "phase00_ingestion"
PHASE00_SYNC_SCHEMA_VERSION = "2.0"
PHASE00_SYNC_BATCH_SIZE = 100
PHASE00_SYNC_MAX_RETRIES = 5
PHASE00_REPORT_FILENAMES = {
    "dataset_report.json",
    "ingestion_errors.jsonl",
    "missing_metadata.json",
    "unmatched_metadata.json",
    "drive_shadow_report.json",
    "standardize_archives_report.json",
    "standardize_progress.jsonl",
    "canonical_import_report.json",
    "stream_standardize_upload_progress.jsonl",
}


def release_remote_prefix(release_id: str) -> str:
    return f"releases/{release_id}"


def phase00_ingestion_remote_prefix(release_id: str) -> str:
    return f"{release_id}/{PHASE00_INGESTION}"


def upload_phase00_ingestion_to_hf(
    release_dir: Path | str,
    *,
    repo_id: str,
    prefix: str = "",
    repo_type: str = "dataset",
    revision: str = "main",
    token: str | None = None,
) -> ReleaseSyncResult:
    """Upload Notebook 00 ingestion artifacts using the phase00_ingestion HF layout.

    The local release folder may still use the legacy shape
    {tables, raw_mapping, manifests}. This function maps those files to the
    new remote contract under <release_id>/phase00_ingestion/.
    """
    release_path = Path(release_dir).resolve()
    if not release_path.exists() or not release_path.is_dir():
        raise FileNotFoundError(release_path)
    if not repo_id:
        raise ValueError("repo_id is required")

    store = _store(repo_id=repo_id, prefix=prefix, repo_type=repo_type, revision=revision, token=token)
    release_id = release_path.name
    remote_root = phase00_ingestion_remote_prefix(release_id)
    paths_to_upload = sorted(_phase00_ingestion_upload_plan(release_path), key=lambda item: item[1])
    local_entries = [
        {
            "path": path,
            "relative_path": relative_path,
            "remote_path": f"{remote_root}/{relative_path}",
            "size_bytes": path.stat().st_size,
            "sha256": _sha256_file(path),
        }
        for path, relative_path in paths_to_upload
    ]
    completion_remote_path = f"{remote_root}/reports/phase00_sync_manifest.json"
    remote_files = {path.as_posix() for path in store.list_files(remote_root)}
    previous_manifest = (
        _download_phase00_sync_manifest(store, completion_remote_path)
        if completion_remote_path in remote_files
        else {}
    )
    previous_by_relative = {
        str(row.get("relative_path")): row
        for row in previous_manifest.get("files", [])
        if isinstance(row, dict) and row.get("relative_path")
    }

    changed_entries: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    desired_remote_paths = {str(entry["remote_path"]) for entry in local_entries}
    for entry in local_entries:
        previous = previous_by_relative.get(str(entry["relative_path"]))
        unchanged = (
            entry["remote_path"] in remote_files
            and previous is not None
            and previous.get("sha256") == entry["sha256"]
            and int(previous.get("size_bytes", -1)) == entry["size_bytes"]
        )
        if not unchanged:
            changed_entries.append(entry)
        rows.append(
            {
                "release_id": release_id,
                "phase": PHASE00_INGESTION,
                "relative_path": entry["relative_path"],
                "remote_path": entry["remote_path"],
                "size_bytes": entry["size_bytes"],
                "sha256": entry["sha256"],
                "status": "skipped_unchanged" if unchanged else "uploaded",
            }
        )

    stale_remote_paths = sorted(
        path
        for path in remote_files
        if path.startswith(f"{remote_root}/")
        and path not in desired_remote_paths
        and path != completion_remote_path
    )
    operations: list[tuple[str, dict[str, Any] | str]] = []
    if (changed_entries or stale_remote_paths) and completion_remote_path in remote_files:
        # Invalidate the previous completion marker in the first atomic commit.
        # If a later batch fails, consumers cannot mistake the partially updated
        # prefix for the previously complete snapshot.
        operations.append(("delete", completion_remote_path))
    operations.extend(("add", entry) for entry in changed_entries)
    operations.extend(("delete", path) for path in stale_remote_paths)
    operation_batches = _chunked(operations, PHASE00_SYNC_BATCH_SIZE)
    for batch_index, batch in enumerate(operation_batches, start=1):
        files = [
            (entry["path"], entry["remote_path"])
            for kind, entry in batch
            if kind == "add" and isinstance(entry, dict)
        ]
        delete_paths = [
            path
            for kind, path in batch
            if kind == "delete" and isinstance(path, str)
        ]
        _sync_phase00_batch_with_retry(
            store,
            files=files,
            delete_paths=delete_paths,
            commit_message=(
                f"Sync {release_id} phase00 batch {batch_index}/"
                f"{len(operation_batches)}"
            ),
        )

    manifest_payload = {
        "release_id": release_id,
        "phase": PHASE00_INGESTION,
        "schema_version": PHASE00_SYNC_SCHEMA_VERSION,
        "status": "complete",
        "completed_at": utc_now(),
        "repo_id": repo_id,
        "prefix": prefix,
        "file_count": len(rows),
        "uploaded_count": len(changed_entries),
        "skipped_unchanged_count": len(rows) - len(changed_entries),
        "deleted_count": len(stale_remote_paths),
        "deleted_remote_paths": stale_remote_paths,
        "files": rows,
    }
    with tempfile.TemporaryDirectory(prefix="system1_phase00_sync_") as tmp:
        manifest_file = Path(tmp) / "phase00_sync_manifest.json"
        manifest_file.write_text(json.dumps(manifest_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        _sync_phase00_batch_with_retry(
            store,
            files=[(manifest_file, completion_remote_path)],
            delete_paths=[],
            commit_message=f"Complete {release_id} phase00 sync",
        )
        uploaded_manifest = store.path(completion_remote_path)

    return ReleaseSyncResult(
        release_dir=release_path,
        repo_id=repo_id,
        prefix=prefix,
        file_count=len(rows),
        manifest_path=uploaded_manifest,
    )


def download_phase00_ingestion_from_hf(
    output_dir: Path | str,
    *,
    release_id: str,
    repo_id: str,
    prefix: str = "",
    repo_type: str = "dataset",
    revision: str = "main",
    token: str | None = None,
    overwrite: bool = True,
) -> ReleaseSyncResult:
    if not repo_id:
        raise ValueError("repo_id is required")
    output_path = Path(output_dir).resolve()
    release_path = output_path / release_id
    phase_path = release_path / PHASE00_INGESTION
    if phase_path.exists() and not overwrite:
        raise FileExistsError(phase_path)
    release_path.mkdir(parents=True, exist_ok=True)

    store = _store(repo_id=repo_id, prefix=prefix, repo_type=repo_type, revision=revision, token=token)
    remote_root = phase00_ingestion_remote_prefix(release_id)
    remote_files = [path.as_posix() for path in store.list_files(remote_root)]
    if not remote_files:
        raise FileNotFoundError(f"no phase00 ingestion files found in HF repo under {remote_root}")
    completion_remote_path = f"{remote_root}/reports/phase00_sync_manifest.json"
    if completion_remote_path not in remote_files:
        raise FileNotFoundError(
            f"Phase00 snapshot is incomplete: missing completion marker {completion_remote_path}"
        )

    filtered_remote_files = []
    for remote_file in sorted(remote_files):
        if remote_file.endswith("/"):
            continue
        relative = remote_file.removeprefix(f"{remote_root}/")
        if relative == remote_file or not relative:
            continue
        filtered_remote_files.append((remote_file, relative))

    with tempfile.TemporaryDirectory(prefix=".phase00_restore_", dir=release_path) as tmp:
        staged_phase_path = Path(tmp) / PHASE00_INGESTION
        staged_phase_path.mkdir(parents=True, exist_ok=True)

        def _download_worker(item: tuple[str, str]) -> None:
            remote_file, relative = item
            target = staged_phase_path / relative
            store.download_file(remote_file, target)

        with ThreadPoolExecutor(max_workers=min(32, (os.cpu_count() or 4) * 2)) as executor:
            list(executor.map(_download_worker, filtered_remote_files))

        staged_manifest = staged_phase_path / "reports" / "phase00_sync_manifest.json"
        _validate_phase00_download(
            staged_phase_path,
            staged_manifest,
            release_id=release_id,
            remote_root=remote_root,
            remote_files=set(remote_files),
        )
        if not overwrite:
            _preflight_phase00_materialization(staged_phase_path, release_path)
        if phase_path.exists():
            shutil.rmtree(phase_path)
        os.replace(staged_phase_path, phase_path)

    _materialize_phase00_ingestion(phase_path, release_path, overwrite=overwrite)

    manifest_path = phase_path / "reports" / "phase00_sync_manifest.json"
    return ReleaseSyncResult(
        release_dir=release_path,
        repo_id=repo_id,
        prefix=prefix,
        file_count=len(filtered_remote_files),
        manifest_path=manifest_path,
    )


def _phase00_ingestion_upload_plan(release_path: Path) -> list[tuple[Path, str]]:
    phase_root = release_path / PHASE00_INGESTION
    if phase_root.exists():
        return [(path, path.relative_to(phase_root).as_posix()) for path in phase_root.rglob("*") if path.is_file()]

    paths: list[tuple[Path, str]] = []
    for local_dir_name, remote_dir_name in (
        ("tables", "tables"),
        ("raw_mapping", "raw_mapping"),
        ("frame_timeline", "frame_timeline"),
    ):
        local_dir = release_path / local_dir_name
        if not local_dir.exists():
            continue
        for path in local_dir.rglob("*"):
            if path.is_file():
                paths.append((path, f"{remote_dir_name}/{path.relative_to(local_dir).as_posix()}"))

    manifests_dir = release_path / "manifests"
    if manifests_dir.exists():
        for path in manifests_dir.rglob("*"):
            if not path.is_file():
                continue
            relative = path.relative_to(manifests_dir).as_posix()
            destination_dir = "reports" if _is_phase00_report_path(path) else "manifests"
            paths.append((path, f"{destination_dir}/{relative}"))

    reports_dir = release_path / "reports"
    if reports_dir.exists():
        for path in reports_dir.rglob("*"):
            if path.is_file():
                paths.append((path, f"reports/{path.relative_to(reports_dir).as_posix()}"))

    if not paths:
        raise FileNotFoundError(f"no phase00 ingestion artifacts found under {release_path}")
    return paths


def _materialize_phase00_ingestion(phase_path: Path, release_path: Path, *, overwrite: bool) -> None:
    if overwrite:
        _remove_stale_materialized_phase00_files(phase_path, release_path)
    for directory_name in ("tables", "raw_mapping", "manifests", "frame_timeline"):
        source_dir = phase_path / directory_name
        if not source_dir.exists():
            continue
        for source in source_dir.rglob("*"):
            if not source.is_file():
                continue
            target = release_path / directory_name / source.relative_to(source_dir)
            if target.exists() and not overwrite:
                raise FileExistsError(target)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)


def _preflight_phase00_materialization(phase_path: Path, release_path: Path) -> None:
    for directory_name in ("tables", "raw_mapping", "manifests", "frame_timeline"):
        source_dir = phase_path / directory_name
        if not source_dir.exists():
            continue
        for source in source_dir.rglob("*"):
            if not source.is_file():
                continue
            target = release_path / directory_name / source.relative_to(source_dir)
            if target.exists():
                raise FileExistsError(target)


def _remove_stale_materialized_phase00_files(
    phase_path: Path,
    release_path: Path,
) -> None:
    expected_timeline_names = {
        path.name for path in (phase_path / "frame_timeline").glob("*.parquet")
    }
    active_timeline_dir = release_path / "frame_timeline"
    if active_timeline_dir.exists():
        for path in active_timeline_dir.glob("*.parquet"):
            if path.name not in expected_timeline_names:
                path.unlink()

    expected_batch_names = {
        path.name for path in (phase_path / "manifests").glob("batch_*.txt")
    }
    active_manifests_dir = release_path / "manifests"
    if active_manifests_dir.exists():
        for path in active_manifests_dir.glob("batch_*.txt"):
            if path.name not in expected_batch_names:
                path.unlink()


def _validate_phase00_download(
    phase_path: Path,
    manifest_path: Path,
    *,
    release_id: str,
    remote_root: str,
    remote_files: set[str],
) -> None:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Phase00 completion manifest must be a JSON object")
    if payload.get("schema_version") != PHASE00_SYNC_SCHEMA_VERSION:
        raise ValueError("Phase00 completion manifest schema_version mismatch")
    if payload.get("status") != "complete" or payload.get("release_id") != release_id:
        raise ValueError("Phase00 completion manifest does not describe a complete requested release")
    rows = payload.get("files")
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise ValueError("Phase00 completion manifest files must be a list of objects")
    if payload.get("file_count") != len(rows):
        raise ValueError("Phase00 completion manifest file_count mismatch")
    declared_remote_paths = {str(row.get("remote_path")) for row in rows}
    completion_remote_path = f"{remote_root}/reports/phase00_sync_manifest.json"
    actual_payload_paths = remote_files - {completion_remote_path}
    if declared_remote_paths != actual_payload_paths:
        raise ValueError("Phase00 completion manifest does not match remote prefix contents")
    for row in rows:
        remote_path = str(row.get("remote_path"))
        relative = remote_path.removeprefix(f"{remote_root}/")
        if relative == remote_path or not relative:
            raise ValueError(f"invalid Phase00 manifest remote_path: {remote_path}")
        local_path = phase_path / relative
        expected_size = row.get("size_bytes")
        expected_sha256 = row.get("sha256")
        if local_path.stat().st_size != expected_size or _sha256_file(local_path) != expected_sha256:
            raise ValueError(f"Phase00 downloaded file checksum mismatch: {relative}")


def _is_phase00_report_path(path: Path) -> bool:
    return path.name in PHASE00_REPORT_FILENAMES or (
        path.name.startswith("stream_standardize_upload_progress_")
        and path.name.endswith(".jsonl")
    )


def _sha256_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def _download_phase00_sync_manifest(
    store: HuggingFaceDatasetArtifactStore,
    remote_path: str,
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="system1_phase00_previous_") as tmp:
        local_path = Path(tmp) / "phase00_sync_manifest.json"
        store.download_file(remote_path, local_path)
        try:
            payload = json.loads(local_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    if not isinstance(payload, dict):
        return {}
    if payload.get("schema_version") != PHASE00_SYNC_SCHEMA_VERSION:
        return {}
    if payload.get("status") != "complete":
        return {}
    return payload


def _chunked(items: list[Any], size: int) -> list[list[Any]]:
    if size <= 0:
        raise ValueError("chunk size must be positive")
    return [items[index : index + size] for index in range(0, len(items), size)]


def _sync_phase00_batch_with_retry(
    store: HuggingFaceDatasetArtifactStore,
    *,
    files: list[tuple[Path, str]],
    delete_paths: list[str],
    commit_message: str,
) -> None:
    for attempt in range(1, PHASE00_SYNC_MAX_RETRIES + 1):
        try:
            store.sync_files(
                files,
                delete_paths=delete_paths,
                commit_message=commit_message,
                num_threads=2,
            )
            return
        except Exception as exc:
            if attempt >= PHASE00_SYNC_MAX_RETRIES or not _is_retryable_phase00_sync_error(exc):
                raise
            time.sleep(_phase00_retry_delay_seconds(exc, attempt))


def _is_retryable_phase00_sync_error(exc: Exception) -> bool:
    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", None)
    if status_code in {409, 429} or isinstance(status_code, int) and status_code >= 500:
        return True
    message = str(exc).lower()
    return any(
        marker in message
        for marker in (
            "rate limit",
            "too many requests",
            "temporarily unavailable",
            "connection reset",
            "connection aborted",
            "connection timed out",
            "read timed out",
            "gateway timeout",
            "service unavailable",
        )
    )


def _phase00_retry_delay_seconds(exc: Exception, attempt: int) -> float:
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", {}) or {}
    retry_after = headers.get("retry-after") or headers.get("Retry-After")
    if retry_after is not None:
        try:
            return min(60.0, max(0.0, float(retry_after)))
        except (TypeError, ValueError):
            pass
    return min(60.0, float(2 ** (attempt - 1)))


def upload_release_to_hf(
    release_dir: Path | str,
    *,
    repo_id: str,
    prefix: str = "",
    repo_type: str = "dataset",
    revision: str = "main",
    token: str | None = None,
) -> ReleaseSyncResult:
    release_path = Path(release_dir).resolve()
    if not release_path.exists() or not release_path.is_dir():
        raise FileNotFoundError(release_path)
    if not repo_id:
        raise ValueError("repo_id is required")

    store = _store(repo_id=repo_id, prefix=prefix, repo_type=repo_type, revision=revision, token=token)
    release_id = release_path.name
    remote_root = release_remote_prefix(release_id)

    # Thu thập danh sách file thực tế cần đẩy lên
    paths_to_upload = [p for p in release_path.rglob("*") if p.is_file()]

    # --- TỐI ƯU MẠNG BẰNG THREADPOOL: Upload đa luồng song song đồng thời ---
    def _upload_worker(path: Path) -> dict[str, Any]:
        relative_path = path.relative_to(release_path).as_posix()
        remote_path = f"{remote_root}/{relative_path}"
        uploaded = store.upload_file(path, remote_path)
        return {
            "release_id": release_id,
            "relative_path": relative_path,
            "remote_path": remote_path,
            "size_bytes": path.stat().st_size,
            "status": "uploaded",
            "uploaded_path": str(uploaded),
        }

    with ThreadPoolExecutor(max_workers=min(32, (os.cpu_count() or 4) * 2)) as executor:
        rows = list(executor.map(_upload_worker, sorted(paths_to_upload)))

    manifest_payload = {
        "release_id": release_id,
        "repo_id": repo_id,
        "prefix": prefix,
        "file_count": len(rows),
        "files": rows,
    }
    import tempfile

    with tempfile.TemporaryDirectory(prefix="system1_release_sync_") as tmp:
        manifest_file = Path(tmp) / "release_sync_manifest.json"
        manifest_file.write_text(json.dumps(manifest_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        uploaded_manifest = store.upload_file(manifest_file, f"{remote_root}/manifests/release_sync_manifest.json")

    return ReleaseSyncResult(
        release_dir=release_path,
        repo_id=repo_id,
        prefix=prefix,
        file_count=len(rows),
        manifest_path=uploaded_manifest,
    )


def download_release_from_hf(
    output_dir: Path | str,
    *,
    release_id: str,
    repo_id: str,
    prefix: str = "",
    repo_type: str = "dataset",
    revision: str = "main",
    token: str | None = None,
    overwrite: bool = True,
) -> ReleaseSyncResult:
    if not repo_id:
        raise ValueError("repo_id is required")
    output_path = Path(output_dir).resolve()
    release_path = output_path / release_id
    if release_path.exists() and not overwrite:
        raise FileExistsError(release_path)
    release_path.mkdir(parents=True, exist_ok=True)

    store = _store(repo_id=repo_id, prefix=prefix, repo_type=repo_type, revision=revision, token=token)
    remote_root = release_remote_prefix(release_id)
    remote_files = [path.as_posix() for path in store.list_files(remote_root)]
    if not remote_files:
        raise FileNotFoundError(f"no release files found in HF repo under {remote_root}")

    # Lọc danh sách file thực tế cần download về local
    filtered_remote_files = []
    for remote_file in sorted(remote_files):
        if remote_file.endswith("/"):
            continue
        relative = remote_file.removeprefix(f"{remote_root}/")
        if relative == remote_file or not relative:
            continue
        filtered_remote_files.append((remote_file, relative))

    # --- TỐI ƯU MẠNG BẰNG THREADPOOL: Tải file đa luồng song song đồng thời ---
    def _download_worker(item: tuple[str, str]) -> None:
        remote_file, relative = item
        target = release_path / relative
        store.download_file(remote_file, target)

    with ThreadPoolExecutor(max_workers=min(32, (os.cpu_count() or 4) * 2)) as executor:
        executor.map(_download_worker, filtered_remote_files)

    manifest_path = release_path / "manifests" / "release_sync_manifest.json"
    return ReleaseSyncResult(
        release_dir=release_path,
        repo_id=repo_id,
        prefix=prefix,
        file_count=len(filtered_remote_files),
        manifest_path=manifest_path,
    )


def _store(*, repo_id: str, prefix: str, repo_type: str, revision: str, token: str | None) -> HuggingFaceDatasetArtifactStore:
    return HuggingFaceDatasetArtifactStore(
        repo_id=repo_id,
        repo_type=repo_type,
        revision=revision,
        token=token or os.environ.get("AIC_HF_TOKEN") or os.environ.get("HF_TOKEN"),
        prefix=prefix,
    )
