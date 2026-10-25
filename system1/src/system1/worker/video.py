"""Process one video into a packaged, validated artifact ZIP.

Terms: a cut segment is the frame range between two hard cuts (TransNetV2). A
shot is a run of near-identical frames: each cut segment is split into shots
where the content changes too much (ADR 0022). Captions and search use shots.

Stages: cuts, keyframes (and shots), image vectors, ASR, OCR, captions, text
documents, text vectors, package. Each stage has a checkpoint
(`stages.StageRunner`). Cuts, keyframes, and image vectors are required; ASR,
OCR, and captions degrade to empty output and a failed status (ADR 0024).
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

CUT_COLUMNS = ["cut_segment_id", "video_id", "start_frame", "end_frame", "start_sec", "end_sec"]
SHOT_COLUMNS = ["shot_id", "video_id", "cut_segment_id", "start_frame", "end_frame", "start_sec", "end_sec"]
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
    cuts: Callable[[Path, list[dict[str, Any]], Path], list[dict[str, Any]]]
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

    def cuts_stage():
        report: dict[str, Any] = {"status": "pass"}
        try:
            rows = models.cuts(video.video_path, video.timeline_rows, root / "scratch")
        except Exception as exc:
            # Without cuts the whole video is one segment; shots still split by visual change.
            rows = [_whole_video_segment(video.timeline_rows)]
            report = {"status": "fallback", "error": f"{type(exc).__name__}: {exc}"[:500]}
        cuts = [{"cut_segment_id": f"{video_id}_CS{index:05d}", "video_id": video_id, **row}
                for index, row in enumerate(rows)]
        pd.DataFrame(cuts, columns=CUT_COLUMNS).to_parquet(package / "cut_segments.parquet", index=False)
        return {**report, "cut_segments": len(cuts)}

    def keyframes_stage():
        shots, keyframes, empty = _split_shots(video, pd.read_parquet(package / "cut_segments.parquet"),
                                               config["keyframes"], package)
        if not keyframes:
            raise ValueError(f"no usable keyframe in {video_id}")
        pd.DataFrame(shots, columns=SHOT_COLUMNS).to_parquet(package / "shots.parquet", index=False)
        pd.DataFrame(keyframes).to_parquet(package / "keyframes.parquet", index=False)
        return {"status": "pass", "shots": len(shots), "keyframes": len(keyframes),
                "cut_segments_without_keyframe": empty}

    def image_stage():
        vectors = models.image.embed_images(_images(package, _keyframes(package)["keyframe_ref"]))
        np.save(package / "image_vectors.npy", np.asarray(vectors, dtype="float32"))
        return {"status": "pass", "vectors": len(vectors)}

    def asr_stage():
        columns = ["video_id", "start_sec", "end_sec", "text"]
        _save_rows(package / "asr_segments.parquet", [], columns)
        segments = models.asr.transcribe(video.video_path, root / "scratch" / f"{video_id}.wav")
        _save_rows(package / "asr_segments.parquet",
                   [{"video_id": video_id, "start_sec": s.start_sec, "end_sec": s.end_sec, "text": s.text}
                    for s in segments], columns)
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
        columns = ["shot_id", "keyframe_id", "caption", "objects", "actions", "visible_text", "problems"]
        _save_rows(package / "captions.parquet", [], columns)
        if models.captioner is None:
            return {"status": "skipped"}
        picks = _representatives(_keyframes(package))
        results = models.captioner.caption(_images(package, picks["keyframe_ref"]))
        rows = []
        for pick, result in zip(picks.itertuples(), results):
            payload = result.payload or {}
            rows.append({"shot_id": pick.shot_id, "keyframe_id": pick.keyframe_id,
                         "caption": payload.get("caption", ""), "objects": list(payload.get("objects", [])),
                         "actions": list(payload.get("actions", [])),
                         "visible_text": payload.get("visible_text", ""), "problems": list(result.problems)})
        _save_rows(package / "captions.parquet", rows, columns)
        return {"status": "pass", "captions": sum(not row["problems"] for row in rows),
                "rejected": sum(bool(row["problems"]) for row in rows)}

    def documents_stage():
        documents = _text_documents(video_id, package, text_config)
        pd.DataFrame(documents, columns=DOCUMENT_COLUMNS).to_parquet(
            package / "text_documents.parquet", index=False)
        return {"status": "pass", "documents": len(documents)}

    def text_vectors_stage():
        texts = pd.read_parquet(package / "text_documents.parquet")["text"].tolist()
        vectors = models.text.embed_passages(texts) if texts else np.zeros((0, 0), dtype="float32")
        np.save(package / "text_vectors.npy", np.asarray(vectors, dtype="float32"))
        return {"status": "pass", "vectors": len(texts)}

    # ASR runs first, while the most GPU memory is free.
    runner.run("asr", config=model_config["asr"], upstream=[], fn=asr_stage, degrade=True)
    runner.run("cuts", config=model_config["shot_detection"], upstream=[], fn=cuts_stage)
    runner.run("keyframes", config=config["keyframes"], upstream=["cuts"], fn=keyframes_stage)
    runner.run("image_vectors", config=model_config["image_embedding"], upstream=["keyframes"], fn=image_stage)
    runner.run("ocr", config=model_config["ocr"], upstream=["keyframes"], fn=ocr_stage, degrade=True)
    runner.run("captions", config=model_config["captions"] if models.captioner else None,
               upstream=["keyframes"], fn=captions_stage, degrade=True)
    runner.run("text_documents", config=text_config, upstream=["keyframes", "asr", "ocr", "captions"],
               fn=documents_stage)
    runner.run("text_vectors", config=model_config["text_embedding"], upstream=["text_documents"],
               fn=text_vectors_stage)

    manifest = {
        "schema_version": "worker_package_v1",
        "video_id": video_id,
        "config_schema_version": config["schema_version"],
        "models": {name: {key: value for key, value in section.items()
                          if key in ("model_id", "revision", "model_revision")}
                   for name, section in model_config.items()},
        "stages": runner.reports,
    }
    (package / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    validate_package(package, video_id=video_id)
    failed = any(report["status"] == "failed" for report in runner.reports.values())
    return write_artifact_zip(artifact_dir=package, zip_path=work_root / f"{video_id}.zip", video_id=video_id,
                              artifact_type="worker", batch_id=batch_id, worker_id=worker_id,
                              status="partial" if failed else "complete")


def _whole_video_segment(timeline_rows: list[dict[str, Any]]) -> dict[str, Any]:
    timeline = sorted(timeline_rows, key=lambda row: int(row["frame_id"]))
    last = timeline[-1]
    return {"start_frame": 0, "end_frame": len(timeline), "start_sec": float(timeline[0]["pts_time"]),
            "end_sec": float(last["pts_time"]) + float(last.get("duration_time") or 0.0)}


def _split_shots(
    video: VideoInput, cuts: pd.DataFrame, settings: Mapping[str, Any], package: Path
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    """Split cut segments into shots, write keyframe images, and return shot and keyframe rows."""

    policy = AdaptiveKeyframePolicy(
        candidate_interval_sec=float(settings["candidate_interval_sec"]),
        min_change=float(settings["min_change"]),
        shot_drift=float(settings["shot_drift"]),
        max_shot_sec=float(settings["max_shot_sec"]),
        edge_margin_frames=int(settings["edge_margin_frames"]),
    )
    timeline = sorted(video.timeline_rows, key=lambda row: int(row["frame_id"]))
    pts = [float(row["pts_time"]) for row in timeline]
    video_end = pts[-1] + float(timeline[-1].get("duration_time") or 0.0)
    plans = [plan_candidate_frames(start_frame=int(cut.start_frame), end_frame=int(cut.end_frame),
                                   pts=pts, policy=policy) for cut in cuts.itertuples()]
    video_id = video.video_id
    shots: list[dict[str, Any]] = []
    keyframes: list[dict[str, Any]] = []
    empty = 0
    for cut, plan, frames in zip(cuts.itertuples(), plans, iter_decode_frame_groups(video.video_path, plans)):
        kept = select_adaptive_keyframes([(frame, pts[frame], frames.get(frame)) for frame in plan],
                                         policy=policy)
        empty += not kept
        starts = {item.shot_index: item.frame_id for item in kept if item.reason == "shot_start"}
        bounds = [int(cut.start_frame)] + [starts[index] for index in sorted(starts) if index > 0]
        bounds.append(int(cut.end_frame))
        shot_ids = {}
        for index in sorted(starts):
            start, end = bounds[index], bounds[index + 1]
            shot_ids[index] = f"{video_id}_SH{len(shots):05d}"
            shots.append({"shot_id": shot_ids[index], "video_id": video_id,
                          "cut_segment_id": cut.cut_segment_id, "start_frame": start, "end_frame": end,
                          "start_sec": pts[start], "end_sec": pts[end] if end < len(pts) else video_end})
        for item in kept:
            keyframe_ref = f"keyframes/{video_id}/{video_id}_f{item.frame_id:07d}.jpg"
            thumbnail_ref = f"thumbnails/{video_id}/{video_id}_f{item.frame_id:07d}.webp"
            write_keyframe_images(frames[item.frame_id], keyframe_path=package / keyframe_ref,
                                  thumbnail_path=package / thumbnail_ref,
                                  keyframe_long_side=int(settings["jpeg_long_side"]),
                                  jpeg_quality=int(settings["jpeg_quality"]),
                                  thumbnail_width=int(settings["thumbnail_width"]))
            keyframes.append({"keyframe_id": f"{video_id}:{item.frame_id}", "video_id": video_id,
                              "frame_id": item.frame_id, "timestamp_sec": item.timestamp_sec,
                              "shot_id": shot_ids[item.shot_index], "cut_segment_id": cut.cut_segment_id,
                              "selection_reason": item.reason, "keyframe_ref": keyframe_ref,
                              "thumbnail_ref": thumbnail_ref})
    return shots, keyframes, empty


def _text_documents(video_id: str, package: Path, settings: Mapping[str, Any]) -> list[dict[str, Any]]:
    shots = pd.read_parquet(package / "shots.parquet")
    spans = list(zip(shots["shot_id"], shots["start_sec"], shots["end_sec"]))
    keyframes = _keyframes(package).set_index("keyframe_id")
    documents: list[dict[str, Any]] = []

    def add(kind: str, start: float, end: float, text: str, keyframe_id: str | None = None,
            shot_ids: str | None = None) -> None:
        text = " ".join(text.split())
        if text:
            documents.append({
                "doc_id": f"{video_id}:{kind}:{len(documents):05d}", "video_id": video_id, "evidence_type": kind,
                "start_sec": float(start), "end_sec": float(end),
                "shot_ids": shot_ids or ",".join(shots_for_interval(start, max(end, start + 1e-6), spans)),
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
        add("ocr", timestamp, timestamp, text, keyframe_id, keyframes.loc[keyframe_id, "shot_id"])

    for row in pd.read_parquet(package / "captions.parquet").itertuples():
        if row.problems is not None and len(row.problems):
            continue
        timestamp = float(keyframes.loc[row.keyframe_id, "timestamp_sec"])
        add("caption", timestamp, timestamp, " ".join([row.caption, *list(row.objects), *list(row.actions)]),
            row.keyframe_id, row.shot_id)
        add("visible_text", timestamp, timestamp, row.visible_text, row.keyframe_id, row.shot_id)
    return documents


def _representatives(keyframes: pd.DataFrame) -> pd.DataFrame:
    """The middle keyframe of each shot, in time order."""

    picks = [group.iloc[len(group) // 2] for _, group in keyframes.groupby("shot_id", sort=False)]
    return pd.DataFrame(picks).reset_index(drop=True)


def _keyframes(package: Path) -> pd.DataFrame:
    return pd.read_parquet(package / "keyframes.parquet")


def _images(package: Path, refs: Sequence[str]) -> list[Image.Image]:
    return [Image.open(package / ref).convert("RGB") for ref in refs]


def _save_rows(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    pd.DataFrame(rows, columns=columns).to_parquet(path, index=False)
