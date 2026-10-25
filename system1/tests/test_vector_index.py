"""Behavior tests for inner-product vector indexes (ADR 0023)."""

from __future__ import annotations

import numpy as np
import pytest

from system1.indexes.vectors import build_vector_index, load_vector_index, search


def _vectors(count: int, dim: int = 16, seed: int = 0) -> np.ndarray:
    return np.random.default_rng(seed).normal(size=(count, dim)).astype("float32")


def test_query_returns_its_own_item_first(tmp_path) -> None:
    vectors = _vectors(50)
    ids = [f"kf{i}" for i in range(50)]
    build_vector_index(tmp_path, "image_siglip2", vectors, ids)
    index, item_ids = load_vector_index(tmp_path, "image_siglip2")

    hits = search(index, item_ids, vectors[[7, 23]], top_k=3)

    assert [row[0][0] for row in hits] == ["kf7", "kf23"]


def test_scores_are_cosine_similarity_regardless_of_vector_length(tmp_path) -> None:
    vectors = _vectors(10)
    scaled = vectors * np.arange(1, 11, dtype="float32")[:, None]
    build_vector_index(tmp_path, "image", scaled, [str(i) for i in range(10)])
    index, item_ids = load_vector_index(tmp_path, "image")

    hits = search(index, item_ids, vectors[[3]] * 100.0, top_k=1)

    assert hits[0][0][0] == "3"
    assert hits[0][0][1] == pytest.approx(1.0, abs=1e-5)


def test_vector_map_keeps_row_order_and_ids(tmp_path) -> None:
    ids = ["b", "a", "c"]
    build_vector_index(tmp_path, "text", _vectors(3), ids)

    _, item_ids = load_vector_index(tmp_path, "text")

    assert item_ids == ids


@pytest.mark.parametrize(
    ("vectors", "ids"),
    [
        (np.zeros((0, 4), dtype="float32"), []),
        (np.ones((2, 4), dtype="float32"), ["only-one-id"]),
        (np.array([[0.0, 0.0], [1.0, 0.0]], dtype="float32"), ["zero", "ok"]),
        (np.array([[np.nan, 1.0]], dtype="float32"), ["nan"]),
    ],
)
def test_invalid_input_fails_instead_of_writing_a_stub(tmp_path, vectors, ids) -> None:
    with pytest.raises(ValueError):
        build_vector_index(tmp_path, "image", vectors, ids)
    assert not list(tmp_path.iterdir())
