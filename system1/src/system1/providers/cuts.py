"""Cut detection with TransNetV2, reusing the pinned project artifact.

The model is loaded once per session, in process, and reads the 48x27 frames
of the worker's single decode pass (plan Step 5f item 3). Cut segments are
built from its predictions in `system1.keyframes.adaptive.iter_cut_segment_frames`;
shots are split from them by visual change. A failure is not retried on CPU:
the worker falls back to one segment (plan Step 5f item 11, ADR 0024).
"""

from __future__ import annotations

from collections import deque
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np

from system1.phase01.model_artifacts import materialize_transnet_artifact
from system1.shots.transnet_worker import FRAME_SHAPE, _load_model, _predict_window


class TransNetCuts:
    def __init__(self, model_config: Mapping[str, Any], storage_config: Mapping[str, Any],
                 cache_root: Path) -> None:
        if str(model_config["transition_run_boundary"]) != "midpoint":
            raise ValueError(f"Unsupported transition-run policy: {model_config['transition_run_boundary']}")
        self.threshold = float(model_config["threshold"])
        artifact = materialize_transnet_artifact(
            model_config=model_config, storage_config=storage_config, cache_root=cache_root)
        self.model, self.device = _load_model(artifact.source_path, artifact.weights_path, "auto")

    def start(self) -> TransNetStream:
        return TransNetStream(lambda frames: _predict_window(self.model, self.device, frames))


class TransNetStream:
    """Streaming form of `transnet_worker.predict_video`: same windows, same predictions.

    Windows hold 100 frames and advance by 50; each gives predictions for its
    middle 50 frames. The first window starts with 25 copies of the first
    frame and the last is padded with the last frame.
    """

    def __init__(self, predict_window) -> None:
        self.predict_window = predict_window
        self.window: deque[np.ndarray] = deque()
        self.frame_count = 0
        self.emitted = 0
        self.last: np.ndarray | None = None

    def push(self, frame: np.ndarray) -> list[float]:
        frame = np.ascontiguousarray(frame, dtype=np.uint8)
        if frame.shape != FRAME_SHAPE:
            raise ValueError(f"TransNet expects {FRAME_SHAPE} frames, got {frame.shape}")
        if self.last is None:
            self.window.extend(frame.copy() for _ in range(25))
        self.window.append(frame)
        self.last = frame
        self.frame_count += 1
        if len(self.window) == 100:
            return self._predict()
        return []

    def finish(self) -> list[float]:
        if self.last is None:
            raise RuntimeError("Video contains no decodable frames")
        values: list[float] = []
        while self.emitted < self.frame_count:
            while len(self.window) < 100:
                self.window.append(self.last.copy())
            values.extend(self._predict())
        return values[:self.frame_count - (self.emitted - len(values))]

    def _predict(self) -> list[float]:
        values = [float(value) for value in self.predict_window(list(self.window))]
        for _ in range(min(50, len(self.window))):
            self.window.popleft()
        self.emitted += len(values)
        return values
