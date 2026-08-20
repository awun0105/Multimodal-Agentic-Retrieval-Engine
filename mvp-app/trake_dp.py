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


def dp_best_path_min(s: np.ndarray) -> tuple[float, list[int]] | None:
    """Maximise the weakest event on the path instead of the sum.

    Summing lets a video with two strong events and one absent event outrank a
    video that actually contains all three. Comparison key is (min, sum) — sum
    only breaks ties.
    """
    length, events = s.shape
    if length < events:
        return None
    dp_min = np.full((length, events), -np.inf, dtype=np.float64)
    dp_sum = np.full((length, events), -np.inf, dtype=np.float64)
    backtrack = np.full((length, events), -1, dtype=np.int64)
    dp_min[:, 0] = s[:, 0]
    dp_sum[:, 0] = s[:, 0]
    for j in range(1, events):
        best_min = -np.inf
        best_sum = -np.inf
        best_idx = -1
        for i in range(length):
            if i >= j and best_idx >= 0:
                dp_min[i, j] = min(best_min, s[i, j])
                dp_sum[i, j] = best_sum + s[i, j]
                backtrack[i, j] = best_idx
            # Updating after the assignment is what keeps indices strictly increasing.
            if (dp_min[i, j - 1], dp_sum[i, j - 1]) > (best_min, best_sum):
                best_min = dp_min[i, j - 1]
                best_sum = dp_sum[i, j - 1]
                best_idx = i
    last_min = dp_min[:, events - 1]
    last_sum = dp_sum[:, events - 1]
    i_last = max(range(length), key=lambda i: (last_min[i], last_sum[i]))
    score = float(last_min[i_last])
    if not np.isfinite(score):
        return None
    indices = [0] * events
    idx = i_last
    for j in range(events - 1, -1, -1):
        indices[j] = idx
        idx = int(backtrack[idx, j]) if j > 0 else idx
    return score, indices
