"""Query history: stepping back to an earlier result set without re-running the search."""

from __future__ import annotations

from app import HISTORY_LIMIT, _push_history


def _rows(count: int = 1) -> list[dict]:
    return [{"keyframe_id": f"V01_{i:03d}"} for i in range(count)]


def test_newest_query_comes_first():
    history = _push_history([], "áo đỏ", _rows())
    history = _push_history(history, "xe máy", _rows())

    assert [entry["label"] for entry in history] == ["xe máy", "áo đỏ"]


def test_repeating_a_query_moves_it_up_instead_of_duplicating():
    history = _push_history([], "áo đỏ", _rows())
    history = _push_history(history, "xe máy", _rows())
    history = _push_history(history, "áo đỏ", _rows())

    assert [entry["label"] for entry in history] == ["áo đỏ", "xe máy"]


def test_empty_results_are_not_recorded():
    """A query that found nothing is not worth stepping back to."""
    assert _push_history([], "không có gì", []) == []


def test_blank_label_is_not_recorded():
    assert _push_history([], "   ", _rows()) == []


def test_history_is_capped_at_the_limit():
    history: list = []
    for index in range(HISTORY_LIMIT + 5):
        history = _push_history(history, f"query {index}", _rows())

    assert len(history) == HISTORY_LIMIT
    assert history[0]["label"] == f"query {HISTORY_LIMIT + 4}"


def test_push_returns_a_new_list_so_gradio_state_updates():
    original: list = []
    updated = _push_history(original, "áo đỏ", _rows())

    assert updated is not original
    assert original == []


def test_stored_rows_are_detached_from_the_caller():
    rows = _rows(2)
    history = _push_history([], "áo đỏ", rows)
    rows.clear()

    assert len(history[0]["rows"]) == 2
