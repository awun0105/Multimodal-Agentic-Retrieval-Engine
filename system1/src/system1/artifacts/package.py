from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ARTIFACT_MANIFEST = "artifact_manifest.json"
CHECKSUMS = "checksums.json"
_PACKAGE_METADATA = {ARTIFACT_MANIFEST, CHECKSUMS}


@dataclass(frozen=True)
class FileChecksum:
    path: str
    size_bytes: int
    sha256: str


def build_file_checksum(path: Path, *, archive_path: str) -> FileChecksum:
    digest = hashlib.sha256()
    size_bytes = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            size_bytes += len(chunk)
            digest.update(chunk)
    return FileChecksum(path=archive_path, size_bytes=size_bytes, sha256=digest.hexdigest())


def build_artifact_manifest(
    *,
    video_id: str,
    artifact_type: str,
    batch_id: str,
    worker_id: str,
    status: str,
    files: list[FileChecksum],
    schema_version: str = "1.0.0",
    created_at: str | None = None,
) -> dict[str, Any]:
    return {
        "artifact_id": f"{video_id}_{artifact_type}",
        "video_id": video_id,
        "artifact_type": artifact_type,
        "batch_id": batch_id,
        "worker_id": worker_id,
        "status": status,
        "schema_version": schema_version,
        "created_at": created_at or datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "files": [
            {
                "path": item.path,
                "size_bytes": item.size_bytes,
                "sha256": item.sha256,
            }
            for item in files
        ],
    }


def write_artifact_zip(
    *,
    artifact_dir: Path,
    zip_path: Path,
    video_id: str,
    artifact_type: str,
    batch_id: str,
    worker_id: str,
    status: str,
    schema_version: str = "1.0.0",
) -> Path:
    artifact_dir = artifact_dir.resolve()
    zip_path.parent.mkdir(parents=True, exist_ok=True)

    files = _collect_payload_checksums(artifact_dir, video_id)
    checksums = {
        item.path: {
            "size_bytes": item.size_bytes,
            "sha256": item.sha256,
        }
        for item in files
    }
    _write_json(artifact_dir / CHECKSUMS, checksums)
    _write_json(
        artifact_dir / ARTIFACT_MANIFEST,
        build_artifact_manifest(
            video_id=video_id,
            artifact_type=artifact_type,
            batch_id=batch_id,
            worker_id=worker_id,
            status=status,
            schema_version=schema_version,
            files=files,
        ),
    )

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(artifact_dir.rglob("*")):
            if path.is_file():
                archive.write(path, arcname=f"{video_id}/{path.relative_to(artifact_dir).as_posix()}")
    return zip_path


def discover_artifact_zip(artifact_root: Path | str, *, video_id: str, artifact_type: str) -> Path | None:
    artifact_root = Path(artifact_root)
    suffix = _artifact_suffix(artifact_type)
    filename = f"{video_id}_{suffix}.zip"
    direct = artifact_root / filename
    if direct.is_file():
        return direct
    if not artifact_root.exists():
        return None
    matches = sorted(path for path in artifact_root.rglob(filename) if path.is_file())
    if len(matches) > 1:
        raise ValueError(f"multiple {artifact_type} artifact zips found for video_id={video_id}: {matches}")
    return matches[0] if matches else None


def validate_artifact_zip(zip_path: Path | str) -> dict[str, Any]:
    zip_path = Path(zip_path)
    with zipfile.ZipFile(zip_path) as archive:
        names = {name for name in archive.namelist() if not name.endswith("/")}
        manifest_name = _single_metadata_path(names, ARTIFACT_MANIFEST)
        checksums_name = _single_metadata_path(names, CHECKSUMS)
        manifest = json.loads(archive.read(manifest_name).decode("utf-8"))
        checksums = json.loads(archive.read(checksums_name).decode("utf-8"))

        required = {"artifact_id", "video_id", "artifact_type", "files"}
        missing = sorted(required - set(manifest))
        if missing:
            raise ValueError(f"artifact manifest missing fields: {missing}")
        video_id = str(manifest["video_id"])
        root_prefix = f"{video_id}/"
        if manifest_name != f"{root_prefix}{ARTIFACT_MANIFEST}":
            raise ValueError(f"artifact manifest must live under {root_prefix}")
        if checksums_name != f"{root_prefix}{CHECKSUMS}":
            raise ValueError(f"checksums.json must live under {root_prefix}")
        outside_root = sorted(name for name in names if not name.startswith(root_prefix))
        if outside_root:
            raise ValueError(f"artifact zip contains files outside {root_prefix}: {outside_root}")
        if not isinstance(manifest["files"], list) or not manifest["files"]:
            raise ValueError("artifact manifest files must be a non-empty list")
        if not isinstance(checksums, dict) or not checksums:
            raise ValueError("checksums.json must be a non-empty object")

        manifest_files = {str(item.get("path")): item for item in manifest["files"]}
        if set(manifest_files) != set(checksums):
            raise ValueError("artifact manifest files do not match checksums.json")
        payload_names = {name for name in names if Path(name).name not in _PACKAGE_METADATA}
        if payload_names != set(checksums):
            missing_checksums = sorted(payload_names - set(checksums))
            stale_checksums = sorted(set(checksums) - payload_names)
            raise ValueError(
                "artifact payload files do not match checksums.json "
                f"(missing_checksums={missing_checksums}, stale_checksums={stale_checksums})"
            )

        for path, expected in checksums.items():
            if path in {manifest_name, checksums_name} or Path(path).name in _PACKAGE_METADATA:
                raise ValueError(f"package metadata must not be checksummed: {path}")
            if not str(path).startswith(root_prefix):
                raise ValueError(f"checksummed path must live under {root_prefix}: {path}")
            if path not in names:
                raise ValueError(f"checksummed file missing from zip: {path}")
            data = archive.read(path)
            size_bytes = len(data)
            sha256 = hashlib.sha256(data).hexdigest()
            if int(expected["size_bytes"]) != size_bytes or str(expected["sha256"]) != sha256:
                raise ValueError(f"checksum mismatch for {path}")
            manifest_item = manifest_files[path]
            if int(manifest_item["size_bytes"]) != size_bytes or str(manifest_item["sha256"]) != sha256:
                raise ValueError(f"artifact manifest checksum mismatch for {path}")
    return manifest


def extract_artifact_zip(
    zip_path: Path | str,
    destination: Path | str,
    *,
    expected_video_id: str | None = None,
    expected_artifact_type: str | None = None,
) -> Path:
    zip_path = Path(zip_path)
    destination = Path(destination)
    manifest = validate_artifact_zip(zip_path)
    video_id = str(manifest["video_id"])
    artifact_type = str(manifest["artifact_type"])
    if expected_video_id is not None and video_id != expected_video_id:
        raise ValueError(f"artifact video_id mismatch for {zip_path}: expected {expected_video_id}, got {video_id}")
    if expected_artifact_type is not None and artifact_type != expected_artifact_type:
        raise ValueError(
            f"artifact type mismatch for {zip_path}: expected {expected_artifact_type}, got {artifact_type}"
        )

    destination.mkdir(parents=True, exist_ok=True)
    target_root = destination / video_id
    if target_root.exists():
        shutil.rmtree(target_root)

    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.infolist():
            if member.is_dir():
                continue
            target = _safe_member_target(destination, member.filename)
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)
    return target_root


def _collect_payload_checksums(artifact_dir: Path, video_id: str) -> list[FileChecksum]:
    files: list[FileChecksum] = []
    for path in sorted(artifact_dir.rglob("*")):
        if not path.is_file() or path.name in _PACKAGE_METADATA:
            continue
        archive_path = f"{video_id}/{path.relative_to(artifact_dir).as_posix()}"
        files.append(build_file_checksum(path, archive_path=archive_path))
    if not files:
        raise FileNotFoundError(f"no artifact payload files found under {artifact_dir}")
    return files


def _artifact_suffix(artifact_type: str) -> str:
    if artifact_type == "features":
        return "features"
    if artifact_type == "structure":
        return "structure"
    raise ValueError(f"unsupported artifact_type={artifact_type!r}")


def _safe_member_target(destination: Path, member_name: str) -> Path:
    member_path = Path(member_name)
    if member_path.is_absolute() or ".." in member_path.parts:
        raise ValueError(f"unsafe artifact zip member path: {member_name}")
    destination_resolved = destination.resolve()
    target = (destination_resolved / member_path).resolve()
    target.relative_to(destination_resolved)
    return target


def _single_metadata_path(names: set[str], filename: str) -> str:
    matches = sorted(name for name in names if Path(name).name == filename)
    if len(matches) != 1:
        raise ValueError(f"expected exactly one {filename}, found {len(matches)}")
    return matches[0]


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
