from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm"}
METADATA_EXTENSIONS = {".json"}
VIDEO_DIR_NAMES = {"raw_videos", "videos", "video", "raw", "clips"}
METADATA_DIR_NAMES = {"metadata", "metadatas", "json", "annotations"}


@dataclass(frozen=True)
class SourceImportResult:
    video_count: int
    metadata_count: int
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
