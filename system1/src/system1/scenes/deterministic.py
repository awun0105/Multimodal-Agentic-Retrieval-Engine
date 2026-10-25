"""Deterministic scene grouping over shot evidence (ADR 0026).

A scene is a run of consecutive shots of one situation. Shots join the current
scene when a weighted continuity score of five signals (visual, semantic,
speech bridge, silence, shared text) reaches a threshold. Short single-shot
scenes merge into a neighbour, and scenes longer than a cap split at their
weakest internal boundary. Scenes tile the shots in order.

Choices the ADR leaves open:

- Adjacent silence: the silent span reaches back to the last ASR segment end
  before the gap and forward to the next ASR segment start after it, bounded
  by the start of the previous shot and the end of the current shot.
- Split point: each internal shot is re-scored against the scene's shots
  before it; the scene splits before the shot with the lowest score.
- Merge tie: a short scene equally close to both neighbours merges into the
  earlier one.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class ShotEvidence:
    shot_id: str
    start_frame: int
    end_frame: int
    start_sec: float
    end_sec: float
    image_vector: np.ndarray
    caption_vector: np.ndarray | None
    ocr_lines: frozenset[str]


@dataclass(frozen=True)
class SceneParams:
    w_img: float
    w_cap: float
    w_asr: float
    w_sil: float
    w_ocr: float
    scene_threshold: float
    silence_sec: float
    min_scene_sec: float
    max_scene_sec: float

    def __post_init__(self) -> None:
        if self.silence_sec < 0 or self.min_scene_sec < 0:
            raise ValueError("silence_sec and min_scene_sec must be non-negative")
        if self.max_scene_sec <= 0:
            raise ValueError("max_scene_sec must be positive")

    @classmethod
    def from_config(cls, mapping: Mapping[str, object]) -> SceneParams:
        return cls(**{name: float(mapping[name]) for name in cls.__dataclass_fields__})


@dataclass(frozen=True)
class Scene:
    scene_id: str
    video_id: str
    start_shot_id: str
    end_shot_id: str
    start_frame: int
    end_frame: int
    start_sec: float
    end_sec: float
    shot_count: int


@dataclass(frozen=True)
class SceneState:
    """Running evidence of the current scene."""

    mean_image: np.ndarray
    mean_caption: np.ndarray | None
    ocr_lines: frozenset[str]


def _unit(vector: np.ndarray) -> np.ndarray:
    vector = np.asarray(vector, dtype=np.float64).ravel()
    norm = float(np.linalg.norm(vector))
    return vector / norm if norm > 0 else vector


def _cosine(a: np.ndarray | None, b: np.ndarray | None) -> float:
    if a is None or b is None:
        return 0.0
    return float(np.dot(_unit(a), _unit(b)))


def scene_state(shots: Sequence[ShotEvidence]) -> SceneState:
    """Mean image and caption vectors and OCR union over `shots`."""

    captions = [_unit(s.caption_vector) for s in shots if s.caption_vector is not None]
    return SceneState(
        mean_image=np.mean([_unit(s.image_vector) for s in shots], axis=0),
        mean_caption=np.mean(captions, axis=0) if captions else None,
        ocr_lines=frozenset().union(*(s.ocr_lines for s in shots)),
    )


def _speech_bridge(previous: ShotEvidence, shot: ShotEvidence, asr: Sequence[tuple[float, float]]) -> float:
    return float(any(start <= previous.end_sec and end >= shot.start_sec for start, end in asr))


def _silence(
    previous: ShotEvidence, shot: ShotEvidence, asr: Sequence[tuple[float, float]], silence_sec: float
) -> float:
    gap_start, gap_end = previous.end_sec, max(shot.start_sec, previous.end_sec)
    if any(start < gap_end and end > gap_start for start, end in asr):
        return 0.0
    if gap_end == gap_start and any(start < gap_start < end for start, end in asr):
        return 0.0
    # Adjacent silence is bounded by the nearest speech and by the two shots.
    silent_from = max([previous.start_sec, *(end for _, end in asr if end <= gap_start)])
    silent_to = min([shot.end_sec, *(start for start, _ in asr if start >= gap_end)])
    return float(silent_to - silent_from > silence_sec)


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    union = a | b
    return len(a & b) / len(union) if union else 0.0


def continuity_score(
    shot: ShotEvidence,
    state: SceneState,
    previous_shot: ShotEvidence,
    asr_segments: Sequence[tuple[float, float]],
    params: SceneParams,
) -> float:
    """Weighted continuity of `shot` with the scene ending at `previous_shot`."""

    return (
        params.w_img * _cosine(shot.image_vector, state.mean_image)
        + params.w_cap * _cosine(shot.caption_vector, state.mean_caption)
        + params.w_asr * _speech_bridge(previous_shot, shot, asr_segments)
        - params.w_sil * _silence(previous_shot, shot, asr_segments, params.silence_sec)
        + params.w_ocr * _jaccard(shot.ocr_lines, state.ocr_lines)
    )


def _internal_scores(
    shots: Sequence[ShotEvidence], asr: Sequence[tuple[float, float]], params: SceneParams
) -> list[float]:
    """Score of shot i+1 against shots[: i+1], for each internal boundary i."""

    return [continuity_score(shots[i], scene_state(shots[:i]), shots[i - 1], asr, params) for i in range(1, len(shots))]


def _duration(group: Sequence[ShotEvidence]) -> float:
    return group[-1].end_sec - group[0].start_sec


def group_scenes(
    video_id: str,
    shots: Sequence[ShotEvidence],
    asr_segments: Sequence[tuple[float, float]],
    params: SceneParams,
) -> list[Scene]:
    """Group time-ordered shots into scenes that tile them (ADR 0026 steps 1-6)."""

    if not shots:
        return []
    asr = [(float(start), float(end)) for start, end in asr_segments]

    groups: list[list[ShotEvidence]] = [[shots[0]]]
    for previous, shot in zip(shots, shots[1:]):
        score = continuity_score(shot, scene_state(groups[-1]), previous, asr, params)
        if score >= params.scene_threshold:
            groups[-1].append(shot)
        else:
            groups.append([shot])

    index = 0
    while index < len(groups) and len(groups) > 1:
        group = groups[index]
        if len(group) == 1 and _duration(group) < params.min_scene_sec:
            image = group[0].image_vector
            neighbours = [n for n in (index - 1, index + 1) if 0 <= n < len(groups)]
            target = max(neighbours, key=lambda n: (_cosine(image, scene_state(groups[n]).mean_image), -n))
            if target < index:
                groups[target].extend(group)
            else:
                groups[target][:0] = group
            del groups[index]
            index = max(index - 1, 0)
            continue
        index += 1

    tiled: list[list[ShotEvidence]] = []
    pending = list(reversed(groups))
    while pending:
        group = pending.pop()
        if len(group) > 1 and _duration(group) > params.max_scene_sec:
            scores = _internal_scores(group, asr, params)
            cut = int(np.argmin(scores)) + 1
            pending.extend([group[cut:], group[:cut]])
        else:
            tiled.append(group)

    return [
        Scene(
            scene_id=f"{video_id}_SC{n:05d}",
            video_id=video_id,
            start_shot_id=group[0].shot_id,
            end_shot_id=group[-1].shot_id,
            start_frame=group[0].start_frame,
            end_frame=group[-1].end_frame,
            start_sec=group[0].start_sec,
            end_sec=group[-1].end_sec,
            shot_count=len(group),
        )
        for n, group in enumerate(tiled)
    ]


def scene_ids_for_shots(scenes: Sequence[Scene], shots: Sequence[ShotEvidence]) -> dict[str, str]:
    """Map each shot_id to its scene_id, using the ordered shot list."""

    mapping: dict[str, str] = {}
    position = 0
    for scene in scenes:
        for shot in shots[position : position + scene.shot_count]:
            mapping[shot.shot_id] = scene.scene_id
        position += scene.shot_count
    if position != len(shots):
        raise ValueError("scenes do not tile the shot list")
    return mapping
