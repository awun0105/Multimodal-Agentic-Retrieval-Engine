import sqlite3
from pathlib import Path

import numpy as np
import pytest

import trake
from schemas import PreparedQuery, TrakeEventMatch, TrakeOutcome, TrakeVideoMatch
from trake import (
    SPREAD_RADIUS,
    SPREAD_ROWS_PER_VIDEO,
    SUBMISSION_MAX_ROWS,
    TrakeSearcher,
    _dp_best_path,
    build_submission,
    format_submission,
    spread_frames,
)


class FakeClipSearcher:
    """Returns a fixed 2-D vector per call, keyed by the text seen."""

    def __init__(self, vectors: dict[str, tuple[float, float]]):
        self.vectors = vectors
        self.calls: list[str] = []

    def get_text_features(self, text):
        self.calls.append(text)
        vector = self.vectors.get(text, (1.0, 0.0))
        return np.asarray([vector], dtype=np.float32)


class FakeTranslator:
    """Mimics QueryTranslator.prepare without any model."""

    def prepare(self, query, requested_language="auto", *, translate_vietnamese=None):
        normalized = " ".join(query.split())
        return PreparedQuery(
            normalized,
            normalized,
            requested_language,
            "not_checked",
            translated=False,
            translation_enabled=False,
        )


# ---------------------------------------------------------------------------
# Dynamic programming
# ---------------------------------------------------------------------------


def test_dp_picks_strictly_increasing_indices():
    s = np.asarray([[9, 0], [0, 9], [0, 0]], dtype=np.float32)
    result = _dp_best_path(s)
    assert result is not None
    score, indices = result
    assert indices == [0, 1]
    assert score == pytest.approx(18)


def test_dp_rejects_video_shorter_than_events():
    s = np.zeros((2, 3), dtype=np.float32)
    assert _dp_best_path(s) is None


def test_dp_forbids_reusing_one_keyframe():
    s = np.asarray([[9, 9], [0, 0]], dtype=np.float32)
    result = _dp_best_path(s)
    assert result is not None
    score, indices = result
    assert score == pytest.approx(9)
    assert indices == [0, 1]


def test_dp_handles_single_event():
    s = np.asarray([[1.0], [5.0], [3.0]], dtype=np.float32)
    result = _dp_best_path(s)
    assert result is not None
    score, indices = result
    assert indices == [1]
    assert score == pytest.approx(5.0)


def test_dp_prefers_global_optimum_not_greedy():
    s = np.asarray(
        [
            [10, 0, 0],
            [0, 1, 0],
            [0, 9, 0],
            [0, 0, 10],
        ],
        dtype=np.float32,
    )
    result = _dp_best_path(s)
    assert result is not None
    score, indices = result
    assert indices == [0, 2, 3]
    assert score == pytest.approx(29)


def test_dp_all_equal_scores_returns_valid_order():
    s = np.ones((5, 3), dtype=np.float32)
    result = _dp_best_path(s)
    assert result is not None
    score, indices = result
    assert len(indices) == 3
    assert indices == sorted(indices)
    assert len(set(indices)) == 3
    assert score == pytest.approx(3)


# ---------------------------------------------------------------------------
# Frame spreading
# ---------------------------------------------------------------------------


def test_spread_stays_within_radius():
    base_frames = [500, 800]
    rows = spread_frames(base_frames, "V01", max_frame_idx=10_000, rows=20)
    for row in rows:
        for base, frame in zip(base_frames, row):
            assert abs(frame - base) <= SPREAD_RADIUS


def test_spread_is_deterministic_for_same_video():
    base_frames = [500, 800]
    first = spread_frames(base_frames, "V01", max_frame_idx=10_000, rows=10)
    second = spread_frames(base_frames, "V01", max_frame_idx=10_000, rows=10)
    assert first == second


def test_spread_differs_across_videos():
    base_frames = [500, 800]
    rows_a = spread_frames(base_frames, "V01", max_frame_idx=10_000, rows=10)
    rows_b = spread_frames(base_frames, "V02", max_frame_idx=10_000, rows=10)
    assert rows_a != rows_b


def test_spread_clamps_at_video_start():
    base_frames = [0, 2]
    rows = spread_frames(base_frames, "V01", max_frame_idx=10_000, rows=20)
    for row in rows:
        assert all(frame >= 0 for frame in row)


def test_spread_clamps_at_video_end():
    base_frames = [9998, 9999]
    max_frame_idx = 9999
    rows = spread_frames(base_frames, "V01", max_frame_idx=max_frame_idx, rows=20)
    for row in rows:
        assert all(frame <= max_frame_idx for frame in row)


def test_spread_first_row_is_unshifted():
    base_frames = [500, 800, 1200]
    rows = spread_frames(base_frames, "V01", max_frame_idx=10_000, rows=5)
    assert rows[0] == tuple(base_frames)


def test_spread_deduplicates_after_clamping():
    base_frames = [1, 2]
    rows = spread_frames(base_frames, "V01", max_frame_idx=10_000, rows=50)
    assert len(rows) == len(set(rows))


# ---------------------------------------------------------------------------
# Submission export
# ---------------------------------------------------------------------------


def _make_video_match(video_id: str, frames: tuple[int, ...], max_frame_idx: int) -> TrakeVideoMatch:
    events = tuple(
        TrakeEventMatch(
            keyframe_id=f"{video_id}_{i:03d}",
            video_id=video_id,
            keyframe_no=i + 1,
            frame_idx=frame,
            pts_time_sec=frame / 30.0,
            fps=30.0,
            image_path=f"/tmp/{video_id}_{i}.jpg",
            image_relpath=f"keyframes/{video_id}/{i}.jpg",
            score=1.0,
            event_index=i,
        )
        for i, frame in enumerate(frames)
    )
    return TrakeVideoMatch(
        video_id=video_id,
        collection_id="C01",
        title=f"Video {video_id}",
        author="Author",
        total_score=sum(e.score for e in events),
        events=events,
    )


def _make_outcome(video_count: int, event_count: int = 3) -> TrakeOutcome:
    videos = tuple(
        _make_video_match(
            f"V{i:02d}",
            tuple(1000 + j * 50 for j in range(event_count)),
            max_frame_idx=100_000,
        )
        for i in range(video_count)
    )
    queries = (
        PreparedQuery("q", "q", "auto", "not_checked", translation_enabled=False),
    ) * event_count
    return TrakeOutcome(videos=videos, queries=queries)


def test_spread_terminates_when_video_too_short_to_vary():
    """A 2-frame video clamps every jitter onto the same set; must not loop forever."""
    result = spread_frames([0, 1], "L01_V001", max_frame_idx=1, rows=34)
    assert len(result) >= 1
    assert result[0] == (0, 1)
    assert len(result) == len(set(result))


def test_spread_keeps_frames_strictly_increasing():
    """Jittering each event independently used to reorder them — 24/34 rows were invalid."""
    rows = spread_frames([100, 110, 120], "L01_V001", max_frame_idx=10_000, rows=34)
    for row in rows:
        assert all(row[i] < row[i + 1] for i in range(len(row) - 1)), row


def test_spread_uses_video_length_not_last_matched_frame():
    """max_frame_idx comes from the video, so jitter past the last match stays allowed."""
    rows = spread_frames([100, 200, 300], "L01_V001", max_frame_idx=10_000, rows=34)
    assert any(row[-1] > 300 for row in rows)


def test_build_submission_respects_patched_max_rows(monkeypatch):
    outcome = _make_outcome(video_count=10)
    monkeypatch.setattr(trake, "SUBMISSION_MAX_ROWS", 7)
    assert len(build_submission(outcome)) == 7


def test_submission_never_exceeds_hundred_rows():
    outcome = _make_outcome(video_count=10)
    rows = build_submission(outcome, max_rows=SUBMISSION_MAX_ROWS)
    assert len(rows) == 100


def test_submission_gives_top_video_full_spread():
    outcome = _make_outcome(video_count=10)
    rows = build_submission(outcome, max_rows=SUBMISSION_MAX_ROWS)
    top_video_id = outcome.videos[0].video_id
    top_rows = [row for row in rows[:SPREAD_ROWS_PER_VIDEO] if row[0] == top_video_id]
    assert len(top_rows) == SPREAD_ROWS_PER_VIDEO


def test_submission_row_shape_matches_event_count():
    outcome = _make_outcome(video_count=1, event_count=4)
    rows = build_submission(outcome, max_rows=SUBMISSION_MAX_ROWS)
    assert len(rows) > 0
    for video_id, frames in rows:
        assert isinstance(video_id, str)
        assert len(frames) == 4


def test_submission_respects_frame_index_base(monkeypatch):
    outcome = _make_outcome(video_count=1, event_count=3)
    baseline_rows = build_submission(outcome, max_rows=10)

    monkeypatch.setattr(trake, "FRAME_INDEX_BASE", 1)
    shifted_text = format_submission(baseline_rows)

    _, frames = baseline_rows[0]
    first_row_shifted = shifted_text.splitlines()[0]
    expected_frames = [f + 1 for f in frames]
    for frame in expected_frames:
        assert str(frame) in first_row_shifted


def test_format_submission_uses_configured_delimiter(monkeypatch):
    outcome = _make_outcome(video_count=1, event_count=2)
    rows = build_submission(outcome, max_rows=1)

    monkeypatch.setattr(trake, "SUBMISSION_DELIMITER", "\t")
    text = format_submission(rows)
    assert "\t" in text
    assert text.count("\t") >= 2


# ---------------------------------------------------------------------------
# Input validation and FPS correctness (searcher, needs sqlite + embeddings)
# ---------------------------------------------------------------------------


def _write_embeddings(tmp_path: Path, embeddings: np.ndarray) -> Path:
    embeddings_file = tmp_path / "embeddings.npy"
    np.save(embeddings_file, embeddings.astype(np.float16))
    return embeddings_file


def _create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE keyframes (
            vector_id INTEGER, keyframe_id TEXT, video_id TEXT, collection_id TEXT,
            keyframe_no INTEGER, frame_idx INTEGER, pts_time_sec REAL, fps REAL,
            width INTEGER, height INTEGER, image_relpath TEXT
        );
        CREATE TABLE videos (
            video_id TEXT, collection_id TEXT, title TEXT, author TEXT,
            channel_id TEXT, channel_url TEXT, description TEXT, keywords_json TEXT,
            duration_sec INTEGER, publish_date_raw TEXT, publish_date_iso TEXT,
            thumbnail_url TEXT, watch_url TEXT
        );
        """
    )


def _insert_video(connection, video_id, collection_id="C01", title="Title", author="Author"):
    connection.execute(
        "INSERT INTO videos VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            video_id,
            collection_id,
            title,
            author,
            "channel-1",
            "",
            "",
            "[]",
            60,
            "01/01/2024",
            "2024-01-01",
            "",
            "https://example.com/watch",
        ),
    )


def _insert_keyframe(
    connection,
    vector_id,
    keyframe_id,
    video_id,
    keyframe_no,
    frame_idx,
    pts_time_sec,
    fps,
    collection_id="C01",
):
    connection.execute(
        "INSERT INTO keyframes VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (
            vector_id,
            keyframe_id,
            video_id,
            collection_id,
            keyframe_no,
            frame_idx,
            pts_time_sec,
            fps,
            640,
            360,
            f"keyframes/{video_id}/{keyframe_no}.jpg",
        ),
    )


def _make_searcher(
    tmp_path: Path,
    embeddings: np.ndarray,
    rows: list[tuple],
    events: dict[str, tuple[float, float]] | None = None,
) -> TrakeSearcher:
    """rows: list of tuples matching _insert_keyframe args (minus connection)."""
    data_root = tmp_path / "release"
    for _, keyframe_id, video_id, keyframe_no, *_rest in rows:
        image_path = data_root / f"keyframes/{video_id}/{keyframe_no}.jpg"
        image_path.parent.mkdir(parents=True, exist_ok=True)
        image_path.write_bytes(b"jpeg")

    sqlite_file = tmp_path / "runtime.sqlite"
    connection = sqlite3.connect(sqlite_file)
    _create_schema(connection)
    video_ids = sorted({row[2] for row in rows})
    for video_id in video_ids:
        _insert_video(connection, video_id)
    for row in rows:
        _insert_keyframe(connection, *row)
    connection.commit()
    connection.close()

    embeddings_file = _write_embeddings(tmp_path, embeddings)
    clip_searcher = FakeClipSearcher(events or {})
    translator = FakeTranslator()
    return TrakeSearcher(
        clip_searcher,
        translator,
        sqlite_file,
        embeddings_file,
        data_root,
    )


def test_search_rejects_fewer_than_two_events():
    with pytest.raises(ValueError):
        trake.encode_events(["only one"], FakeTranslator(), FakeClipSearcher({}))


def test_search_rejects_more_than_six_events():
    with pytest.raises(ValueError):
        trake.encode_events(
            ["e1", "e2", "e3", "e4", "e5", "e6", "e7"],
            FakeTranslator(),
            FakeClipSearcher({}),
        )


def test_search_ignores_blank_event_boxes():
    matrix, prepared = trake.encode_events(
        ["first event", "  ", "", "second event"],
        FakeTranslator(),
        FakeClipSearcher({}),
    )
    assert matrix.shape[0] == 2
    assert len(prepared) == 2


def test_encode_events_translates_each_event_once():
    """search() used to re-run prepare() on top of encode_events — 2x the NLLB work."""

    class CountingTranslator(FakeTranslator):
        def __init__(self):
            self.calls = 0

        def prepare(self, query, *args, **kwargs):
            self.calls += 1
            return super().prepare(query, *args, **kwargs)

    translator = CountingTranslator()
    trake.encode_events(["one", "two", "three"], translator, FakeClipSearcher({}))
    assert translator.calls == 3


def test_searcher_rejects_non_contiguous_vector_ids(tmp_path):
    embeddings = np.asarray(
        [[1.0, 0.0], [0.9, 0.1], [0.0, 1.0]],
        dtype=np.float32,
    )
    # vector_id 1 is missing for video V01 -> a hole in its slice.
    rows = [
        (0, "V01_001", "V01", 1, 100, 3.3, 30.0),
        (2, "V01_002", "V01", 2, 200, 6.6, 30.0),
    ]
    with pytest.raises(ValueError, match="V01"):
        _make_searcher(tmp_path, embeddings, rows)


def test_event_match_carries_per_row_fps(tmp_path):
    # V01 is 25fps, V02 is 30fps, mixed in the same result set.
    embeddings = np.asarray(
        [
            [1.0, 0.0],
            [0.9, 0.1],
            [0.0, 1.0],
            [0.1, 0.9],
        ],
        dtype=np.float32,
    )
    rows = [
        (0, "V01_001", "V01", 1, 100, 4.0, 25.0),
        (1, "V01_002", "V01", 2, 200, 8.0, 25.0),
        (2, "V02_001", "V02", 1, 150, 5.0, 30.0),
        (3, "V02_002", "V02", 2, 300, 10.0, 30.0),
    ]
    searcher = _make_searcher(
        tmp_path,
        embeddings,
        rows,
        events={"event one": (1.0, 0.0), "event two": (0.0, 1.0)},
    )
    outcome = searcher.search(["event one", "event two"], top_videos=5)

    fps_by_video = {}
    for video in outcome.videos:
        for event in video.events:
            fps_by_video.setdefault(video.video_id, set()).add(event.fps)

    assert fps_by_video.get("V01") == {25.0}
    assert fps_by_video.get("V02") == {30.0}


def test_frame_idx_read_from_column_not_recomputed(tmp_path):
    embeddings = np.asarray(
        [[1.0, 0.0], [0.0, 1.0]],
        dtype=np.float32,
    )
    # frame_idx deliberately does NOT equal round(pts_time_sec * fps):
    # round(2.0 * 30.0) == 60, but the column says 999.
    rows = [
        (0, "V01_001", "V01", 1, 999, 2.0, 30.0),
        (1, "V01_002", "V01", 2, 1500, 4.0, 30.0),
    ]
    searcher = _make_searcher(
        tmp_path,
        embeddings,
        rows,
        events={"event one": (1.0, 0.0), "event two": (0.0, 1.0)},
    )
    outcome = searcher.search(["event one", "event two"], top_videos=5)

    frame_indices = [event.frame_idx for video in outcome.videos for event in video.events]
    assert 999 in frame_indices
    assert 60 not in frame_indices


# ---------------------------------------------------------------------------
# No heavy dependencies
# ---------------------------------------------------------------------------


def test_trake_module_imports_without_gradio_or_torch():
    source = Path(trake.__file__).read_text(encoding="utf-8")
    assert "import gradio" not in source
    assert "import torch" not in source
