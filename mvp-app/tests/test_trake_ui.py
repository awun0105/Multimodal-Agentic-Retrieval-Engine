from pathlib import Path

import pytest

import trake_ui
from schemas import TrakeOutcome
from trake import MAX_EVENTS, MIN_EVENTS
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
        TrakeController(searcher).search_events(flag, "one", "two")
        assert searcher.seen is flag


def test_add_event_keeps_text_already_typed():
    """Growing must not clear boxes; only shrinking clears the hidden one."""
    result = TrakeController.add_event(3)
    for update in result[1 : 1 + MAX_EVENTS]:
        assert "value" not in update


def test_export_submission_without_results_returns_message_not_error():
    controller = TrakeController(trake_searcher=None)
    file_path, message = controller.export_submission(None, pinned_frames={})
    assert file_path is None
    assert "No search results" in message


def test_search_trake_gpu_raises_when_controller_missing(monkeypatch):
    monkeypatch.setattr(trake_ui, "_trake_controller", None)
    with pytest.raises(RuntimeError, match="not been initialized"):
        search_trake_gpu(True, "an event")


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


def test_preview_and_export_use_same_rows(tmp_path, monkeypatch):
    controller = _controller()
    outcome = _pv_outcome()
    preview_rows, _c = controller._build_rows(outcome, {})
    monkeypatch.setattr(trake_ui.tempfile, "gettempdir", lambda: str(tmp_path))
    file_path, _msg = controller.export_submission(outcome, {})
    exported = Path(file_path).read_text(encoding="utf-8").splitlines()
    assert len(exported) == len(preview_rows)
    assert exported[0].startswith(preview_rows[0][0])


def test_preview_markdown_labels_answer_and_reference_sections():
    body = _controller().preview_submission(_pv_outcome(), {})["value"]
    assert "nộp" in body.lower()
    assert "tham khảo" in body.lower()


def test_preview_markdown_escapes_video_id():
    from trake_ui_render import build_submission_preview_markdown

    body = build_submission_preview_markdown([("<b>x</b>", (1,))], 1, {})
    assert "<b>" not in body


def test_preview_shows_pinned_marker():
    from trake_submission import pin_key

    pinned = {pin_key("L21_V001", 1): 2500}
    body = _controller().preview_submission(_pv_outcome(), pinned)["value"]
    assert "2500" in body


def test_preview_without_results_returns_message():
    result = _controller().preview_submission(None, {})
    assert "No search results" in result["value"]


def test_export_message_includes_filename_and_row_count(tmp_path, monkeypatch):
    monkeypatch.setattr(trake_ui.tempfile, "gettempdir", lambda: str(tmp_path))
    file_path, message = _controller().export_submission(_pv_outcome(), {})
    assert Path(file_path).name in message
    assert str(len(Path(file_path).read_text(encoding="utf-8").splitlines())) in message


def test_export_writes_utf8(tmp_path, monkeypatch):
    """Organizers flagged wrong encoding as the most common submission failure."""
    monkeypatch.setattr(trake_ui.tempfile, "gettempdir", lambda: str(tmp_path))
    file_path, _msg = _controller().export_submission(_pv_outcome(), {})
    raw = Path(file_path).read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert raw.decode("utf-8")


def test_preview_frame_numbers_match_exported_file(monkeypatch, tmp_path):
    """FRAME_INDEX_BASE is a knob the organizers may flip; the preview has to
    follow the file, not its own copy of the numbers."""
    import trake

    monkeypatch.setattr(trake, "FRAME_INDEX_BASE", 1)
    monkeypatch.setattr(trake_ui.tempfile, "gettempdir", lambda: str(tmp_path))
    controller = _controller()
    outcome = _pv_outcome()

    preview = controller.preview_submission(outcome, {})["value"]
    file_path, _msg = controller.export_submission(outcome, {})
    first_row = Path(file_path).read_text(encoding="utf-8").splitlines()[0]

    frames = first_row.split(", ")[1:]
    assert all(frame in preview for frame in frames)


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
