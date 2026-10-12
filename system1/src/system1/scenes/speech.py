"""Deterministic speech facts for adjacent shots, never boundary decisions."""
from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from itertools import pairwise
from typing import Any

from system1.asr.links import assign_words_to_intervals

CONTRACT_VERSION = "aligned_speech_continuity_v2"
TIMELINE_EPSILON = 1e-9


@dataclass(frozen=True)
class SpeechGapEvidence:
    contract_version: str
    left_shot_id: str
    right_shot_id: str
    asr_status: str
    speech_evidence_reliable: bool
    reliability_reason: str
    left_aligned_word_count: int
    right_aligned_word_count: int
    shared_segment_ids: tuple[str, ...]
    shared_segment_crosses_gap: bool
    left_last_word_end_sec: float | None
    right_first_word_start_sec: float | None
    left_word_distance_to_boundary_sec: float | None
    right_word_distance_to_boundary_sec: float | None
    inter_word_gap_sec: float | None
    near_boundary_speech_continuity: bool
    selected_shared_segment_id: str | None
    left_shared_segment_word_count: int
    right_shared_segment_word_count: int
    left_segment_coverage: float | None
    right_segment_coverage: float | None


def validate_speech_policy(policy: Mapping[str, Any]) -> None:
    path = "scene_grouping.speech_continuity"
    if not isinstance(policy, Mapping):
        raise TypeError(f"{path} must be a mapping")
    if type(policy.get("enabled")) is not bool:
        raise ValueError(f"{path}.enabled must be bool")
    if policy.get("contract_version") != CONTRACT_VERSION:
        raise ValueError(f"{path}.contract_version is unsupported")
    for field in ("max_boundary_word_distance_sec", "max_inter_word_gap_sec"):
        value = policy.get(field)
        if (
            isinstance(value, bool)
            or not isinstance(value, (float, int))
            or not math.isfinite(value)
            or value <= 0
        ):
            raise ValueError(f"{path}.{field} must be finite and positive")


def build_speech_gap_evidence(
    *,
    shots: Sequence[Mapping[str, Any]],
    asr_words: Sequence[Mapping[str, Any]],
    shot_transcript_links: Sequence[Mapping[str, Any]],
    asr_status: str,
    policy: Mapping[str, Any],
) -> dict[str, SpeechGapEvidence]:
    validate_speech_policy(policy)
    if asr_status not in {"pass", "no_audio", "no_speech", "low_confidence"}:
        raise ValueError(f"Unsupported canonical ASR status: {asr_status}")
    assignments = assign_words_to_intervals(shots, asr_words, entity_id_field="shot_id")
    ids = [str(shot["shot_id"]) for shot in shots]
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate shot IDs in speech evidence")
    links: dict[tuple[str, str], Mapping[str, Any]] = {}
    for row in shot_transcript_links:
        key = (str(row["shot_id"]), str(row["asr_segment_id"]))
        if key in links:
            raise ValueError(
                "Duplicate shot transcript link in speech evidence: "
                f"shot_id={key[0]}, asr_segment_id={key[1]}"
            )
        links[key] = row

    result: dict[str, SpeechGapEvidence] = {}
    for left, right in pairwise(shots):
        boundary = float(left["end_sec"])
        if abs(boundary - float(right["start_sec"])) > TIMELINE_EPSILON:
            raise ValueError("Speech evidence requires contiguous ordered shots")
        left_id = str(left["shot_id"])
        right_id = str(right["shot_id"])
        left_words = assignments[left_id]
        right_words = assignments[right_id]
        reliable, reliability_reason = _gap_reliability(
            enabled=bool(policy["enabled"]),
            asr_status=asr_status,
            left_word_count=len(left_words),
            right_word_count=len(right_words),
        )
        left_segments = {str(w["asr_segment_id"]) for w in left_words}
        right_segments = {str(w["asr_segment_id"]) for w in right_words}
        # Lexical ID order is deterministic; selected ID is only for compact coverage.
        shared = tuple(sorted(left_segments & right_segments)) if reliable else ()
        selected = shared[0] if shared else None
        left_end = max((float(w["end_sec"]) for w in left_words), default=None)
        right_start = min((float(w["start_sec"]) for w in right_words), default=None)
        left_distance = boundary - left_end if left_end is not None else None
        right_distance = right_start - boundary if right_start is not None else None
        gap = (
            right_start - left_end
            if left_end is not None and right_start is not None
            else None
        )
        # Negative distances are valid for words straddling the cut; retain them.
        near = bool(
            reliable
            and gap is not None
            and left_distance <= policy["max_boundary_word_distance_sec"]
            and right_distance <= policy["max_boundary_word_distance_sec"]
            and max(0.0, gap) <= policy["max_inter_word_gap_sec"]
        )
        left_link = links.get((left_id, selected))
        right_link = links.get((right_id, selected))
        result[left_id] = SpeechGapEvidence(
            contract_version=CONTRACT_VERSION,
            left_shot_id=left_id,
            right_shot_id=right_id,
            asr_status=asr_status,
            speech_evidence_reliable=reliable,
            reliability_reason=reliability_reason,
            left_aligned_word_count=len(left_words),
            right_aligned_word_count=len(right_words),
            shared_segment_ids=shared,
            shared_segment_crosses_gap=bool(shared),
            left_last_word_end_sec=left_end,
            right_first_word_start_sec=right_start,
            left_word_distance_to_boundary_sec=left_distance,
            right_word_distance_to_boundary_sec=right_distance,
            inter_word_gap_sec=gap,
            near_boundary_speech_continuity=near,
            selected_shared_segment_id=selected,
            left_shared_segment_word_count=sum(
                str(word["asr_segment_id"]) == selected for word in left_words
            ),
            right_shared_segment_word_count=sum(
                str(word["asr_segment_id"]) == selected for word in right_words
            ),
            left_segment_coverage=(
                float(left_link["segment_coverage"])
                if left_link is not None
                else None
            ),
            right_segment_coverage=(
                float(right_link["segment_coverage"])
                if right_link is not None
                else None
            ),
        )
    return result


def _gap_reliability(
    *,
    enabled: bool,
    asr_status: str,
    left_word_count: int,
    right_word_count: int,
) -> tuple[bool, str]:
    if not enabled:
        return False, "disabled"
    if asr_status != "pass":
        return False, f"video_asr_{asr_status}"
    if left_word_count == 0 and right_word_count == 0:
        return False, "missing_both_aligned_words"
    if left_word_count == 0:
        return False, "missing_left_aligned_words"
    if right_word_count == 0:
        return False, "missing_right_aligned_words"
    return True, "reliable_words_both_sides"


def speech_diagnostics(evidence: SpeechGapEvidence | None) -> dict[str, Any]:
    if evidence is None:
        return {}
    return {
        "speech_contract_version": evidence.contract_version,
        "speech_asr_status": evidence.asr_status,
        "speech_evidence_reliable": evidence.speech_evidence_reliable,
        "speech_reliability_reason": evidence.reliability_reason,
        "speech_left_aligned_word_count": evidence.left_aligned_word_count,
        "speech_right_aligned_word_count": evidence.right_aligned_word_count,
        "speech_shared_segment_crosses_gap": evidence.shared_segment_crosses_gap,
        "speech_shared_segment_ids": evidence.shared_segment_ids,
        "speech_left_word_distance_to_boundary_sec": (
            evidence.left_word_distance_to_boundary_sec
        ),
        "speech_right_word_distance_to_boundary_sec": (
            evidence.right_word_distance_to_boundary_sec
        ),
        "speech_inter_word_gap_sec": evidence.inter_word_gap_sec,
        "speech_near_boundary_continuity": evidence.near_boundary_speech_continuity,
    }


def render_speech_evidence(evidence: SpeechGapEvidence | None) -> str:
    if evidence is None:
        return "SPEECH_GAP_EVIDENCE: <NONE>"
    enabled = evidence.reliability_reason != "disabled"
    if not evidence.speech_evidence_reliable:
        return "\n".join(
            (
                "SPEECH_GAP_EVIDENCE:",
                f"CONTRACT: {evidence.contract_version}",
                f"ENABLED: {'YES' if enabled else 'NO'}",
                "SPEECH_EVIDENCE_RELIABLE: NO",
                f"RELIABILITY_REASON: {evidence.reliability_reason}",
                "CONTINUITY_EVALUATION: NOT_EVALUATED",
            )
        )
    lines = ["SPEECH_GAP_EVIDENCE:"]
    for key, value in asdict(evidence).items():
        if isinstance(value, bool):
            text = "YES" if value else "NO"
        elif value is None:
            text = "<NONE>"
        elif isinstance(value, tuple):
            text = ", ".join(value) or "<NONE>"
        elif isinstance(value, float):
            text = f"{value:.3f}"
        else:
            text = str(value)
        lines.append(f"{key.upper()}: {text}")
    return "\n".join(lines)
