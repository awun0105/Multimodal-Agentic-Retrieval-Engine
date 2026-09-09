from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from system1.asr.links import build_interval_transcript


SPEECH_EVIDENCE_STATUSES = ("available", "no_speech", "unavailable")
MODEL_AUDIO_VISUAL_RELATIONS = (
    "aligned",
    "complementary",
    "partial",
    "b_roll",
    "unrelated",
    "contradictory",
)
AUDIO_VISUAL_RELATIONS = (
    *MODEL_AUDIO_VISUAL_RELATIONS,
    "no_speech",
    "speech_unavailable",
)


@dataclass(frozen=True)
class SpeechSummaryEvidence:
    status: str
    transcript: str
    body: str
    fingerprint: str
    words: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class VisualSummaryEvidence:
    body: str
    fingerprint: str
    image_paths: tuple[Path, ...]
    image_shots: tuple[dict[str, Any], ...]
    evidence_shots: tuple[dict[str, Any], ...]


def validate_scene_summary_policy(policy: Mapping[str, Any] | None) -> None:
    if not isinstance(policy, Mapping):
        raise TypeError("Phase01 scene_summary must be a mapping")
    expected = {
        "contract_version": "adaptive_scene_summary_v1",
        "image_sampling": "evenly_spaced_shots",
        "visual_overflow_policy": "evenly_spaced_complete_blocks_v1",
        "relation_contract_version": "audio_visual_relation_v1",
        "no_reliable_speech_policy": "visual_only_v1",
    }
    for field, value in expected.items():
        if str(policy.get(field)) != value:
            raise ValueError(f"Unsupported Phase01 scene_summary.{field}")
    for field in (
        "max_representative_images",
        "max_shot_evidence_items",
        "max_ocr_chars_per_shot",
        "max_visual_evidence_chars",
        "max_transcript_chars",
    ):
        if int(policy.get(field, 0)) < 1:
            raise ValueError(f"Phase01 scene_summary.{field} must be positive")
    if "max_total_evidence_chars" in policy:
        raise ValueError(
            "Phase01 scene_summary.max_total_evidence_chars is incompatible "
            "with modality-specific evidence budgets"
        )


def classify_speech_evidence_status(
    *, asr_status: str, assigned_words: Sequence[Mapping[str, Any]]
) -> str:
    normalized = str(asr_status).strip()
    if normalized in {"no_audio", "no_speech"}:
        return "no_speech"
    if normalized == "low_confidence":
        return "unavailable"
    if normalized == "pass":
        return "available" if assigned_words else "unavailable"
    raise ValueError(f"Unsupported canonical ASR status for scene summary: {asr_status}")


def build_speech_summary_evidence(
    *,
    scene: Mapping[str, Any],
    assigned_words: Sequence[Mapping[str, Any]],
    asr_status: str,
    scene_links: Sequence[Mapping[str, Any]],
    policy: Mapping[str, Any],
) -> SpeechSummaryEvidence:
    status = classify_speech_evidence_status(
        asr_status=asr_status,
        assigned_words=assigned_words,
    )
    ordered_words = sorted(assigned_words, key=_word_sort_key)
    included_words = (
        _bound_complete_words(
            ordered_words,
            max_chars=int(policy["max_transcript_chars"]),
        )
        if status == "available"
        else []
    )
    if status == "available" and not included_words:
        raise ValueError("Available scene speech cannot be empty after budgeting")
    transcript = build_interval_transcript(included_words)
    scene_id = str(scene["scene_id"])
    body = (
        f"SCENE_ID: {scene_id}\n"
        f"TIME: {float(scene['start_sec']):.3f}-{float(scene['end_sec']):.3f}\n"
        "CANONICAL_TRANSCRIPT:\n"
        + (transcript or "<UNAVAILABLE>")
    )
    relevant_links = sorted(
        (
            {
                key: row.get(key)
                for key in (
                    "asr_segment_id",
                    "overlap_start_sec",
                    "overlap_end_sec",
                    "overlap_sec",
                    "segment_coverage",
                    "entity_coverage",
                    "assigned_word_count",
                )
            }
            for row in scene_links
            if str(row.get("scene_id")) == scene_id
        ),
        key=lambda row: str(row.get("asr_segment_id")),
    )
    identity = {
        "contract_version": str(policy["contract_version"]),
        "budget_chars": int(policy["max_transcript_chars"]),
        "scene_id": scene_id,
        "speech_evidence_status": status,
        "asr_status": str(asr_status),
        "words": [
            {
                "asr_word_id": str(word["asr_word_id"]),
                "asr_segment_id": str(word["asr_segment_id"]),
                "text": str(word["text"]),
                "start_sec": float(word["start_sec"]),
                "end_sec": float(word["end_sec"]),
            }
            for word in included_words
        ],
        "transcript": transcript,
        "scene_links": relevant_links,
    }
    return SpeechSummaryEvidence(
        status=status,
        transcript=transcript,
        body=body,
        fingerprint=_sha256_json(identity),
        words=tuple(dict(word) for word in included_words),
    )


def build_visual_summary_evidence(
    *,
    scene: Mapping[str, Any],
    scene_shots: Sequence[Mapping[str, Any]],
    representative: Mapping[str, Mapping[str, Any]],
    keyframes_by_shot: Mapping[str, Sequence[Mapping[str, Any]]],
    captions_by_shot: Mapping[str, Mapping[str, Any]],
    ocr_by_keyframe: Mapping[str, str],
    stage_dir: Path,
    policy: Mapping[str, Any],
) -> VisualSummaryEvidence:
    if not scene_shots:
        raise ValueError(f"Scene has no shots: {scene['scene_id']}")
    scene_id = str(scene["scene_id"])
    image_shots = _evenly_sample(
        scene_shots,
        int(policy["max_representative_images"]),
    )
    image_paths: list[Path] = []
    image_identity: list[dict[str, Any]] = []
    for shot in image_shots:
        shot_id = str(shot["shot_id"])
        keyframe = representative.get(shot_id)
        if keyframe is None:
            raise ValueError(f"Shot has no representative keyframe: {shot_id}")
        image_path = (
            stage_dir
            / "keyframes"
            / Path(str(keyframe["keyframe_ref"])).name
        )
        if not image_path.is_file():
            raise FileNotFoundError(f"Missing representative image: {image_path}")
        image_paths.append(image_path)
        image_identity.append(
            {
                "shot_id": shot_id,
                "keyframe_id": str(keyframe["keyframe_id"]),
                "timestamp_sec": float(keyframe["timestamp_sec"]),
                "image_sha256": hashlib.sha256(image_path.read_bytes()).hexdigest(),
            }
        )

    maximum_blocks = min(
        len(scene_shots),
        int(policy["max_shot_evidence_items"]),
    )
    header = (
        f"SCENE_ID: {scene_id}\n"
        f"TIME: {float(scene['start_sec']):.3f}-{float(scene['end_sec']):.3f}\n"
        "ORDERED_VISUAL_PROGRESSION:\n"
    )
    max_chars = int(policy["max_visual_evidence_chars"])
    selected: list[Mapping[str, Any]] = []
    rendered_blocks: list[str] = []
    for count in range(maximum_blocks, 0, -1):
        candidates = _evenly_sample(scene_shots, count)
        blocks = [
            _render_visual_shot_block(
                shot,
                captions_by_shot[str(shot["shot_id"])],
                ocr_text=_shot_ocr_text(
                    str(shot["shot_id"]),
                    keyframes_by_shot,
                    ocr_by_keyframe,
                ),
                max_ocr_chars=int(policy["max_ocr_chars_per_shot"]),
            )
            for shot in candidates
        ]
        body = header + "\n\n".join(blocks)
        if len(body) <= max_chars:
            selected = list(candidates)
            rendered_blocks = blocks
            break
    if not rendered_blocks:
        selected = [scene_shots[len(scene_shots) // 2]]
        available = max_chars - len(header)
        if available < 80:
            raise ValueError(
                "Phase01 scene_summary.max_visual_evidence_chars is too small "
                "to retain a traceable shot block"
            )
        shot = selected[0]
        rendered_blocks = [
            _render_compact_visual_shot_block(
                shot,
                captions_by_shot[str(shot["shot_id"])],
                ocr_text=_shot_ocr_text(
                    str(shot["shot_id"]),
                    keyframes_by_shot,
                    ocr_by_keyframe,
                ),
                max_chars=available,
            )
        ]
    body = header + "\n\n".join(rendered_blocks)
    if len(body) > max_chars:
        raise ValueError("Visual evidence budget failed to retain a complete shot block")

    identity = {
        "contract_version": str(policy["contract_version"]),
        "overflow_policy": str(policy["visual_overflow_policy"]),
        "budget_chars": max_chars,
        "scene_id": scene_id,
        "selected_shot_ids": [str(shot["shot_id"]) for shot in selected],
        "images": image_identity,
        "rendered_evidence": body,
    }
    return VisualSummaryEvidence(
        body=body,
        fingerprint=_sha256_json(identity),
        image_paths=tuple(image_paths),
        image_shots=tuple(dict(shot) for shot in image_shots),
        evidence_shots=tuple(dict(shot) for shot in selected),
    )


def normalize_audio_visual_relation(value: Any) -> str:
    relation = str(value).strip().lower()
    if relation not in MODEL_AUDIO_VISUAL_RELATIONS:
        raise ValueError(f"Invalid model-generated audio-visual relation: {value!r}")
    return relation


def validate_scene_summary_semantics(row: Mapping[str, Any]) -> None:
    status = str(row.get("speech_evidence_status"))
    relation = str(row.get("audio_visual_relation"))
    if status not in SPEECH_EVIDENCE_STATUSES:
        raise ValueError("Invalid scene summary speech_evidence_status")
    if relation not in AUDIO_VISUAL_RELATIONS:
        raise ValueError("Invalid scene summary audio_visual_relation")
    for field in ("speech_evidence_fingerprint", "visual_evidence_fingerprint"):
        value = str(row.get(field, ""))
        if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
            raise ValueError(f"Invalid scene summary {field}")
    speech_vi = row.get("speech_summary_vi")
    speech_en = row.get("speech_summary_en")
    if status == "available":
        if relation not in MODEL_AUDIO_VISUAL_RELATIONS:
            raise ValueError("Available speech requires a model audio-visual relation")
        if not str(speech_vi or "").strip() or not str(speech_en or "").strip():
            raise ValueError("Available speech requires bilingual speech summaries")
    else:
        expected_relation = "no_speech" if status == "no_speech" else "speech_unavailable"
        if relation != expected_relation:
            raise ValueError(f"{status} speech requires relation {expected_relation}")
        if speech_vi is not None or speech_en is not None:
            raise ValueError(f"{status} speech summaries must be null")
        if row.get("summary_vi") != row.get("visual_summary_vi"):
            raise ValueError("Visual-only Vietnamese final summary must be a deterministic copy")
        if row.get("summary_en") != row.get("visual_summary_en"):
            raise ValueError("Visual-only English final summary must be a deterministic copy")


def _bound_complete_words(
    words: Sequence[Mapping[str, Any]], *, max_chars: int
) -> list[Mapping[str, Any]]:
    selected: list[Mapping[str, Any]] = []
    length = 0
    for word in words:
        text = str(word.get("text", "")).strip()
        if not text:
            continue
        added = len(text) + (1 if selected else 0)
        if length + added > max_chars:
            break
        selected.append(word)
        length += added
    return selected


def _render_visual_shot_block(
    shot: Mapping[str, Any],
    caption: Mapping[str, Any],
    *,
    ocr_text: str,
    max_ocr_chars: int,
) -> str:
    return "\n".join(
        (
            "--- SHOT ---",
            f"SHOT_ID: {shot['shot_id']}",
            f"TIME: {float(shot['start_sec']):.3f}-{float(shot['end_sec']):.3f}",
            f"CAPTION_VI: {caption['caption_vi']}",
            f"CAPTION_EN: {caption['caption_en']}",
            "OBJECTS_VI: " + " | ".join(_string_list(caption.get("objects_vi"))),
            "OBJECTS_EN: " + " | ".join(_string_list(caption.get("objects_en"))),
            "ACTIONS_VI: " + " | ".join(_string_list(caption.get("actions_vi"))),
            "ACTIONS_EN: " + " | ".join(_string_list(caption.get("actions_en"))),
            "VISIBLE_TEXT_VI: " + str(caption.get("visible_text_summary_vi") or ""),
            "VISIBLE_TEXT_EN: " + str(caption.get("visible_text_summary_en") or ""),
            "OCR: " + (_bounded_text(ocr_text, max_chars=max_ocr_chars) or "<NONE>"),
        )
    )


def _render_compact_visual_shot_block(
    shot: Mapping[str, Any],
    caption: Mapping[str, Any],
    *,
    ocr_text: str,
    max_chars: int,
) -> str:
    lines = [
        "--- SHOT ---",
        f"SHOT_ID: {shot['shot_id']}",
        f"TIME: {float(shot['start_sec']):.3f}-{float(shot['end_sec']):.3f}",
    ]
    optional = (
        ("CAPTION_VI", caption.get("caption_vi")),
        ("ACTIONS_VI", " | ".join(_string_list(caption.get("actions_vi")))),
        ("CAPTION_EN", caption.get("caption_en")),
        ("ACTIONS_EN", " | ".join(_string_list(caption.get("actions_en")))),
        ("VISIBLE_TEXT_VI", caption.get("visible_text_summary_vi")),
        ("OCR", ocr_text),
    )
    for label, raw in optional:
        value = str(raw or "").strip()
        if not value:
            continue
        used = len("\n".join(lines))
        remaining = max_chars - used - len(label) - 3
        if remaining < 1:
            break
        lines.append(f"{label}: {_bounded_text(value, max_chars=remaining)}")
    return "\n".join(lines)


def _shot_ocr_text(
    shot_id: str,
    keyframes_by_shot: Mapping[str, Sequence[Mapping[str, Any]]],
    ocr_by_keyframe: Mapping[str, str],
) -> str:
    return " ".join(
        text
        for row in sorted(
            keyframes_by_shot.get(shot_id, ()),
            key=lambda value: (float(value["timestamp_sec"]), str(value["keyframe_id"])),
        )
        if (text := str(ocr_by_keyframe.get(str(row["keyframe_id"]), "")).strip())
    )


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if value is None:
        return []
    if not isinstance(value, (list, tuple)) and hasattr(value, "tolist"):
        value = value.tolist()
    if not isinstance(value, (list, tuple)):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _bounded_text(value: Any, *, max_chars: int) -> str:
    if max_chars < 1:
        raise ValueError("text evidence limit must be positive")
    text = str(value or "").strip()
    if len(text) <= max_chars:
        return text
    marker = "[TRUNCATED]"
    if max_chars <= len(marker):
        return text[:max_chars]
    return text[: max_chars - len(marker)].rstrip() + marker


def _evenly_sample(
    rows: Sequence[Mapping[str, Any]], maximum: int
) -> list[Mapping[str, Any]]:
    if maximum < 1:
        raise ValueError("Scene summary sampling limit must be positive")
    if len(rows) <= maximum:
        return list(rows)
    indices = (
        sorted(
            {
                round(position * (len(rows) - 1) / (maximum - 1))
                for position in range(maximum)
            }
        )
        if maximum > 1
        else [len(rows) // 2]
    )
    return [rows[index] for index in indices]


def _word_sort_key(row: Mapping[str, Any]) -> tuple[float, float, str, int]:
    return (
        float(row["start_sec"]),
        float(row["end_sec"]),
        str(row["asr_segment_id"]),
        int(row["word_index"]),
    )


def _sha256_json(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
