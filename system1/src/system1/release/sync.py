from __future__ import annotations

import json
import os
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


def release_remote_prefix(release_id: str) -> str:
    return f"releases/{release_id}"


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