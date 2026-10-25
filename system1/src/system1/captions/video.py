"""Caption one video from its worker package into a caption package (ADR 0025).

The worker ZIP is read in place: only `manifest.json`, `shots.parquet`,
`keyframes.parquet`, and the representative keyframe image of each shot are
read; the package is never extracted or rewritten. Output layout:
docs/architecture/data-contracts.md, section "Caption Package".
"""

from __future__ import annotations

import hashlib
import io
import json
import time
import zipfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Protocol

import numpy as np
import pandas as pd
from PIL import Image

from system1.artifacts.package import validate_artifact_zip, write_artifact_zip
from system1.text.evidence import unaccent
from system1.worker.package import PackageError, validate_table

CAPTION_COLUMNS = ["shot_id", "keyframe_id", "caption", "objects", "actions", "visible_text", "problems"]
DOCUMENT_COLUMNS = ["doc_id", "video_id", "evidence_type", "start_sec", "end_sec", "shot_ids",
                    "keyframe_id", "text", "text_unaccented"]


class Captioner(Protocol):
    def caption(self, images: Sequence[Image.Image]) -> list[Any]: ...


class TextEmbedder(Protocol):
    def embed_passages(self, texts: Sequence[str]) -> np.ndarray: ...


def caption_video(
    zip_path: Path,
    *,
    config: Mapping[str, Any],
    captioner: Captioner,
    text_embedder: TextEmbedder,
    work_root: Path,
    batch_id: str,
    worker_id: str,
) -> Path:
    started = time.monotonic()
    video_id = str(validate_artifact_zip(zip_path)["video_id"])
    with zipfile.ZipFile(zip_path) as archive:
        worker_manifest = json.loads(archive.read(f"{video_id}/manifest.json"))
        if worker_manifest.get("video_id") != video_id:
            raise PackageError(f"worker manifest is for {worker_manifest.get('video_id')}, not {video_id}")
        keyframes = pd.read_parquet(io.BytesIO(archive.read(f"{video_id}/keyframes.parquet")))
        shots = pd.read_parquet(io.BytesIO(archive.read(f"{video_id}/shots.parquet")))
        picks = keyframes[keyframes["is_representative"].astype(bool)].reset_index(drop=True)
        images = [Image.open(io.BytesIO(archive.read(f"{video_id}/{ref}"))).convert("RGB")
                  for ref in picks["keyframe_ref"]]
    if set(picks["shot_id"]) != set(shots["shot_id"]):
        raise PackageError(f"{video_id}: some shots have no keyframe")

    results = captioner.caption(images)
    if len(results) != len(picks):
        raise ValueError(f"captioner returned {len(results)} results for {len(picks)} images")
    captions = []
    for pick, result in zip(picks.itertuples(), results):
        payload = result.payload or {}
        captions.append({"shot_id": pick.shot_id, "keyframe_id": pick.keyframe_id,
                         "caption": payload.get("caption", ""), "objects": list(payload.get("objects", [])),
                         "actions": list(payload.get("actions", [])),
                         "visible_text": payload.get("visible_text", ""), "problems": list(result.problems)})
    timestamps = dict(zip(keyframes["keyframe_id"], keyframes["timestamp_sec"]))
    documents = _documents(video_id, captions, timestamps)

    package = work_root / video_id / "package"
    package.mkdir(parents=True, exist_ok=True)
    captions_table = pd.DataFrame(captions, columns=CAPTION_COLUMNS)
    documents_table = pd.DataFrame(documents, columns=DOCUMENT_COLUMNS).astype({"keyframe_id": "string"})
    validate_table("captions", captions_table)
    validate_table("text_documents", documents_table)
    captions_table.to_parquet(package / "captions.parquet", index=False)
    documents_table.to_parquet(package / "text_documents.parquet", index=False)
    texts = documents_table["text"].tolist()
    vectors = text_embedder.embed_passages(texts) if texts else np.zeros((0, 0), dtype="float32")
    vectors = np.asarray(vectors, dtype="float32")
    if vectors.shape[0] != len(texts) or not np.isfinite(vectors).all():
        raise ValueError(f"text vectors do not match {len(texts)} documents")
    np.save(package / "text_vectors.npy", vectors)

    rejected = sum(bool(row["problems"]) for row in captions)
    manifest = {
        "schema_version": "caption_package_v1",
        "video_id": video_id,
        "worker_package_sha256": _sha256(zip_path),
        "models": {"captions": {key: config["captions"][key] for key in ("model_id", "revision")},
                   "text_embedding": {key: config["models"]["text_embedding"][key]
                                      for key in ("model_id", "revision")}},
        "stages": {"captions": {"status": "pass", "captions": len(captions) - rejected, "rejected": rejected,
                                "seconds": round(time.monotonic() - started, 1)}},
    }
    (package / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    return write_artifact_zip(artifact_dir=package, zip_path=work_root / f"{video_id}.zip", video_id=video_id,
                              artifact_type="captions", batch_id=batch_id, worker_id=worker_id,
                              status="complete")


def _documents(video_id: str, captions: list[dict[str, Any]], timestamps: Mapping[str, float]) -> list[dict]:
    """Caption and visible_text documents; a rejected caption gives none."""

    documents: list[dict[str, Any]] = []
    for row in captions:
        if row["problems"]:
            continue
        timestamp = float(timestamps[row["keyframe_id"]])
        for kind, text in (("caption", " ".join([row["caption"], *row["objects"], *row["actions"]])),
                           ("visible_text", row["visible_text"])):
            text = " ".join(text.split())
            if text:
                documents.append({"doc_id": f"{video_id}:{kind}:{len(documents):05d}", "video_id": video_id,
                                  "evidence_type": kind, "start_sec": timestamp, "end_sec": timestamp,
                                  "shot_ids": row["shot_id"], "keyframe_id": row["keyframe_id"],
                                  "text": text, "text_unaccented": unaccent(text)})
    return documents


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
