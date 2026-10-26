"""Process one video into a packaged, validated artifact ZIP.

Terms: a cut segment is the frame range between two hard cuts (TransNetV2). A
shot is a run of near-identical frames: each cut segment is split into shots
where the content changes too much (ADR 0022). Captions and search use shots.

Stages: cuts, keyframes (and shots), image vectors, ASR, OCR, text documents,
text vectors, package. Each stage has a checkpoint (`stages.StageRunner`).
Cuts, keyframes, and image vectors are required; ASR and OCR degrade to empty
output and a failed status (ADR 0024). Captions run in a separate pass
(`system1.captions`, ADR 0025).

The cuts stage decodes the video once: each frame feeds TransNet and the
candidate frames of each cut segment are selected as soon as the segment is
known (plan Step 5f item 3). It hands the shots and keyframes to the keyframes
stage in memory; when only the keyframes stage reruns, it decodes the
candidates again from `cut_segments.parquet`.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import numpy as np
import pandas as pd
from PIL import Image

from system1.artifacts.package import write_artifact_zip
from system1.keyframes.adaptive import (
    AdaptiveKeyframePolicy,
    CutDetectionError,
    CutPredictor,
    iter_cut_segment_frames,
    plan_candidate_frames,
    select_adaptive_keyframes,
)
from system1.keyframes.builder import iter_decode_frame_groups, write_keyframe_images
from system1.providers.ocr import CropCache, clean_ocr_lines, frame_text_hashes, should_rerun_ocr
from system1.text.evidence import (
    AsrSegment,
    asr_windows,
    chunk_asr_segments,
    shots_for_interval,
    strip_video_wide_repeats,
    unaccent,
)
from system1.worker.package import representative_keyframes, validate_package
from system1.worker.stages import StageRunner

CUT_COLUMNS = ["cut_segment_id", "video_id", "start_frame", "end_frame", "start_sec", "end_sec"]
SHOT_COLUMNS = ["shot_id", "video_id", "cut_segment_id", "scene_id", "start_frame", "end_frame", "start_sec",
                "end_sec"]
DOCUMENT_COLUMNS = ["doc_id", "video_id", "evidence_type", "start_sec", "end_sec", "shot_ids",
                    "keyframe_id", "text", "text_unaccented", "window"]


class CutDetector(Protocol):
    threshold: float

    def start(self) -> CutPredictor: ...


class ImageEmbedder(Protocol):
    def embed_images(self, images: Sequence[Image.Image]) -> np.ndarray: ...


class SpeechRecognizer(Protocol):
    def transcribe(self, video_path: Path, wav_path: Path) -> list[AsrSegment]: ...


class TextReader(Protocol):
    def read(self, image: Image.Image, cache: CropCache | None = None) -> list[str]: ...


class TextEmbedder(Protocol):
    def embed_passages(self, texts: Sequence[str]) -> np.ndarray: ...


@dataclass(frozen=True)
class VideoInput:
    video_id: str
    video_path: Path
    timeline_rows: list[dict[str, Any]]


@dataclass
class WorkerModels:
    cuts: CutDetector
    image: ImageEmbedder
    asr: SpeechRecognizer
    ocr: TextReader
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

    single_pass: dict[str, Any] = {}

    def cuts_stage():
        report: dict[str, Any] = {"status": "pass"}
        try:
            cuts, result = _single_pass(video, config["keyframes"], package, models.image, models.cuts)
        except CutDetectionError as exc:
            # No CPU retry (plan Step 5f item 11): the whole video is one segment,
            # shots still split by visual change, and the next run retries the cuts.
            for folder in ("keyframes", "thumbnails"):
                shutil.rmtree(package / folder / video_id, ignore_errors=True)
            cuts, result = _single_pass(video, config["keyframes"], package, models.image, None)
            report = {"status": "fallback", "error": str(exc)[:500]}
        pd.DataFrame(cuts, columns=CUT_COLUMNS).to_parquet(package / "cut_segments.parquet", index=False)
        single_pass["result"] = result
        return {**report, "cut_segments": len(cuts)}

    vectors_path = root / "scratch" / "keyframe_vectors.npy"

    def keyframes_stage():
        if "result" in single_pass:
            shots, keyframes, vectors, report = single_pass.pop("result")
        else:
            shots, keyframes, vectors, report = _split_shots(
                video, pd.read_parquet(package / "cut_segments.parquet"), config["keyframes"], package,
                models.image)
        if not keyframes:
            raise ValueError(f"no usable keyframe in {video_id}")
        # scene_id is null in worker packages; the release sets it (ADR 0026).
        pd.DataFrame(shots, columns=SHOT_COLUMNS).astype({"scene_id": "string"}).to_parquet(
            package / "shots.parquet", index=False)
        keyframes = pd.DataFrame(keyframes)
        representatives = set(representative_keyframes(keyframes, vectors)["keyframe_id"])
        keyframes["is_representative"] = keyframes["keyframe_id"].isin(representatives)
        keyframes.to_parquet(package / "keyframes.parquet", index=False)
        # The image_vectors stage writes these to the package; no JPEG is re-read.
        np.save(vectors_path, vectors)
        return {"status": "pass", "shots": len(shots), "keyframes": len(keyframes), **report}

    def image_stage():
        vectors = np.load(vectors_path)
        np.save(package / "image_vectors.npy", vectors)
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
        min_ratio = float(text_config.get("ocr_min_syllable_ratio", 0.0))
        min_change = float(model_config["ocr"].get("rerun_min_change", 0.0))
        cache = CropCache()
        rows, reused = [], 0
        # One OCR run per shot start; later keyframes in the shot run again only
        # when the frame or its lower third changed (plan Step 5c items 1 and 2).
        for _, group in keyframes.groupby("shot_id", sort=False):
            previous, lines = None, []
            for keyframe_id, image in zip(group["keyframe_id"], _images(package, group["keyframe_ref"])):
                hashes = frame_text_hashes(image)
                if should_rerun_ocr(previous, hashes, min_change=min_change):
                    lines = clean_ocr_lines(models.ocr.read(image, cache), min_chars=min_chars,
                                            min_syllable_ratio=min_ratio)
                    previous = hashes
                else:
                    reused += 1
                rows.append({"keyframe_id": keyframe_id, "lines": lines})
        rows.sort(key=lambda row: keyframes.index[keyframes["keyframe_id"] == row["keyframe_id"]][0])
        _save_rows(package / "ocr.parquet", rows, ["keyframe_id", "lines"])
        return {"status": "pass", "keyframes_with_text": sum(bool(row["lines"]) for row in rows),
                "reused_from_shot": reused, "crop_cache_hits": cache.hits}

    def documents_stage():
        documents = _text_documents(video_id, package, text_config)
        # keyframe_id is null for asr rows; a string column keeps it null, not NaN.
        pd.DataFrame(documents, columns=DOCUMENT_COLUMNS).astype({"keyframe_id": "string", "window": "bool"}).to_parquet(
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
    # The keyframes stage embeds candidates, so the image model is part of its fingerprint.
    runner.run("keyframes", config={**config["keyframes"], "image_embedding": model_config["image_embedding"]},
               upstream=["cuts"], fn=keyframes_stage)
    runner.run("image_vectors", config=model_config["image_embedding"], upstream=["keyframes"], fn=image_stage)
    runner.run("ocr", config=model_config["ocr"], upstream=["keyframes"], fn=ocr_stage, degrade=True)
    runner.run("text_documents", config=text_config, upstream=["keyframes", "asr", "ocr"],
               fn=documents_stage)
    runner.run("text_vectors", config=model_config["text_embedding"], upstream=["text_documents"],
               fn=text_vectors_stage)

    manifest = {
        "schema_version": "worker_package_v2",
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


def _policy(settings: Mapping[str, Any]) -> AdaptiveKeyframePolicy:
    return AdaptiveKeyframePolicy(
        candidate_interval_sec=float(settings["candidate_interval_sec"]),
        min_change=float(settings["min_change"]),
        shot_drift=float(settings["shot_drift"]),
        max_shot_sec=float(settings["max_shot_sec"]),
        edge_margin_frames=int(settings["edge_margin_frames"]),
        min_sharpness_ratio=float(settings.get("min_sharpness_ratio", 0.3)),
    )


def _timeline_pts(video: VideoInput) -> tuple[list[float], float]:
    timeline = sorted(video.timeline_rows, key=lambda row: int(row["frame_id"]))
    pts = [float(row["pts_time"]) for row in timeline]
    return pts, pts[-1] + float(timeline[-1].get("duration_time") or 0.0)


def _single_pass(
    video: VideoInput, settings: Mapping[str, Any], package: Path, embedder: ImageEmbedder,
    detector: CutDetector | None,
) -> tuple[list[dict[str, Any]], tuple[list[dict[str, Any]], list[dict[str, Any]], np.ndarray, dict[str, int]]]:
    """Detect cuts and split shots in one decode; return cut rows and the `_split_shots` result.

    With `detector=None` the whole video is one cut segment. A detector failure
    raises `CutDetectionError`; keyframe images already written stay on disk.
    """

    policy = _policy(settings)
    pts, video_end = _timeline_pts(video)
    if detector is None:
        predictor, threshold = None, 0.5
    else:
        try:
            predictor, threshold = detector.start(), float(detector.threshold)
        except Exception as exc:
            raise CutDetectionError(f"{type(exc).__name__}: {exc}") from exc
    cuts: list[dict[str, Any]] = []

    def segments():
        for start, end, plan, frames in iter_cut_segment_frames(
                video.video_path, pts=pts, policy=policy, predictor=predictor, threshold=threshold):
            cut_segment_id = f"{video.video_id}_CS{len(cuts):05d}"
            cuts.append({"cut_segment_id": cut_segment_id, "video_id": video.video_id, "start_frame": start,
                         "end_frame": end, "start_sec": pts[start],
                         "end_sec": pts[end] if end < len(pts) else video_end})
            yield cut_segment_id, start, end, plan, frames

    result = _build_shots(video.video_id, pts, video_end, segments(), policy, settings, package, embedder)
    return cuts, result


def _split_shots(
    video: VideoInput, cuts: pd.DataFrame, settings: Mapping[str, Any], package: Path, embedder: ImageEmbedder
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], np.ndarray, dict[str, int]]:
    """Split stored cut segments into shots, decoding the candidates again; see `_build_shots`."""

    policy = _policy(settings)
    pts, video_end = _timeline_pts(video)
    plans = [plan_candidate_frames(start_frame=int(cut.start_frame), end_frame=int(cut.end_frame),
                                   pts=pts, policy=policy) for cut in cuts.itertuples()]
    segments = ((cut.cut_segment_id, int(cut.start_frame), int(cut.end_frame), plan, frames)
                for cut, plan, frames in zip(cuts.itertuples(), plans,
                                             iter_decode_frame_groups(video.video_path, plans)))
    return _build_shots(video.video_id, pts, video_end, segments, policy, settings, package, embedder)


def _build_shots(
    video_id: str, pts: list[float], video_end: float,
    segments: Iterable[tuple[str, int, int, list[int], dict[int, np.ndarray]]],
    policy: AdaptiveKeyframePolicy, settings: Mapping[str, Any], package: Path, embedder: ImageEmbedder,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], np.ndarray, dict[str, int]]:
    """Split cut segments into shots, write keyframe images, and return shot rows,
    keyframe rows, keyframe image vectors aligned to the rows, and a stage report.

    `segments` yields `(cut_segment_id, start_frame, end_frame, plan, frames)`.
    The usable candidates of each cut segment are embedded in one call; the
    shot split uses the vectors (plan Step 5c item 4).
    """

    def embed(frames: list[np.ndarray]) -> np.ndarray:
        return embedder.embed_images([Image.fromarray(frame) for frame in frames])

    shots: list[dict[str, Any]] = []
    keyframes: list[dict[str, Any]] = []
    vectors: list[np.ndarray] = []
    report = {"cut_segments_without_keyframe": 0, "blurred_dropped": 0}
    for cut_segment_id, cut_start, cut_end, plan, frames in segments:
        kept = select_adaptive_keyframes([(frame, pts[frame], frames.get(frame)) for frame in plan],
                                         policy=policy, embed=embed, report=report)
        report["cut_segments_without_keyframe"] += not kept
        starts = {item.shot_index: item.frame_id for item in kept if item.reason == "shot_start"}
        bounds = [cut_start] + [starts[index] for index in sorted(starts) if index > 0]
        bounds.append(cut_end)
        shot_ids = {}
        for index in sorted(starts):
            start, end = bounds[index], bounds[index + 1]
            shot_ids[index] = f"{video_id}_SH{len(shots):05d}"
            shots.append({"shot_id": shot_ids[index], "video_id": video_id,
                          "cut_segment_id": cut_segment_id, "start_frame": start, "end_frame": end,
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
                              "shot_id": shot_ids[item.shot_index], "cut_segment_id": cut_segment_id,
                              "selection_reason": item.reason, "keyframe_ref": keyframe_ref,
                              "thumbnail_ref": thumbnail_ref})
            vectors.append(item.vector)
    return shots, keyframes, np.asarray(vectors, dtype="float32"), report


def _text_documents(video_id: str, package: Path, settings: Mapping[str, Any]) -> list[dict[str, Any]]:
    shots = pd.read_parquet(package / "shots.parquet")
    spans = list(zip(shots["shot_id"], shots["start_sec"], shots["end_sec"]))
    keyframes = _keyframes(package).set_index("keyframe_id")
    documents: list[dict[str, Any]] = []

    def add(kind: str, start: float, end: float, text: str, keyframe_id: str | None = None,
            shot_ids: str | None = None, window: bool = False) -> None:
        text = " ".join(text.split())
        if text:
            documents.append({
                "doc_id": f"{video_id}:{kind}:{len(documents):05d}", "video_id": video_id, "evidence_type": kind,
                "start_sec": float(start), "end_sec": float(end),
                "shot_ids": shot_ids or ",".join(shots_for_interval(start, max(end, start + 1e-6), spans)),
                "keyframe_id": keyframe_id, "text": text, "text_unaccented": unaccent(text),
                "window": window,
            })

    segments = [AsrSegment(row.start_sec, row.end_sec, row.text)
                for row in pd.read_parquet(package / "asr_segments.parquet").itertuples()]
    for chunk in chunk_asr_segments(segments, min_sec=float(settings["asr_chunk_min_sec"]),
                                    max_sec=float(settings["asr_chunk_max_sec"]),
                                    max_gap_sec=float(settings["asr_chunk_max_gap_sec"]),
                                    sentence_gap_sec=float(settings["asr_sentence_gap_sec"])):
        add("asr", chunk.start_sec, chunk.end_sec, chunk.text)
    for window in asr_windows(segments, window_sec=float(settings["asr_window_sec"]),
                              step_sec=float(settings["asr_window_step_sec"])):
        add("asr", window.start_sec, window.end_sec, window.text, window=True)

    ocr = pd.read_parquet(package / "ocr.parquet")
    texts = {row.keyframe_id: "\n".join(row.lines) for row in ocr.itertuples()}
    for keyframe_id, text in strip_video_wide_repeats(
            texts, min_fraction=float(settings["ocr_repeat_min_fraction"])).items():
        timestamp = float(keyframes.loc[keyframe_id, "timestamp_sec"])
        add("ocr", timestamp, timestamp, text, keyframe_id, keyframes.loc[keyframe_id, "shot_id"])

    return documents


def _keyframes(package: Path) -> pd.DataFrame:
    return pd.read_parquet(package / "keyframes.parquet")


def _images(package: Path, refs: Sequence[str]) -> list[Image.Image]:
    return [Image.open(package / ref).convert("RGB") for ref in refs]


def _save_rows(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    pd.DataFrame(rows, columns=columns).to_parquet(path, index=False)
