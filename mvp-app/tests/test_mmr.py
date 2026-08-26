"""MMR duplicate-penalty tests. Pure numpy — no DB, no model, no fixtures."""

from __future__ import annotations

import inspect
import math

import numpy as np
import pytest

from db import MMR_PENALTY_BASE, MMR_SIMILARITY_THRESHOLD, SearchMechanism, _apply_mmr


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
