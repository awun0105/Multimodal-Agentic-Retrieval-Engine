"""Query-by-example search: the same ranking path, driven by a vector instead of text."""

from __future__ import annotations

import inspect

import numpy as np
import pytest

from db import SearchMechanism
from schemas import SearchFilters, SearchOutcome
from tests.test_search import _make_store


def test_search_by_vector_matches_search_by_text_for_same_vector(tmp_path):
    store = _make_store(tmp_path)
    store.mmr_enabled = False

    by_text = store.search_by_text("red car", top_k=3)
    by_vector = store.search_by_vector(np.asarray([1.0, 0.0], dtype=np.float32), top_k=3)

    assert [r.keyframe_id for r in by_vector.results] == [
        r.keyframe_id for r in by_text.results
    ]
    assert [r.score for r in by_vector.results] == pytest.approx(
        [r.score for r in by_text.results]
    )


def test_search_by_vector_respects_filters(tmp_path):
    store = _make_store(tmp_path)
    filters = SearchFilters(object_entities=("Car",), minimum_object_confidence=0.5)

    outcome = store.search_by_vector(
        np.asarray([1.0, 0.0], dtype=np.float32), top_k=3, filters=filters
    )

    assert [r.keyframe_id for r in outcome.results] == ["V01_002"]


def test_search_by_vector_rejects_out_of_range_top_k(tmp_path):
    store = _make_store(tmp_path)
    vector = np.asarray([1.0, 0.0], dtype=np.float32)

    for bad_top_k in (0, 201):
        with pytest.raises(ValueError, match="top_k"):
            store.search_by_vector(vector, top_k=bad_top_k)


def test_search_by_vector_normalizes_unnormalized_input(tmp_path):
    store = _make_store(tmp_path)
    store.mmr_enabled = False

    unit = store.search_by_vector(np.asarray([1.0, 0.0], dtype=np.float32), top_k=3)
    scaled = store.search_by_vector(np.asarray([2.0, 0.0], dtype=np.float32), top_k=3)

    assert [r.keyframe_id for r in scaled.results] == [r.keyframe_id for r in unit.results]
    assert [r.score for r in scaled.results] == pytest.approx(
        [r.score for r in unit.results]
    )


def test_search_by_vector_rejects_wrong_dimension(tmp_path):
    store = _make_store(tmp_path)

    with pytest.raises(ValueError):
        store.search_by_vector(np.asarray([1.0, 0.0, 0.0], dtype=np.float32), top_k=3)


def test_search_by_text_still_returns_search_outcome(tmp_path):
    store = _make_store(tmp_path)

    outcome = store.search_by_text("red car", top_k=3)

    assert isinstance(outcome, SearchOutcome)
    assert isinstance(outcome.results, tuple)
    assert outcome.query.clip_query


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


def test_use_mmr_override_leaves_the_shared_flag_untouched(tmp_path):
    """Two teammates share one process: a per-call override must not leak to the other."""
    store = _make_store(tmp_path)
    store.mmr_enabled = True

    store.search_by_vector(np.asarray([1.0, 0.0], dtype=np.float32), top_k=3, use_mmr=False)

    assert store.mmr_enabled is True


def test_use_mmr_none_follows_the_shared_flag(tmp_path):
    store = _make_store(tmp_path)
    vector = np.asarray([1.0, 0.0], dtype=np.float32)

    store.mmr_enabled = False
    ungrouped = store.search_by_vector(vector, top_k=3)
    store.mmr_enabled = True
    grouped = store.search_by_vector(vector, top_k=3)

    assert ungrouped.duplicate_details == {}
    assert grouped.duplicate_details != {}


def test_bad_top_k_fails_before_translation(tmp_path, monkeypatch):
    """Validating after translation would burn NLLB + CLIP on an input we already reject."""
    store = _make_store(tmp_path)

    def explode(*_args, **_kwargs):
        raise AssertionError("top_k must be rejected before the translator runs")

    monkeypatch.setattr(store.translator, "prepare", explode)

    with pytest.raises(ValueError, match="top_k"):
        store.search_by_text("red car", top_k=201)


def test_no_image_model_is_loaded_during_vector_search(tmp_path, monkeypatch):
    """Loading the second CLIP model mid-contest would stall the app for minutes."""
    store = _make_store(tmp_path)

    def explode():
        raise AssertionError("image encoder must not load during vector search")

    monkeypatch.setattr(store.clip_searcher, "_ensure_image_loaded", explode, raising=False)

    store.search_by_vector(np.asarray([1.0, 0.0], dtype=np.float32), top_k=3)
