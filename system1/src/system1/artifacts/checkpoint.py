from __future__ import annotations

from pathlib import Path
from typing import Any
import datetime as dt
import hashlib
import json
import os
import shutil
import tempfile
import zipfile

from system1.artifacts.factory import make_artifact_store_from_env
from system1.release.types import DEFAULT_RELEASE_ID


_REGISTRY_PATH = Path("manifests") / "checkpoint_registry.json"
_CHECKPOINT_METADATA_DIR = Path("manifests") / "checkpoints"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def checkpoint_name(phase: str, batch_id: str | None = None) -> str:
    if phase == "phase00_ingest_assignment":
        return phase
    if phase in {"phase01_structure", "phase02_features"}:
        if not batch_id:
            raise ValueError(f"{phase} requires batch_id")
        return f"{phase}_{batch_id}"
    if phase == "phase03_final_release":
        return phase
    raise ValueError(f"Unknown checkpoint phase: {phase}")


def checkpoint_relative_path(phase: str, batch_id: str | None = None) -> Path:
    return Path("checkpoints") / f"{checkpoint_name(phase, batch_id)}.zip"

def checkpoint_metadata_relative_path(phase: str, batch_id: str | None = None) -> Path:
    return _CHECKPOINT_METADATA_DIR / f"{checkpoint_name(phase, batch_id)}.json"


def _phase_required_paths(phase: str, batch_id: str | None = None) -> list[Path]:
    phase00 = [
        Path("tables/videos.parquet"),
        Path("raw_mapping/media_store_manifest.parquet"),
        Path("manifests/dataset_report.json"),
        Path("manifests/ingestion_errors.jsonl"),
        Path("manifests/batch_manifest.csv"),
        Path("manifests/batch_*.txt"),
    ]
    if phase == "phase00_ingest_assignment":
        return phase00
    if phase == "phase01_structure":
        checkpoint_name(phase, batch_id)
        return phase00 + [
            Path("artifacts/structure"),
            Path("artifacts/structure_batches"),
            Path("manifests/worker_runtime_report_structure.json"),
        ]
    if phase == "phase02_features":
        checkpoint_name(phase, batch_id)
        return phase00 + [
            Path("artifacts/structure"),
            Path("artifacts/structure_batches"),
            Path("manifests/worker_runtime_report_structure.json"),
            Path("artifacts/features"),
            Path("manifests/worker_runtime_report_features.json"),
        ]
    if phase == "phase03_final_release":
        return [
            Path("tables"),
            Path("raw_mapping"),
            Path("manifests"),
            Path("artifacts"),
            Path("media"),
            Path("indexes"),
            Path("db"),
        ]
    raise ValueError(f"Unknown checkpoint phase: {phase}")


def _iter_phase_members(release_dir: Path, phase: str, batch_id: str | None = None) -> list[Path]:
    members: set[Path] = set()
    for relative_path in _phase_required_paths(phase, batch_id):
        if "*" in str(relative_path):
            matches = [path.relative_to(release_dir) for path in release_dir.glob(str(relative_path)) if path.is_file()]
            if not matches:
                raise FileNotFoundError(release_dir / relative_path)
            members.update(matches)
            continue

        absolute_path = release_dir / relative_path
        if not absolute_path.exists():
            raise FileNotFoundError(absolute_path)
        if absolute_path.is_file():
            members.add(relative_path)
            continue

        if absolute_path.is_dir():
            files = [path.relative_to(release_dir) for path in absolute_path.rglob("*") if path.is_file()]
            if not files:
                raise FileNotFoundError(absolute_path)
            members.update(files)
            continue

        raise FileNotFoundError(absolute_path)
    return sorted(members)


def _registry_key(phase: str, batch_id: str | None = None) -> str:
    return checkpoint_name(phase, batch_id)


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

def _make_checkpoint_record(
    *,
    release_id: str,
    phase: str,
    batch_id: str | None,
    worker_id: str | None,
    status: str,
    checksum: str,
    size_bytes: int,
) -> dict[str, Any]:
    return {
        "path": checkpoint_relative_path(phase, batch_id).as_posix(),
        "status": status,
        "checksum": checksum,
        "size_bytes": size_bytes,
        "created_at": _utc_now(),
        "phase": phase,
        "batch_id": batch_id,
        "worker_id": worker_id,
        "release_id": release_id,
    }

def _metadata_key(payload: dict[str, Any]) -> str:
    required = {"path", "status", "checksum", "size_bytes", "created_at", "phase", "release_id"}
    missing = sorted(required - set(payload))
    if missing:
        raise ValueError(f"Checkpoint metadata missing required fields: {', '.join(missing)}")
    phase = payload["phase"]
    if not isinstance(phase, str):
        raise ValueError("Checkpoint metadata phase must be a string")
    batch_id = payload.get("batch_id")
    if batch_id is not None and not isinstance(batch_id, str):
        raise ValueError("Checkpoint metadata batch_id must be string or null")
    return checkpoint_name(phase, batch_id)

def _status_from_individual_metadata(store, release_id: str) -> dict[str, Any] | None:
    metadata_files = [path for path in store.list_files(_CHECKPOINT_METADATA_DIR) if path.suffix == ".json"]
    if not metadata_files:
        return None
    latest: dict[str, Any] = {}
    for metadata_path in sorted(metadata_files):
        payload = store.read_json(metadata_path)
        key = _metadata_key(payload)
        latest[key] = payload
    return {"release_id": release_id, "latest": dict(sorted(latest.items()))}


def save_checkpoint(
    release_dir: Path,
    artifact_root: Path,
    phase: str,
    batch_id: str | None = None,
    worker_id: str | None = None,
    status: str = "pass",
    artifact_backend: str | None = None,
    hf_repo_id: str | None = None,
    hf_repo_type: str | None = None,
    hf_revision: str | None = None,
    hf_token: str | None = None,
    hf_prefix: str | None = None,
) -> Path | str:
    release_dir = Path(release_dir).resolve()
    if not release_dir.exists() or not release_dir.is_dir():
        raise FileNotFoundError(release_dir)

    store = make_artifact_store_from_env(
        artifact_root=artifact_root,
        backend=artifact_backend,
        hf_repo_id=hf_repo_id,
        hf_repo_type=hf_repo_type,
        hf_revision=hf_revision,
        hf_token=hf_token,
        hf_prefix=hf_prefix,
    )
    members = _iter_phase_members(release_dir, phase, batch_id)

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_zip = Path(temp_dir) / f"{checkpoint_name(phase, batch_id)}.zip"
        with zipfile.ZipFile(temp_zip, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for member in members:
                archive.write(release_dir / member, arcname=member.as_posix())
        checksum = sha256_file(temp_zip)
        size_bytes = temp_zip.stat().st_size
        uploaded = store.upload_file(temp_zip, checkpoint_relative_path(phase, batch_id))

    record = _make_checkpoint_record(
        release_id=release_dir.name,
        phase=phase,
        batch_id=batch_id,
        worker_id=worker_id,
        status=status,
        checksum=checksum,
        size_bytes=size_bytes,
    )
    store.write_json(checkpoint_metadata_relative_path(phase, batch_id), record)

    registry = checkpoint_status(
        artifact_root,
        release_id=release_dir.name,
        artifact_backend=artifact_backend,
        hf_repo_id=hf_repo_id,
        hf_repo_type=hf_repo_type,
        hf_revision=hf_revision,
        hf_token=hf_token,
        hf_prefix=hf_prefix,
    )
    registry["release_id"] = release_dir.name
    registry.setdefault("latest", {})
    registry["latest"][_registry_key(phase, batch_id)] = record
    store.write_json(_REGISTRY_PATH, registry)
    return uploaded


def _safe_extract_zip(archive_path: Path, target_dir: Path) -> None:
    target_dir = target_dir.resolve()
    with zipfile.ZipFile(archive_path) as archive:
        for member in archive.infolist():
            member_path = Path(member.filename)
            if member_path.is_absolute():
                raise ValueError(f"Archive member must be relative: {member.filename}")
            destination = (target_dir / member_path).resolve()
            try:
                destination.relative_to(target_dir)
            except ValueError as exc:
                raise ValueError(f"Archive member escapes target directory: {member.filename}") from exc
        archive.extractall(target_dir)


def restore_checkpoint(
    output_dir: Path,
    artifact_root: Path,
    phase: str,
    batch_id: str | None = None,
    release_id: str = DEFAULT_RELEASE_ID,
    overwrite: bool = True,
    artifact_backend: str | None = None,
    hf_repo_id: str | None = None,
    hf_repo_type: str | None = None,
    hf_revision: str | None = None,
    hf_token: str | None = None,
    hf_prefix: str | None = None,
) -> Path:
    store = make_artifact_store_from_env(
        artifact_root=artifact_root,
        backend=artifact_backend,
        hf_repo_id=hf_repo_id,
        hf_repo_type=hf_repo_type,
        hf_revision=hf_revision,
        hf_token=hf_token,
        hf_prefix=hf_prefix,
    )
    relative_path = checkpoint_relative_path(phase, batch_id)
    if not store.exists(relative_path):
        raise FileNotFoundError(store.path(relative_path))

    output_dir = Path(output_dir)
    release_dir = (output_dir / release_id).resolve()
    if release_dir.exists():
        if not overwrite:
            raise FileExistsError(release_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    temporary_release_dir: Path | None = None
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_zip = Path(temp_dir) / relative_path.name
        store.download_file(relative_path, temp_zip)
        temp_restore_root = Path(
            tempfile.mkdtemp(prefix=f".{release_id}.restore.", dir=output_dir)
        )
        temporary_release_dir = temp_restore_root / release_id
        try:
            temporary_release_dir.mkdir(parents=True, exist_ok=False)
            _safe_extract_zip(temp_zip, temporary_release_dir)
            _iter_phase_members(temporary_release_dir, phase, batch_id)
            if release_dir.exists() and overwrite:
                shutil.rmtree(release_dir)
            os.replace(temporary_release_dir, release_dir)
            temp_restore_root.rmdir()
        except Exception:
            if temp_restore_root.exists():
                shutil.rmtree(temp_restore_root, ignore_errors=True)
            raise

    return release_dir


def checkpoint_status(
    artifact_root: Path,
    release_id: str = DEFAULT_RELEASE_ID,
    artifact_backend: str | None = None,
    hf_repo_id: str | None = None,
    hf_repo_type: str | None = None,
    hf_revision: str | None = None,
    hf_token: str | None = None,
    hf_prefix: str | None = None,
) -> dict[str, Any]:
    store = make_artifact_store_from_env(
        artifact_root=artifact_root,
        backend=artifact_backend,
        hf_repo_id=hf_repo_id,
        hf_repo_type=hf_repo_type,
        hf_revision=hf_revision,
        hf_token=hf_token,
        hf_prefix=hf_prefix,
    )
    if not store.exists(_REGISTRY_PATH):
        metadata_status = _status_from_individual_metadata(store, release_id)
        if metadata_status is not None:
            return metadata_status
        return {"release_id": release_id, "latest": {}}
    metadata_status = _status_from_individual_metadata(store, release_id)
    if metadata_status is not None:
        return metadata_status
    return store.read_json(_REGISTRY_PATH)
