"""Behavior tests for building a searchable release from worker packages."""

from __future__ import annotations

import json
import sqlite3
import zipfile

import numpy as np
import pytest

from system1.indexes.vectors import load_vector_index, search
from system1.release.build import ReleaseError, build_release
from system1.worker.video import VideoInput, process_video
from test_worker_video import CONFIG, Calls, _make_video, _models, _timeline


@pytest.fixture
def packages(tmp_path):
    video_path = tmp_path / "video.mp4"
    _make_video(video_path)
    zips = []
    for video_id in ("V1", "V2"):
        video = VideoInput(video_id=video_id, video_path=video_path, timeline_rows=_timeline(video_id))
        zips.append(process_video(video, config=CONFIG, models=_models(Calls()), work_root=tmp_path / "work",
                                  batch_id="batch_000", worker_id="worker_000"))
    return zips


def test_release_indexes_every_keyframe_and_document(packages, tmp_path) -> None:
    release = build_release(packages, tmp_path / "release", release_id="test_release")

    with sqlite3.connect(release / "db" / "app.sqlite") as db:
        keyframe_ids = [row[0] for row in db.execute("SELECT keyframe_id FROM keyframes ORDER BY rowid")]
        doc_ids = [row[0] for row in db.execute("SELECT doc_id FROM text_documents ORDER BY rowid")]
        videos = {row[0] for row in db.execute("SELECT DISTINCT video_id FROM keyframes")}
    image_index, image_ids = load_vector_index(release / "indexes", "image_siglip2")
    text_index, text_ids = load_vector_index(release / "indexes", "text_e5")

    assert videos == {"V1", "V2"}
    assert image_ids == keyframe_ids
    assert text_ids == doc_ids
    assert image_index.ntotal == len(keyframe_ids)
    assert text_index.ntotal == len(doc_ids)
    first = image_index.reconstruct(0)
    assert search(image_index, image_ids, np.asarray([first]), top_k=1)[0][0][0] == keyframe_ids[0]


def test_full_text_search_matches_with_and_without_accents(packages, tmp_path) -> None:
    release = build_release(packages, tmp_path / "release", release_id="test_release")

    with sqlite3.connect(release / "db" / "app.sqlite") as db:
        accented = db.execute(
            "SELECT d.doc_id FROM text_documents_fts f JOIN text_documents d ON d.rowid = f.rowid "
            "WHERE text_documents_fts MATCH ?", ('text:"Tấn Phát"',)).fetchall()
        plain = db.execute(
            "SELECT d.doc_id FROM text_documents_fts f JOIN text_documents d ON d.rowid = f.rowid "
            "WHERE text_documents_fts MATCH ?", ('text_unaccented:"tan phat"',)).fetchall()

    assert accented
    assert sorted(plain) == sorted(accented)


def test_release_copies_keyframe_media(packages, tmp_path) -> None:
    release = build_release(packages, tmp_path / "release", release_id="test_release")

    with sqlite3.connect(release / "db" / "app.sqlite") as db:
        refs = [row[0] for row in db.execute("SELECT keyframe_ref FROM keyframes")]
    manifest = json.loads((release / "manifest.json").read_text())

    assert all((release / "media" / ref).is_file() for ref in refs)
    assert manifest["videos"] == ["V1", "V2"]
    assert manifest["counts"]["keyframes"] == len(refs)


def test_tampered_package_is_rejected(packages, tmp_path) -> None:
    tampered = tmp_path / "tampered.zip"
    with zipfile.ZipFile(packages[0]) as source, zipfile.ZipFile(tampered, "w") as target:
        for item in source.infolist():
            data = source.read(item.filename)
            if item.filename.endswith("shots.parquet"):
                data = data[:-10]
            target.writestr(item, data)

    with pytest.raises(ReleaseError):
        build_release([tampered, packages[1]], tmp_path / "release", release_id="test_release")


def test_duplicate_video_is_rejected(packages, tmp_path) -> None:
    with pytest.raises(ReleaseError, match="V1"):
        build_release([packages[0], packages[0]], tmp_path / "release", release_id="test_release")
