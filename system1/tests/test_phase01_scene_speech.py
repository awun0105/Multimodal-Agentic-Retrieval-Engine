from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from PIL import Image

from system1.asr.links import assign_words_to_intervals, build_shot_transcript_links
from system1.phase01.production import _build_scene_evidence
from system1.scenes.grouping import group_scenes
from system1.scenes.speech import (
    SpeechGapEvidence,
    build_speech_gap_evidence,
    render_speech_evidence,
    validate_speech_policy,
)
from system1.scenes.vlm_judge import SemanticSceneBoundaryJudge
from system1.shots.transnet import scenes_to_shot_rows


def _policy() -> dict[str, Any]:
    return {
        "enabled": True,
        "contract_version": "aligned_speech_continuity_v2",
        "max_boundary_word_distance_sec": 1.0,
        "max_inter_word_gap_sec": 1.0,
    }


def _grouping_config() -> dict[str, Any]:
    return {
        "focus_gap_count": 8,
        "context_shots_each_side": 4,
        "stride": 6,
        "boundary_threshold": 0.67,
        "non_boundary_threshold": 0.33,
        "dense_boundary_count": 2,
        "dense_boundary_gap_window": 3,
        "strong_disagreement_min_votes": 2,
        "strong_disagreement_requires_both_labels": True,
        "max_consistency_review_rounds": 1,
        "scene_confidence_aggregation": "null_v1",
        "quality_guard": {
            "enabled": True,
            "min_shot_count": 8,
            "suspicious_boundary_density": 0.9,
            "suspicious_one_shot_scene_rate": 0.8,
            "unresolved_action": "review_required",
            "degenerate_review": {
                "enabled": True,
                "focus_gap_count": 8,
                "context_shots_each_side": 6,
                "max_rounds": 1,
            },
        },
    }


def _shots() -> list[dict[str, Any]]:
    return [
        {
            "video_id": "v",
            "shot_id": f"s{index}",
            "shot_index": index,
            "start_sec": index * 10.0,
            "end_sec": (index + 1) * 10.0,
            "start_frame": index * 100,
            "end_frame": (index + 1) * 100,
        }
        for index in range(2)
    ]


def _words(*, shared: bool = True, near: bool = True) -> list[dict[str, Any]]:
    timings = [
        ("xin", 9.6 if near else 6.0, 9.85 if near else 7.0),
        ("chào", 10.1 if near else 12.5, 10.35 if near else 13.0),
    ]
    return [
        {
            "asr_word_id": f"w{index}",
            "asr_segment_id": "a" if shared or index == 0 else "b",
            "word_index": index,
            "text": text,
            "start_sec": start,
            "end_sec": end,
        }
        for index, (text, start, end) in enumerate(timings)
    ]


def _evidence(
    word_rows: list[dict[str, Any]] | None = None,
    *,
    status: str = "pass",
    policy: dict[str, Any] | None = None,
) -> SpeechGapEvidence:
    rows = _words() if word_rows is None else word_rows
    segments = [
        {"asr_segment_id": identifier, "start_sec": 0.0, "end_sec": 20.0}
        for identifier in sorted({str(word["asr_segment_id"]) for word in rows})
    ]
    shot_rows = _shots()
    return build_speech_gap_evidence(
        shots=shot_rows,
        asr_words=rows,
        shot_transcript_links=build_shot_transcript_links(
            shot_rows,
            segments,
            rows,
        ),
        asr_status=status,
        policy=policy or _policy(),
    )["s0"]


def test_shared_and_near_boundary_facts() -> None:
    item = _evidence()

    assert item.shared_segment_ids == ("a",)
    assert item.speech_evidence_reliable
    assert item.reliability_reason == "reliable_words_both_sides"
    assert item.shared_segment_crosses_gap
    assert item.near_boundary_speech_continuity
    assert item.left_word_distance_to_boundary_sec == pytest.approx(0.15)
    assert item.right_word_distance_to_boundary_sec == pytest.approx(0.1)
    assert item.inter_word_gap_sec == pytest.approx(0.25)
    assert item.left_segment_coverage == 0.5
    assert item.left_shared_segment_word_count == 1


def test_segment_overlap_without_words_is_not_crossing() -> None:
    item = _evidence(_words()[1:])
    assert not item.shared_segment_crosses_gap
    assert not item.speech_evidence_reliable
    assert item.reliability_reason == "missing_left_aligned_words"


def test_different_segments_can_have_near_speech() -> None:
    item = _evidence(_words(shared=False))

    assert not item.shared_segment_crosses_gap
    assert item.near_boundary_speech_continuity


def test_multiple_shared_segments_are_ordered_and_selected_deterministically() -> None:
    word_rows = [
        {
            "asr_word_id": f"w{index}",
            "asr_segment_id": segment_id,
            "word_index": word_index,
            "text": text,
            "start_sec": start,
            "end_sec": end,
        }
        for index, (segment_id, word_index, text, start, end) in enumerate(
            [
                ("b", 0, "mot", 9.2, 9.4),
                ("a", 0, "hai", 9.6, 9.8),
                ("b", 1, "ba", 10.1, 10.3),
                ("a", 1, "bon", 10.4, 10.6),
            ]
        )
    ]

    item = _evidence(word_rows)

    assert item.shared_segment_ids == ("a", "b")
    assert item.selected_shared_segment_id == "a"
    assert item.left_shared_segment_word_count == 1
    assert item.right_shared_segment_word_count == 1


def test_remote_speech_does_not_imply_near_continuity() -> None:
    assert not _evidence(_words(near=False)).near_boundary_speech_continuity


@pytest.mark.parametrize(
    ("status", "reason"),
    [
        ("no_audio", "video_asr_no_audio"),
        ("no_speech", "video_asr_no_speech"),
        ("low_confidence", "video_asr_low_confidence"),
    ],
)
def test_unreliable_asr_never_asserts_positive_continuity(
    status: str, reason: str
) -> None:
    item = _evidence(status=status)

    assert not item.speech_evidence_reliable
    assert item.reliability_reason == reason
    assert not item.shared_segment_crosses_gap
    assert not item.near_boundary_speech_continuity
    rendered = render_speech_evidence(item)
    assert "CONTINUITY_EVALUATION: NOT_EVALUATED" in rendered
    assert "SHARED_SEGMENT_CROSSES_GAP" not in rendered
    assert "NEAR_BOUNDARY_SPEECH_CONTINUITY" not in rendered


def test_empty_and_disabled_speech() -> None:
    empty = _evidence([])
    assert not empty.near_boundary_speech_continuity
    assert empty.reliability_reason == "missing_both_aligned_words"
    disabled = _evidence(
        policy={**_policy(), "enabled": False}
    )
    assert not disabled.speech_evidence_reliable
    assert disabled.reliability_reason == "disabled"
    rendered = render_speech_evidence(disabled)
    assert "ENABLED: NO" in rendered
    assert "CONTINUITY_EVALUATION: NOT_EVALUATED" in rendered


def test_one_sided_words_are_gap_locally_unreliable() -> None:
    left_only = _evidence(_words()[:1])
    right_only = _evidence(_words()[1:])

    assert left_only.reliability_reason == "missing_right_aligned_words"
    assert right_only.reliability_reason == "missing_left_aligned_words"
    assert not left_only.speech_evidence_reliable
    assert not right_only.speech_evidence_reliable


@pytest.mark.parametrize("value", [0, -1, float("nan"), float("inf"), True])
def test_invalid_threshold(value: object) -> None:
    with pytest.raises(ValueError, match="finite and positive"):
        validate_speech_policy({**_policy(), "max_inter_word_gap_sec": value})


def test_malformed_shot_partition_rejected() -> None:
    shot_rows = _shots()
    shot_rows[1]["start_sec"] += 0.5

    with pytest.raises(ValueError, match="contiguous"):
        build_speech_gap_evidence(
            shots=shot_rows,
            asr_words=_words(),
            shot_transcript_links=[],
            asr_status="pass",
            policy=_policy(),
        )


def test_vfr_pts_partition_assigns_boundary_words_once_and_builds_gap_evidence() -> None:
    timeline = [
        {"frame_id": 0, "pts_time": 0.0, "duration_time": 0.08},
        {"frame_id": 1, "pts_time": 0.05, "duration_time": 0.20},
        {"frame_id": 2, "pts_time": 0.11, "duration_time": 0.04},
        {"frame_id": 3, "pts_time": 0.18, "duration_time": 0.03},
    ]
    shots = scenes_to_shot_rows(
        video_id="v",
        scenes_inclusive=[[0, 1], [2, 3]],
        frame_timeline=timeline,
    )
    words = [
        {
            "asr_word_id": "w0",
            "asr_segment_id": "a",
            "word_index": 0,
            "text": "xin",
            "start_sec": 0.08,
            "end_sec": 0.10,
        },
        {
            "asr_word_id": "w1",
            "asr_segment_id": "a",
            "word_index": 1,
            "text": "chào",
            "start_sec": 0.105,
            "end_sec": 0.125,
        },
    ]
    segments = [{"asr_segment_id": "a", "start_sec": 0.07, "end_sec": 0.14}]
    assignments = assign_words_to_intervals(
        shots,
        words,
        entity_id_field="shot_id",
    )

    assert shots[0]["end_sec"] == shots[1]["start_sec"] == pytest.approx(0.11)
    assert [word["asr_word_id"] for word in assignments[shots[0]["shot_id"]]] == [
        "w0"
    ]
    assert [word["asr_word_id"] for word in assignments[shots[1]["shot_id"]]] == [
        "w1"
    ]
    evidence = build_speech_gap_evidence(
        shots=shots,
        asr_words=words,
        shot_transcript_links=build_shot_transcript_links(shots, segments, words),
        asr_status="pass",
        policy=_policy(),
    )[shots[0]["shot_id"]]
    assert evidence.speech_evidence_reliable
    assert evidence.shared_segment_crosses_gap
    assert evidence.near_boundary_speech_continuity


def test_production_scene_evidence_attaches_exact_gap_speech(
    tmp_path: Path,
) -> None:
    shot_rows = _shots()
    word_rows = _words()
    segment_rows = [
        {"asr_segment_id": "a", "start_sec": 9.0, "end_sec": 11.0}
    ]
    link_rows = build_shot_transcript_links(
        shot_rows,
        segment_rows,
        word_rows,
    )
    keyframes = [
        {
            "keyframe_id": f"v:{index}",
            "shot_id": shot["shot_id"],
            "frame_id": index * 100,
            "keyframe_role": "middle",
            "is_representative": True,
            "keyframe_ref": f"media://keyframes/v/{index}.jpg",
        }
        for index, shot in enumerate(shot_rows)
    ]
    captions = [
        {
            "shot_id": shot["shot_id"],
            "caption_vi": "Một cảnh",
            "caption_en": "A scene",
        }
        for shot in shot_rows
    ]

    scene_evidence = _build_scene_evidence(
        shot_rows,
        keyframes,
        [],
        captions,
        word_rows,
        tmp_path,
        shot_transcript_links=link_rows,
        asr_status="pass",
        speech_policy=_policy(),
    )

    assert scene_evidence[0]["transcript"] == "xin"
    assert scene_evidence[1]["transcript"] == "chào"
    assert scene_evidence[0][
        "speech_to_next_gap"
    ].shared_segment_crosses_gap
    assert scene_evidence[1]["speech_to_next_gap"] is None


@pytest.mark.parametrize(
    "route",
    ["primary", "focused_review", "consistency_review", "degenerate_review"],
)
@pytest.mark.parametrize(
    ("scenario", "label"),
    [
        ("interview question then response", "SAME_SCENE"),
        ("sports wide view then close-up of same play", "SAME_SCENE"),
        ("cooking ingredient then pan during same instruction", "SAME_SCENE"),
        ("documentary factory 1990 then city 2026", "BOUNDARY"),
        ("silent new event", "BOUNDARY"),
    ],
)
def test_all_routes_render_speech_and_preserve_semantic_label(
    tmp_path: Path,
    route: str,
    scenario: str,
    label: str,
) -> None:
    requests_seen = []

    def request_many(requests):
        requests_seen.extend(requests)
        return [{"text": label} for _ in requests]

    image_path = tmp_path / "frame.jpg"
    Image.new("RGB", (16, 16)).save(image_path)
    context = [
        {
            **shot,
            "representative_path": image_path,
            "caption_vi": scenario,
            "transcript": "xin" if index == 0 else "chào",
            "speech_to_next_gap": (
                _evidence(
                    status=("no_speech" if scenario.startswith("silent") else "pass")
                )
                if index == 0
                else None
            ),
        }
        for index, shot in enumerate(_shots())
    ]
    judge = SemanticSceneBoundaryJudge(
        SimpleNamespace(request_many=request_many),
        video_id="v",
        prompt_dir=tmp_path,
        diagnostics_dir=tmp_path / "diag",
        model_config={
            "prompt_version": "scene_boundary_primary_label_v3",
            "focused_prompt_version": "scene_boundary_focused_label_v3",
            "consistency_prompt_version": "scene_boundary_consistency_label_v3",
            "degenerate_prompt_version": "scene_boundary_degenerate_label_v2",
        },
    )

    expected = {"s0": label == "BOUNDARY"}
    assert judge.judge(
        focus_gap_ids=("s0",),
        context=context,
        request_kind=route,
    ) == expected
    prompt = requests_seen[0].prompt
    reliable = not scenario.startswith("silent")
    required_fields = [
        "SPEECH_GAP_EVIDENCE",
        "SPEECH_EVIDENCE_RELIABLE",
        "TARGET_LEFT_SHOT_ID",
        "TARGET_RIGHT_SHOT_ID",
        "ORDERED_CONTEXT",
    ]
    if reliable:
        required_fields.extend(
            (
                "ASR_STATUS",
                "SHARED_SEGMENT_CROSSES_GAP",
                "NEAR_BOUNDARY_SPEECH_CONTINUITY",
                "INTER_WORD_GAP_SEC",
            )
        )
    else:
        required_fields.extend(("RELIABILITY_REASON", "CONTINUITY_EVALUATION"))
        assert "SHARED_SEGMENT_CROSSES_GAP" not in prompt
        assert "NEAR_BOUNDARY_SPEECH_CONTINUITY" not in prompt
    for field in required_fields:
        assert field in prompt
    assert "Speech continuity alone does not prove" in prompt
    assert "documentary/news voice-over" in prompt
    assert "missing ASR is not proof of silence" in prompt
    assert scenario in prompt

    result = group_scenes(
        video_id="v",
        shots=_shots(),
        evidence=context,
        judge=judge,
        config=_grouping_config(),
    )
    assert result.decisions[0].is_boundary == (label == "BOUNDARY")
    diagnostic = asdict(result.decisions[0])
    assert diagnostic["diagnostics_schema_version"] == (
        "scene_boundary_diagnostics_v4"
    )
    assert diagnostic["speech_reliability_reason"] == (
        "video_asr_no_speech" if scenario.startswith("silent")
        else "reliable_words_both_sides"
    )
    assert diagnostic["speech_near_boundary_continuity"] == (
        not scenario.startswith("silent")
    )
