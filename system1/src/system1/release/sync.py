from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from concurrent.futures import ThreadPoolExecutor

from system1.artifacts.hf_store import HuggingFaceDatasetArtifactStore


@dataclass(frozen=True)
class ReleaseSyncResult:
    release_dir: Path
    repo_id: str
    prefix: str
    file_count: int
    manifest_path: Path | str


PHASE00_INGESTION = "phase00_ingestion"
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
    paths_to_upload = _phase00_ingestion_upload_plan(release_path)

    def _upload_worker(item: tuple[Path, str]) -> dict[str, Any]:
        path, relative_path = item
        remote_path = f"{remote_root}/{relative_path}"
        uploaded = store.upload_file(path, remote_path)
        return {
            "release_id": release_id,
            "phase": PHASE00_INGESTION,
            "relative_path": relative_path,
            "remote_path": remote_path,
            "size_bytes": path.stat().st_size,
            "status": "uploaded",
            "uploaded_path": str(uploaded),
        }

    with ThreadPoolExecutor(max_workers=min(32, (os.cpu_count() or 4) * 2)) as executor:
        rows = list(executor.map(_upload_worker, sorted(paths_to_upload, key=lambda item: item[1])))

    manifest_payload = {
        "release_id": release_id,
        "phase": PHASE00_INGESTION,
        "repo_id": repo_id,
        "prefix": prefix,
        "file_count": len(rows),
        "files": rows,
    }
    import tempfile

    with tempfile.TemporaryDirectory(prefix="system1_phase00_sync_") as tmp:
        manifest_file = Path(tmp) / "phase00_sync_manifest.json"
        manifest_file.write_text(json.dumps(manifest_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        uploaded_manifest = store.upload_file(manifest_file, f"{remote_root}/reports/phase00_sync_manifest.json")

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
    phase_path.mkdir(parents=True, exist_ok=True)

    store = _store(repo_id=repo_id, prefix=prefix, repo_type=repo_type, revision=revision, token=token)
    remote_root = phase00_ingestion_remote_prefix(release_id)
    remote_files = [path.as_posix() for path in store.list_files(remote_root)]
    if not remote_files:
        raise FileNotFoundError(f"no phase00 ingestion files found in HF repo under {remote_root}")

    filtered_remote_files = []
    for remote_file in sorted(remote_files):
        if remote_file.endswith("/"):
            continue
        relative = remote_file.removeprefix(f"{remote_root}/")
        if relative == remote_file or not relative:
            continue
        filtered_remote_files.append((remote_file, relative))

    def _download_worker(item: tuple[str, str]) -> None:
        remote_file, relative = item
        target = phase_path / relative
        store.download_file(remote_file, target)

    with ThreadPoolExecutor(max_workers=min(32, (os.cpu_count() or 4) * 2)) as executor:
        executor.map(_download_worker, filtered_remote_files)

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


def _is_phase00_report_path(path: Path) -> bool:
    return path.name in PHASE00_REPORT_FILENAMES


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
