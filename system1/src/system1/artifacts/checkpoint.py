from __future__ import annotations

from pathlib import Path
from typing import Any
import datetime as dt
import hashlib
import os
import shutil
import tempfile
import zipfile

from system1.artifacts.factory import make_artifact_store_from_env
from system1.artifacts.reports import worker_report_relative_path
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
        return []
    if phase == "phase02_features":
        checkpoint_name(phase, batch_id)
        return []
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


def _iter_phase_members(
    release_dir: Path,
    phase: str,
    batch_id: str | None = None,
    *,
    worker_id: str | None = None,
    allow_missing_batch_manifest: bool = False,
) -> list[Path]:
    if phase in {"phase01_structure", "phase02_features"}:
        return _iter_batch_artifact_members(
            release_dir,
            phase,
            batch_id,
            worker_id=worker_id,
            allow_missing_batch_manifest=allow_missing_batch_manifest,
        )

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


def _iter_batch_artifact_members(
    release_dir: Path,
    phase: str,
    batch_id: str | None,
    *,
    worker_id: str | None,
    allow_missing_batch_manifest: bool,
) -> list[Path]:
    checkpoint_name(phase, batch_id)
    assert batch_id is not None
    report_phase, artifact_dir_name, artifact_suffix = _batch_phase_contract(phase)
    artifact_dir = release_dir / "artifacts" / artifact_dir_name
    members: set[Path] = set()

    video_ids = _read_batch_video_ids(release_dir, batch_id)
    if video_ids:
        for video_id in video_ids:
            relative_path = Path("artifacts") / artifact_dir_name / f"{video_id}_{artifact_suffix}.zip"
            if not (release_dir / relative_path).is_file():
                raise FileNotFoundError(release_dir / relative_path)
            members.add(relative_path)
    elif allow_missing_batch_manifest:
        matches = sorted(path.relative_to(release_dir) for path in artifact_dir.glob(f"*_{artifact_suffix}.zip") if path.is_file())
        if not matches:
            raise FileNotFoundError(artifact_dir / f"*_{artifact_suffix}.zip")
        members.update(matches)
    else:
        raise FileNotFoundError(release_dir / "manifests" / f"{batch_id}.txt")

    members.update(_worker_report_members(release_dir, phase=report_phase, batch_id=batch_id, worker_id=worker_id))
    return sorted(members)


def _batch_phase_contract(phase: str) -> tuple[str, str, str]:
    if phase == "phase01_structure":
        return ("structure", "structure", "structure")
    if phase == "phase02_features":
        return ("features", "features", "features")
    raise ValueError(f"Unknown batch artifact phase: {phase}")


def _read_batch_video_ids(release_dir: Path, batch_id: str) -> list[str]:
    batch_path = release_dir / "manifests" / f"{batch_id}.txt"
    if not batch_path.exists():
        return []
    return [line.strip() for line in batch_path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _worker_report_members(
    release_dir: Path,
    *,
    phase: str,
    batch_id: str,
    worker_id: str | None,
) -> list[Path]:
    if worker_id:
        report = worker_report_relative_path(phase, batch_id, worker_id)
        return [report] if (release_dir / report).is_file() else []
    report_root = release_dir / "manifests" / "worker_reports"
    return sorted(path.relative_to(release_dir) for path in report_root.glob(f"{phase}_{batch_id}_*.json") if path.is_file())


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
    members = _iter_phase_members(release_dir, phase, batch_id, worker_id=worker_id)

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
            _iter_phase_members(temporary_release_dir, phase, batch_id, allow_missing_batch_manifest=True)
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
