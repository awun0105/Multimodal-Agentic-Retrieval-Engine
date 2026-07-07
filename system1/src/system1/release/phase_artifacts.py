from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from system1.artifacts.hf_store import HuggingFaceDatasetArtifactStore
from system1.artifacts.package import validate_artifact_zip
from system1.artifacts.reports import worker_report_relative_path

PHASE01_STRUCTURE = "phase01_structure"
STRUCTURE_REPORT_PHASE = "structure"


@dataclass(frozen=True)
class PhaseArtifactFile:
    local_path: Path
    remote_path: str
    kind: str
    video_id: str | None = None


@dataclass(frozen=True)
class PhaseArtifactSyncResult:
    release_dir: Path
    repo_id: str
    release_id: str
    batch_id: str
    file_count: int
    files: tuple[PhaseArtifactFile, ...]


def phase01_structure_remote_root(release_id: str) -> str:
    return f"{release_id}/{PHASE01_STRUCTURE}"


def phase01_structure_artifact_remote_path(release_id: str, batch_id: str, video_id: str) -> str:
    return f"{phase01_structure_remote_root(release_id)}/artifacts/{batch_id}/{video_id}_structure.zip"


def phase01_structure_worker_report_remote_path(release_id: str, report_name: str) -> str:
    return f"{phase01_structure_remote_root(release_id)}/worker_reports/{report_name}"


def plan_structure_artifact_sync(
    release_dir: Path | str,
    *,
    release_id: str,
    batch_id: str,
    worker_id: str,
) -> list[PhaseArtifactFile]:
    release_path = Path(release_dir).resolve()
    if release_path.name != release_id:
        raise ValueError(f"release_dir name must match release_id: {release_path.name} != {release_id}")
    video_ids = read_batch_video_ids(release_path, batch_id)
    files: list[PhaseArtifactFile] = []
    for video_id in video_ids:
        zip_path = release_path / "artifacts" / "structure" / f"{video_id}_structure.zip"
        manifest = _validate_structure_zip(zip_path, expected_video_id=video_id, expected_batch_id=batch_id)
        files.append(
            PhaseArtifactFile(
                local_path=zip_path,
                remote_path=phase01_structure_artifact_remote_path(release_id, batch_id, video_id),
                kind="structure_artifact",
                video_id=str(manifest["video_id"]),
            )
        )

    report = release_path / worker_report_relative_path(STRUCTURE_REPORT_PHASE, batch_id, worker_id)
    if not report.is_file():
        raise FileNotFoundError(report)
    files.append(
        PhaseArtifactFile(
            local_path=report,
            remote_path=phase01_structure_worker_report_remote_path(release_id, report.name),
            kind="worker_report",
        )
    )
    return files


def plan_structure_artifact_restore(
    output_dir: Path | str,
    *,
    release_id: str,
    batch_id: str,
    remote_files: list[str | Path],
) -> list[PhaseArtifactFile]:
    release_path = Path(output_dir).resolve() / release_id
    remote_root = phase01_structure_remote_root(release_id)
    artifact_prefix = f"{remote_root}/artifacts/{batch_id}/"
    report_prefix = f"{remote_root}/worker_reports/"
    files: list[PhaseArtifactFile] = []

    for remote_file in sorted(str(path).replace("\\", "/") for path in remote_files):
        if remote_file.endswith("/"):
            continue
        if remote_file.startswith(artifact_prefix) and remote_file.endswith("_structure.zip"):
            filename = Path(remote_file).name
            video_id = filename.removesuffix("_structure.zip")
            files.append(
                PhaseArtifactFile(
                    local_path=release_path / "artifacts" / "structure" / filename,
                    remote_path=remote_file,
                    kind="structure_artifact",
                    video_id=video_id,
                )
            )
            continue
        if remote_file.startswith(report_prefix) and Path(remote_file).name.startswith(f"structure_{batch_id}_"):
            files.append(
                PhaseArtifactFile(
                    local_path=release_path / "manifests" / "worker_reports" / Path(remote_file).name,
                    remote_path=remote_file,
                    kind="worker_report",
                )
            )

    if not any(item.kind == "structure_artifact" for item in files):
        raise FileNotFoundError(f"no structure artifacts found in HF repo under {artifact_prefix}")
    return files


def upload_structure_artifacts_to_hf(
    release_dir: Path | str,
    *,
    repo_id: str,
    release_id: str,
    batch_id: str,
    worker_id: str,
    prefix: str = "",
    repo_type: str = "dataset",
    revision: str = "main",
    token: str | None = None,
) -> PhaseArtifactSyncResult:
    if not repo_id:
        raise ValueError("repo_id is required")
    files = plan_structure_artifact_sync(
        release_dir,
        release_id=release_id,
        batch_id=batch_id,
        worker_id=worker_id,
    )
    store = _store(repo_id=repo_id, prefix=prefix, repo_type=repo_type, revision=revision, token=token)
    store.upload_files(
        [(item.local_path, item.remote_path) for item in files],
        commit_message=f"Upload phase01 structure artifacts {release_id}/{batch_id}",
    )
    return PhaseArtifactSyncResult(
        release_dir=Path(release_dir).resolve(),
        repo_id=repo_id,
        release_id=release_id,
        batch_id=batch_id,
        file_count=len(files),
        files=tuple(files),
    )


def download_structure_artifacts_from_hf(
    output_dir: Path | str,
    *,
    repo_id: str,
    release_id: str,
    batch_id: str,
    prefix: str = "",
    repo_type: str = "dataset",
    revision: str = "main",
    token: str | None = None,
    overwrite: bool = True,
) -> PhaseArtifactSyncResult:
    if not repo_id:
        raise ValueError("repo_id is required")
    store = _store(repo_id=repo_id, prefix=prefix, repo_type=repo_type, revision=revision, token=token)
    remote_root = phase01_structure_remote_root(release_id)
    remote_files = [path.as_posix() for path in store.list_files(remote_root)]
    files = plan_structure_artifact_restore(
        output_dir,
        release_id=release_id,
        batch_id=batch_id,
        remote_files=remote_files,
    )
    for item in files:
        if item.local_path.exists() and not overwrite:
            raise FileExistsError(item.local_path)
        store.download_file(item.remote_path, item.local_path)
    return PhaseArtifactSyncResult(
        release_dir=Path(output_dir).resolve() / release_id,
        repo_id=repo_id,
        release_id=release_id,
        batch_id=batch_id,
        file_count=len(files),
        files=tuple(files),
    )


def read_batch_video_ids(release_dir: Path, batch_id: str) -> list[str]:
    batch_path = release_dir / "manifests" / f"{batch_id}.txt"
    if not batch_path.is_file():
        raise FileNotFoundError(batch_path)
    video_ids = [line.strip() for line in batch_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not video_ids:
        raise ValueError(f"batch manifest is empty: {batch_path}")
    return video_ids


def _validate_structure_zip(zip_path: Path, *, expected_video_id: str, expected_batch_id: str) -> dict[str, object]:
    if not zip_path.is_file():
        raise FileNotFoundError(zip_path)
    manifest = validate_artifact_zip(zip_path)
    artifact_type = str(manifest.get("artifact_type"))
    video_id = str(manifest.get("video_id"))
    batch_id = str(manifest.get("batch_id"))
    if artifact_type != "structure":
        raise ValueError(f"artifact type mismatch for {zip_path}: expected structure, got {artifact_type}")
    if video_id != expected_video_id:
        raise ValueError(f"artifact video_id mismatch for {zip_path}: expected {expected_video_id}, got {video_id}")
    if batch_id != expected_batch_id:
        raise ValueError(f"artifact batch_id mismatch for {zip_path}: expected {expected_batch_id}, got {batch_id}")
    return manifest


def _store(*, repo_id: str, prefix: str, repo_type: str, revision: str, token: str | None) -> HuggingFaceDatasetArtifactStore:
    return HuggingFaceDatasetArtifactStore(
        repo_id=repo_id,
        repo_type=repo_type,
        revision=revision,
        token=token or os.environ.get("AIC_HF_TOKEN") or os.environ.get("HF_TOKEN"),
        prefix=prefix,
    )
