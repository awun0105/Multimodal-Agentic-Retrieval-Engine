from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from system1.asr.alignment import (
    AsrAlignmentError,
    align_nemo_hypothesis_words,
    ctc_viterbi_align,
)


def _matrix(path: list[int], vocabulary_size: int) -> np.ndarray:
    values = np.full((len(path), vocabulary_size), -10.0, dtype=np.float64)
    for timestep, symbol in enumerate(path):
        values[timestep, symbol] = 0.0
    return values


def test_ctc_viterbi_aligns_simple_target() -> None:
    spans = ctc_viterbi_align(
        _matrix([2, 0, 0, 2, 1, 1, 2], 3),
        [0, 1],
        blank_id=2,
    )
    assert [(row.token_id, row.start_timestep, row.end_timestep) for row in spans] == [
        (0, 1, 3),
        (1, 4, 6),
    ]


def test_ctc_viterbi_requires_blank_between_repeated_tokens() -> None:
    spans = ctc_viterbi_align(
        _matrix([1, 0, 1, 0, 1], 2),
        [0, 0],
        blank_id=1,
    )
    assert [(row.start_timestep, row.end_timestep) for row in spans] == [
        (1, 2),
        (3, 4),
    ]


def test_ctc_viterbi_rejects_impossible_path() -> None:
    with pytest.raises(AsrAlignmentError, match="no possible path"):
        ctc_viterbi_align(_matrix([1], 2), [0, 0], blank_id=1)


@pytest.mark.parametrize(
    "matrix",
    [np.asarray([1.0, 2.0]), np.asarray([[0.0, np.nan]])],
)
def test_ctc_viterbi_rejects_invalid_matrix(matrix: np.ndarray) -> None:
    with pytest.raises(AsrAlignmentError, match="finite T x V"):
        ctc_viterbi_align(matrix, [0], blank_id=1)


def test_nemo_char_vocabulary_groups_aligned_tokens_into_words() -> None:
    model = SimpleNamespace(
        decoder=SimpleNamespace(vocabulary=["a", " ", "b"]),
        cfg={"preprocessor": {"window_stride": 0.01}},
        encoder=SimpleNamespace(subsampling_factor=2),
    )
    hypothesis = SimpleNamespace(alignments=_matrix([3, 0, 3, 1, 3, 2, 3], 4))
    timeline = [
        {"frame_id": index, "pts_time": index * 0.02, "duration_time": 0.02}
        for index in range(20)
    ]
    words = align_nemo_hypothesis_words(
        hypothesis,
        model,
        text="a b",
        segment_id="v_ASR00000",
        video_id="v",
        segment_start_sec=0.0,
        segment_end_sec=0.2,
        frame_timeline=timeline,
        provider="nemo",
        model_name="fixture",
        model_version="revision",
    )
    assert [row["text"] for row in words] == ["a", "b"]
    assert [(row["start_sec"], row["end_sec"]) for row in words] == [
        (0.02, 0.04),
        (0.1, 0.12),
    ]
    assert all(row["alignment_method"] == "ctc_forced_alignment" for row in words)
