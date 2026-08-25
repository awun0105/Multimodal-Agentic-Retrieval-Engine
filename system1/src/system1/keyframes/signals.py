from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np


@dataclass(frozen=True)
class TextRegionAnalysis:
    edges: np.ndarray
    boxes: tuple[tuple[int, int, int, int], ...]
    edge_density: float
    gray_std: float


@dataclass(frozen=True)
class TextSignal:
    text_present: bool
    signature: np.ndarray | None
    region_count: int


def difference_hash(frame: np.ndarray, *, hash_size: int) -> np.ndarray:
    if hash_size < 1:
        raise ValueError("dHash hash_size must be positive")
    grayscale = _grayscale(frame)
    import cv2

    resized = cv2.resize(
        grayscale,
        (hash_size + 1, hash_size),
        interpolation=cv2.INTER_AREA,
    )
    return (resized[:, 1:] > resized[:, :-1]).reshape(-1)


def difference_hash_distance(left: np.ndarray, right: np.ndarray) -> float:
    if left.shape != right.shape or left.size == 0:
        raise ValueError("dHash signatures must have the same non-empty shape")
    return float(np.count_nonzero(left != right) / left.size)


def analyze_text_regions(
    image: Path | np.ndarray,
    config: Mapping[str, Any],
) -> TextRegionAnalysis:
    import cv2

    grayscale = _grayscale(image)
    if grayscale.size == 0:
        raise ValueError("Text analysis received an empty image")
    max_long_side = int(config["max_long_side"])
    height, width = grayscale.shape[:2]
    if max(height, width) > max_long_side:
        scale = max_long_side / float(max(height, width))
        grayscale = cv2.resize(
            grayscale,
            (max(1, round(width * scale)), max(1, round(height * scale))),
            interpolation=cv2.INTER_AREA,
        )
    edges = cv2.Canny(
        grayscale,
        int(config["canny_low"]),
        int(config["canny_high"]),
    )
    edge_density = float((edges > 0).mean())
    gray_std = float(grayscale.std())
    regions, boxes = cv2.MSER_create().detectRegions(grayscale)
    plausible: list[tuple[int, int, int, int]] = []
    image_area = float(grayscale.shape[0] * grayscale.shape[1])
    for region, box in zip(regions, boxes, strict=False):
        x, y, region_width, region_height = (int(value) for value in box)
        area = float(region_width * region_height)
        aspect = region_width / float(max(1, region_height))
        if (
            len(region) >= 10
            and 0.00002 <= area / image_area <= 0.08
            and 0.15 <= aspect <= 20.0
        ):
            plausible.append((x, y, region_width, region_height))
    return TextRegionAnalysis(
        edges=edges,
        boxes=tuple(plausible),
        edge_density=edge_density,
        gray_std=gray_std,
    )


def text_presence_gate(image: Path | np.ndarray, config: Mapping[str, Any]) -> str:
    if str(config.get("policy")) != "opencv_conservative_v1":
        raise ValueError(f"Unsupported OCR text gate policy: {config.get('policy')}")
    analysis = analyze_text_regions(image, config)
    if (
        not analysis.boxes
        and analysis.edge_density <= float(config["max_no_text_edge_density"])
        and analysis.gray_std <= float(config["max_no_text_gray_std"])
    ):
        return "no_text"
    return "uncertain"


def text_edge_signal(
    frame: np.ndarray,
    config: Mapping[str, Any],
) -> TextSignal:
    if str(config.get("policy")) != "mser_masked_edge_jaccard_v1":
        raise ValueError(f"Unsupported text-change policy: {config.get('policy')}")
    analysis = analyze_text_regions(frame, config)
    minimum_regions = int(config["min_plausible_regions"])
    if len(analysis.boxes) < minimum_regions:
        return TextSignal(
            text_present=False,
            signature=None,
            region_count=len(analysis.boxes),
        )

    import cv2

    mask = np.zeros_like(analysis.edges, dtype=np.uint8)
    height, width = mask.shape[:2]
    for x, y, region_width, region_height in analysis.boxes:
        x0 = max(0, x)
        y0 = max(0, y)
        x1 = min(width, x + region_width)
        y1 = min(height, y + region_height)
        if x1 > x0 and y1 > y0:
            mask[y0:y1, x0:x1] = 255
    masked_edges = cv2.bitwise_and(analysis.edges, mask)
    signature = cv2.resize(
        masked_edges,
        (int(config["signature_width"]), int(config["signature_height"])),
        interpolation=cv2.INTER_AREA,
    )
    return TextSignal(
        text_present=True,
        signature=(signature > 0).reshape(-1),
        region_count=len(analysis.boxes),
    )


def text_jaccard_distance(left: np.ndarray, right: np.ndarray) -> float:
    if left.shape != right.shape or left.size == 0:
        raise ValueError("Text signatures must have the same non-empty shape")
    union = np.count_nonzero(left | right)
    if union == 0:
        return 0.0
    intersection = np.count_nonzero(left & right)
    return float(1.0 - intersection / union)


def _grayscale(image: Path | np.ndarray) -> np.ndarray:
    import cv2

    if isinstance(image, Path):
        grayscale = cv2.imread(str(image), cv2.IMREAD_GRAYSCALE)
        if grayscale is None:
            raise ValueError(f"Could not decode image: {image}")
        return grayscale
    frame = np.asarray(image)
    if frame.ndim == 2:
        return frame.astype(np.uint8)
    if frame.ndim != 3 or frame.shape[2] < 3:
        raise ValueError("Image must be grayscale or RGB")
    return cv2.cvtColor(frame[:, :, :3].astype(np.uint8), cv2.COLOR_RGB2GRAY)
