"""OCR: EasyOCR text detection + VietOCR recognition (ADR 0023)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

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


def clean_ocr_lines(lines: Sequence[str], *, min_chars: int) -> list[str]:
    """Drop recognition noise: lines with fewer than `min_chars` letters or digits."""

    cleaned = []
    for line in lines:
        text = " ".join(line.split())
        if sum(char.isalnum() for char in text) >= min_chars:
            cleaned.append(text)
    return cleaned


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

    def read(self, image: Any) -> list[str]:
        """Return cleaned text lines for one PIL image in reading order."""

        import numpy as np

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
        lines: list[str] = []
        size = int(self.config["batch_size"])
        for offset in range(0, len(crops), size):
            lines += [text.strip() for text in self.recognizer.predict_batch(crops[offset:offset + size])]
        return lines
