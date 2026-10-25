"""Build the runtime release for System 2 from per-video worker and caption packages.

Layout (docs/architecture/data-contracts.md, "Runtime Release"):

    {out_dir}/release/
      manifest.json             release_v2
      db/app.sqlite             videos, cut_segments, shots, scenes, keyframes, text_documents,
                                text_documents_fts (FTS5 over text, text_unaccented), vector_map
      indexes/image_siglip2.faiss + image_siglip2_vector_map.parquet
      indexes/text_e5.faiss + text_e5_vector_map.parquet
      media/keyframes/{video_id}/*.webp, media/thumbnails/{video_id}/*.webp

The build streams one video at a time (plan Step 5f item 1): the worker package
is validated and extracted to a temporary directory, its keyframes are
re-encoded to WebP, the video's media is handed to `media_sink` (which may
upload and delete it), and the temporary directory is removed. Only tables and
vectors stay in memory until the end.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import resource
import shutil
import sqlite3
import tempfile
import zipfile
from collections.abc import Callable, Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from PIL import Image

from system1.artifacts.package import extract_artifact_zip, validate_artifact_zip
from system1.indexes.vectors import build_vector_index
from system1.worker.package import SCHEMA_DIR, PackageError, validate_package, validate_table

IMAGE_INDEX = "image_siglip2"
TEXT_INDEX = "text_e5"
PACKAGE_TABLES = ("cut_segments", "shots", "keyframes", "text_documents")
WEBP_QUALITY = 80
VIDEO_COLUMNS = ["video_id", "video_ref", "duration_sec", "fps", "frame_count", "width", "height",
                 "organizer_metadata_present", "title", "author", "channel_id", "channel_url", "description",
                 "keywords", "length", "publish_date", "thumbnail_url", "watch_url"]
SCENE_COLUMNS = ["scene_id", "video_id", "start_shot_id", "end_shot_id", "start_frame", "end_frame",
                 "start_sec", "end_sec", "shot_count"]
# videos_v2 column -> accepted Phase00 column names, first match wins.
VIDEO_SOURCES = {
    "video_id": ("video_id",),
    "video_ref": ("video_ref",),
    "duration_sec": ("duration_sec", "duration_seconds"),
    "fps": ("fps", "fps_detected"),
    "frame_count": ("frame_count",),
    "width": ("width",),
    "height": ("height",),
    "organizer_metadata_present": ("organizer_metadata_present",),
}
OPTIONAL_VIDEO_SOURCES = {name: (name,) for name in VIDEO_COLUMNS if name not in VIDEO_SOURCES}
OPTIONAL_VIDEO_SOURCES["title"] = ("title", "metadata_title")

MediaSink = Callable[[str, Path], None]
# scene_builder(video_id, evidence) -> (scenes table, {shot_id: scene_id}); evidence holds that
# video's shots, keyframes, text_documents tables and image_vectors array.
SceneBuilder = Callable[[str, Mapping[str, Any]], tuple[pd.DataFrame, Mapping[str, str]]]


class ReleaseError(ValueError):
    pass


def build_release(
    *,
    release_id: str,
    worker_zips: Iterable[Path] | Callable[[], Iterable[Path]],
    caption_zips_by_video: Mapping[str, Path] | Callable[[str], Path | None] | None = None,
    phase00_videos: pd.DataFrame | None,
    out_dir: Path,
    media_sink: MediaSink | None = None,
    scene_builder: SceneBuilder | None = None,
    progress: Callable[[Mapping[str, Any]], None] | None = None,
) -> Path:
    """Write the release into `out_dir/release` and return that directory.

    `worker_zips` may be lazy (a generator or a callable returning one), and
    `caption_zips_by_video` may be a fetcher `video_id -> Path | None`, so a
    caller can download each package only when it is needed.
    """

    out_dir = Path(out_dir)
    release = out_dir / "release"
    if release.exists():
        shutil.rmtree(release)
    media = release / "media"
    media.mkdir(parents=True)
    fetch_captions = _caption_fetcher(caption_zips_by_video)

    tables: dict[str, list[pd.DataFrame]] = {name: [] for name in (*PACKAGE_TABLES, "scenes")}
    image_vectors: list[np.ndarray] = []
    text_vectors: list[np.ndarray] = []
    manifests: dict[str, dict[str, Any]] = {}
    caption_models: dict[str, Any] = {}
    with_captions: list[str] = []

    for zip_path in (worker_zips() if callable(worker_zips) else worker_zips):
        zip_path = Path(zip_path)
        video = _read_video(zip_path, out_dir, media, seen=manifests)
        caption_zip = fetch_captions(video["video_id"])
        if caption_zip is not None:
            documents, vectors, models = _read_captions(Path(caption_zip), video["video_id"], zip_path)
            video["text_documents"] = pd.concat([video["text_documents"], documents], ignore_index=True)
            video["text_vectors"] = _stack([video["text_vectors"], vectors])
            caption_models = models
            with_captions.append(video["video_id"])
        _assign_scenes(video, scene_builder, tables["scenes"])
        for name in PACKAGE_TABLES:
            tables[name].append(video[name])
        image_vectors.append(video["image_vectors"])
        if len(video["text_vectors"]):
            text_vectors.append(video["text_vectors"])
        manifests[video["video_id"]] = video["manifest"]
        if media_sink is not None:
            media_sink(video["video_id"], media)
        if progress is not None:
            progress({"video_id": video["video_id"], "videos_done": len(manifests),
                      "keyframes": len(video["keyframes"]), "text_documents": len(video["text_documents"]),
                      "has_captions": caption_zip is not None})
    if not manifests:
        raise ReleaseError("no packages given")

    merged = {name: pd.concat(frames, ignore_index=True) for name, frames in tables.items() if frames}
    merged["scenes"] = merged.get("scenes", pd.DataFrame(columns=SCENE_COLUMNS))
    merged["videos"] = _videos_table(phase00_videos, sorted(manifests))
    merged["text_documents"] = merged["text_documents"].astype({"keyframe_id": "string"})

    indexes = release / "indexes"
    all_image = np.concatenate(image_vectors)
    build_vector_index(indexes, IMAGE_INDEX, all_image, merged["keyframes"]["keyframe_id"].tolist())
    index_sizes = {IMAGE_INDEX: len(all_image)}
    maps = [pd.read_parquet(indexes / f"{IMAGE_INDEX}_vector_map.parquet").assign(index_name=IMAGE_INDEX)]
    if text_vectors:
        all_text = _stack(text_vectors)
        build_vector_index(indexes, TEXT_INDEX, all_text, merged["text_documents"]["doc_id"].tolist())
        index_sizes[TEXT_INDEX] = len(all_text)
        maps.append(pd.read_parquet(indexes / f"{TEXT_INDEX}_vector_map.parquet").assign(index_name=TEXT_INDEX))
    merged["vector_map"] = pd.concat(maps, ignore_index=True)[["index_name", "vector_id", "item_id"]]

    for name, table in merged.items():
        try:
            validate_table(name, table)
        except PackageError as exc:
            raise ReleaseError(f"merged table {exc}") from exc

    (release / "db").mkdir()
    _write_database(release / "db" / "app.sqlite", merged)

    first = next(iter(manifests.values()))
    models = dict(first["models"])
    models.update(caption_models)
    manifest = {
        "schema_version": "release_v2",
        "release_id": release_id,
        "built_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "videos": sorted(manifests),
        "videos_with_captions": sorted(with_captions),
        "models": models,
        "counts": {name: len(table) for name, table in merged.items()},
        "indexes": index_sizes,
        "degraded_stages": {
            video_id: sorted([stage for stage, report in m["stages"].items()
                              if report["status"] in ("failed", "fallback")]
                             + ([] if video_id in with_captions else ["captions"]))
            for video_id, m in manifests.items()},
        "schema_sha256": {path.name: _sha256(path) for path in sorted(SCHEMA_DIR.glob("*.schema.json"))},
        "peak_rss_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1),
    }
    (release / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    return release


def _read_video(zip_path: Path, out_dir: Path, media: Path, *, seen: Mapping[str, Any]) -> dict[str, Any]:
    """Validate one worker package, write its WebP media, and return its tables and vectors."""

    try:
        video_id = str(validate_artifact_zip(zip_path)["video_id"])
    except (ValueError, KeyError, OSError, zipfile.BadZipFile) as exc:
        raise ReleaseError(f"invalid package {zip_path}: {exc}") from exc
    if video_id in seen:
        raise ReleaseError(f"duplicate package for video {video_id}: {zip_path}")
    with tempfile.TemporaryDirectory(dir=out_dir, prefix=".package-") as temp:
        try:
            root = extract_artifact_zip(zip_path, Path(temp), expected_artifact_type="worker")
            validate_package(root, video_id=video_id)
        except (ValueError, KeyError, OSError, PackageError) as exc:
            raise ReleaseError(f"invalid package {zip_path}: {exc}") from exc
        video: dict[str, Any] = {name: pd.read_parquet(root / f"{name}.parquet") for name in PACKAGE_TABLES}
        video["image_vectors"] = np.load(root / "image_vectors.npy")
        video["text_vectors"] = np.load(root / "text_vectors.npy")
        video["manifest"] = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        keyframes = video["keyframes"]
        webp_refs = [re.sub(r"\.jpg$", ".webp", ref) for ref in keyframes["keyframe_ref"]]
        for jpg_ref, webp_ref, thumb_ref in zip(keyframes["keyframe_ref"], webp_refs, keyframes["thumbnail_ref"]):
            target = media / webp_ref
            target.parent.mkdir(parents=True, exist_ok=True)
            with Image.open(root / jpg_ref) as image:
                image.convert("RGB").save(target, "WEBP", quality=WEBP_QUALITY)
            thumb = media / thumb_ref
            thumb.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(root / thumb_ref, thumb)
        video["keyframes"] = keyframes.assign(keyframe_ref=webp_refs)
    video["video_id"] = video_id
    return video


def _read_captions(caption_zip: Path, video_id: str, worker_zip: Path) -> tuple[pd.DataFrame, np.ndarray, dict]:
    """Caption documents and vectors of one video, tied to the exact worker package."""

    try:
        caption_video = str(validate_artifact_zip(caption_zip)["video_id"])
        with zipfile.ZipFile(caption_zip) as archive:
            manifest = json.loads(archive.read(f"{caption_video}/manifest.json"))
            documents = pd.read_parquet(io.BytesIO(archive.read(f"{caption_video}/text_documents.parquet")))
            vectors = np.load(io.BytesIO(archive.read(f"{caption_video}/text_vectors.npy")))
    except (ValueError, KeyError, OSError, zipfile.BadZipFile) as exc:
        raise ReleaseError(f"invalid caption package {caption_zip}: {exc}") from exc
    if caption_video != video_id:
        raise ReleaseError(f"caption package {caption_zip} is for {caption_video}, not {video_id}")
    if manifest.get("worker_package_sha256") != _sha256(worker_zip):
        raise ReleaseError(f"caption package {caption_zip} was built from a different worker package "
                           f"than {worker_zip} (worker_package_sha256 mismatch)")
    try:
        validate_table("text_documents", documents)
    except PackageError as exc:
        raise ReleaseError(f"caption package {caption_zip}: {exc}") from exc
    if not documents.empty and (set(documents["video_id"]) != {video_id} or vectors.shape[0] != len(documents)
                                or not np.isfinite(vectors).all()):
        raise ReleaseError(f"caption package {caption_zip}: documents and vectors do not match")
    return documents, vectors, dict(manifest.get("models", {}))


def _assign_scenes(video: dict[str, Any], scene_builder: SceneBuilder | None, scenes: list[pd.DataFrame]) -> None:
    """Hook for ADR 0026 grouping. Without a builder, `shots.scene_id` stays null."""

    shots = video["shots"]
    if scene_builder is None:
        video["shots"] = shots.assign(scene_id=pd.Series([None] * len(shots), dtype="object"))
        return
    table, shot_scene_ids = scene_builder(video["video_id"], {
        "shots": shots, "keyframes": video["keyframes"], "text_documents": video["text_documents"],
        "image_vectors": video["image_vectors"]})
    video["shots"] = shots.assign(scene_id=[shot_scene_ids.get(shot_id) for shot_id in shots["shot_id"]])
    scenes.append(table)


def _videos_table(phase00: pd.DataFrame | None, video_ids: list[str]) -> pd.DataFrame:
    """videos_v2 rows from the Phase00 videos table; a missing required column is an error."""

    if phase00 is None:
        return pd.DataFrame(columns=VIDEO_COLUMNS)
    columns: dict[str, str] = {}
    for name, sources in VIDEO_SOURCES.items():
        found = next((source for source in sources if source in phase00.columns), None)
        if found is None:
            raise ReleaseError(f"Phase00 videos table lacks required column {name!r} (accepted: {list(sources)})")
        columns[name] = found
    rows = phase00.drop_duplicates("video_id").set_index("video_id", drop=False)
    missing = sorted(set(video_ids) - set(rows.index))
    if missing:
        raise ReleaseError(f"Phase00 videos table has no row for videos {missing}")
    records = []
    for video_id in video_ids:
        source = rows.loc[video_id]
        record = {name: source[column] for name, column in columns.items()}
        for name, sources in OPTIONAL_VIDEO_SOURCES.items():
            found = next((column for column in sources if column in rows.columns), None)
            value = source[found] if found is not None else None
            record[name] = None if _is_missing(value) else value
        record["video_ref"] = str(record["video_ref"]).removeprefix("media://")
        record = {name: value.item() if isinstance(value, np.generic) else value for name, value in record.items()}
        for name in ("frame_count", "width", "height", "length"):
            if not _is_missing(record[name]):
                record[name] = int(record[name])
        if isinstance(record["keywords"], np.ndarray):
            record["keywords"] = record["keywords"].tolist()
        records.append(record)
    return pd.DataFrame(records, columns=VIDEO_COLUMNS, dtype=object)


def _write_database(path: Path, tables: Mapping[str, pd.DataFrame]) -> None:
    db = sqlite3.connect(path)
    try:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA foreign_keys=ON")
        for name, table in tables.items():
            if name == "videos" and len(table):
                table = table.assign(keywords=[None if value is None else json.dumps(value, ensure_ascii=False)
                                               for value in table["keywords"]])
            table.to_sql(name, db, index=False)
        db.executescript(
            """
            CREATE UNIQUE INDEX videos_id ON videos(video_id);
            CREATE UNIQUE INDEX shots_id ON shots(shot_id);
            CREATE INDEX shots_video_time ON shots(video_id, start_sec);
            CREATE UNIQUE INDEX scenes_id ON scenes(scene_id);
            CREATE UNIQUE INDEX keyframes_id ON keyframes(keyframe_id);
            CREATE INDEX keyframes_video_time ON keyframes(video_id, timestamp_sec);
            CREATE UNIQUE INDEX text_documents_id ON text_documents(doc_id);
            CREATE INDEX text_documents_video_time ON text_documents(video_id, start_sec);
            CREATE UNIQUE INDEX vector_map_id ON vector_map(index_name, vector_id);
            CREATE VIRTUAL TABLE text_documents_fts USING fts5(
                text, text_unaccented, content='text_documents', content_rowid='rowid',
                tokenize='unicode61 remove_diacritics 0');
            INSERT INTO text_documents_fts(text_documents_fts) VALUES('rebuild');
            """
        )
        db.commit()
        fts_rows = db.execute("SELECT count(*) FROM text_documents_fts").fetchone()[0]
        if fts_rows != len(tables["text_documents"]):
            raise ReleaseError(f"FTS has {fts_rows} rows, text_documents has {len(tables['text_documents'])}")
    finally:
        db.close()


def _caption_fetcher(source: Mapping[str, Path] | Callable[[str], Path | None] | None) -> Callable[[str], Path | None]:
    if source is None:
        return lambda video_id: None
    if callable(source):
        return source
    return lambda video_id: source.get(video_id)


def _stack(arrays: list[np.ndarray]) -> np.ndarray:
    arrays = [np.asarray(array, dtype="float32") for array in arrays if len(array)]
    if not arrays:
        return np.zeros((0, 0), dtype="float32")
    if len({array.shape[1] for array in arrays}) != 1:
        raise ReleaseError(f"text vectors have different dimensions: {sorted({a.shape[1] for a in arrays})}")
    return np.concatenate(arrays)


def _is_missing(value: Any) -> bool:
    if value is None or value is pd.NA:
        return True
    return isinstance(value, float) and np.isnan(value)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
