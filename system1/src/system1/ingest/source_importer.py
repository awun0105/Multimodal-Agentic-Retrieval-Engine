from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse
from typing import Any

from system1.artifacts.hf_store import HuggingFaceDatasetArtifactStore

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".wav"}
METADATA_EXTENSIONS = {".json"}
VIDEO_DIR_NAMES = {"raw_videos", "videos", "video", "raw", "clips"}
METADATA_DIR_NAMES = {"metadata", "metadatas", "json", "annotations"}


@dataclass(frozen=True)
class SourceImportResult:
    video_count: int
    metadata_count: int
    report_path: Path


@dataclass(frozen=True)
class CanonicalImportResult:
    video_count: int
    metadata_count: int
    report_path: Path | str


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

    drive_service = service or _build_google_drive_service()
    rows: list[dict[str, Any]] = []
    counters = {
        "copied_files": 0,
        "created_folders": 0,
        "skipped_google_apps": 0,
        "skipped_existing": 0,
        "error_count": 0,
    }

    def copy_folder_contents(source_id: str, target_id: str, logical_path: str = "") -> None:
        source_children = _list_drive_children(drive_service, source_id)
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
                    copy_folder_contents(item_id, str(existing_target["id"]), item_path)
                    continue
                folder_metadata = {
                    "name": item_name,
                    "mimeType": "application/vnd.google-apps.folder",
                    "parents": [target_id],
                }
                try:
                    new_folder = drive_service.files().create(body=folder_metadata, fields="id").execute()
                    counters["created_folders"] += 1
                    rows.append({"kind": "folder", "source_id": item_id, "name": item_name, "path": item_path, "status": "created"})
                    copy_folder_contents(item_id, str(new_folder["id"]), item_path)
                except Exception as exc:
                    counters["error_count"] += 1
                    rows.append({"kind": "folder", "source_id": item_id, "name": item_name, "path": item_path, "status": "failed", "error": str(exc)})
                continue

            if mime_type.startswith("application/vnd.google-apps"):
                counters["skipped_google_apps"] += 1
                rows.append({"kind": "google_app", "source_id": item_id, "name": item_name, "path": item_path, "status": "skipped"})
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
                    continue
                counters["error_count"] += 1
                rows.append({"kind": "file", "source_id": item_id, "name": item_name, "path": item_path, "status": "failed", "error": "target file exists but size does not match source"})
                continue

            copy_metadata = {"name": item_name, "parents": [target_id]}
            try:
                drive_service.files().copy(fileId=item_id, body=copy_metadata).execute()
                counters["copied_files"] += 1
                rows.append({"kind": "file", "source_id": item_id, "name": item_name, "path": item_path, "status": "copied"})
            except Exception as exc:
                counters["error_count"] += 1
                rows.append({"kind": "file", "source_id": item_id, "name": item_name, "path": item_path, "status": "failed", "error": str(exc)})

    copy_folder_contents(source_folder_id, dest_folder_id)
    report = {
        "status": "pass" if counters["error_count"] == 0 else "partial",
        "source_folder_id": source_folder_id,
        "dest_folder_id": dest_folder_id,
        **counters,
        "items": rows,
    }
    resolved_report_path = Path(report_path).expanduser().resolve()
    resolved_report_path.parent.mkdir(parents=True, exist_ok=True)
    resolved_report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
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
) -> ArchiveStandardizeResult:
    """Extract nested zip archives into target raw_videos/ and metadata/ folders."""
    source_root = Path(source_dir).expanduser().resolve()
    target_root = Path(target_dir).expanduser().resolve()
    if not source_root.exists() or not source_root.is_dir():
        raise FileNotFoundError(f"archive source directory does not exist: {source_root}")

    raw_root = target_root / "raw_videos"
    metadata_root = target_root / "metadata"
    temp_root = Path(temp_dir).expanduser().resolve() if temp_dir else target_root / ".tmp_archive_extract"
    raw_root.mkdir(parents=True, exist_ok=True)
    metadata_root.mkdir(parents=True, exist_ok=True)
    temp_root.mkdir(parents=True, exist_ok=True)

    accepted_media_extensions = {ext.lower() for ext in (media_extensions or VIDEO_EXTENSIONS)}
    rows: list[dict[str, Any]] = []
    counters = {
        "zip_count": 0,
        "video_count": 0,
        "metadata_count": 0,
        "skipped_count": 0,
        "error_count": 0,
    }

    for zip_path in sorted(source_root.rglob("*.zip")):
        counters["zip_count"] += 1
        batch_temp = temp_root / zip_path.stem
        if batch_temp.exists():
            shutil.rmtree(batch_temp)
        batch_temp.mkdir(parents=True, exist_ok=True)
        try:
            _safe_extract_zip(zip_path, batch_temp)
        except (OSError, zipfile.BadZipFile, ValueError) as exc:
            counters["error_count"] += 1
            rows.append({"archive": str(zip_path), "status": "failed", "error": str(exc)})
            shutil.rmtree(batch_temp, ignore_errors=True)
            continue

        for item in sorted(batch_temp.rglob("*")):
            if not item.is_file():
                continue
            suffix = item.suffix.lower()
            if suffix in accepted_media_extensions:
                target = raw_root / f"{zip_path.stem}_{item.name}"
                try:
                    status = _move_flattened_file(item, target, overwrite=overwrite)
                    if status == "moved":
                        counters["video_count"] += 1
                    else:
                        counters["skipped_count"] += 1
                    rows.append({"archive": str(zip_path), "kind": "media", "source": str(item), "target": str(target), "status": status})
                except OSError as exc:
                    counters["error_count"] += 1
                    rows.append({"archive": str(zip_path), "kind": "media", "source": str(item), "target": str(target), "status": "failed", "error": str(exc)})
            elif suffix in METADATA_EXTENSIONS:
                target = metadata_root / f"{zip_path.stem}_{item.name}"
                try:
                    status = _move_flattened_file(item, target, overwrite=overwrite)
                    if status == "moved":
                        counters["metadata_count"] += 1
                    else:
                        counters["skipped_count"] += 1
                    rows.append({"archive": str(zip_path), "kind": "metadata", "source": str(item), "target": str(target), "status": status})
                except OSError as exc:
                    counters["error_count"] += 1
                    rows.append({"archive": str(zip_path), "kind": "metadata", "source": str(item), "target": str(target), "status": "failed", "error": str(exc)})
            else:
                counters["skipped_count"] += 1
                rows.append({"archive": str(zip_path), "kind": "unsupported", "source": str(item), "status": "skipped"})
        shutil.rmtree(batch_temp, ignore_errors=True)

    report = {
        "status": "pass" if counters["error_count"] == 0 else "partial",
        "source_dir": str(source_root),
        "target_dir": str(target_root),
        "raw_videos": str(raw_root),
        "metadata": str(metadata_root),
        "media_extensions": sorted(accepted_media_extensions),
        **counters,
        "items": rows,
    }
    report_path = target_root / "standardize_archives_report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return ArchiveStandardizeResult(report_path=report_path, **counters)


def import_source_to_hf_canonical(
    source_uri: str,
    *,
    repo_id: str,
    prefix: str = "",
    repo_type: str = "dataset",
    revision: str = "main",
    token: str | None = None,
    staging_root: Path | str | None = None,
) -> CanonicalImportResult:
    """Normalize an organizer source into a Hugging Face Dataset repository.

    The source is materialized in a temporary staging directory only long enough
    to discover and upload files. The target repository must already exist.
    """
    if not source_uri:
        raise ValueError("source_uri is required")
    if not repo_id:
        raise ValueError("repo_id is required")

    store = HuggingFaceDatasetArtifactStore(
        repo_id=repo_id,
        repo_type=repo_type,
        revision=revision,
        token=token or os.environ.get("AIC_HF_TOKEN") or os.environ.get("HF_TOKEN"),
        prefix=prefix,
    )
    staging_parent = Path(staging_root).expanduser().resolve() if staging_root else None
    if staging_parent:
        staging_parent.mkdir(parents=True, exist_ok=True)

    existing_files = {path.as_posix() for path in store.list_files("")}
    uploaded_rows: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    with tempfile.TemporaryDirectory(prefix="system1_canonical_import_", dir=staging_parent) as tmp:
        source_root = _materialize_source(source_uri, Path(tmp))
        video_files = _find_video_files(source_root)
        metadata_files = _find_metadata_files(source_root)
        video_by_stem = _index_unique_by_stem(video_files, kind="video")
        metadata_by_stem = _index_unique_by_stem(metadata_files, kind="metadata")

        for video_id in sorted(video_by_stem):
            video_path = video_by_stem[video_id]
            metadata_path = metadata_by_stem.get(video_id)
            generated_metadata_path: Path | None = None
            if metadata_path is None:
                generated_metadata_path = Path(tmp) / "generated_metadata" / f"{video_id}.json"
                _write_minimal_metadata(generated_metadata_path, video_id, source_uri)
                metadata_path = generated_metadata_path

            video_remote_path = PureCanonicalPath.raw_video(video_path.name)
            metadata_remote_path = PureCanonicalPath.metadata(f"{video_id}.json")
            row = {
                "video_id": video_id,
                "video_filename": video_path.name,
                "metadata_filename": f"{video_id}.json",
                "video_path": video_remote_path,
                "metadata_path": metadata_remote_path,
                "video_size_bytes": video_path.stat().st_size,
                "metadata_size_bytes": metadata_path.stat().st_size,
                "metadata_generated": generated_metadata_path is not None,
                "status": "pending",
            }
            try:
                _upload_if_needed(store, existing_files, video_path, video_remote_path)
                _upload_if_needed(store, existing_files, metadata_path, metadata_remote_path)
                row["status"] = "pass"
            except Exception as exc:
                row["status"] = "failed"
                row["error"] = str(exc)
                errors.append({"video_id": video_id, "message": str(exc)})
            uploaded_rows.append(row)

    report = {
        "status": "pass" if not errors else "fail",
        "source_uri": source_uri,
        "repo_id": repo_id,
        "repo_type": repo_type,
        "revision": revision,
        "prefix": prefix,
        "video_count": len([row for row in uploaded_rows if row["status"] == "pass"]),
        "metadata_count": len([row for row in uploaded_rows if row["status"] == "pass"]),
        "error_count": len(errors),
        "errors": errors,
    }
    manifest_text = "".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in uploaded_rows)
    with tempfile.TemporaryDirectory(prefix="system1_canonical_manifest_") as tmp:
        tmp_path = Path(tmp)
        manifest_path = tmp_path / "canonical_file_manifest.jsonl"
        report_path = tmp_path / "canonical_import_report.json"
        manifest_path.write_text(manifest_text, encoding="utf-8")
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
        store.upload_file(manifest_path, "manifests/canonical_file_manifest.jsonl")
        uploaded_report = store.upload_file(report_path, "manifests/canonical_import_report.json")

    if errors:
        raise RuntimeError(f"canonical import failed for {len(errors)} file pair(s); report: {uploaded_report}")
    return CanonicalImportResult(
        video_count=int(report["video_count"]),
        metadata_count=int(report["metadata_count"]),
        report_path=uploaded_report,
    )


class PureCanonicalPath:
    @staticmethod
    def raw_video(filename: str) -> str:
        return f"raw_videos/{filename}"

    @staticmethod
    def metadata(filename: str) -> str:
        return f"metadata/{filename}"


def _upload_if_needed(store: HuggingFaceDatasetArtifactStore, existing_files: set[str], source: Path, relative_path: str) -> None:
    if relative_path in existing_files:
        return
    store.upload_file(source, relative_path)
    existing_files.add(relative_path)


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


def _list_drive_children(service: Any, folder_id: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    page_token: str | None = None
    while True:
        result = service.files().list(
            q=f"'{folder_id}' in parents and trashed=false",
            fields="nextPageToken, files(id, name, mimeType, size)",
            pageToken=page_token,
        ).execute()
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
