from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class TimelineFrame:
    frame_id: int
    pts_time: float
    duration_time: float | None


@dataclass(frozen=True)
class TimelineContext:
    video_id: str
    frames: tuple[TimelineFrame, ...] = ()
    source_ref: str | None = None

    @property
    def available(self) -> bool:
        return bool(self.frames)

    @property
    def frame_count(self) -> int | None:
        return len(self.frames) if self.frames else None

    def pts_for_frame(self, frame_id: int) -> float | None:
        if frame_id < 0 or frame_id >= len(self.frames):
            return None
        return self.frames[frame_id].pts_time

    def duration_for_frame(self, frame_id: int) -> float | None:
        if frame_id < 0 or frame_id >= len(self.frames):
            return None
        return self.frames[frame_id].duration_time

    def end_seconds(self, fallback: float) -> float:
        if not self.frames:
            return fallback
        last = self.frames[-1]
        return last.pts_time + (last.duration_time or 0.0)


@dataclass(frozen=True)
class ShotBoundary:
    shot_id: str
    start_frame: int
    end_frame: int
    start_seconds: float
    end_seconds: float
    detection_method: str
    status: str


@dataclass(frozen=True)
class KeyframeSelection:
    keyframe_id: str
    frame_id: int
    time_seconds: float
    frame_id_method: str
    selection_method: str
    status: str
    shot_id: str
    scene_id: str


@dataclass(frozen=True)
class SceneBoundary:
    scene_id: str
    start_frame: int
    end_frame: int
    start_seconds: float
    end_seconds: float
    shot_ids: tuple[str, ...]
    construction_method: str
    status: str


class ShotDetectionProvider(Protocol):
    def detect_shots(
        self,
        *,
        video_id: str,
        timeline: TimelineContext,
        frame_count: int | None,
        duration_seconds: float,
    ) -> list[ShotBoundary]: ...


class KeyframeSelectionProvider(Protocol):
    def select_keyframes(
        self,
        *,
        video_id: str,
        timeline: TimelineContext,
        shots: list[ShotBoundary],
        scene_id: str,
    ) -> list[KeyframeSelection]: ...


class SceneConstructionProvider(Protocol):
    def construct_scenes(
        self,
        *,
        video_id: str,
        timeline: TimelineContext,
        shots: list[ShotBoundary],
    ) -> list[SceneBoundary]: ...


@dataclass(frozen=True)
class TimelineAwareFallbackProvider:
    """Deterministic phase01 fallback that uses decoded timeline facts when available."""

    def detect_shots(
        self,
        *,
        video_id: str,
        timeline: TimelineContext,
        frame_count: int | None,
        duration_seconds: float,
    ) -> list[ShotBoundary]:
        end_frame = timeline.frame_count or frame_count or 1
        end_seconds = timeline.end_seconds(duration_seconds)
        return [
            ShotBoundary(
                shot_id=f"{video_id}_SH00000",
                start_frame=0,
                end_frame=end_frame,
                start_seconds=0.0,
                end_seconds=end_seconds,
                detection_method="fallback_full_video_from_frame_timeline" if timeline.available else "fallback_full_video",
                status="degraded",
            )
        ]

    def construct_scenes(
        self,
        *,
        video_id: str,
        timeline: TimelineContext,
        shots: list[ShotBoundary],
    ) -> list[SceneBoundary]:
        first_shot = shots[0]
        return [
            SceneBoundary(
                scene_id=f"{video_id}_SC00000",
                start_frame=first_shot.start_frame,
                end_frame=first_shot.end_frame,
                start_seconds=first_shot.start_seconds,
                end_seconds=first_shot.end_seconds,
                shot_ids=tuple(shot.shot_id for shot in shots),
                construction_method="fallback_scene_from_timeline_shots" if timeline.available else "fallback_scene_from_full_video_shot",
                status="degraded",
            )
        ]

    def select_keyframes(
        self,
        *,
        video_id: str,
        timeline: TimelineContext,
        shots: list[ShotBoundary],
        scene_id: str,
    ) -> list[KeyframeSelection]:
        shot = shots[0]
        frame_id = shot.start_frame
        time_seconds = timeline.pts_for_frame(frame_id) if timeline.available else None
        return [
            KeyframeSelection(
                keyframe_id=f"{video_id}:{frame_id}",
                frame_id=frame_id,
                time_seconds=time_seconds if time_seconds is not None else shot.start_seconds,
                frame_id_method="decoded_frame_timeline" if timeline.available else "first_frame_extraction_assumed_frame_0",
                selection_method="timeline_first_frame" if timeline.available else "fallback_first_frame",
                status="pass" if timeline.available else "degraded",
                shot_id=shot.shot_id,
                scene_id=scene_id,
            )
        ]
