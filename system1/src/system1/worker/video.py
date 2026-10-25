"""Process one video into a packaged, validated artifact ZIP.

Stages: shots, keyframes, image vectors, ASR, OCR, captions, text documents,
text vectors, package. Each stage has a checkpoint (`stages.StageRunner`).
Shots, keyframes, and image vectors are required; ASR, OCR, and captions
degrade to empty output and a failed status (ADR 0024).
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import numpy as np
import pandas as pd
from PIL import Image

from system1.artifacts.package import write_artifact_zip
from system1.keyframes.adaptive import AdaptiveKeyframePolicy, plan_candidate_frames, select_adaptive_keyframes
from system1.keyframes.builder import iter_decode_frame_groups, write_keyframe_images
from system1.providers.ocr import clean_ocr_lines
from system1.text.evidence import (
    AsrSegment,
    chunk_asr_segments,
    shots_for_interval,
    strip_video_wide_repeats,
    unaccent,
)
from system1.worker.package import validate_package
from system1.worker.stages import StageRunner

SHOT_COLUMNS = ["shot_id", "video_id", "shot_index", "start_frame", "end_frame", "start_sec", "end_sec"]
DOCUMENT_COLUMNS = ["doc_id", "video_id", "evidence_type", "start_sec", "end_sec", "shot_ids",
                    "keyframe_id", "text", "text_unaccented"]


class ImageEmbedder(Protocol):
    def embed_images(self, images: Sequence[Image.Image]) -> np.ndarray: ...


class SpeechRecognizer(Protocol):
    def transcribe(self, video_path: Path, wav_path: Path) -> list[AsrSegment]: ...


class TextReader(Protocol):
    def read(self, image: Image.Image) -> list[str]: ...


class Captioner(Protocol):
    def caption(self, images: Sequence[Image.Image]) -> list[Any]: ...


class TextEmbedder(Protocol):
    def embed_passages(self, texts: Sequence[str]) -> np.ndarray: ...


@dataclass(frozen=True)
class VideoInput:
    video_id: str
    video_path: Path
    timeline_rows: list[dict[str, Any]]


@dataclass
class WorkerModels:
    shots: Callable[[Path, list[dict[str, Any]], Path], list[dict[str, Any]]]
    image: ImageEmbedder
    asr: SpeechRecognizer
    ocr: TextReader
    captioner: Captioner | None
    text: TextEmbedder


def process_video(
    video: VideoInput,
    *,
    config: Mapping[str, Any],
    models: WorkerModels,
    work_root: Path,
    batch_id: str,
    worker_id: str,
) -> Path:
    video_id = video.video_id
    root = work_root / video_id
    package = root / "package"
    package.mkdir(parents=True, exist_ok=True)
    (root / "scratch").mkdir(exist_ok=True)
    runner = StageRunner(root / "stages")
    model_config = config["models"]
    text_config = config["text"]

    def shots_stage():
        rows = models.shots(video.video_path, video.timeline_rows, root / "scratch")
        pd.DataFrame(rows)[SHOT_COLUMNS].to_parquet(package / "shots.parquet", index=False)
        return {"status": "pass", "shots": len(rows)}

    def keyframes_stage():
        rows, empty = _write_keyframes(video, pd.read_parquet(package / "shots.parquet"),
                                       config["keyframes"], package)
        if not rows:
            raise ValueError(f"no usable keyframe in {video_id}")
        pd.DataFrame(rows).to_parquet(package / "keyframes.parquet", index=False)
        return {"status": "pass", "keyframes": len(rows), "shots_without_keyframe": empty}

    def image_stage():
        vectors = models.image.embed_images(_images(package, _keyframes(package)["keyframe_ref"]))
        np.save(package / "image_vectors.npy", np.asarray(vectors, dtype="float32"))
        return {"status": "pass", "vectors": len(vectors)}

    def asr_stage():
        _save_rows(package / "asr_segments.parquet", [], ["video_id", "start_sec", "end_sec", "text"])
        segments = models.asr.transcribe(video.video_path, root / "scratch" / f"{video_id}.wav")
        _save_rows(package / "asr_segments.parquet",
                   [{"video_id": video_id, "start_sec": s.start_sec, "end_sec": s.end_sec, "text": s.text}
                    for s in segments], ["video_id", "start_sec", "end_sec", "text"])
        return {"status": "pass" if segments else "empty", "segments": len(segments)}

    def ocr_stage():
        _save_rows(package / "ocr.parquet", [], ["keyframe_id", "lines"])
        keyframes = _keyframes(package)
        min_chars = int(text_config["ocr_min_line_chars"])
        rows = [{"keyframe_id": keyframe_id, "lines": clean_ocr_lines(models.ocr.read(image), min_chars=min_chars)}
                for keyframe_id, image in zip(keyframes["keyframe_id"],
                                              _images(package, keyframes["keyframe_ref"]))]
        _save_rows(package / "ocr.parquet", rows, ["keyframe_id", "lines"])
        return {"status": "pass", "keyframes_with_text": sum(bool(row["lines"]) for row in rows)}

    def captions_stage():
        columns = ["sub_shot_id", "keyframe_id", "caption", "objects", "actions", "visible_text", "problems"]
        _save_rows(package / "captions.parquet", [], columns)
        if models.captioner is None:
            return {"status": "skipped"}
        picks = _representatives(_keyframes(package))
        results = models.captioner.caption(_images(package, picks["keyframe_ref"]))
        rows = []
        for pick, result in zip(picks.itertuples(), results):
            payload = result.payload or {}
            rows.append({"sub_shot_id": pick.sub_shot_id, "keyframe_id": pick.keyframe_id,
                         "caption": payload.get("caption", ""), "objects": list(payload.get("objects", [])),
                         "actions": list(payload.get("actions", [])),
                         "visible_text": payload.get("visible_text", ""), "problems": list(result.problems)})
        _save_rows(package / "captions.parquet", rows, columns)
        return {"status": "pass", "captions": sum(not row["problems"] for row in rows),
                "rejected": sum(bool(row["problems"]) for row in rows)}

    def documents_stage():
        documents = _text_documents(video, package, text_config)
        pd.DataFrame(documents, columns=DOCUMENT_COLUMNS).to_parquet(
            package / "text_documents.parquet", index=False)
        return {"status": "pass", "documents": len(documents)}

    def text_vectors_stage():
        documents = pd.read_parquet(package / "text_documents.parquet")
        texts = documents["text"].tolist()
        vectors = models.text.embed_passages(texts) if texts else np.zeros((0, 0), dtype="float32")
        np.save(package / "text_vectors.npy", np.asarray(vectors, dtype="float32"))
        return {"status": "pass", "vectors": len(texts)}

    runner.run("shots", config=model_config["shot_detection"], upstream=[], fn=shots_stage)
    runner.run("keyframes", config=config["keyframes"], upstream=["shots"], fn=keyframes_stage)
    runner.run("image_vectors", config=model_config["image_embedding"], upstream=["keyframes"], fn=image_stage)
    runner.run("asr", config=model_config["asr"], upstream=[], fn=asr_stage, degrade=True)
    runner.run("ocr", config=model_config["ocr"], upstream=["keyframes"], fn=ocr_stage, degrade=True)
    runner.run("captions", config=model_config["captions"] if models.captioner else None,
               upstream=["keyframes"], fn=captions_stage, degrade=True)
    runner.run("text_documents", config=text_config, upstream=["shots", "asr", "ocr", "captions"],
               fn=documents_stage)
    runner.run("text_vectors", config=model_config["text_embedding"], upstream=["text_documents"],
               fn=text_vectors_stage)

    manifest = {
        "schema_version": "worker_package_v1",
        "video_id": video_id,
        "config_schema_version": config["schema_version"],
        "models": {name: {key: value for key, value in section.items() if key in ("model_id", "revision",
                                                                                  "model_revision")}
                   for name, section in model_config.items()},
        "stages": runner.reports,
    }
    (package / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    validate_package(package, video_id=video_id)
    failed = any(report["status"] == "failed" for report in runner.reports.values())
    return write_artifact_zip(artifact_dir=package, zip_path=work_root / f"{video_id}.zip", video_id=video_id,
                              artifact_type="worker", batch_id=batch_id, worker_id=worker_id,
                              status="partial" if failed else "complete")


def _write_keyframes(
    video: VideoInput, shots: pd.DataFrame, settings: Mapping[str, Any], package: Path
) -> tuple[list[dict[str, Any]], int]:
    policy = AdaptiveKeyframePolicy(
        candidate_interval_sec=float(settings["candidate_interval_sec"]),
        min_change=float(settings["min_change"]),
        subshot_drift=float(settings["subshot_drift"]),
        max_subshot_sec=float(settings["max_subshot_sec"]),
        edge_margin_frames=int(settings["edge_margin_frames"]),
    )
    pts = [float(row["pts_time"]) for row in sorted(video.timeline_rows, key=lambda row: int(row["frame_id"]))]
    plans = [plan_candidate_frames(start_frame=int(shot.start_frame), end_frame=int(shot.end_frame),
                                   pts=pts, policy=policy) for shot in shots.itertuples()]
    rows: list[dict[str, Any]] = []
    empty = 0
    video_id = video.video_id
    for shot, plan, frames in zip(shots.itertuples(), plans, iter_decode_frame_groups(video.video_path, plans)):
        kept = select_adaptive_keyframes([(frame, pts[frame], frames.get(frame)) for frame in plan], policy=policy)
        empty += not kept
        for item in kept:
            keyframe_ref = f"keyframes/{video_id}/{video_id}_f{item.frame_id:07d}.jpg"
            thumbnail_ref = f"thumbnails/{video_id}/{video_id}_f{item.frame_id:07d}.webp"
            write_keyframe_images(frames[item.frame_id], keyframe_path=package / keyframe_ref,
                                  thumbnail_path=package / thumbnail_ref,
                                  keyframe_long_side=int(settings["jpeg_long_side"]),
                                  jpeg_quality=int(settings["jpeg_quality"]),
                                  thumbnail_width=int(settings["thumbnail_width"]))
            rows.append({"keyframe_id": f"{video_id}:{item.frame_id}", "video_id": video_id,
                         "frame_id": item.frame_id, "timestamp_sec": item.timestamp_sec,
                         "shot_id": shot.shot_id, "sub_shot_id": f"{shot.shot_id}_SS{item.sub_shot_index:03d}",
                         "selection_reason": item.reason, "keyframe_ref": keyframe_ref,
                         "thumbnail_ref": thumbnail_ref})
    return rows, empty


def _text_documents(video: VideoInput, package: Path, settings: Mapping[str, Any]) -> list[dict[str, Any]]:
    video_id = video.video_id
    shots = pd.read_parquet(package / "shots.parquet")
    spans = list(zip(shots["shot_id"], shots["start_sec"], shots["end_sec"]))
    keyframes = _keyframes(package).set_index("keyframe_id")
    documents: list[dict[str, Any]] = []

    def add(kind: str, start: float, end: float, text: str, keyframe_id: str | None = None) -> None:
        text = " ".join(text.split())
        if text:
            documents.append({
                "doc_id": f"{video_id}:{kind}:{len(documents):05d}", "video_id": video_id, "evidence_type": kind,
                "start_sec": float(start), "end_sec": float(end),
                "shot_ids": ",".join(shots_for_interval(start, max(end, start + 1e-6), spans)),
                "keyframe_id": keyframe_id, "text": text, "text_unaccented": unaccent(text),
            })

    segments = [AsrSegment(row.start_sec, row.end_sec, row.text)
                for row in pd.read_parquet(package / "asr_segments.parquet").itertuples()]
    for chunk in chunk_asr_segments(segments, min_sec=float(settings["asr_chunk_min_sec"]),
                                    max_sec=float(settings["asr_chunk_max_sec"]),
                                    max_gap_sec=float(settings["asr_chunk_max_gap_sec"])):
        add("asr", chunk.start_sec, chunk.end_sec, chunk.text)

    ocr = pd.read_parquet(package / "ocr.parquet")
    texts = {row.keyframe_id: "\n".join(row.lines) for row in ocr.itertuples()}
    for keyframe_id, text in strip_video_wide_repeats(
            texts, min_fraction=float(settings["ocr_repeat_min_fraction"])).items():
        timestamp = float(keyframes.loc[keyframe_id, "timestamp_sec"])
        add("ocr", timestamp, timestamp, text, keyframe_id)

    for row in pd.read_parquet(package / "captions.parquet").itertuples():
        if row.problems is not None and len(row.problems):
            continue
        timestamp = float(keyframes.loc[row.keyframe_id, "timestamp_sec"])
        add("caption", timestamp, timestamp,
            " ".join([row.caption, *list(row.objects), *list(row.actions)]), row.keyframe_id)
        add("visible_text", timestamp, timestamp, row.visible_text, row.keyframe_id)
    return documents


def _representatives(keyframes: pd.DataFrame) -> pd.DataFrame:
    """The middle keyframe of each sub-shot, in time order."""

    picks = [group.iloc[len(group) // 2] for _, group in keyframes.groupby("sub_shot_id", sort=False)]
    return pd.DataFrame(picks).reset_index(drop=True)


def _keyframes(package: Path) -> pd.DataFrame:
    return pd.read_parquet(package / "keyframes.parquet")


def _images(package: Path, refs: Sequence[str]) -> list[Image.Image]:
    return [Image.open(package / ref).convert("RGB") for ref in refs]


def _save_rows(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    pd.DataFrame(rows, columns=columns).to_parquet(path, index=False)
