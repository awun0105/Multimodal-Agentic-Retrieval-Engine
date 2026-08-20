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
    file_path, message = controller.export_submission(None)
    assert file_path is None
    assert "No search results" in message


def test_search_trake_gpu_raises_when_controller_missing(monkeypatch):
    monkeypatch.setattr(trake_ui, "_trake_controller", None)
    with pytest.raises(RuntimeError, match="not been initialized"):
        search_trake_gpu(True, "an event")
