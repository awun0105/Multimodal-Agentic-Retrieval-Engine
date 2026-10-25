"""Build the runtime release for System 2 from per-video worker packages.

Layout (docs/architecture/system1-target.md, "Runtime Contract For System 2"):

    release/
      manifest.json
      db/app.sqlite             cut_segments, shots, keyframes, text_documents,
                                text_documents_fts (FTS5 over text, text_unaccented)
      indexes/image_siglip2.faiss + image_siglip2_vector_map.parquet
      indexes/text_e5.faiss + text_e5_vector_map.parquet
      media/keyframes/, media/thumbnails/
"""

from __future__ import annotations

import json
import shutil
import sqlite3
from collections.abc import Sequence
from pathlib import Path

import numpy as np
import pandas as pd

from system1.artifacts.package import extract_artifact_zip, validate_artifact_zip
from system1.indexes.vectors import build_vector_index
from system1.worker.package import PackageError, validate_package

IMAGE_INDEX = "image_siglip2"
TEXT_INDEX = "text_e5"
TABLES = ("cut_segments", "shots", "keyframes", "text_documents")


class ReleaseError(ValueError):
    pass


def build_release(package_zips: Sequence[Path], out_dir: Path, *, release_id: str) -> Path:
    """Validate every package, then write the release into `out_dir`."""

    out_dir = Path(out_dir)
    if out_dir.exists():
        shutil.rmtree(out_dir)
    staging = out_dir / ".staging"
    packages = _extract(package_zips, staging)

    tables = {name: pd.concat([pd.read_parquet(path / f"{name}.parquet") for path in packages.values()],
                              ignore_index=True) for name in TABLES}
    image_vectors = np.concatenate([np.load(path / "image_vectors.npy") for path in packages.values()])
    text_vectors = [np.load(path / "text_vectors.npy") for path in packages.values()]
    text_vectors = [vectors for vectors in text_vectors if len(vectors)]

    media = out_dir / "media"
    for path in packages.values():
        for folder in ("keyframes", "thumbnails"):
            shutil.copytree(path / folder, media / folder, dirs_exist_ok=True)

    (out_dir / "db").mkdir(parents=True)
    _write_database(out_dir / "db" / "app.sqlite", tables)
    indexes = out_dir / "indexes"
    build_vector_index(indexes, IMAGE_INDEX, image_vectors, tables["keyframes"]["keyframe_id"].tolist())
    if text_vectors:
        build_vector_index(indexes, TEXT_INDEX, np.concatenate(text_vectors),
                           tables["text_documents"]["doc_id"].tolist())

    manifests = {video_id: json.loads((path / "manifest.json").read_text(encoding="utf-8"))
                 for video_id, path in packages.items()}
    first = next(iter(manifests.values()))
    manifest = {
        "schema_version": "release_v1",
        "release_id": release_id,
        "videos": sorted(packages),
        "models": first["models"],
        "counts": {name: len(table) for name, table in tables.items()},
        "indexes": {IMAGE_INDEX: len(image_vectors),
                    TEXT_INDEX: int(sum(len(vectors) for vectors in text_vectors))},
        "degraded_stages": {video_id: sorted(stage for stage, report in m["stages"].items()
                                             if report["status"] in ("failed", "fallback"))
                            for video_id, m in manifests.items()},
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    shutil.rmtree(staging)
    return out_dir


def _extract(package_zips: Sequence[Path], staging: Path) -> dict[str, Path]:
    packages: dict[str, Path] = {}
    for zip_path in package_zips:
        try:
            video_id = str(validate_artifact_zip(zip_path)["video_id"])
            if video_id in packages:
                raise ReleaseError(f"duplicate package for video {video_id}: {zip_path}")
            root = extract_artifact_zip(zip_path, staging, expected_artifact_type="worker")
            validate_package(root, video_id=video_id)
        except ReleaseError:
            raise
        except (ValueError, KeyError, OSError, PackageError) as exc:
            raise ReleaseError(f"invalid package {zip_path}: {exc}") from exc
        packages[video_id] = root
    if not packages:
        raise ReleaseError("no packages given")
    return packages


def _write_database(path: Path, tables: dict[str, pd.DataFrame]) -> None:
    with sqlite3.connect(path) as db:
        for name, table in tables.items():
            table.to_sql(name, db, index=False)
        db.executescript(
            """
            CREATE UNIQUE INDEX keyframes_id ON keyframes(keyframe_id);
            CREATE INDEX keyframes_video_time ON keyframes(video_id, timestamp_sec);
            CREATE UNIQUE INDEX shots_id ON shots(shot_id);
            CREATE UNIQUE INDEX text_documents_id ON text_documents(doc_id);
            CREATE INDEX text_documents_video_time ON text_documents(video_id, start_sec);
            CREATE VIRTUAL TABLE text_documents_fts USING fts5(
                text, text_unaccented, content='text_documents', content_rowid='rowid',
                tokenize='unicode61 remove_diacritics 0');
            INSERT INTO text_documents_fts(text_documents_fts) VALUES('rebuild');
            """
        )
