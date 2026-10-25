"""OCR: EasyOCR text detection + VietOCR recognition (ADR 0023).

Per-shot rerun (plan Step 5c item 1): the worker computes `frame_text_hashes`
for each keyframe. The first keyframe of each shot always runs OCR. A later
keyframe in the same shot runs OCR only when `should_rerun_ocr(previous,
current, min_change=models.ocr.rerun_min_change)` is True, where `previous` is
the hashes of the last keyframe that ran OCR in the shot; otherwise it reuses
that keyframe's lines.

Crop cache (plan Step 5c item 2): one `CropCache` per video is passed to
`EasyVietOcr.read`; a text box crop whose 16x16 difference hash was seen before
reuses the recognized string instead of calling VietOCR.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

from system1.keyframes.signals import difference_hash
from system1.text.evidence import vietnamese_syllable_ratio

Rect = tuple[int, int, int, int]


def reading_order_rects(
    boxes: Sequence[Sequence[Sequence[float]]], *, width: int, height: int, padding: int, min_size: int
) -> list[Rect]:
    """Padded axis-aligned rectangles for detected boxes, top to bottom then left to right.

    Boxes smaller than `min_size` in either dimension are dropped before padding.
    """

    rects = []
    for box in boxes:
        xs = [float(point[0]) for point in box]
        ys = [float(point[1]) for point in box]
        if max(xs) - min(xs) < min_size or max(ys) - min(ys) < min_size:
            continue
        rects.append((int(max(0, min(xs) - padding)), int(max(0, min(ys) - padding)),
                      int(min(width, max(xs) + padding)), int(min(height, max(ys) + padding))))
    return sorted(rects, key=lambda rect: (round(rect[1] / 12), rect[0]))


def clean_ocr_lines(lines: Sequence[str], *, min_chars: int, min_syllable_ratio: float = 0.0) -> list[str]:
    """Drop recognition noise.

    A line is dropped when it has fewer than `min_chars` letters or digits, or
    when `min_syllable_ratio` > 0 and its `vietnamese_syllable_ratio` is lower.
    """

    cleaned = []
    for line in lines:
        text = " ".join(line.split())
        if sum(char.isalnum() for char in text) < min_chars:
            continue
        if min_syllable_ratio > 0 and vietnamese_syllable_ratio(text) < min_syllable_ratio:
            continue
        cleaned.append(text)
    return cleaned


def _hash_int(bits: np.ndarray) -> int:
    return int("".join("1" if bit else "0" for bit in bits.reshape(-1)), 2)


def _dhash(image: Any, hash_size: int) -> int:
    return _hash_int(difference_hash(np.asarray(image.convert("RGB")), hash_size=hash_size))


def frame_text_hashes(image: Any, hash_size: int = 8) -> tuple[int, int]:
    """Difference hashes of a PIL image: whole frame and lower third (ticker and subtitle band)."""

    band = image.crop((0, image.height * 2 // 3, image.width, image.height))
    return _dhash(image, hash_size), _dhash(band, hash_size)


def should_rerun_ocr(
    previous: tuple[int, int] | None, current: tuple[int, int], *, min_change: float, hash_size: int = 8
) -> bool:
    """True when there is no previous hash or either hash differs in at least `min_change` of its bits."""

    if previous is None:
        return True
    bits = hash_size * hash_size
    return any(bin(old ^ new).count("1") / bits >= min_change for old, new in zip(previous, current))


def crop_hash(image: Any) -> int:
    """16x16 difference hash of a text box crop."""

    return _dhash(image, 16)


class CropCache:
    """Recognized text per crop hash, exact match only, with hit and miss counters."""

    def __init__(self) -> None:
        self._texts: dict[int, str] = {}
        self.hits = 0
        self.misses = 0

    def get(self, crop: Any) -> str | None:
        text = self._texts.get(crop_hash(crop))
        if text is None:
            self.misses += 1
        else:
            self.hits += 1
        return text

    def put(self, crop: Any, text: str) -> None:
        self._texts[crop_hash(crop)] = text


class EasyVietOcr:
    def __init__(self, config: Mapping[str, Any], device: str = "cuda:0") -> None:
        import easyocr
        from vietocr.tool.config import Cfg
        from vietocr.tool.predictor import Predictor

        self.config = config
        self.detector = easyocr.Reader(list(config["detector_languages"]), gpu=device.startswith("cuda"))
        recognizer_config = Cfg.load_config_from_name("vgg_transformer")
        recognizer_config["device"] = device
        recognizer_config["predictor"]["beamsearch"] = False
        self.recognizer = Predictor(recognizer_config)

    def read(self, image: Any, cache: CropCache | None = None) -> list[str]:
        """Return recognized text lines for one PIL image in reading order.

        With `cache`, crops seen before reuse their text and only new crops go to VietOCR.
        """

        image = image.copy()
        image.thumbnail((int(self.config["max_image_side"]),) * 2)
        horizontal, free = self.detector.detect(np.asarray(image))
        boxes = [[[x0, y0], [x1, y0], [x1, y1], [x0, y1]] for x0, x1, y0, y1 in horizontal[0]]
        boxes += [list(polygon) for polygon in free[0]]
        rects = reading_order_rects(
            boxes, width=image.width, height=image.height,
            padding=int(self.config["crop_padding_px"]), min_size=int(self.config["min_crop_px"]))
        if not rects:
            return []
        crops = [image.crop(rect) for rect in rects]
        known = [cache.get(crop) if cache is not None else None for crop in crops]
        pending = [index for index, text in enumerate(known) if text is None]
        size = int(self.config["batch_size"])
        for offset in range(0, len(pending), size):
            batch = pending[offset:offset + size]
            for index, text in zip(batch, self.recognizer.predict_batch([crops[i] for i in batch])):
                known[index] = text.strip()
                if cache is not None:
                    cache.put(crops[index], known[index])
        return [str(text) for text in known]
