"""TRAKE: multi-event temporal search across keyframes. No gradio, no torch."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import numpy as np

from schemas import TrakeEventMatch, TrakeOutcome, TrakeVideoMatch
from trake_dp import VideoSlice
from trake_dp import dp_best_path as _dp_best_path
from trake_dp import dp_best_path_min as _dp_best_path_min
from trake_dp import dp_best_path_dante as _dp_best_path_dante
from trake_dp import dp_best_path_min_dante as _dp_best_path_min_dante
from trake_submission import build_submission as _build_submission
from trake_submission import format_submission as _format_submission
from trake_submission import spread_frames as _spread_frames

# Submission format. Everything the organizers control lives in this block, so a
# rule change is a value edit here — never a hunt through the codebase.
# Sources checked against training session 4 (see
# plans/reports/btc-260821-tap-huan-4-dinh-dang-nop-bai.md for timestamps).
#
#   FRAME_INDEX_BASE   confirmed — 0 and 1 are both accepted
#   SUBMISSION_*       unconfirmed — official spec due Tuesday
#
# Still unspecified: exact per-line CSV layout for TRAKE, submission filename
# rules, and the ZIP wrapper (zip > submission/ > one CSV per query, UTF-8).
SUBMISSION_DELIMITER = ","
SUBMISSION_INCLUDE_HEADER = False
SUBMISSION_MAX_ROWS = 100
FRAME_INDEX_BASE = 0
SPREAD_RADIUS = 40
SPREAD_ROWS_PER_VIDEO = 34

# "min" ranks by the weakest event, stopping a video that is missing one event
# from winning on the strength of the others. Set to "sum" to A/B the old
# behaviour. Measured over 60 cases: distractor accuracy 13.3% -> 93.3%.
RANKING_OBJECTIVE = "dante_min"
PENALTY_WEIGHT = 0.005

MIN_EVENTS = 1
MAX_EVENTS = 6


def encode_events(
    events: list[str],
    translator: Any,
    clip_searcher: Any,
    *,
    translate_vietnamese: bool | None = None,
) -> tuple[np.ndarray, list[Any]]:
    """Returns the (N, dim) query matrix and the PreparedQuery behind each row."""
    cleaned = [e.strip() for e in events if e.strip()]
    if len(cleaned) < MIN_EVENTS or len(cleaned) > MAX_EVENTS:
        raise ValueError(
            f"Expected {MIN_EVENTS}-{MAX_EVENTS} non-empty events, got {len(cleaned)}"
        )
    vectors = []
    prepared_queries = []
    for event in cleaned:
        prepared = translator.prepare(event, translate_vietnamese=translate_vietnamese)
        prepared_queries.append(prepared)
        vectors.append(np.asarray(clip_searcher.get_text_features(prepared.clip_query)))
    return np.vstack(vectors).astype(np.float32), prepared_queries


def spread_frames(
    frame_idx: list[int],
    video_id: str,
    max_frame_idx: int,
    rows: int,
) -> list[tuple[int, ...]]:
    return _spread_frames(frame_idx, video_id, max_frame_idx, rows, radius=SPREAD_RADIUS)


def build_submission(
    outcome: TrakeOutcome,
    max_rows: int | None = None,
    pinned_frames: dict[str, int] | None = None,
) -> list[tuple[str, tuple[int, ...]]]:
    # Read at call time so monkeypatching SUBMISSION_MAX_ROWS takes effect.
    return _build_submission(
        outcome,
        SUBMISSION_MAX_ROWS if max_rows is None else max_rows,
        rows_per_video=SPREAD_ROWS_PER_VIDEO,
        radius=SPREAD_RADIUS,
        pinned_frames=pinned_frames,
    )


def _select_dp(objective: str):
    if objective == "min":
        return _dp_best_path_min
    if objective == "sum":
        return _dp_best_path
    if objective == "dante":
        return _dp_best_path_dante
    if objective == "dante_min":
        return _dp_best_path_min_dante
    raise ValueError(f"Unknown RANKING_OBJECTIVE: {objective!r}")


def format_submission(rows: list[tuple[str, tuple[int, ...]]]) -> str:
    return _format_submission(
        rows,
        delimiter=SUBMISSION_DELIMITER,
        include_header=SUBMISSION_INCLUDE_HEADER,
        frame_index_base=FRAME_INDEX_BASE,
    )


class TrakeSearcher:
    def __init__(
        self,
        clip_searcher: Any,
        translator: Any,
        sqlite_file: str | Path,
        embeddings_file: str | Path,
        data_root: str | Path,
    ) -> None:
        self.clip_searcher = clip_searcher
        self.translator = translator
        self.sqlite_file = Path(sqlite_file)
        self.data_root = Path(data_root)
        self.embeddings = np.load(Path(embeddings_file), mmap_mode="r", allow_pickle=False)
        self.slices = self._build_slices()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(f"file:{self.sqlite_file}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        return connection

    def _build_slices(self) -> list[VideoSlice]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT video_id, MIN(vector_id), MAX(vector_id), COUNT(*), MAX(frame_idx) "
                "FROM keyframes GROUP BY video_id ORDER BY MIN(vector_id)"
            ).fetchall()
        slices = []
        for video_id, min_id, max_id, count, max_frame_idx in rows:
            if max_id - min_id + 1 != count:
                raise ValueError(
                    f"Non-contiguous vector_id range for video_id={video_id!r}: "
                    f"min={min_id}, max={max_id}, count={count}"
                )
            slices.append(VideoSlice(str(video_id), int(min_id), int(max_id) + 1, int(max_frame_idx)))
        return slices

    def search(
        self,
        events: list[str],
        top_videos: int = 20,
        *,
        translate_vietnamese: bool | None = None,
        penalty_weight: float | None = None,
        ranking_objective: str | None = None,
    ) -> TrakeOutcome:
        query_matrix, queries = encode_events(
            events,
            self.translator,
            self.clip_searcher,
            translate_vietnamese=translate_vietnamese,
        )
        # Matching the memmap dtype avoids a 363MB float32 copy on every search.
        scores = (self.embeddings @ query_matrix.astype(self.embeddings.dtype).T).astype(
            np.float32
        )

        obj = ranking_objective or RANKING_OBJECTIVE
        pw = penalty_weight if penalty_weight is not None else PENALTY_WEIGHT
        dp = _select_dp(obj)
        candidates = []
        for video_slice in self.slices:
            slice_scores = scores[video_slice.start : video_slice.end]
            if obj in {"dante", "dante_min"}:
                result = dp(slice_scores, pw)
            else:
                result = dp(slice_scores)
            if result is None:
                continue
            score, local_indices = result
            vector_ids = [video_slice.start + i for i in local_indices]
            candidates.append((score, video_slice.video_id, vector_ids, video_slice.max_frame_idx))

        candidates.sort(key=lambda c: c[0], reverse=True)
        top = candidates[:top_videos]

        all_vector_ids = [vid for _, _, vector_ids, _ in top for vid in vector_ids]
        metadata = self._metadata_for_vector_ids(all_vector_ids)

        videos = []
        for score, video_id, vector_ids, max_frame_idx in top:
            events_out = []
            for event_index, vector_id in enumerate(vector_ids):
                row = metadata[vector_id]
                events_out.append(
                    TrakeEventMatch(
                        keyframe_id=row["keyframe_id"],
                        video_id=row["video_id"],
                        keyframe_no=row["keyframe_no"],
                        frame_idx=row["frame_idx"],
                        pts_time_sec=row["pts_time_sec"],
                        fps=row["fps"],
                        image_path=str(self.data_root / row["image_relpath"]),
                        image_relpath=row["image_relpath"],
                        score=float(scores[vector_id, event_index]),
                        event_index=event_index,
                    )
                )
            first_row = metadata[vector_ids[0]]
            videos.append(
                TrakeVideoMatch(
                    video_id=video_id,
                    collection_id=first_row["collection_id"],
                    title=first_row["title"],
                    author=first_row["author"],
                    total_score=float(score),
                    events=tuple(events_out),
                    max_frame_idx=max_frame_idx,
                    watch_url=str(first_row.get("watch_url") or ""),
                )
            )
        return TrakeOutcome(videos=tuple(videos), queries=tuple(queries))

    def _metadata_for_vector_ids(self, vector_ids: list[int]) -> dict[int, dict]:
        if not vector_ids:
            return {}
        placeholders = ",".join("?" for _ in vector_ids)
        query = f"""
            SELECT k.vector_id, k.keyframe_id, k.video_id, k.collection_id,
                   k.keyframe_no, k.frame_idx, k.pts_time_sec, k.fps, k.image_relpath,
                   v.title, v.author, v.watch_url
            FROM keyframes k
            JOIN videos v ON v.video_id = k.video_id
            WHERE k.vector_id IN ({placeholders})
        """
        with self._connect() as connection:
            rows = connection.execute(query, [int(v) for v in vector_ids]).fetchall()
        return {int(row["vector_id"]): dict(row) for row in rows}
