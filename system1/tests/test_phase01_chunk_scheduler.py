from __future__ import annotations

import pytest

from system1.phase01.scheduler import plan_runtime_chunks

POLICY = {
    "max_chunk_videos": 4,
    "max_chunk_raw_bytes": 1_500,
    "min_free_disk_gb": 20,
    "medium_free_disk_gb": 35,
    "medium_max_chunk_videos": 2,
    "low_disk_max_chunk_videos": 1,
}


def test_chunk_planner_applies_video_count_and_manifest_order() -> None:
    video_ids = [f"video_{index}" for index in range(8)]

    chunks = plan_runtime_chunks(
        video_ids,
        raw_bytes_by_video={video_id: 100 for video_id in video_ids},
        free_disk_gb=100,
        policy=POLICY,
    )

    assert [chunk.video_ids for chunk in chunks] == [
        tuple(video_ids[:4]),
        tuple(video_ids[4:]),
    ]
    assert [chunk.raw_bytes for chunk in chunks] == [400, 400]


def test_chunk_planner_applies_raw_byte_limit_without_splitting_a_video() -> None:
    chunks = plan_runtime_chunks(
        ["a", "b", "large", "c"],
        raw_bytes_by_video={"a": 600, "b": 600, "large": 2_000, "c": 100},
        free_disk_gb=100,
        policy=POLICY,
    )

    assert [chunk.video_ids for chunk in chunks] == [
        ("a", "b"),
        ("large",),
        ("c",),
    ]
    assert chunks[1].raw_bytes == 2_000


@pytest.mark.parametrize(
    ("free_disk_gb", "expected_sizes"),
    [
        (19.9, [1, 1, 1, 1, 1]),
        (20.0, [2, 2, 1]),
        (35.0, [2, 2, 1]),
        (35.1, [4, 1]),
    ],
)
def test_chunk_planner_reduces_chunk_size_under_disk_pressure(
    free_disk_gb: float, expected_sizes: list[int]
) -> None:
    video_ids = [f"video_{index}" for index in range(5)]

    chunks = plan_runtime_chunks(
        video_ids,
        raw_bytes_by_video={video_id: 1 for video_id in video_ids},
        free_disk_gb=free_disk_gb,
        policy=POLICY,
    )

    assert [len(chunk.video_ids) for chunk in chunks] == expected_sizes


def test_chunk_planner_treats_unknown_raw_size_conservatively() -> None:
    chunks = plan_runtime_chunks(
        ["unknown", "known"],
        raw_bytes_by_video={"unknown": None, "known": 1},
        free_disk_gb=100,
        policy=POLICY,
    )

    assert [chunk.video_ids for chunk in chunks] == [("unknown",), ("known",)]


def test_chunk_planner_rejects_invalid_policy() -> None:
    with pytest.raises(ValueError, match="max_chunk_videos"):
        plan_runtime_chunks(
            ["video"],
            raw_bytes_by_video={"video": 1},
            free_disk_gb=100,
            policy={**POLICY, "max_chunk_videos": 0},
        )
