from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from system1.media.probe import VideoProbe, VideoProbeWithTimeline
from system1.media.timeline import (
    FrameTimelineError,
    build_frame_timeline_file_with_retry,
    build_frame_timeline_with_retry,
    resolve_timeline_workers,
    validate_frame_timeline_file,
    validate_frame_timeline_rows,
    write_frame_timeline,
)


def _probe() -> VideoProbe:
    return VideoProbe(25.0, "test", 2, False, "decoded_frame_timeline", 0.08, 640, 360, False)


def _rows(video_id: str) -> list[dict[str, float | int | str | None]]:
    return [
        {"video_id": video_id, "frame_id": 0, "pts_time": 0.0, "duration_time": 0.04},
        {"video_id": video_id, "frame_id": 1, "pts_time": 0.04, "duration_time": 0.04},
    ]


def test_required_frame_timeline_retries_then_passes(tmp_path: Path) -> None:
    calls = 0
    sleeps: list[float] = []

    def fake_probe(_path: Path, *, video_id: str) -> VideoProbeWithTimeline:
        nonlocal calls
        calls += 1
        return VideoProbeWithTimeline(_probe(), [] if calls < 3 else _rows(video_id))

    result = build_frame_timeline_with_retry(
        tmp_path / "A.mp4",
        video_id="A",
        policy="required",
        probe_fn=fake_probe,
        sleep_fn=sleeps.append,
    )

    assert result.status == "pass"
    assert result.attempts == 3
    assert sleeps == [0.5, 1.0]


def test_required_frame_timeline_fails_after_retry_budget(tmp_path: Path) -> None:
    with pytest.raises(FrameTimelineError, match="after 3 attempts"):
        build_frame_timeline_with_retry(
            tmp_path / "A.mp4",
            video_id="A",
            policy="required",
            probe_fn=lambda _path, *, video_id: VideoProbeWithTimeline(_probe(), []),
            sleep_fn=lambda _delay: None,
        )


def test_frame_timeline_validation_rejects_gaps_and_non_finite_pts() -> None:
    with pytest.raises(FrameTimelineError, match="contiguous"):
        validate_frame_timeline_rows(
            [
                {"video_id": "A", "frame_id": 0, "pts_time": 0.0, "duration_time": 0.04},
                {"video_id": "A", "frame_id": 2, "pts_time": 0.04, "duration_time": 0.04},
            ],
            expected_video_id="A",
        )
    with pytest.raises(FrameTimelineError, match="pts_time"):
        validate_frame_timeline_rows(
            [{"video_id": "A", "frame_id": 0, "pts_time": float("nan"), "duration_time": 0.04}],
            expected_video_id="A",
        )


def test_frame_timeline_parquet_round_trip(tmp_path: Path) -> None:
    result = build_frame_timeline_with_retry(
        tmp_path / "A.mp4",
        video_id="A",
        policy="required",
        probe_fn=lambda _path, *, video_id: VideoProbeWithTimeline(_probe(), _rows(video_id)),
        sleep_fn=lambda _delay: None,
    )
    target = tmp_path / "A.parquet"

    assert write_frame_timeline(target, result, video_id="A") == 2
    assert validate_frame_timeline_file(target, expected_video_id="A") == 2
    assert list(pd.read_parquet(target).columns) == [
        "video_id",
        "frame_id",
        "pts_time",
        "duration_time",
    ]


def test_streamed_frame_timeline_writes_one_atomic_file_in_small_chunks(tmp_path: Path) -> None:
    target = tmp_path / "frame_timeline" / "A.parquet"
    result = build_frame_timeline_file_with_retry(
        tmp_path / "A.mp4",
        target,
        video_id="A",
        policy="required",
        chunk_rows=1,
        row_iter_fn=lambda _path, *, video_id: iter(_rows(video_id)),
        header_probe_fn=lambda _path: _probe(),
        sleep_fn=lambda _delay: None,
    )

    assert result.status == "pass"
    assert result.path == target
    assert result.row_count == 2
    assert result.probe.frame_count == 2
    assert result.probe.frame_count_method == "decoded_frame_timeline"
    assert validate_frame_timeline_file(target, expected_video_id="A") == 2
    assert not target.with_suffix(".parquet.partial").exists()


def test_streamed_frame_timeline_failure_removes_partial_file(tmp_path: Path) -> None:
    target = tmp_path / "A.parquet"

    with pytest.raises(FrameTimelineError, match="after 3 attempts"):
        build_frame_timeline_file_with_retry(
            tmp_path / "A.mp4",
            target,
            video_id="A",
            policy="required",
            row_iter_fn=lambda _path, *, video_id: iter(
                [
                    {
                        "video_id": video_id,
                        "frame_id": 1,
                        "pts_time": 0.0,
                        "duration_time": 0.04,
                    }
                ]
            ),
            header_probe_fn=lambda _path: _probe(),
            sleep_fn=lambda _delay: None,
        )

    assert not target.exists()
    assert not target.with_suffix(".parquet.partial").exists()


def test_optional_streamed_frame_timeline_returns_unavailable_without_partial(
    tmp_path: Path,
) -> None:
    target = tmp_path / "A.parquet"

    result = build_frame_timeline_file_with_retry(
        tmp_path / "A.mp4",
        target,
        video_id="A",
        policy="if-available",
        row_iter_fn=lambda _path, *, video_id: iter(()),
        header_probe_fn=lambda _path: _probe(),
        sleep_fn=lambda _delay: None,
    )

    assert result.status == "unavailable"
    assert result.path is None
    assert result.row_count == 0
    assert result.attempts == 3
    assert not target.exists()
    assert not target.with_suffix(".parquet.partial").exists()


def test_timeline_worker_resolution_is_colab_safe(monkeypatch) -> None:
    monkeypatch.setattr("system1.media.timeline.os.sched_getaffinity", lambda _pid: {0, 1, 2, 3})

    assert resolve_timeline_workers("auto") == 2
    assert resolve_timeline_workers("1") == 1
    assert resolve_timeline_workers(2) == 2
    with pytest.raises(FrameTimelineError, match="auto, 1, or 2"):
        resolve_timeline_workers("4")
