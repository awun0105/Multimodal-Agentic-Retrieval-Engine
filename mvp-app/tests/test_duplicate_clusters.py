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


def test_representative_is_labelled_in_the_main_gallery(tmp_path):
    """Knowing which frame a duplicate was folded into is what makes the
    grouping auditable — the demoted side was already marked, the kept side
    was not."""
    from tests.test_search import _make_store

    controller = SearchController(_make_store(tmp_path), page_size=10)
    image = tmp_path / "frame.jpg"
    image.write_bytes(b"")
    rows = [
        {**_row(1), "image_path": str(image), "pts_time_sec": 1.0, "score": 0.9},
        {**_row(2, similar_to=1, duplicates=1), "image_path": str(image),
         "pts_time_sec": 2.0, "score": 0.4},
    ]

    gallery = controller.page_payload(rows, 0)[0]

    assert "[đại diện]" in gallery[0][1]
    assert "[gộp x1]" in gallery[1][1]
    assert "[đại diện]" not in gallery[1][1]


def test_marker_rule_covers_both_galleries():
    """The outline is derived from caption text at render time, so the cluster
    strip has to use the same wording as the main gallery."""
    from app import APP_CSS, SHORTCUTS_HEAD

    assert "aiou-anchor" in APP_CSS
    assert "#cluster-gallery .aiou-anchor" in APP_CSS
    assert "[đại diện]" in SHORTCUTS_HEAD


def test_cluster_strip_labels_match_the_main_gallery(tmp_path):
    image = tmp_path / "frame.jpg"
    image.write_bytes(b"")
    cluster = [
        {**_row(1), "image_path": str(image)},
        {**_row(2, similar_to=1, duplicates=1), "image_path": str(image)},
    ]

    items = SearchController._cluster_items(cluster)

    assert items[0][1].startswith("[đại diện]")
    assert items[1][1].startswith("[gộp x1]")


def test_a_demoted_frame_is_never_called_a_representative(tmp_path):
    """Chained similarity means a frame can be folded into one image while
    another folds into it. Calling that frame a representative reads as a
    contradiction, so the demoted side wins the label."""
    from tests.test_search import _make_store

    controller = SearchController(_make_store(tmp_path), page_size=10)
    image = tmp_path / "frame.jpg"
    image.write_bytes(b"")
    rows = [
        {**_row(1), "image_path": str(image), "pts_time_sec": 1.0, "score": 0.9},
        {**_row(2, similar_to=1, duplicates=1), "image_path": str(image),
         "pts_time_sec": 2.0, "score": 0.4},
        {**_row(3, similar_to=2, duplicates=1), "image_path": str(image),
         "pts_time_sec": 3.0, "score": 0.2},
    ]

    captions = [item[1] for item in controller.page_payload(rows, 0)[0]]

    assert "[đại diện]" in captions[0]
    assert "[đại diện]" not in captions[1], "a grouped frame must not also be a representative"
    assert "[gộp x1]" in captions[1]


def _store_with_vectors(tmp_path, vectors):
    """A store whose embedding matrix is the caller's, so clustering is testable
    without the 173MB release file."""
    import numpy as np
    from tests.test_search import _make_store

    store = _make_store(tmp_path)
    store.embeddings = np.asarray(vectors, dtype=np.float32)
    return store


def test_complete_link_refuses_to_chain(tmp_path):
    """Measured on real frames: A-B 0.944, A-C 0.946, B-C 0.853 — three views of
    one pitch. Grouping all three would put B and C together despite them not
    resembling each other at all."""
    import numpy as np

    angle = np.arccos(0.944)
    vectors = np.zeros((3, 4), dtype=np.float32)
    vectors[0] = [1.0, 0.0, 0.0, 0.0]
    vectors[1] = [np.cos(angle), np.sin(angle), 0.0, 0.0]
    vectors[2] = [np.cos(angle), -np.sin(angle), 0.0, 0.0]
    vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
    assert vectors[1] @ vectors[2] < 0.94, "fixture must be non-transitive"

    controller = SearchController(_store_with_vectors(tmp_path, vectors), page_size=10)
    rows = [{**_row(i), "vector_id": i} for i in range(3)]

    clusters = controller.linkage_clusters(rows)

    for cluster in clusters:
        ids = [row["vector_id"] for row in cluster]
        assert not (1 in ids and 2 in ids), "B and C must not share a cluster"


def test_every_pair_inside_a_cluster_clears_the_threshold(tmp_path):
    import numpy as np

    vectors = np.eye(4, dtype=np.float32)
    vectors[1] = vectors[0] * 0.99 + vectors[1] * 0.141
    vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)

    controller = SearchController(_store_with_vectors(tmp_path, vectors), page_size=10)
    rows = [{**_row(i), "vector_id": i} for i in range(4)]

    for cluster in controller.linkage_clusters(rows):
        members = np.stack([vectors[row["vector_id"]] for row in cluster])
        similarity = members @ members.T
        off_diagonal = similarity[~np.eye(len(members), dtype=bool)]
        assert off_diagonal.min() >= SearchController.CLUSTER_LINK_THRESHOLD


def test_both_grouping_modes_are_offered(tmp_path):
    from tests.test_search import _make_store

    controller = SearchController(_make_store(tmp_path), page_size=10)

    assert controller.ANCHOR_MODE in controller.CLUSTER_MODES
    assert controller.LINKAGE_MODE in controller.CLUSTER_MODES
    assert controller._clusters_for([], controller.LINKAGE_MODE) == []
    assert controller._clusters_for([], controller.ANCHOR_MODE) == []


def test_neither_mode_is_a_special_case(tmp_path):
    """Both readings are first-class: a lookup, not an if-else where one mode is
    the exception."""
    from tests.test_search import _make_store

    controller = SearchController(_make_store(tmp_path), page_size=10)

    assert len(controller.CLUSTER_MODES) == 2
    for label in controller.CLUSTER_MODES:
        assert controller._clusters_for([], label) == []


def test_summary_reports_both_modes(tmp_path):
    """The counts disagree between modes — showing one alone hides the choice."""
    import numpy as np

    vectors = np.eye(3, dtype=np.float32)
    controller = SearchController(_store_with_vectors(tmp_path, vectors), page_size=10)
    rows = [
        {**_row(0), "vector_id": 0},
        {**_row(1, similar_to=0, duplicates=1), "vector_id": 1},
    ]

    text = controller.compare_modes_text(rows)

    for label in controller.CLUSTER_MODES:
        assert label in text
