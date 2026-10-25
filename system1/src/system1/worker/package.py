"""Packaging-time output validator for one video (ADR 0024).

This is the single place that rejects corrupted output. Missing or weak evidence
(no speech, no text) is not an error here; it is recorded in the manifest stage
reports. Every table is also checked against its JSON schema in
`system1/schemas/v2/` (docs/architecture/data-contracts.md).
"""

from __future__ import annotations

import json
import math
from functools import cache
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from jsonschema import Draft202012Validator

SCHEMA_DIR = Path(__file__).resolve().parents[3] / "schemas" / "v2"
EVIDENCE_TYPES = {"asr", "ocr"}
TABLES = ("cut_segments", "shots", "keyframes", "asr_segments", "ocr", "text_documents")
REQUIRED_FILES = (
    "manifest.json", *(f"{name}.parquet" for name in TABLES), "image_vectors.npy", "text_vectors.npy",
)


class PackageError(ValueError):
    pass


def validate_package(package_dir: Path, *, video_id: str) -> None:
    missing = [name for name in REQUIRED_FILES if not (package_dir / name).is_file()]
    if missing:
        raise PackageError(f"missing package files: {missing}")
    for name in TABLES:
        validate_table(name, pd.read_parquet(package_dir / f"{name}.parquet"))

    cuts = pd.read_parquet(package_dir / "cut_segments.parquet")
    shots = pd.read_parquet(package_dir / "shots.parquet")
    keyframes = pd.read_parquet(package_dir / "keyframes.parquet")
    documents = pd.read_parquet(package_dir / "text_documents.parquet")
    _check(not keyframes.empty, "keyframes.parquet is empty")
    for name, table in (("cut_segments", cuts), ("shots", shots), ("keyframes", keyframes),
                        ("text_documents", documents)):
        _check(table.empty or set(table["video_id"]) == {video_id}, f"{name} has rows for another video")

    cut_ranges = cuts.set_index("cut_segment_id")[["start_frame", "end_frame"]]
    for row in shots.itertuples():
        _check(row.cut_segment_id in cut_ranges.index, f"shot {row.shot_id} has unknown cut segment")
        start, end = cut_ranges.loc[row.cut_segment_id]
        _check(start <= row.start_frame < row.end_frame <= end,
               f"shot {row.shot_id} is outside cut segment {row.cut_segment_id}")

    _check(keyframes["keyframe_id"].is_unique, "keyframe_id is not unique")
    expected_ids = [f"{video_id}:{frame}" for frame in keyframes["frame_id"]]
    _check(keyframes["keyframe_id"].tolist() == expected_ids, "keyframe_id is not {video_id}:{frame_id}")
    _check((keyframes.groupby("shot_id")["is_representative"].sum() == 1).all(),
           "every shot needs exactly one representative keyframe")
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


def validate_table(name: str, table: pd.DataFrame) -> None:
    """Check every row of `table` against `schemas/v2/{name}.schema.json`."""

    validator = _validator(name)
    for index, row in enumerate(table.to_dict("records")):
        try:
            record = {key: _python(value) for key, value in row.items()}
        except ValueError as exc:
            raise PackageError(f"{name} row {index}: {exc}") from exc
        error = next(iter(validator.iter_errors(record)), None)
        if error is not None:
            path = "/".join(str(part) for part in error.absolute_path) or "row"
            raise PackageError(f"{name} row {index} violates {name}.schema.json at {path}: {error.message}")


def representative_keyframes(keyframes: pd.DataFrame, vectors: np.ndarray | None = None) -> pd.DataFrame:
    """One keyframe per shot, in time order. The keyframe captioned for the shot.

    With `vectors` (one row per keyframe row) it is the keyframe closest by
    cosine to the mean vector of the shot's keyframes; without them, the middle one.
    """

    picks = []
    for _, group in keyframes.groupby("shot_id", sort=False):
        if vectors is None:
            picks.append(group.iloc[len(group) // 2])
            continue
        rows = np.asarray(vectors, dtype=np.float32)[keyframes.index.get_indexer(group.index)]
        rows = rows / np.maximum(np.linalg.norm(rows, axis=1, keepdims=True), 1e-12)
        picks.append(group.iloc[int(np.argmax(rows @ rows.mean(axis=0)))])
    return pd.DataFrame(picks).reset_index(drop=True)


@cache
def _validator(name: str) -> Draft202012Validator:
    schema = json.loads((SCHEMA_DIR / f"{name}.schema.json").read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


def _python(value: Any) -> Any:
    """Convert numpy and pandas values to JSON-schema values; NaN is an error."""

    if isinstance(value, np.ndarray | list | tuple):
        return [_python(item) for item in value]
    if value is None or value is pd.NA:
        return None
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and math.isnan(value):
        raise ValueError("NaN value")
    return value


def _check_vectors(path: Path, rows: int, name: str) -> None:
    vectors = np.load(path)
    _check(vectors.shape[0] == rows, f"{name} has {vectors.shape[0]} rows, expected {rows}")
    _check(bool(np.isfinite(vectors).all()), f"{name} contains NaN or infinity")


def _check(condition: bool, message: str) -> None:
    if not condition:
        raise PackageError(message)
