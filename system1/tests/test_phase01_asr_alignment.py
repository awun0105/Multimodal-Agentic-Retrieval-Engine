from __future__ import annotations

from types import SimpleNamespace
from typing import ClassVar

import numpy as np
import pytest

from system1.asr.alignment import (
    AsrAlignmentError,
    align_nemo_hypothesis_words,
    ctc_viterbi_align,
    trim_aligned_word_prefix,
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


def test_forced_split_trims_after_full_ctc_alignment_and_preserves_late_timing() -> None:
    model = SimpleNamespace(
        decoder=SimpleNamespace(vocabulary=["b", " ", "c", "d"]),
        cfg={"preprocessor": {"window_stride": 0.01}},
        encoder=SimpleNamespace(subsampling_factor=2),
    )
    hypothesis = SimpleNamespace(
        alignments=_matrix([4, 0, 4, 1, 4, 2, 4, 1, 4, 3, 4], 5)
    )
    timeline = [
        {"frame_id": index, "pts_time": index * 0.02, "duration_time": 0.02}
        for index in range(30)
    ]
    raw_words = align_nemo_hypothesis_words(
        hypothesis,
        model,
        text="b c d",
        segment_id="v_ASR00001",
        video_id="v",
        segment_start_sec=1.0,
        segment_end_sec=1.3,
        frame_timeline=timeline,
        provider="nemo",
        model_name="fixture",
        model_version="revision",
    )
    words = trim_aligned_word_prefix(
        raw_words,
        removed_prefix_text="b c",
        canonical_text="d",
        segment_id="v_ASR00001",
    )
    assert [row["text"] for row in words] == ["d"]
    assert words[0]["start_sec"] == pytest.approx(1.18)
    assert words[0]["end_sec"] == pytest.approx(1.2)
    assert words[0]["word_index"] == 0
    assert words[0]["asr_word_id"] == "v_ASR00001_W00000"


class _SubwordTokenizer:
    vocab: ClassVar[tuple[str, ...]] = ("x", "in", "ch", "ao", "unused")
    vocab_size = len(vocab)
    unk_id = 4

    _tokens: ClassVar[dict[str, tuple[str, ...]]] = {
        "xin": ("x", "in"),
        "chao": ("ch", "ao"),
        "xin chao": ("x", "in", "ch", "ao"),
    }

    def text_to_tokens(self, text: str) -> list[str]:
        return list(self._tokens[text])

    def text_to_ids(self, text: str) -> list[int]:
        return [self.vocab.index(token) for token in self.text_to_tokens(text)]

    def ids_to_text(self, token_ids: list[int]) -> str:
        return "<unk>" if token_ids == [self.unk_id] else ""

    def ids_to_tokens(self, token_ids: list[int]) -> list[str]:
        return [self.vocab[token_id] for token_id in token_ids]


def test_nemo_subword_tokenizer_groups_multiple_tokens_per_word() -> None:
    tokenizer = _SubwordTokenizer()
    model = SimpleNamespace(
        tokenizer=tokenizer,
        blank_id=tokenizer.vocab_size,
        cfg={"preprocessor": {"window_stride": 0.01}},
        encoder=SimpleNamespace(subsampling_factor=2),
    )
    hypothesis = SimpleNamespace(
        alignments=_matrix([5, 0, 5, 1, 5, 2, 5, 3, 5], 6)
    )
    timeline = [
        {"frame_id": index, "pts_time": index * 0.02, "duration_time": 0.02}
        for index in range(20)
    ]
    words = align_nemo_hypothesis_words(
        hypothesis,
        model,
        text="xin chao",
        segment_id="v_ASR00000",
        video_id="v",
        segment_start_sec=0.0,
        segment_end_sec=0.2,
        frame_timeline=timeline,
        provider="nemo",
        model_name="fixture",
        model_version="revision",
    )
    assert [row["text"] for row in words] == ["xin", "chao"]
    assert [(row["start_sec"], row["end_sec"]) for row in words] == [
        (0.02, 0.08),
        (0.1, 0.16),
    ]


def test_forced_split_trim_rejects_tokenizer_word_mismatch() -> None:
    with pytest.raises(AsrAlignmentError, match="overlap prefix"):
        trim_aligned_word_prefix(
            [
                {"text": "different", "word_index": 0, "asr_word_id": "old"},
                {"text": "retained", "word_index": 1, "asr_word_id": "old2"},
            ],
            removed_prefix_text="expected",
            canonical_text="retained",
            segment_id="v_ASR00000",
        )
