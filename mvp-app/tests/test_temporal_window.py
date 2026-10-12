"""Neighbouring keyframes around a selection — confirm a scene without opening the video."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import faiss
import numpy as np
import pytest

from clip import CLIPSearcher
from clusterer import ImageIndexer
from db import SearchMechanism
from translation import QueryTranslator


def _make_long_video_store(tmp_path: Path, frame_count: int = 12) -> SearchMechanism:
    """One video with `frame_count` keyframes, so a +/-5 window has room on both sides."""
    data_root = tmp_path / "release"
    for number in range(1, frame_count + 1):
        path = data_root / f"keyframes/C01/V01/{number:03d}.jpg"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"jpeg")

    embeddings = np.asarray(
        [[np.cos(i), np.sin(i)] for i in range(frame_count)], dtype=np.float32
    )
    embeddings /= np.linalg.norm(embeddings, axis=1, keepdims=True)
    embeddings_file = tmp_path / "embeddings.npy"
    np.save(embeddings_file, embeddings.astype(np.float16))

    index = faiss.IndexFlatIP(2)
    index.add(embeddings)
    index_file = tmp_path / "keyframes.faiss"
    faiss.write_index(index, str(index_file))

    sqlite_file = tmp_path / "runtime.sqlite"
    connection = sqlite3.connect(sqlite_file)
    connection.executescript(
        """
        CREATE TABLE videos (
            video_id TEXT PRIMARY KEY, collection_id TEXT, title TEXT, author TEXT,
            channel_id TEXT, channel_url TEXT, description TEXT, keywords_json TEXT,
            duration_sec INTEGER, publish_date_raw TEXT, publish_date_iso TEXT,
            thumbnail_url TEXT, watch_url TEXT
        );
        CREATE TABLE keyframes (
            vector_id INTEGER PRIMARY KEY, keyframe_id TEXT, video_id TEXT,
            collection_id TEXT, keyframe_no INTEGER, frame_idx INTEGER,
            pts_time_sec REAL, fps REAL, width INTEGER, height INTEGER,
            image_relpath TEXT
        );
        CREATE TABLE detections (
            keyframe_id TEXT, rank INTEGER, entity TEXT, class_mid TEXT,
            class_label TEXT, score REAL, ymin REAL, xmin REAL, ymax REAL, xmax REAL
        );
        """
    )
    connection.execute(
        "INSERT INTO videos VALUES ('V01','C01','Title','Author','ch','url','desc','[]',"
        "600,'2024-01-01','2024-01-01','thumb','https://youtube.com/watch?v=aaaaaaaaaaa')"
    )
    for number in range(1, frame_count + 1):
        connection.execute(
            "INSERT INTO keyframes VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                number - 1,
                f"V01_{number:03d}",
                "V01",
                "C01",
                number,
                number * 30,
                float(number),
                30.0,
                1280,
                720,
                f"keyframes/C01/V01/{number:03d}.jpg",
            ),
        )
    connection.commit()
    connection.close()

    return SearchMechanism(
        CLIPSearcher(),
        QueryTranslator(),
        ImageIndexer(index_file),
        sqlite_file,
        embeddings_file,
        data_root,
    )


def test_window_returns_only_same_video(tmp_path):
    store = _make_long_video_store(tmp_path)
    rows = store.get_temporal_window("V01_006")
    assert {row["video_id"] for row in rows} == {"V01"}


def test_window_is_ordered_by_keyframe_no(tmp_path):
    store = _make_long_video_store(tmp_path)
    numbers = [row["keyframe_no"] for row in store.get_temporal_window("V01_006")]
    assert numbers == sorted(numbers)
    assert len(set(numbers)) == len(numbers)


def test_window_includes_the_target_keyframe(tmp_path):
    store = _make_long_video_store(tmp_path)
    rows = store.get_temporal_window("V01_006")
    assert "V01_006" in [row["keyframe_id"] for row in rows]


def test_window_clips_at_video_start(tmp_path):
    store = _make_long_video_store(tmp_path)
    rows = store.get_temporal_window("V01_001", before=5, after=5)
    assert [row["keyframe_no"] for row in rows] == [1, 2, 3, 4, 5, 6]


def test_window_clips_at_video_end(tmp_path):
    store = _make_long_video_store(tmp_path, frame_count=12)
    rows = store.get_temporal_window("V01_012", before=5, after=5)
    assert [row["keyframe_no"] for row in rows] == [7, 8, 9, 10, 11, 12]


def test_window_rows_have_keys_required_by_page_payload(tmp_path):
    store = _make_long_video_store(tmp_path)
    for row in store.get_temporal_window("V01_006"):
        assert row["score"] == 0.0
        assert row["keyframe_id"]
        assert isinstance(row["pts_time_sec"], float)
        assert Path(row["image_path"]).is_absolute()
        assert Path(row["image_path"]).is_file()


def test_unknown_keyframe_raises_key_error(tmp_path):
    store = _make_long_video_store(tmp_path)
    with pytest.raises(KeyError):
        store.get_temporal_window("V99_001")


def test_window_size_respects_before_and_after(tmp_path):
    store = _make_long_video_store(tmp_path)
    rows = store.get_temporal_window("V01_006", before=5, after=5)
    assert len(rows) == 11


def test_zero_window_returns_only_target(tmp_path):
    store = _make_long_video_store(tmp_path)
    rows = store.get_temporal_window("V01_006", before=0, after=0)
    assert [row["keyframe_id"] for row in rows] == ["V01_006"]


def test_filmstrip_click_reuses_the_selection_handler(tmp_path):
    """The filmstrip was rendered but never bound, so clicking a neighbour did nothing."""
    from app import build_app
    from tests.test_search import _make_store

    demo = build_app(_make_store(tmp_path))
    galleries = [
        block
        for block in demo.blocks.values()
        if getattr(block, "elem_id", None) == "neighbour-gallery"
    ]
    assert galleries, "filmstrip gallery missing"
    gallery_id = galleries[0]._id
    selects = [
        dep
        for dep in demo.config["dependencies"]
        if dep["targets"] and any(t[0] == gallery_id and t[1] == "select" for t in dep["targets"])
    ]
    assert selects, "filmstrip has no select handler"
