"""Strictly-increasing maximal-prefix dynamic programming for TRAKE event chains."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class VideoSlice:
    video_id: str
    start: int
    end: int
    max_frame_idx: int


def dp_best_path(s: np.ndarray) -> tuple[float, list[int]] | None:
    length, events = s.shape
    if length < events:
        return None
    dp = np.full((length, events), -np.inf, dtype=np.float64)
    backtrack = np.full((length, events), -1, dtype=np.int64)
    dp[:, 0] = s[:, 0]
    for j in range(1, events):
        best_prefix = -np.inf
        best_prefix_idx = -1
        for i in range(length):
            if i >= j:
                dp[i, j] = s[i, j] + best_prefix
                backtrack[i, j] = best_prefix_idx
            # running max over dp[:, j-1] up to i (i-1 for row i keeps indices strictly increasing)
            if dp[i, j - 1] > best_prefix:
                best_prefix = dp[i, j - 1]
                best_prefix_idx = i
    last_col = dp[:, events - 1]
    i_last = int(np.argmax(last_col))
    score = float(last_col[i_last])
    if not np.isfinite(score):
        return None
    indices = [0] * events
    idx = i_last
    for j in range(events - 1, -1, -1):
        indices[j] = idx
        idx = int(backtrack[idx, j]) if j > 0 else idx
    return score, indices
