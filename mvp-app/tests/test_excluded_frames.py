"""Marking rejected frames so a second pass over 100 results does not re-read them."""

from __future__ import annotations

from pathlib import Path

import pytest

from app import SearchController
from tests.test_app import FakeSearchMechanism


def _rows(tmp_path: Path, count: int = 3) -> list[dict]:
    rows = []
    for index in range(count):
        image = tmp_path / f"{index:03d}.jpg"
        image.write_bytes(b"jpeg")
        rows.append(
            {
                "keyframe_id": f"V01_{index:03d}",
                "image_path": str(image),
                "pts_time_sec": float(index),
                "score": 0.5,
            }
        )
    return rows


@pytest.fixture
def controller() -> SearchController:
    return SearchController(FakeSearchMechanism(), page_size=10)


def test_marking_a_frame_prefixes_its_caption(controller, tmp_path):
    rows = _rows(tmp_path)

    excluded, gallery, *_ = controller.toggle_excluded(set(), "V01_001", rows, 0, "Chỉ đánh dấu")

    assert excluded == {"V01_001"}
    assert gallery[1][1].startswith("[ĐÃ LOẠI] ")
    assert not gallery[0][1].startswith("[ĐÃ LOẠI] ")


def test_marking_twice_unmarks(controller, tmp_path):
    rows = _rows(tmp_path)

    marked, *_ = controller.toggle_excluded(set(), "V01_001", rows, 0, "Chỉ đánh dấu")
    unmarked, gallery, *_ = controller.toggle_excluded(
        marked, "V01_001", rows, 0, "Chỉ đánh dấu"
    )

    assert unmarked == set()
    assert not any(caption.startswith("[ĐÃ LOẠI] ") for _, caption in gallery)


def test_hide_mode_removes_the_frame_from_the_grid(controller, tmp_path):
    rows = _rows(tmp_path)

    _, gallery, *_ = controller.toggle_excluded(set(), "V01_001", rows, 0, "Ẩn hẳn")

    assert len(gallery) == 2
    assert all("V01_001" not in caption for _, caption in gallery)


def test_switching_mode_repaints_without_changing_the_set(controller, tmp_path):
    rows = _rows(tmp_path)

    gallery, *_ = controller.restyle_excluded({"V01_002"}, rows, 0, "Ẩn hẳn")
    assert len(gallery) == 2

    gallery, *_ = controller.restyle_excluded({"V01_002"}, rows, 0, "Chỉ đánh dấu")
    assert len(gallery) == 3


def test_clearing_restores_every_frame(controller, tmp_path):
    rows = _rows(tmp_path)

    excluded, gallery, *_ = controller.clear_excluded(rows, 0, "Ẩn hẳn")

    assert excluded == set()
    assert len(gallery) == 3


def test_empty_selection_is_ignored(controller, tmp_path):
    rows = _rows(tmp_path)

    excluded, *_ = controller.toggle_excluded(set(), "", rows, 0, "Chỉ đánh dấu")

    assert excluded == set()


def test_unmarking_survives_a_repaint_that_reshuffles_the_grid(controller, tmp_path):
    """Hide mode drops rows before slicing, so grid position 1 becomes a different frame."""
    rows = _rows(tmp_path, count=5)

    marked, *_ = controller.toggle_excluded(set(), "V01_001", rows, 0, "Ẩn hẳn")
    assert marked == {"V01_001"}

    unmarked, *_ = controller.toggle_excluded(marked, "V01_001", rows, 0, "Ẩn hẳn")
    assert unmarked == set()


def test_toggle_returns_a_new_set_so_gradio_state_updates(controller, tmp_path):
    rows = _rows(tmp_path)
    original: set = set()

    excluded, *_ = controller.toggle_excluded(original, "V01_000", rows, 0, "Chỉ đánh dấu")

    assert excluded is not original
    assert original == set()
