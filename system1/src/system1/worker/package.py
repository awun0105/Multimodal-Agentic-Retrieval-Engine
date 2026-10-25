"""Packaging-time output validator for one video (ADR 0024).

This is the single place that rejects corrupted output. Missing or weak evidence
(no speech, no text, failed captions) is not an error here; it is recorded in
the manifest stage reports.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

EVIDENCE_TYPES = {"asr", "ocr", "caption", "visible_text"}
REQUIRED_FILES = (
    "manifest.json", "shots.parquet", "keyframes.parquet", "image_vectors.npy",
    "asr_segments.parquet", "ocr.parquet", "captions.parquet", "text_documents.parquet",
    "text_vectors.npy",
)


class PackageError(ValueError):
    pass


def validate_package(package_dir: Path, *, video_id: str) -> None:
    missing = [name for name in REQUIRED_FILES if not (package_dir / name).is_file()]
    if missing:
        raise PackageError(f"missing package files: {missing}")

    shots = pd.read_parquet(package_dir / "shots.parquet")
    keyframes = pd.read_parquet(package_dir / "keyframes.parquet")
    documents = pd.read_parquet(package_dir / "text_documents.parquet")
    _check(not keyframes.empty, "keyframes.parquet is empty")
    for name, table in (("shots", shots), ("keyframes", keyframes), ("text_documents", documents)):
        _check(table.empty or set(table["video_id"]) == {video_id}, f"{name} has rows for another video")

    _check(keyframes["keyframe_id"].is_unique, "keyframe_id is not unique")
    expected_ids = [f"{video_id}:{frame}" for frame in keyframes["frame_id"]]
    _check(keyframes["keyframe_id"].tolist() == expected_ids, "keyframe_id is not {video_id}:{frame_id}")
    ranges = shots.set_index("shot_id")[["start_frame", "end_frame"]]
    for row in keyframes.itertuples():
        _check(row.shot_id in ranges.index, f"keyframe {row.keyframe_id} has unknown shot {row.shot_id}")
        start, end = ranges.loc[row.shot_id]
        _check(start <= row.frame_id < end, f"keyframe {row.keyframe_id} is outside shot {row.shot_id}")
        for ref in (row.keyframe_ref, row.thumbnail_ref):
            _check((package_dir / ref).is_file(), f"missing media file {ref}")

    _check_vectors(package_dir / "image_vectors.npy", len(keyframes), "image_vectors")
    _check(documents.empty or documents["doc_id"].is_unique, "doc_id is not unique")
    _check(set(documents["evidence_type"]) <= EVIDENCE_TYPES, "unknown evidence_type in text_documents")
    _check(documents.empty or documents["text"].str.strip().astype(bool).all(), "empty text document")
    _check_vectors(package_dir / "text_vectors.npy", len(documents), "text_vectors")


def _check_vectors(path: Path, rows: int, name: str) -> None:
    vectors = np.load(path)
    _check(vectors.shape[0] == rows, f"{name} has {vectors.shape[0]} rows, expected {rows}")
    _check(bool(np.isfinite(vectors).all()), f"{name} contains NaN or infinity")


def _check(condition: bool, message: str) -> None:
    if not condition:
        raise PackageError(message)
