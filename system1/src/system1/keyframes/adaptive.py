"""Content-adaptive shots and keyframes (ADR 0022).

A shot is a run of near-identical frames. A new shot starts at a cut or when
the content drifts too far from the start of the current shot. Cuts come from
TransNetV2 as cut segments; this module splits each cut segment into shots.

Candidates are planned at a fixed time interval inside each cut segment, then
kept only when they differ enough from the last kept keyframe. A shot also
ends when it reaches a maximum length, so a video recorded in one take is
covered across its whole length.
"""

from __future__ import annotations

import bisect
from collections import deque
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np

from system1.keyframes.signals import difference_hash, difference_hash_distance, laplacian_variance

HASH_SIZE = 8
BLANK_LUMA_STD = 4.0
CUT_FRAME_SIZE = (48, 27)  # (width, height) of the frames the cut predictor reads


class CutPredictor(Protocol):
    """Per-frame cut probabilities from a stream of 48x27 RGB frames.

    `push` returns the predictions that became available, in frame order;
    `finish` returns the rest. Together they give one value per pushed frame.
    """

    def push(self, frame: np.ndarray) -> Sequence[float]: ...

    def finish(self) -> Sequence[float]: ...


class CutDetectionError(RuntimeError):
    """The cut predictor failed or disagreed with the timeline; the caller falls back to one segment."""


@dataclass(frozen=True)
class AdaptiveKeyframePolicy:
    candidate_interval_sec: float
    min_change: float
    shot_drift: float
    max_shot_sec: float
    edge_margin_frames: int
    # A candidate sharper than this fraction of the segment median is kept; 0 disables the filter.
    min_sharpness_ratio: float = 0.3

    def __post_init__(self) -> None:
        if self.candidate_interval_sec <= 0 or self.max_shot_sec <= 0:
            raise ValueError("candidate_interval_sec and max_shot_sec must be positive")
        # min_change is a dHash distance; shot_drift is a cosine distance with
        # image vectors and a dHash distance without them.
        if not (0 < self.min_change <= 1 and 0 < self.shot_drift <= 1):
            raise ValueError("expected 0 < min_change <= 1 and 0 < shot_drift <= 1")
        if self.edge_margin_frames < 0:
            raise ValueError("edge_margin_frames must be non-negative")
        if not 0 <= self.min_sharpness_ratio <= 1:
            raise ValueError("expected 0 <= min_sharpness_ratio <= 1")


@dataclass(frozen=True)
class AdaptiveKeyframe:
    frame_id: int
    timestamp_sec: float
    shot_index: int  # index of the shot inside its cut segment
    reason: str  # "shot_start" or "visual_change"
    vector: np.ndarray | None = None  # image vector, when an embedder was given


def plan_candidate_frames(
    *,
    start_frame: int,
    end_frame: int,
    pts: Sequence[float],
    policy: AdaptiveKeyframePolicy,
) -> list[int]:
    """Return candidate frame IDs for one cut segment `[start_frame, end_frame)`.

    `pts` holds the decoded presentation time of every frame in the video,
    indexed by frame ID. Frames within `edge_margin_frames` of a cut are
    avoided; a segment shorter than one candidate interval gets its middle frame.
    """

    first = start_frame + policy.edge_margin_frames
    last = end_frame - 1 - policy.edge_margin_frames
    if last < first or float(pts[last]) - float(pts[first]) < policy.candidate_interval_sec:
        return [(start_frame + end_frame - 1) // 2]
    frames: list[int] = []
    target = float(pts[first])
    while target <= float(pts[last]):
        frame = bisect.bisect_left(pts, target, lo=first, hi=last + 1)
        frames.append(min(frame, last))
        target += policy.candidate_interval_sec
    return sorted(set(frames))


def select_adaptive_keyframes(
    candidates: Sequence[tuple[int, float, np.ndarray | None]],
    *,
    policy: AdaptiveKeyframePolicy,
    embed: Callable[[list[np.ndarray]], np.ndarray] | None = None,
    report: dict[str, int] | None = None,
) -> list[AdaptiveKeyframe]:
    """Split one cut segment into shots and keep keyframes that add visual information.

    `candidates` are `(frame_id, timestamp_sec, rgb_frame)` in time order.
    Undecodable (`None`), blank, and blurred frames are skipped; a blurred frame
    has a Laplacian variance below `min_sharpness_ratio` times the segment
    median, and the sharpest frame is kept when all are blurred. With `embed`,
    the usable frames are embedded in one call and a new shot starts when the
    cosine distance to the shot start vector exceeds `shot_drift`; without it
    the dHash distance is used. `report["blurred_dropped"]` is incremented by
    the number of blurred frames dropped. An empty result means the segment
    had no usable frame; the caller logs it.
    """

    usable = [(int(frame_id), float(timestamp), frame) for frame_id, timestamp, frame in candidates
              if frame is not None and not _is_blank(frame)]
    if usable and policy.min_sharpness_ratio > 0:
        sharpness = [laplacian_variance(frame) for _, _, frame in usable]
        floor = policy.min_sharpness_ratio * float(np.median(sharpness))
        sharp = [item for item, value in zip(usable, sharpness) if value >= floor]
        if not sharp:
            sharp = [usable[int(np.argmax(sharpness))]]
        if report is not None:
            report["blurred_dropped"] = report.get("blurred_dropped", 0) + len(usable) - len(sharp)
        usable = sharp
    vectors: list[np.ndarray | None] = [None] * len(usable)
    if embed is not None and usable:
        embedded = np.asarray(embed([frame for _, _, frame in usable]), dtype=np.float32)
        if embedded.shape[0] != len(usable):
            raise ValueError(f"embedder returned {embedded.shape[0]} vectors for {len(usable)} frames")
        vectors = list(embedded)

    kept: list[AdaptiveKeyframe] = []
    last_hash: np.ndarray | None = None
    shot_hash: np.ndarray | None = None
    shot_vector: np.ndarray | None = None
    shot_start = 0.0
    shot_index = -1
    for (frame_id, timestamp, frame), vector in zip(usable, vectors):
        signature = difference_hash(frame, hash_size=HASH_SIZE)
        if shot_hash is None or timestamp - shot_start >= policy.max_shot_sec:
            new_shot = True
        elif vector is not None:
            new_shot = _cosine_distance(vector, shot_vector) > policy.shot_drift
        else:
            new_shot = difference_hash_distance(signature, shot_hash) >= policy.shot_drift
        if new_shot:
            shot_index += 1
            shot_hash = signature
            shot_vector = vector
            shot_start = timestamp
            reason = "shot_start"
        elif difference_hash_distance(signature, last_hash) >= policy.min_change:
            reason = "visual_change"
        else:
            continue
        kept.append(AdaptiveKeyframe(frame_id, timestamp, shot_index, reason, vector))
        last_hash = signature
    return kept


def _cosine_distance(left: np.ndarray, right: np.ndarray) -> float:
    norm = float(np.linalg.norm(left) * np.linalg.norm(right))
    return 1.0 - float(np.dot(left, right)) / norm if norm > 0 else 1.0


def _is_blank(frame: np.ndarray) -> bool:
    return float(np.asarray(frame, dtype=np.float32).mean(axis=-1).std()) < BLANK_LUMA_STD


def iter_cut_segment_frames(
    video_path: Path | str,
    *,
    pts: Sequence[float],
    policy: AdaptiveKeyframePolicy,
    predictor: CutPredictor | None,
    threshold: float,
) -> Iterator[tuple[int, int, list[int], dict[int, np.ndarray]]]:
    """Decode the video once; yield `(start_frame, end_frame, plan, frames)` per cut segment.

    Each frame feeds the cut predictor as a 48x27 frame. Cut segments follow
    `predictions_to_scenes` (midpoint of each positive run that touches neither
    end); `plan` is `plan_candidate_frames` of the segment and `frames` maps its
    decoded candidates to RGB arrays, as `iter_decode_frame_groups` would.
    A full-resolution frame is held only while its segment start is unknown
    (the predictor lag plus any open positive run) or while it can still be a
    candidate of its segment. With `predictor=None` the whole timeline is one
    segment. Predictor errors and a frame count different from `pts` raise
    `CutDetectionError`.
    """

    import cv2

    frame_total = len(pts)
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise RuntimeError(f"Cannot open video for keyframe extraction: {video_path}")
    predictions: list[float] = []
    boundaries: deque[int] = deque()  # last frame of each cut segment, from closed runs
    state = {"run_start": None, "scanned": 0, "classified": 0, "start": 0}
    pending: dict[int, np.ndarray] = {}  # BGR frames whose segment is not known yet
    kept: dict[int, np.ndarray] = {}  # RGB frames that can be candidates of the current segment
    window = _CandidateWindow(0, pts, policy)

    def known_until() -> int:
        # Frames before the returned index have a known segment start.
        while state["scanned"] < len(predictions):
            index = state["scanned"]
            positive = predictions[index] > threshold
            if positive and state["run_start"] is None:
                state["run_start"] = index
            elif not positive and state["run_start"] is not None:
                if state["run_start"] > 0:
                    boundaries.append((state["run_start"] + index - 1) // 2)
                state["run_start"] = None
            state["scanned"] += 1
        return state["run_start"] if state["run_start"] is not None else state["scanned"]

    def finalize(end: int) -> tuple[int, int, list[int], dict[int, np.ndarray]]:
        start = state["start"]
        plan = plan_candidate_frames(start_frame=start, end_frame=end, pts=pts, policy=policy)
        frames = {frame: kept[frame] for frame in plan if frame in kept}
        kept.clear()
        return start, end, plan, frames

    def classify(limit: int) -> Iterator[tuple[int, int, list[int], dict[int, np.ndarray]]]:
        nonlocal window
        while state["classified"] < limit:
            frame = state["classified"]
            bgr = pending.pop(frame, None)
            if bgr is not None and window.wants(frame):
                kept[frame] = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            state["classified"] += 1
            if boundaries and boundaries[0] == frame:
                boundaries.popleft()
                yield finalize(frame + 1)
                state["start"] = frame + 1
                window = _CandidateWindow(frame + 1, pts, policy)

    def predict(call, *args) -> Sequence[float]:
        try:
            return [float(value) for value in call(*args)]
        except Exception as exc:
            raise CutDetectionError(f"{type(exc).__name__}: {exc}") from exc

    try:
        decoded = 0
        while decoded < frame_total and capture.grab():  # frames past the timeline are never used
            ok, bgr = capture.retrieve()
            if ok and bgr is not None:
                pending[decoded] = bgr
            if predictor is None:
                predictions.append(0.0)
            elif not ok or bgr is None:
                raise CutDetectionError(f"frame {decoded} could not be decoded for cut detection")
            else:
                small = cv2.resize(bgr, CUT_FRAME_SIZE, interpolation=cv2.INTER_AREA)
                predictions.extend(predict(predictor.push, cv2.cvtColor(small, cv2.COLOR_BGR2RGB)))
            decoded += 1
            yield from classify(known_until())
        if predictor is None:
            predictions.extend([0.0] * (frame_total - len(predictions)))
        else:
            predictions.extend(predict(predictor.finish))
            if not decoded == len(predictions) == frame_total:
                raise CutDetectionError(f"decoded {decoded} frames and {len(predictions)} predictions "
                                        f"for a timeline of {frame_total} frames")
        known_until()  # a positive run that reaches the last frame is not a cut
        yield from classify(frame_total)
        yield finalize(frame_total)
    finally:
        capture.release()


class _CandidateWindow:
    """Which frames of a segment starting at `start` can appear in its candidate plan.

    The plan holds grid frames from `start + edge_margin_frames` every
    `candidate_interval_sec`, or the middle frame of a segment shorter than one
    interval. Every frame up to the second grid frame is kept (it covers the
    middle frame); after that only grid frames. The grid repeats the float
    steps of `plan_candidate_frames`, so the selected frames match it exactly.
    """

    def __init__(self, start: int, pts: Sequence[float], policy: AdaptiveKeyframePolicy) -> None:
        self.pts = pts
        self.first = start + policy.edge_margin_frames
        self.interval = policy.candidate_interval_sec
        if self.first >= len(pts):
            self.until, self.next = len(pts), len(pts)
            return
        self.target = float(pts[self.first]) + self.interval
        self.until = bisect.bisect_left(pts, self.target, lo=self.first)
        self.next = self.until

    def wants(self, frame: int) -> bool:
        if frame <= self.until:
            return True
        while self.next < frame and self.next < len(self.pts):
            self.target += self.interval
            self.next = bisect.bisect_left(self.pts, self.target, lo=self.first)
        return frame == self.next
