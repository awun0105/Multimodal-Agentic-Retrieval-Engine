"""MMR duplicate-penalty tests. Pure numpy — no DB, no model, no fixtures."""

from __future__ import annotations

import inspect
import math

import numpy as np
import pytest

from db import (
    MMR_OVERFETCH,
    MMR_PENALTY_BASE,
    MMR_SIMILARITY_THRESHOLD,
    SearchMechanism,
    _apply_mmr,
)
from tests.test_search import _make_store


def _unit(*components: float) -> list[float]:
    vector = np.asarray(components, dtype=np.float32)
    return list(vector / np.linalg.norm(vector))


def _pair_at_cosine(cosine: float) -> np.ndarray:
    """Two unit vectors in 2-D whose dot product is exactly `cosine`."""
    angle = math.acos(cosine)
    return np.asarray(
        [[1.0, 0.0], [math.cos(angle), math.sin(angle)]],
        dtype=np.float32,
    )


def test_first_item_of_cluster_keeps_original_score():
    vectors = np.asarray([[1.0, 0.0]] * 3, dtype=np.float32)
    scores = np.asarray([0.9, 0.8, 0.7], dtype=np.float32)
    ids = np.asarray([10, 11, 12])

    new_scores, new_ids = _apply_mmr(vectors, scores, ids)

    by_id = dict(zip(new_ids.tolist(), new_scores.tolist(), strict=True))
    assert by_id[10] == pytest.approx(0.9)
    assert by_id[11] == pytest.approx(0.8 * MMR_PENALTY_BASE)
    assert by_id[12] == pytest.approx(0.7 * MMR_PENALTY_BASE**2)


def test_distinct_scenes_are_not_penalized():
    vectors = np.asarray([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]], dtype=np.float32)
    scores = np.asarray([0.9, 0.8, 0.7], dtype=np.float32)
    ids = np.asarray([1, 2, 3])

    new_scores, new_ids = _apply_mmr(vectors, scores, ids)

    assert new_ids.tolist() == [1, 2, 3]
    assert new_scores == pytest.approx(scores)


def test_threshold_boundary_is_inclusive():
    ids = np.asarray([0, 1])
    scores = np.asarray([0.9, 0.8], dtype=np.float32)

    at_threshold, _ = _apply_mmr(_pair_at_cosine(MMR_SIMILARITY_THRESHOLD), scores, ids)
    assert at_threshold[1] == pytest.approx(0.8 * MMR_PENALTY_BASE, rel=1e-4)

    below, _ = _apply_mmr(_pair_at_cosine(MMR_SIMILARITY_THRESHOLD - 0.001), scores, ids)
    assert below[1] == pytest.approx(0.8, rel=1e-4)


def test_reordering_pushes_duplicates_down():
    vectors = np.asarray([[1.0, 0.0], [1.0, 0.0], [0.0, 1.0]], dtype=np.float32)
    scores = np.asarray([0.9, 0.89, 0.5], dtype=np.float32)
    ids = np.asarray([0, 1, 2])

    new_scores, new_ids = _apply_mmr(vectors, scores, ids)

    assert new_ids.tolist() == [0, 2, 1]
    assert new_scores == pytest.approx([0.9, 0.5, 0.89 * MMR_PENALTY_BASE])


def test_empty_and_single_input_are_noop():
    empty_scores, empty_ids = _apply_mmr(
        np.zeros((0, 2), dtype=np.float32),
        np.asarray([], dtype=np.float32),
        np.asarray([], dtype=np.int64),
    )
    assert empty_ids.size == 0
    assert empty_scores.size == 0

    one_scores, one_ids = _apply_mmr(
        np.asarray([[1.0, 0.0]], dtype=np.float32),
        np.asarray([0.42], dtype=np.float32),
        np.asarray([7]),
    )
    assert one_ids.tolist() == [7]
    assert one_scores == pytest.approx([0.42])


def test_penalty_counts_only_kept_items():
    """A, A' near-duplicates; B, B' near-duplicates. Each cluster penalises independently."""
    vectors = np.asarray(
        [_unit(1.0, 0.0), _unit(0.0, 1.0), _unit(1.0, 0.02), _unit(0.02, 1.0)],
        dtype=np.float32,
    )
    scores = np.asarray([0.9, 0.85, 0.8, 0.75], dtype=np.float32)
    ids = np.asarray([0, 1, 2, 3])

    new_scores, new_ids = _apply_mmr(vectors, scores, ids)

    by_id = dict(zip(new_ids.tolist(), new_scores.tolist(), strict=True))
    assert by_id[0] == pytest.approx(0.9)
    assert by_id[1] == pytest.approx(0.85)
    assert by_id[2] == pytest.approx(0.8 * MMR_PENALTY_BASE)
    assert by_id[3] == pytest.approx(0.75 * MMR_PENALTY_BASE)


def test_return_details_false_keeps_two_value_contract():
    """Existing callers unpack two values; the details flag must stay opt-in."""
    vectors = np.asarray([[1.0, 0.0], [1.0, 0.0]], dtype=np.float32)
    scores = np.asarray([0.9, 0.8], dtype=np.float32)

    result = _apply_mmr(vectors, scores, np.asarray([0, 1]))

    assert len(result) == 2


def test_return_details_reports_duplicate_count():
    vectors = np.asarray([[1.0, 0.0]] * 3, dtype=np.float32)
    scores = np.asarray([0.9, 0.8, 0.7], dtype=np.float32)

    _, _, details = _apply_mmr(
        vectors, scores, np.asarray([10, 11, 12]), return_details=True
    )

    assert details[10]["duplicates"] == 0
    assert details[11]["duplicates"] == 1
    assert details[12]["duplicates"] == 2


def test_return_details_names_the_representative():
    vectors = np.asarray([[1.0, 0.0]] * 3, dtype=np.float32)
    scores = np.asarray([0.9, 0.8, 0.7], dtype=np.float32)

    _, _, details = _apply_mmr(
        vectors, scores, np.asarray([10, 11, 12]), return_details=True
    )

    assert details[10]["similar_to"] is None
    assert details[11]["similar_to"] == 10
    assert details[12]["similar_to"] == 10


def test_distinct_scenes_report_zero_duplicates():
    vectors = np.asarray([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32)
    scores = np.asarray([0.9, 0.8], dtype=np.float32)

    _, _, details = _apply_mmr(
        vectors, scores, np.asarray([0, 1]), return_details=True
    )

    assert all(entry["duplicates"] == 0 for entry in details.values())
    assert all(entry["similar_to"] is None for entry in details.values())


def test_search_by_text_signature_unchanged():
    parameters = inspect.signature(SearchMechanism.search_by_text).parameters
    assert list(parameters) == [
        "self",
        "query",
        "top_k",
        "query_language",
        "filters",
        "translate_vietnamese",
    ]


def test_same_studio_frames_survive_the_threshold():
    """Anchors change but the studio fills the frame: measured 0.90-0.94 cosine.
    Those are distinct scenes and must not be grouped."""
    for cosine in (0.900, 0.922, 0.931, 0.939):
        vectors = _pair_at_cosine(cosine)
        _, _, details = _apply_mmr(
            vectors,
            np.asarray([0.9, 0.8], dtype=np.float32),
            np.asarray([0, 1]),
            return_details=True,
        )
        assert details[1]["duplicates"] == 0, f"cosine {cosine} was grouped"


def test_near_identical_frames_are_still_grouped():
    vectors = _pair_at_cosine(0.97)
    _, _, details = _apply_mmr(
        vectors,
        np.asarray([0.9, 0.8], dtype=np.float32),
        np.asarray([0, 1]),
        return_details=True,
    )
    assert details[1]["duplicates"] == 1


def test_the_pool_is_widened_whether_or_not_grouping_runs(tmp_path, monkeypatch):
    """Grouping is a filter over the results already on screen. Widening only
    when it is on would make Apply a second search over a different set, and a
    frame the searcher was looking at could vanish without being grouped away."""
    store = _make_store(tmp_path)
    asked = []
    original = store.image_indexer.search

    def record(query, k):
        asked.append(k)
        return original(query, k)

    monkeypatch.setattr(store.image_indexer, "search", record)

    for enabled in (True, False):
        asked.clear()
        store.mmr_enabled = enabled
        outcome = store.search_by_text("red car", top_k=2)
        assert asked == [2 * MMR_OVERFETCH]
        assert len(outcome.results) <= 2, "the searcher still sees top_k"


def test_result_count_is_capped_at_top_k(tmp_path):
    store = _make_store(tmp_path)
    store.mmr_enabled = True

    outcome = store.search_by_text("red car", top_k=2)

    assert len(outcome.results) <= 2
    assert set(outcome.duplicate_details) <= {r.vector_id for r in outcome.results}


def test_pool_scales_with_the_slider_maximum(tmp_path, monkeypatch):
    """top_k maxes out at 200; the widened pool follows it rather than capping."""
    store = _make_store(tmp_path)
    asked = []
    original = store.image_indexer.search
    monkeypatch.setattr(
        store.image_indexer,
        "search",
        lambda query, k: (asked.append(k), original(query, k))[1],
    )
    store.mmr_enabled = True

    store.search_by_text("red car", top_k=200)

    assert asked == [200 * MMR_OVERFETCH]


def test_first_search_is_raw(tmp_path):
    """Grouping is applied from the refine panel, so the opening result set has
    to be the unmodified ranking to compare against."""
    store = _make_store(tmp_path)

    assert store.mmr_enabled is False


def test_apply_button_drives_grouping_not_the_checkbox(tmp_path):
    """Toggling used to take effect immediately, which made the before/after
    comparison impossible to hold on screen."""
    from app import build_app
    from tests.test_search import _make_store as make

    demo = build_app(make(tmp_path))
    checkboxes = [
        block
        for block in demo.blocks.values()
        if getattr(block, "label", None) == "Gộp ảnh trùng lặp"
    ]
    assert checkboxes, "grouping checkbox missing"
    checkbox_id = checkboxes[0]._id
    changes = [
        dep
        for dep in demo.config["dependencies"]
        if dep["targets"] and any(t[0] == checkbox_id and t[1] == "change" for t in dep["targets"])
    ]
    assert not changes, "checkbox should not re-rank on toggle"


def test_linkage_grouping_refuses_to_chain():
    """A frame can resemble two others that do not resemble each other — measured
    A-B 0.944, A-C 0.946, B-C 0.853 on three views of one pitch. Demoting against
    whichever frame ranked higher would treat all three as one scene."""
    from db import _apply_linkage

    angle = np.arccos(0.944)
    vectors = np.asarray(
        [
            [1.0, 0.0],
            [np.cos(angle), np.sin(angle)],
            [np.cos(angle), -np.sin(angle)],
        ],
        dtype=np.float32,
    )
    vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
    assert vectors[1] @ vectors[2] < MMR_SIMILARITY_THRESHOLD

    _, _, details = _apply_linkage(
        vectors,
        np.asarray([0.9, 0.8, 0.7], dtype=np.float32),
        np.asarray([10, 11, 12]),
        return_details=True,
    )

    anchors = {entry["similar_to"] for entry in details.values()} - {None}
    assert len(anchors) <= 1, "B and C must not be folded into one another"


def test_linkage_keeps_the_strongest_frame_of_each_cluster():
    from db import _apply_linkage

    vectors = _pair_at_cosine(0.99)
    scores, ids, details = _apply_linkage(
        vectors,
        np.asarray([0.5, 0.9], dtype=np.float32),
        np.asarray([10, 11]),
        return_details=True,
    )

    assert ids[0] == 11, "the higher-scoring frame leads its cluster"
    assert details[11]["duplicates"] == 0
    assert details[10]["duplicates"] == 1
    assert details[10]["similar_to"] == 11


def test_grouping_mode_selects_the_ranking_function(tmp_path):
    """The picker sits beside the grouping checkbox because it changes results,
    not just how they are displayed."""
    from app import SearchController
    from db import GROUPING_ANCHOR, GROUPING_LINKAGE

    store = _make_store(tmp_path)
    controller = SearchController(store, page_size=10)

    controller.set_mmr(True, SearchController.LINKAGE_MODE)
    assert store.grouping_mode == GROUPING_LINKAGE

    controller.set_mmr(True, SearchController.ANCHOR_MODE)
    assert store.grouping_mode == GROUPING_ANCHOR


def test_grouping_mode_is_a_single_choice(tmp_path):
    """The two modes read the same frames differently — running both at once has
    no meaning, so the control must not allow it."""
    import gradio as gr
    from app import SearchController, build_app
    from tests.test_search import _make_store as make

    demo = build_app(make(tmp_path))
    pickers = [
        block
        for block in demo.blocks.values()
        if getattr(block, "elem_id", None) == "cluster-mode"
    ]

    assert pickers, "grouping mode picker missing"
    picker = pickers[0]
    assert isinstance(picker, gr.Radio), "a checkbox group would allow both at once"
    assert list(picker.choices) == [
        (label, label) for label in SearchController.CLUSTER_MODES
    ]
    assert picker.value in SearchController.CLUSTER_MODES
