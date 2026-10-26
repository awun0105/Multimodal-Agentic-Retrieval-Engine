"""Behavior tests for streaming a searchable release from worker and caption packages."""

from __future__ import annotations

import json
import shutil
import sqlite3
import zipfile

import numpy as np
import pandas as pd
import pytest
from PIL import Image

from system1.captions.video import caption_video
from system1.indexes.vectors import load_vector_index, search
from system1.release.build import ReleaseError, build_release
from system1.worker.video import VideoInput, process_video
from test_caption_pass import Captioner, Text
from test_worker_video import CONFIG, FPS, FRAMES, Calls, _make_video, _models, _timeline


def _phase00(video_ids) -> pd.DataFrame:
    """Columns as written by Phase00 ingest, plus organizer_metadata_present."""

    return pd.DataFrame([{"video_id": video_id, "video_ref": f"media://raw_videos/{video_id}.mp4",
                          "duration_seconds": FRAMES / FPS, "fps_detected": float(FPS), "frame_count": FRAMES,
                          "width": 64, "height": 48, "organizer_metadata_present": video_id == "V1",
                          "metadata_title": "Bài giảng" if video_id == "V1" else None}
                         for video_id in video_ids])


@pytest.fixture
def packages(tmp_path):
    video_path = tmp_path / "video.mp4"
    _make_video(video_path)
    zips = {}
    for video_id in ("V1", "V2"):
        video = VideoInput(video_id=video_id, video_path=video_path, timeline_rows=_timeline(video_id))
        zips[video_id] = process_video(video, config=CONFIG, models=_models(Calls()),
                                       work_root=tmp_path / "work" / video_id,
                                       batch_id="batch_000", worker_id="worker_000")
    return zips


@pytest.fixture
def captions(packages, tmp_path):
    """A caption package for V1 only; V2 ships without captions."""

    calls = Calls()
    return {"V1": caption_video(packages["V1"], config=CONFIG, captioner=Captioner(calls),
                                text_embedder=Text(calls), work_root=tmp_path / "captions",
                                batch_id="batch_000", worker_id="worker_000")}


def _build(packages, captions, out_dir, **kwargs):
    kwargs.setdefault("phase00_videos", _phase00(packages))
    return build_release(release_id="test_release", worker_zips=list(packages.values()),
                         caption_zips_by_video=captions, out_dir=out_dir, **kwargs)


def _query(release, sql):
    db = sqlite3.connect(release / "db" / "app.sqlite")
    try:
        return db.execute(sql).fetchall()
    finally:
        db.close()


def test_release_indexes_every_keyframe_and_document(packages, captions, tmp_path) -> None:
    release = _build(packages, captions, tmp_path / "build")

    keyframe_ids = [row[0] for row in _query(release, "SELECT keyframe_id FROM keyframes ORDER BY rowid")]
    doc_ids = [row[0] for row in _query(release, "SELECT doc_id FROM text_documents ORDER BY rowid")]
    videos = {row[0] for row in _query(release, "SELECT DISTINCT video_id FROM keyframes")}
    image_index, image_ids = load_vector_index(release / "indexes", "image_siglip2")
    text_index, text_ids = load_vector_index(release / "indexes", "text_e5")

    assert videos == {"V1", "V2"}
    assert image_ids == keyframe_ids
    assert text_ids == doc_ids
    assert image_index.ntotal == len(keyframe_ids)
    assert text_index.ntotal == len(doc_ids)
    first = image_index.reconstruct(0)
    assert search(image_index, image_ids, np.asarray([first]), top_k=1)[0][0][0] == keyframe_ids[0]


def test_caption_documents_are_merged_and_a_video_without_captions_is_listed(packages, captions, tmp_path) -> None:
    release = _build(packages, captions, tmp_path / "build")

    kinds = _query(release, "SELECT video_id, evidence_type FROM text_documents")
    manifest = json.loads((release / "manifest.json").read_text())

    assert ("V1", "caption") in kinds
    assert not any(video == "V2" and kind in ("caption", "visible_text") for video, kind in kinds)
    assert manifest["videos"] == ["V1", "V2"]
    assert manifest["videos_with_captions"] == ["V1"]
    assert "captions" in manifest["degraded_stages"]["V2"]
    assert "captions" not in manifest["degraded_stages"]["V1"]


def test_full_text_search_matches_with_and_without_accents(packages, captions, tmp_path) -> None:
    release = _build(packages, captions, tmp_path / "build")

    sql = ("SELECT d.doc_id FROM text_documents_fts f JOIN text_documents d ON d.rowid = f.rowid "
           "WHERE text_documents_fts MATCH '{}'")
    accented = _query(release, sql.format('text:"Tấn Phát"'))
    plain = _query(release, sql.format('text_unaccented:"tan phat"'))

    assert accented
    assert sorted(plain) == sorted(accented)


def test_keyframes_are_webp_at_the_same_resolution(packages, captions, tmp_path) -> None:
    release = _build(packages, captions, tmp_path / "build")

    refs = [row[0] for row in _query(release, "SELECT keyframe_ref FROM keyframes")]
    thumbs = [row[0] for row in _query(release, "SELECT thumbnail_ref FROM keyframes")]
    with zipfile.ZipFile(packages["V1"]) as archive:
        first_jpg = sorted(name for name in archive.namelist() if name.endswith(".jpg"))[0]
        jpg_size = Image.open(archive.open(first_jpg)).size

    assert refs and all(ref.endswith(".webp") for ref in refs)
    for ref in refs:
        with Image.open(release / "media" / ref) as image:
            assert image.format == "WEBP"
            image.load()
    with Image.open(release / "media" / sorted(r for r in refs if r.startswith("keyframes/V1/"))[0]) as image:
        assert image.size == jpg_size
    assert all((release / "media" / ref).is_file() for ref in thumbs)


def test_media_sink_gets_each_video_and_may_delete_its_media(packages, captions, tmp_path) -> None:
    seen = []

    def sink(video_id, media_root):
        seen.append((video_id, sorted(p.name for p in (media_root / "keyframes" / video_id).iterdir())))
        for kind in ("keyframes", "thumbnails"):
            shutil.rmtree(media_root / kind / video_id)

    release = _build(packages, captions, tmp_path / "build", media_sink=sink)

    assert [video_id for video_id, _ in seen] == ["V1", "V2"]
    assert all(names and all(name.endswith(".webp") for name in names) for _, names in seen)
    assert not any(path.is_file() for path in (release / "media").rglob("*"))


def test_build_leaves_only_the_release_directory(packages, captions, tmp_path) -> None:
    out_dir = tmp_path / "build"
    _build(packages, captions, out_dir)

    assert sorted(path.name for path in out_dir.iterdir()) == ["release"]


def test_vector_map_parquet_equals_sqlite(packages, captions, tmp_path) -> None:
    release = _build(packages, captions, tmp_path / "build")

    sqlite_rows = sorted(_query(release, "SELECT index_name, vector_id, item_id FROM vector_map"))
    parquet_rows = sorted(
        (name, int(row.vector_id), row.item_id)
        for name in ("image_siglip2", "text_e5")
        for row in pd.read_parquet(release / "indexes" / f"{name}_vector_map.parquet").itertuples())

    assert sqlite_rows == parquet_rows


def test_videos_table_comes_from_phase00_without_invented_values(packages, captions, tmp_path) -> None:
    release = _build(packages, captions, tmp_path / "build")

    rows = _query(release, "SELECT video_id, video_ref, duration_sec, fps, frame_count, width, height, "
                           "organizer_metadata_present, title, author FROM videos ORDER BY video_id")

    assert rows == [("V1", "raw_videos/V1.mp4", FRAMES / FPS, float(FPS), FRAMES, 64, 48, 1, "Bài giảng", None),
                    ("V2", "raw_videos/V2.mp4", FRAMES / FPS, float(FPS), FRAMES, 64, 48, 0, None, None)]


def test_phase00_table_without_a_required_column_is_rejected(packages, captions, tmp_path) -> None:
    phase00 = _phase00(packages).drop(columns=["organizer_metadata_present"])

    with pytest.raises(ReleaseError, match="organizer_metadata_present"):
        _build(packages, captions, tmp_path / "build", phase00_videos=phase00)


def test_every_shot_has_a_scene_and_scenes_tile_each_video(packages, captions, tmp_path) -> None:
    release = _build(packages, captions, tmp_path / "build")

    assert _query(release, "SELECT count(*) FROM shots WHERE scene_id IS NULL") == [(0,)]
    assert _query(release, "SELECT count(*) FROM shots WHERE scene_id NOT IN (SELECT scene_id FROM scenes)") == [(0,)]
    per_video = dict(_query(release, "SELECT video_id, count(*) FROM scenes GROUP BY video_id"))
    assert set(per_video) == {"V1", "V2"} and min(per_video.values()) >= 1
    shot_counts = dict(_query(release, "SELECT video_id, count(*) FROM shots GROUP BY video_id"))
    assert dict(_query(release, "SELECT video_id, sum(shot_count) FROM scenes GROUP BY video_id")) == shot_counts


def test_scene_summary_joins_captions_and_is_null_without_them(packages, captions, tmp_path) -> None:
    release = _build(packages, captions, tmp_path / "build")

    for scene_id, video_id, summary in _query(release, "SELECT scene_id, video_id, summary FROM scenes"):
        captions_in_order = [row[0] for row in _query(release, f"""
            SELECT d.text FROM text_documents d JOIN shots s ON s.shot_id = d.shot_ids
            WHERE d.evidence_type = 'caption' AND s.scene_id = '{scene_id}' ORDER BY s.start_frame""")]
        if video_id == "V1":
            assert captions_in_order and summary == " ".join(dict.fromkeys(captions_in_order))
        else:
            assert summary is None
    assert _query(release, "SELECT count(*) FROM text_documents WHERE evidence_type = 'scene'") == [(0,)]


def test_custom_scene_builder_is_used(packages, captions, tmp_path) -> None:
    calls = []

    def builder(video_id, evidence):
        calls.append((video_id, sorted(evidence)))
        from system1.scenes.release_builder import make_scene_builder
        from test_scene_deterministic import PARAMS
        return make_scene_builder(PARAMS.__dict__)(video_id, evidence)

    _build(packages, captions, tmp_path / "build", scene_builder=builder)

    assert [video_id for video_id, _ in calls] == ["V1", "V2"]
    assert calls[0][1] == ["image_vectors", "keyframes", "shots", "text_documents", "text_vectors"]


def test_manifest_records_release_v2_fields(packages, captions, tmp_path) -> None:
    release = _build(packages, captions, tmp_path / "build")

    manifest = json.loads((release / "manifest.json").read_text())
    keyframes = _query(release, "SELECT count(*) FROM keyframes")[0][0]

    assert manifest["schema_version"] == "release_v2"
    assert manifest["release_id"] == "test_release"
    assert manifest["built_at"]
    assert manifest["counts"]["keyframes"] == keyframes
    assert manifest["counts"]["videos"] == 2
    assert manifest["indexes"]["image_siglip2"] == keyframes
    assert "captions" in manifest["models"]
    assert "videos.schema.json" in manifest["schema_sha256"]
    assert len(manifest["schema_sha256"]["videos.schema.json"]) == 64
    assert manifest["peak_rss_mb"] > 0


def test_caption_package_from_another_worker_package_is_rejected(packages, tmp_path) -> None:
    calls = Calls()
    wrong = caption_video(packages["V1"], config=CONFIG, captioner=Captioner(calls), text_embedder=Text(calls),
                          work_root=tmp_path / "captions", batch_id="batch_000", worker_id="worker_000")
    rebuilt = tmp_path / "rebuilt" / "V1.zip"
    rebuilt.parent.mkdir()
    with zipfile.ZipFile(packages["V1"]) as source, zipfile.ZipFile(rebuilt, "w") as target:
        for item in source.infolist():
            target.writestr(item, source.read(item.filename))
        target.comment = b"different bytes"

    with pytest.raises(ReleaseError, match="worker_package_sha256"):
        _build({"V1": rebuilt, "V2": packages["V2"]}, {"V1": wrong}, tmp_path / "build")


def test_lazy_inputs_are_consumed_one_video_at_a_time(packages, captions, tmp_path) -> None:
    order = []

    def worker_zips():
        for video_id, path in packages.items():
            order.append(f"worker:{video_id}")
            yield path

    def fetch(video_id):
        order.append(f"captions:{video_id}")
        return captions.get(video_id)

    build_release(release_id="test_release", worker_zips=worker_zips, caption_zips_by_video=fetch,
                  phase00_videos=_phase00(packages), out_dir=tmp_path / "build",
                  progress=lambda item: order.append(f"done:{item['video_id']}"))

    assert order == ["worker:V1", "captions:V1", "done:V1", "worker:V2", "captions:V2", "done:V2"]


def test_tampered_package_is_rejected(packages, captions, tmp_path) -> None:
    tampered = tmp_path / "tampered.zip"
    with zipfile.ZipFile(packages["V1"]) as source, zipfile.ZipFile(tampered, "w") as target:
        for item in source.infolist():
            data = source.read(item.filename)
            if item.filename.endswith("shots.parquet"):
                data = data[:-10]
            target.writestr(item, data)

    with pytest.raises(ReleaseError):
        _build({"V1": tampered, "V2": packages["V2"]}, {}, tmp_path / "build")


def test_duplicate_video_is_rejected(packages, tmp_path) -> None:
    with pytest.raises(ReleaseError, match="V1"):
        build_release(release_id="test_release", worker_zips=[packages["V1"], packages["V1"]],
                      caption_zips_by_video=None, phase00_videos=_phase00(["V1"]), out_dir=tmp_path / "build")
