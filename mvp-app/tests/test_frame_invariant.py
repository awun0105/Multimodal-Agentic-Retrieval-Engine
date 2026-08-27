"""Release-wide invariant: floor(pts * fps) == frame_idx for every keyframe.

This is the evidence that turns the floor rule into the organizer-compatible
mapping used by the player and pin logic. Skipped automatically when the
release data is not present on the machine.
"""

import os
import sqlite3
from pathlib import Path

import pytest

from frame_math import calculated_frame

_ENV_CANDIDATES = (
    os.environ.get("AIOU_RELEASE_DIR"),
    "~/Downloads/aiou-app-storage/releases/aic25-b1-v1",
)


def _find_release_db() -> Path | None:
    for candidate in _ENV_CANDIDATES:
        if not candidate:
            continue
        path = Path(candidate).expanduser() / "metadata" / "runtime.sqlite"
        if path.is_file():
            return path
    return None


RELEASE_DB = _find_release_db()

pytestmark = pytest.mark.skipif(
    RELEASE_DB is None, reason="release runtime.sqlite not available on this machine"
)


def test_every_release_keyframe_satisfies_floor_rule():
    connection = sqlite3.connect(f"file:{RELEASE_DB}?mode=ro", uri=True)
    try:
        rows = connection.execute(
            "SELECT pts_time_sec, fps, frame_idx FROM keyframes WHERE fps > 0"
        ).fetchall()
    finally:
        connection.close()

    assert len(rows) > 100_000, "release unexpectedly small; wrong database?"
    mismatches = [
        (pts, fps, frame_idx)
        for pts, fps, frame_idx in rows
        if calculated_frame(pts, fps) != frame_idx
    ]
    assert mismatches == []
