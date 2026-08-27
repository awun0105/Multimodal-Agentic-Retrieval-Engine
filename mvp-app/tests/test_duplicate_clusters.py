"""Grouping penalised frames under the representative that outranked them."""

from __future__ import annotations

from app import SearchController


def _row(vector_id: int, similar_to: int | None = None, duplicates: int = 0) -> dict:
    return {
        "vector_id": vector_id,
        "keyframe_id": f"L01_V001_{vector_id:03d}",
        "image_path": f"/nowhere/{vector_id}.jpg",
        "similar_to": similar_to,
        "duplicates": duplicates,
    }


def test_no_rows_yields_no_clusters():
    assert SearchController.duplicate_clusters([]) == []
    assert SearchController.duplicate_clusters(None) == []


def test_distinct_scenes_yield_no_clusters():
    rows = [_row(1), _row(2), _row(3)]
    assert SearchController.duplicate_clusters(rows) == []


def test_representative_leads_its_cluster():
    rows = [_row(1), _row(2, similar_to=1, duplicates=1), _row(3, similar_to=1, duplicates=2)]

    clusters = SearchController.duplicate_clusters(rows)

    assert len(clusters) == 1
    assert [row["vector_id"] for row in clusters[0]] == [1, 2, 3]


def test_bigger_clusters_come_first():
    rows = [
        _row(1),
        _row(2, similar_to=1),
        _row(3, similar_to=1),
        _row(4, similar_to=1),
        _row(10),
        _row(11, similar_to=10),
    ]

    clusters = SearchController.duplicate_clusters(rows)

    assert [len(c) for c in clusters] == [4, 2]


def test_rows_without_the_key_are_skipped():
    rows = [{"vector_id": 1, "keyframe_id": "a", "image_path": "/x.jpg"}]
    assert SearchController.duplicate_clusters(rows) == []


def test_representative_trimmed_out_of_top_k_drops_its_cluster():
    """The pool is widened then trimmed, so an anchor can fall outside the results."""
    rows = [_row(2, similar_to=999, duplicates=1)]

    assert SearchController.duplicate_clusters(rows) == []


def test_choices_read_as_cluster_number_and_size():
    rows = [_row(1), _row(2, similar_to=1), _row(3, similar_to=1)]

    clusters = SearchController.duplicate_clusters(rows)

    assert SearchController.cluster_choices(clusters) == ["Cụm 1 (3 ảnh)"]
    assert SearchController.cluster_choices([]) == []


def test_summary_counts_pushed_down_frames_not_whole_clusters():
    rows = [_row(1), _row(2, similar_to=1), _row(3, similar_to=1)]

    clusters = SearchController.duplicate_clusters(rows)
    summary = SearchController.cluster_summary_text(clusters, len(rows))

    assert "2 ảnh" in summary
    assert "1 cụm" in summary


def test_summary_says_so_when_nothing_was_grouped():
    assert "không có ảnh trùng" in SearchController.cluster_summary_text([], 20)
