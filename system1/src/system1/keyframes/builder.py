from __future__ import annotations

import math
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

ROLE_ORDER = ("early", "middle", "late")


@dataclass(frozen=True)
class CandidateQuality:
    frame_id: int
    role: str
    target_frame: float
    quality_score: float
    valid: bool
    invalid_reason: str | None


@dataclass(frozen=True)
class SelectedKeyframe:
    frame_id: int
    role: str
    quality_score: float
    is_representative: bool
    selection_reason: str


def candidate_frame_ids_for_shot(
    shot: Mapping[str, Any], config: Mapping[str, Any]
) -> dict[str, tuple[int, ...]]:
    start = int(shot["start_frame"])
    end = int(shot["end_frame"])
    if end <= start:
        raise ValueError("Shot frame range must be non-empty and half-open")
    roles = config["roles"]
    selection = config["selection"]
    maximum = int(selection["max_candidates_per_band"])
    expansion = float(selection["expansion_step_ratio"])
    safe_start = float(selection["safe_interior_start_ratio"])
    safe_end = float(selection["safe_interior_end_ratio"])
    result: dict[str, tuple[int, ...]] = {}
    for role in ROLE_ORDER:
        role_config = roles[role]
        low = float(role_config["search_start_ratio"])
        high = float(role_config["search_end_ratio"])
        candidates: list[int] = []
        while True:
            candidates.extend(_sample_ratio_band(start, end, low, high, maximum))
            if low <= safe_start and high >= safe_end:
                break
            low = max(safe_start, low - expansion)
            high = min(safe_end, high + expansion)
        result[role] = tuple(dict.fromkeys(candidates))
    return result


def decode_selected_frames(
    video_path: Path | str, frame_ids: set[int]
) -> dict[int, np.ndarray]:
    """Decode one group of frames with the same streaming implementation used in production."""

    return next(iter_decode_frame_groups(video_path, (frame_ids,)), {})


def iter_decode_frame_groups(
    video_path: Path | str,
    frame_id_groups: Iterable[Iterable[int]],
) -> Iterator[dict[int, np.ndarray]]:
    """Decode monotonically ordered frame groups in one pass over a video.

    Production supplies one group per shot. Only the current shot's temporary
    candidate frames remain resident, which bounds peak RAM without seeking or
    decoding the video again for every shot.
    """

    try:
        import cv2
    except ImportError as exc:  # pragma: no cover - production dependency preflight
        raise RuntimeError("opencv-python-headless is required for keyframe extraction") from exc
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise RuntimeError(f"Cannot open video for keyframe extraction: {video_path}")
    index = 0
    exhausted = False
    try:
        for frame_ids in frame_id_groups:
            requested = sorted(set(int(frame_id) for frame_id in frame_ids))
            if requested and requested[0] < index:
                raise ValueError(
                    "Frame groups must be monotonically ordered and non-overlapping"
                )
            frames: dict[int, np.ndarray] = {}
            for target in requested:
                if target < 0:
                    raise ValueError("Frame IDs must be non-negative")
                while not exhausted and index <= target:
                    ok = capture.grab()
                    if not ok:
                        exhausted = True
                        break
                    if index == target:
                        ok, bgr = capture.retrieve()
                        if ok and bgr is not None:
                            frames[index] = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
                    index += 1
            yield frames
    finally:
        capture.release()


def select_keyframes_for_shot(
    shot: Mapping[str, Any],
    decoded_frames: Mapping[int, np.ndarray],
    config: Mapping[str, Any],
) -> tuple[list[SelectedKeyframe], list[CandidateQuality]]:
    role_config = config["roles"]
    selection_config = config["selection"]
    quality_config = config["quality"]
    start = int(shot["start_frame"])
    end = int(shot["end_frame"])
    frame_span = max(1, end - start - 1)
    selected_by_role: dict[str, CandidateQuality] = {}
    diagnostics: list[CandidateQuality] = []

    for role in ROLE_ORDER:
        target = start + float(role_config[role]["target_ratio"]) * frame_span
        initial_low = float(role_config[role]["search_start_ratio"])
        initial_high = float(role_config[role]["search_end_ratio"])
        expansion = float(selection_config["expansion_step_ratio"])
        safe_start = float(selection_config["safe_interior_start_ratio"])
        safe_end = float(selection_config["safe_interior_end_ratio"])
        low = initial_low
        high = initial_high
        evaluated: set[int] = set()
        while True:
            round_ids = _sample_ratio_band(
                start,
                end,
                low,
                high,
                int(selection_config["max_candidates_per_band"]),
            )
            round_quality: list[CandidateQuality] = []
            for frame_id in round_ids:
                if frame_id in evaluated:
                    continue
                evaluated.add(frame_id)
                quality = evaluate_candidate(
                    frame_id=frame_id,
                    role=role,
                    target_frame=target,
                    frame=decoded_frames.get(frame_id),
                    quality_config=quality_config,
                )
                diagnostics.append(quality)
                round_quality.append(quality)
            valid = [item for item in diagnostics if item.role == role and item.valid]
            if valid:
                selected_by_role[role] = max(
                    valid,
                    key=lambda item: (item.quality_score, -abs(item.frame_id - item.target_frame)),
                )
                break
            if low <= safe_start and high >= safe_end:
                break
            low = max(safe_start, low - expansion)
            high = min(safe_end, high + expansion)

    if not selected_by_role:
        raise ValueError(f"No valid keyframe candidate for shot {shot.get('shot_id')}")

    # When very short shots map multiple roles to one decoded frame, preserve
    # the middle semantic role first and never mint duplicate keyframe IDs.
    unique: dict[int, CandidateQuality] = {}
    for role in ("middle", "early", "late"):
        selected = selected_by_role.get(role)
        if selected is not None and selected.frame_id not in unique:
            unique[selected.frame_id] = selected

    best_quality = max(item.quality_score for item in unique.values())
    middle = next((item for item in unique.values() if item.role == "middle"), None)
    ratio = float(config["representative"]["preferred_min_ratio_of_best"])
    shot_center = start + frame_span / 2.0
    if middle is not None and middle.quality_score >= ratio * best_quality:
        representative = middle
        representative_reason = "middle_within_quality_ratio"
    else:
        representative = max(
            unique.values(),
            key=lambda item: (item.quality_score, -abs(item.frame_id - shot_center)),
        )
        representative_reason = "highest_quality_fallback"

    selected_rows = [
        SelectedKeyframe(
            frame_id=item.frame_id,
            role=item.role,
            quality_score=item.quality_score,
            is_representative=item.frame_id == representative.frame_id,
            selection_reason=(
                representative_reason
                if item.frame_id == representative.frame_id
                else "best_valid_candidate_in_search_band"
            ),
        )
        for item in sorted(unique.values(), key=lambda value: value.frame_id)
    ]
    return selected_rows, diagnostics


def evaluate_candidate(
    *,
    frame_id: int,
    role: str,
    target_frame: float,
    frame: np.ndarray | None,
    quality_config: Mapping[str, Any],
) -> CandidateQuality:
    if frame is None or frame.ndim != 3 or frame.shape[2] < 3:
        return CandidateQuality(frame_id, role, target_frame, 0.0, False, "decode_failure")
    preview = np.asarray(
        Image.fromarray(frame[:, :, :3].astype(np.uint8), "RGB").resize(
            (int(quality_config["resize_width"]), int(quality_config["resize_height"])),
            Image.Resampling.BILINEAR,
        ),
        dtype=np.float32,
    )
    luma = 0.2126 * preview[:, :, 0] + 0.7152 * preview[:, :, 1] + 0.0722 * preview[:, :, 2]
    black_ratio = float(np.mean(luma <= float(quality_config["near_black_luma_threshold"])))
    white_ratio = float(np.mean(luma >= float(quality_config["near_white_luma_threshold"])))
    if black_ratio >= float(quality_config["near_black_pixel_ratio_threshold"]):
        return CandidateQuality(frame_id, role, target_frame, 0.0, False, "near_black")
    if white_ratio >= float(quality_config["near_white_pixel_ratio_threshold"]):
        return CandidateQuality(frame_id, role, target_frame, 0.0, False, "near_white")
    center = luma[1:-1, 1:-1]
    laplacian = (
        luma[:-2, 1:-1]
        + luma[2:, 1:-1]
        + luma[1:-1, :-2]
        + luma[1:-1, 2:]
        - 4.0 * center
    )
    sharpness = float(np.var(laplacian))
    return CandidateQuality(frame_id, role, target_frame, sharpness, True, None)


def write_keyframe_images(
    frame: np.ndarray,
    *,
    keyframe_path: Path,
    thumbnail_path: Path,
    keyframe_long_side: int = 960,
    jpeg_quality: int = 95,
    thumbnail_width: int = 256,
    webp_quality: int = 80,
) -> None:
    image = Image.fromarray(frame[:, :, :3].astype(np.uint8), "RGB")
    keyframe_path.parent.mkdir(parents=True, exist_ok=True)
    thumbnail_path.parent.mkdir(parents=True, exist_ok=True)
    keyframe = _resize_long_side(image, keyframe_long_side)
    keyframe.save(keyframe_path, format="JPEG", quality=jpeg_quality, subsampling=0)
    thumbnail_height = max(1, round(image.height * thumbnail_width / image.width))
    thumbnail = image.resize((thumbnail_width, thumbnail_height), Image.Resampling.LANCZOS)
    thumbnail.save(thumbnail_path, format="WEBP", quality=webp_quality, method=6)


def _sample_ratio_band(
    start: int, end: int, low_ratio: float, high_ratio: float, maximum: int
) -> list[int]:
    frame_span = max(0, end - start - 1)
    low = start + low_ratio * frame_span
    high = start + high_ratio * frame_span
    count = min(maximum, max(1, math.floor(high) - math.ceil(low) + 1))
    if count == 1:
        return [round((low + high) / 2.0)]
    return sorted({round(value) for value in np.linspace(low, high, count)})


def _resize_long_side(image: Image.Image, long_side: int) -> Image.Image:
    scale = long_side / max(image.width, image.height)
    size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
    return image.resize(size, Image.Resampling.LANCZOS)
