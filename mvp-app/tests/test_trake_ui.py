from dataclasses import replace
from pathlib import Path

import pytest

import trake_ui
from schemas import KeyframeDetails, TrakeOutcome, TrakeVideoMatch
from trake import MAX_EVENTS, MIN_EVENTS, format_submission
from trake_ui import TrakeController, search_trake_gpu


def _visible_flags(result):
    """add_event/remove_event return (count, *box_updates, add_update, remove_update)."""
    return [update["visible"] for update in result[1 : 1 + MAX_EVENTS]]


def test_add_event_stops_at_six():
    count = 3
    for _ in range(10):
        result = TrakeController.add_event(count)
        count = result[0]
    assert count == MAX_EVENTS
    assert _visible_flags(result) == [True] * MAX_EVENTS
    assert result[-2]["interactive"] is False


def test_remove_event_stops_at_two():
    count = 6
    for _ in range(10):
        result = TrakeController.remove_event(count)
        count = result[0]
    assert count == MIN_EVENTS
    assert _visible_flags(result)[:MIN_EVENTS] == [True] * MIN_EVENTS
    assert result[-1]["interactive"] is False


def test_remove_event_clears_hidden_textbox_value():
    result = TrakeController.remove_event(4)
    box_updates = result[1 : 1 + MAX_EVENTS]
    assert box_updates[3]["visible"] is False
    assert box_updates[3]["value"] == ""


def test_search_events_forwards_translate_checkbox():
    """The checkbox used to be accepted and then dropped, so it did nothing."""

    class RecordingSearcher:
        def __init__(self):
            self.seen = None

        def search(self, events, **kwargs):
            self.seen = kwargs.get("translate_vietnamese")
            return TrakeOutcome(videos=(), queries=())

    for flag in (True, False):
        searcher = RecordingSearcher()
        TrakeController(searcher).search_events(flag, "dante_min", 0.005, "one", "two")
        assert searcher.seen is flag


def test_add_event_keeps_text_already_typed():
    """Growing must not clear boxes; only shrinking clears the hidden one."""
    result = TrakeController.add_event(3)
    for update in result[1 : 1 + MAX_EVENTS]:
        assert "value" not in update


def test_search_events_without_events_shows_friendly_message():
    """An empty form must not raise ValueError into the UI."""

    class FailingSearcher:
        def search(self, *_args, **_kwargs):
            raise AssertionError("searcher must not be called without events")

    result = TrakeController(FailingSearcher()).search_events(True, "dante_min", 0.005, "  ", "")
    assert "ít nhất một sự kiện" in result[2]
    assert result[3] is None


def test_search_events_failure_returns_error_status():
    class FailingSearcher:
        def search(self, *_args, **_kwargs):
            raise RuntimeError("database unavailable")

    result = TrakeController(FailingSearcher()).search_events(True, "dante_min", 0.005, "event one")

    gallery_update, details, status, outcome, page, page_label, previous, next_ = result
    assert gallery_update["value"] == []
    assert details == ""
    assert status == "Error: database unavailable"
    assert outcome is None
    assert page == 0
    assert page_label == "Page 1 / 1 | 0 results"
    assert previous["interactive"] is False
    assert next_["interactive"] is False


def test_search_trake_gpu_raises_when_controller_missing(monkeypatch):
    monkeypatch.setattr(trake_ui, "_trake_controller", None)
    with pytest.raises(RuntimeError, match="not been initialized"):
        search_trake_gpu(True, "dante_min", 0.005, "an event")


# --- Preview / Export ---


def _pv_event(index, frame_idx, video_id, score):
    from schemas import TrakeEventMatch

    return TrakeEventMatch(
        keyframe_id=f"kf{index}",
        video_id=video_id,
        keyframe_no=index + 1,
        frame_idx=frame_idx,
        pts_time_sec=frame_idx / 25.0,
        fps=25.0,
        image_path="x.jpg",
        image_relpath="x.jpg",
        score=score,
        event_index=index,
    )


def _pv_outcome():
    """Three videos, descending score, three events each."""
    from schemas import TrakeVideoMatch

    specs = [("L21_V001", 1000, 0.41), ("L21_V002", 5000, 0.38), ("L21_V003", 2000, 0.35)]
    videos = []
    for video_id, base, score in specs:
        events = tuple(
            _pv_event(i, base + i * 1000, video_id, score) for i in range(3)
        )
        videos.append(
            TrakeVideoMatch(
                video_id=video_id,
                collection_id="L21",
                title="t",
                author="a",
                total_score=score,
                events=events,
                max_frame_idx=base + 9000,
            )
        )
    return TrakeOutcome(videos=tuple(videos), queries=())


def _controller():
    return TrakeController(trake_searcher=None)


def test_select_gallery_event_populates_image_player_metadata_and_detections(
    tmp_path, monkeypatch
):
    image = tmp_path / "event.jpg"
    image.write_bytes(b"jpeg")
    event = replace(
        _pv_event(0, 351, "L21_V001", 0.41),
        image_path=str(image),
        image_relpath="keyframes/L21/L21_V001/001.jpg",
    )
    video = TrakeVideoMatch(
        video_id="L21_V001",
        collection_id="L21",
        title="TRAKE title",
        author="TRAKE author",
        total_score=0.41,
        events=(event,),
        max_frame_idx=1000,
        watch_url="https://youtu.be/dQw4w9WgXcQ",
    )
    details = KeyframeDetails(
        keyframe={
            "keyframe_id": event.keyframe_id,
            "video_id": event.video_id,
            "collection_id": "L21",
            "keyframe_no": event.keyframe_no,
            "frame_idx": event.frame_idx,
            "pts_time_sec": event.pts_time_sec,
            "fps": event.fps,
            "width": 1280,
            "height": 720,
            "image_path": str(image),
        },
        video={
            "title": "TRAKE title",
            "author": "TRAKE author",
            "channel_id": "channel-1",
            "publish_date_iso": "2026-08-26",
            "watch_url": video.watch_url,
        },
        detections=(
            {
                "entity": "Person",
                "score": 0.98765,
                "class_mid": "/m/01g317",
                "class_label": 1,
                "ymin": 0.1,
                "xmin": 0.2,
                "ymax": 0.8,
                "xmax": 0.9,
            },
        ),
    )

    class DetailsProvider:
        def get_keyframe_details(self, keyframe_id):
            assert keyframe_id == event.keyframe_id
            return details

    monkeypatch.setattr(trake_ui, "get_video_path", lambda _video_id: None)
    controller = TrakeController(None, DetailsProvider())

    result = controller.select_gallery_event(
        TrakeOutcome(videos=(video,), queries=()), 0, 0
    )

    assert result[0] == str(image)
    assert "data-player=" in result[1]["value"]
    assert 'id="trake-player-jump-frame"' in result[1]["value"]
    assert 'id="trake-player-jump-btn"' in result[1]["value"]
    assert "L21_V001" in result[2]
    assert "1280 x 720" in result[2]
    assert result[3][0][:4] == ["Person", 0.9877, "/m/01g317", 1]
    assert result[4]["interactive"] is True
    assert result[5]["interactive"] is True
    assert result[6]["interactive"] is True
    assert result[7:] == (25.0, "L21_V001", 0, 351)


def test_select_gallery_event_without_details_provider_uses_event_metadata(
    tmp_path, monkeypatch
):
    image = tmp_path / "event.jpg"
    image.write_bytes(b"jpeg")
    event = replace(_pv_event(0, 100, "L21_V001", 0.4), image_path=str(image))
    video = TrakeVideoMatch(
        video_id="L21_V001",
        collection_id="L21",
        title="Fallback title",
        author="Fallback author",
        total_score=0.4,
        events=(event,),
    )
    monkeypatch.setattr(trake_ui, "get_video_path", lambda _video_id: None)

    result = TrakeController(None).select_gallery_event(
        TrakeOutcome(videos=(video,), queries=()), 0, (0, 0)
    )

    assert result[0] == str(image)
    assert "Fallback title" in result[2]
    assert "Resolution | N/A" in result[2]
    assert result[3] == []
    assert result[4]["interactive"] is False
    assert result[5]["interactive"] is False
    assert result[6]["interactive"] is True


def test_primary_rows_come_before_spread_rows():
    """The best answer per video must be readable without scrolling past jitter."""
    rows, primary_count = _controller()._build_rows(_pv_outcome(), {})
    assert primary_count == 3
    assert [row[0] for row in rows[:3]] == ["L21_V001", "L21_V002", "L21_V003"]


def test_primary_rows_ordered_by_score_desc():
    rows, _count = _controller()._build_rows(_pv_outcome(), {})
    assert rows[0][0] == "L21_V001"
    assert rows[1][0] == "L21_V002"
    assert rows[2][0] == "L21_V003"


def test_first_row_is_unjittered_answer():
    rows, _count = _controller()._build_rows(_pv_outcome(), {})
    assert rows[0][1] == (1000, 2000, 3000)


def test_preview_is_editable_csv_matching_built_rows():
    body = _controller().preview_submission(_pv_outcome(), {})["value"]
    lines = body.splitlines()
    assert len(lines) > 3
    assert lines[0].startswith("L21_V001,")
    assert all(line.split(",")[0] in {"L21_V001", "L21_V002", "L21_V003"} for line in lines)


def test_preview_shows_pinned_marker():
    from trake_submission import pin_key

    pinned = {pin_key("L21_V001", 1): 2500}
    body = _controller().preview_submission(_pv_outcome(), pinned)["value"]
    assert "2500" in body


def test_preview_without_results_returns_message():
    result = _controller().preview_submission(None, {})
    assert "No search results" in result["value"]


def _export(tmp_path, monkeypatch, content="L21_V001, 1000", filename="query-4-trake.csv"):
    from trake_submission import export_csv_file

    monkeypatch.setattr("trake_submission.tempfile.gettempdir", lambda: str(tmp_path))
    return export_csv_file(content, filename)


def test_export_writes_utf8_without_bom(tmp_path, monkeypatch):
    """Organizers flagged wrong encoding as the most common submission failure."""
    update, message = _export(tmp_path, monkeypatch)
    raw = Path(update["value"]).read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert raw.decode("utf-8")
    assert Path(update["value"]).name in message


def test_export_rejects_empty_content():
    from trake_submission import export_csv_file

    update, message = export_csv_file("   \n", "query-4-trake.csv")
    assert update["value"] is None
    assert "No data" in message


def test_export_sanitizes_path_traversal_in_filename(tmp_path, monkeypatch):
    update, _msg = _export(tmp_path, monkeypatch, filename="../../etc/evil.csv")
    written = Path(update["value"])
    assert tmp_path in written.parents or written.parent == tmp_path / "aic26_submissions"
    assert written.exists()


def test_export_never_overwrites_existing_file(tmp_path, monkeypatch):
    first, _m1 = _export(tmp_path, monkeypatch)
    second, _m2 = _export(tmp_path, monkeypatch)
    assert Path(first["value"]) != Path(second["value"])
    assert Path(first["value"]).exists()
    assert Path(second["value"]).exists()


def test_preview_and_exported_file_share_frame_numbers(monkeypatch, tmp_path):
    """FRAME_INDEX_BASE is a knob the organizers may flip; the preview has to
    follow the file, not its own copy of the numbers."""
    import trake

    monkeypatch.setattr(trake, "FRAME_INDEX_BASE", 1)
    controller = _controller()
    outcome = _pv_outcome()

    preview = controller.preview_submission(outcome, {})["value"]
    rows, _count = controller._build_rows(outcome, {})
    file_body = format_submission(rows)
    exported_first_row = file_body.splitlines()[0]

    assert preview.splitlines()[0] == exported_first_row


def test_every_ranked_video_gets_an_answer_row():
    """SUBMISSION_MAX_ROWS used to be consumed by jitter around the top 2-3 videos,
    so most of the ranking never reached the file."""
    from schemas import TrakeVideoMatch

    videos = []
    for rank in range(20):
        video_id = f"L21_V{rank:03d}"
        base = 1000 + rank * 100
        events = tuple(
            _pv_event(i, base + i * 1000, video_id, 0.5 - rank * 0.01) for i in range(3)
        )
        videos.append(
            TrakeVideoMatch(
                video_id=video_id,
                collection_id="L21",
                title="t",
                author="a",
                total_score=0.5 - rank * 0.01,
                events=events,
                max_frame_idx=base + 9000,
            )
        )
    outcome = TrakeOutcome(videos=tuple(videos), queries=())

    rows, primary_count = _controller()._build_rows(outcome, {})
    assert primary_count == 20
    assert len({row[0] for row in rows[:primary_count]}) == 20


def test_total_rows_never_exceed_submission_max():
    """Answers plus jitter used to overflow the 100-row contest budget."""
    from schemas import TrakeVideoMatch

    videos = []
    for rank in range(20):
        video_id = f"L21_V{rank:03d}"
        base = 1000 + rank * 100
        events = tuple(
            _pv_event(i, base + i * 1000, video_id, 0.5 - rank * 0.01) for i in range(3)
        )
        videos.append(
            TrakeVideoMatch(
                video_id=video_id,
                collection_id="L21",
                title="t",
                author="a",
                total_score=0.5 - rank * 0.01,
                events=events,
                max_frame_idx=base + 9000,
            )
        )
    outcome = TrakeOutcome(videos=tuple(videos), queries=())

    import trake

    rows, _primary_count = _controller()._build_rows(outcome, {})
    assert len(rows) <= trake.SUBMISSION_MAX_ROWS
    # The one-answer-per-video block still leads the file.
    assert [row[0] for row in rows[:20]] == [f"L21_V{rank:03d}" for rank in range(20)]
