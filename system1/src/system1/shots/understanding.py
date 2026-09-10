from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont, ImageOps

from system1.artifacts.checkpoint import sha256_file
from system1.keyframes.signals import difference_hash, difference_hash_distance

CAPTION_MODES = ("representative_only", "temporal_storyboard")
MEANINGFUL_SUPPLEMENTAL_REASONS = (
    "visual_novelty",
    "text_change",
    "visual_and_text_novelty",
)
RELIABLE_OCR_STATUSES = ("pass", "empty")
PROVENANCE_SCHEMA_VERSION = "shot_caption_field_provenance_v2"


@dataclass(frozen=True)
class ShotCaptionEvidence:
    mode: str
    representative_keyframe_id: str
    source_keyframes: tuple[dict[str, Any], ...]
    image_path: Path
    evidence_body: str
    evidence_fingerprint: str
    trigger_reasons: tuple[str, ...]
    max_visual_change_score: float | None
    max_ocr_change_score: float | None
    temporal_understanding_contract_version: str
    source_selection_policy: str
    storyboard_policy: str
    storyboard_sha256: str | None


@dataclass(frozen=True)
class _Candidate:
    row: dict[str, Any]
    image_path: Path
    image_sha256: str
    visual_hash: Any
    ocr_status: str
    ocr_text: str

    @property
    def keyframe_id(self) -> str:
        return str(self.row["keyframe_id"])

    @property
    def frame_id(self) -> int:
        return int(self.row["frame_id"])

    @property
    def timestamp_sec(self) -> float:
        return float(self.row["timestamp_sec"])


@dataclass(frozen=True)
class _PairSignal:
    left_id: str
    right_id: str
    visual_change: float
    ocr_change: float | None
    crossed_visual: bool
    crossed_ocr: bool

    @property
    def strength(self) -> float:
        return max(self.visual_change, self.ocr_change or 0.0)


def validate_temporal_understanding_policy(value: Any) -> None:
    if not isinstance(value, Mapping):
        raise TypeError("phase01.shot_caption.temporal_understanding must be a mapping")
    expected = {
        "enabled": bool,
        "contract_version": str,
        "mode_policy": str,
        "min_duration_sec": (int, float),
        "max_source_keyframes": int,
        "supplemental_trigger": bool,
        "visual_change": Mapping,
        "ocr_change": Mapping,
        "source_selection_policy": str,
        "storyboard_policy": str,
    }
    for key, expected_type in expected.items():
        if key not in value:
            raise ValueError(f"Missing phase01.shot_caption.temporal_understanding.{key}")
        if not isinstance(value[key], expected_type):
            raise TypeError(
                "Invalid phase01.shot_caption.temporal_understanding."
                f"{key}"
            )
    exact_values = {
        "contract_version": "shot_temporal_understanding_v1",
        "mode_policy": "adaptive_representative_or_storyboard_v1",
        "source_selection_policy": "meaningful_ordered_frames_v1",
        "storyboard_policy": "ordered_temporal_storyboard_v2",
    }
    for key, expected_value in exact_values.items():
        if str(value[key]) != expected_value:
            raise ValueError(
                "Unsupported phase01.shot_caption.temporal_understanding."
                f"{key}: {value[key]}"
            )
    if value["enabled"] is not True:
        raise ValueError("Dynamic shot understanding must be enabled in production")
    if isinstance(value["min_duration_sec"], bool):
        raise TypeError("shot_caption temporal min_duration_sec must be numeric")
    if float(value["min_duration_sec"]) <= 0:
        raise ValueError("shot_caption temporal min_duration_sec must be positive")
    if type(value["max_source_keyframes"]) is not int:
        raise TypeError("shot_caption temporal max_source_keyframes must be an integer")
    if int(value["max_source_keyframes"]) < 2:
        raise ValueError("shot_caption temporal max_source_keyframes must be >= 2")

    visual = value["visual_change"]
    if str(visual.get("policy")) != "dhash_v1":
        raise ValueError("Unsupported shot_caption visual_change.policy")
    hash_size = visual.get("hash_size")
    if type(hash_size) is not int:
        raise TypeError("shot_caption visual_change.hash_size must be an integer")
    if hash_size < 1:
        raise ValueError("shot_caption visual_change.hash_size must be positive")
    _validate_unit_interval(
        visual.get("min_hamming_ratio"),
        "shot_caption visual_change.min_hamming_ratio",
    )

    ocr = value["ocr_change"]
    if str(ocr.get("policy")) != "normalized_token_jaccard_v1":
        raise ValueError("Unsupported shot_caption ocr_change.policy")
    _validate_unit_interval(
        ocr.get("min_jaccard_distance"),
        "shot_caption ocr_change.min_jaccard_distance",
    )


def build_shot_caption_evidence(
    *,
    shot: Mapping[str, Any],
    keyframes: Sequence[Mapping[str, Any]],
    ocr_rows: Sequence[Mapping[str, Any]],
    stage_dir: Path,
    policy: Mapping[str, Any],
) -> ShotCaptionEvidence:
    validate_temporal_understanding_policy(policy)
    shot_id = str(shot["shot_id"])
    ordered_rows = sorted(
        (dict(row) for row in keyframes if str(row["shot_id"]) == shot_id),
        key=lambda row: (float(row["timestamp_sec"]), int(row["frame_id"])),
    )
    representatives = [row for row in ordered_rows if bool(row["is_representative"])]
    if len(representatives) != 1:
        raise ValueError(f"Shot must have exactly one representative keyframe: {shot_id}")
    representative_id = str(representatives[0]["keyframe_id"])
    ocr_by_keyframe = _ocr_rows_by_keyframe(ocr_rows, shot_id=shot_id)
    candidates = tuple(
        _candidate_from_row(
            row,
            stage_dir=stage_dir,
            ocr_row=ocr_by_keyframe.get(str(row["keyframe_id"])),
            hash_size=int(policy["visual_change"]["hash_size"]),
        )
        for row in ordered_rows
    )
    distinct = _deduplicate_candidates(candidates, representative_id=representative_id)
    pair_signals = _pair_signals(distinct, policy)
    max_visual = max((pair.visual_change for pair in pair_signals), default=None)
    reliable_ocr_scores = [
        pair.ocr_change for pair in pair_signals if pair.ocr_change is not None
    ]
    max_ocr = max(reliable_ocr_scores, default=None)
    supplemental_ids = {
        candidate.keyframe_id
        for candidate in distinct
        if str(candidate.row["keyframe_role"]) == "supplemental"
        and str(candidate.row["selection_reason"])
        in MEANINGFUL_SUPPLEMENTAL_REASONS
    }
    crossed_pairs = [
        pair for pair in pair_signals if pair.crossed_visual or pair.crossed_ocr
    ]
    duration = float(shot["end_sec"]) - float(shot["start_sec"])
    trigger_reasons: list[str] = []
    if bool(policy["supplemental_trigger"]) and supplemental_ids:
        trigger_reasons.append("meaningful_supplemental")
    if duration >= float(policy["min_duration_sec"]):
        if any(pair.crossed_visual for pair in pair_signals):
            trigger_reasons.append("visual_change")
        if any(pair.crossed_ocr for pair in pair_signals):
            trigger_reasons.append("ocr_change")

    dynamic = len(distinct) >= 2 and bool(trigger_reasons)
    if dynamic:
        selected = _select_temporal_sources(
            distinct,
            representative_id=representative_id,
            supplemental_ids=supplemental_ids,
            crossed_pairs=crossed_pairs,
            maximum=int(policy["max_source_keyframes"]),
        )
        if len(selected) < 2:
            dynamic = False
    if not dynamic:
        selected = (
            next(item for item in candidates if item.keyframe_id == representative_id),
        )
        trigger_reasons = []

    mode = "temporal_storyboard" if dynamic else "representative_only"
    evidence_body = _render_evidence_body(shot, selected, mode=mode)
    if dynamic:
        image_path = (
            stage_dir
            / "diagnostics"
            / "shot_caption_requests"
            / f"{shot_id}_temporal_storyboard.jpg"
        )
        _write_storyboard(image_path, selected)
    else:
        image_path = selected[0].image_path

    storyboard_sha256 = sha256_file(image_path) if dynamic else None
    fingerprint_payload = {
        "contract_version": str(policy["contract_version"]),
        "mode_policy": str(policy["mode_policy"]),
        "source_selection_policy": str(policy["source_selection_policy"]),
        "storyboard_policy": str(policy["storyboard_policy"]),
        "shot_id": shot_id,
        "shot_start_sec": float(shot["start_sec"]),
        "shot_end_sec": float(shot["end_sec"]),
        "shot_duration_sec": duration,
        "caption_mode": mode,
        "trigger_reasons": trigger_reasons,
        "max_visual_change_score": max_visual,
        "max_ocr_change_score": max_ocr,
        "source_frames": [_candidate_identity(item) for item in selected],
        "evidence_body": evidence_body,
        "storyboard_sha256": storyboard_sha256,
    }
    fingerprint = hashlib.sha256(
        json.dumps(
            fingerprint_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return ShotCaptionEvidence(
        mode=mode,
        representative_keyframe_id=representative_id,
        source_keyframes=tuple(_source_keyframe(item) for item in selected),
        image_path=image_path,
        evidence_body=evidence_body,
        evidence_fingerprint=fingerprint,
        trigger_reasons=tuple(trigger_reasons),
        max_visual_change_score=max_visual,
        max_ocr_change_score=max_ocr,
        temporal_understanding_contract_version=str(policy["contract_version"]),
        source_selection_policy=str(policy["source_selection_policy"]),
        storyboard_policy=str(policy["storyboard_policy"]),
        storyboard_sha256=storyboard_sha256,
    )


def normalized_ocr_token_jaccard_distance(
    left_status: str,
    left_text: str,
    right_status: str,
    right_text: str,
) -> float | None:
    if left_status not in RELIABLE_OCR_STATUSES or right_status not in RELIABLE_OCR_STATUSES:
        return None
    left = _normalized_tokens(left_text)
    right = _normalized_tokens(right_text)
    if not left and not right:
        return 0.0
    if not left or not right:
        return 1.0
    return float(1.0 - len(left & right) / len(left | right))


def _candidate_from_row(
    row: dict[str, Any],
    *,
    stage_dir: Path,
    ocr_row: Mapping[str, Any] | None,
    hash_size: int,
) -> _Candidate:
    image_path = stage_dir / "keyframes" / Path(str(row["keyframe_ref"])).name
    if not image_path.is_file():
        raise FileNotFoundError(f"Missing shot-caption keyframe image: {image_path}")
    status = "unavailable" if ocr_row is None else str(ocr_row.get("status", "unavailable"))
    text = "" if ocr_row is None else str(ocr_row.get("text") or ocr_row.get("raw_text") or "").strip()
    return _Candidate(
        row=row,
        image_path=image_path,
        image_sha256=sha256_file(image_path),
        visual_hash=difference_hash(image_path, hash_size=hash_size),
        ocr_status=status,
        ocr_text=text,
    )


def _ocr_rows_by_keyframe(
    rows: Sequence[Mapping[str, Any]], *, shot_id: str
) -> dict[str, Mapping[str, Any]]:
    output: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        if str(row.get("shot_id")) != shot_id:
            continue
        keyframe_id = str(row["keyframe_id"])
        if keyframe_id in output:
            raise ValueError(f"Duplicate OCR row for keyframe: {keyframe_id}")
        output[keyframe_id] = row
    return output


def _deduplicate_candidates(
    candidates: Sequence[_Candidate], *, representative_id: str
) -> tuple[_Candidate, ...]:
    ordered = sorted(
        candidates,
        key=lambda item: (
            item.keyframe_id != representative_id,
            item.timestamp_sec,
            item.frame_id,
        ),
    )
    kept: list[_Candidate] = []
    identities: set[tuple[str, str, str]] = set()
    for item in ordered:
        reliable_identity = (
            (item.image_sha256, item.ocr_status, item.ocr_text)
            if item.ocr_status in RELIABLE_OCR_STATUSES
            else None
        )
        if reliable_identity is not None and reliable_identity in identities:
            continue
        kept.append(item)
        if reliable_identity is not None:
            identities.add(reliable_identity)
    return tuple(sorted(kept, key=lambda item: (item.timestamp_sec, item.frame_id)))


def _pair_signals(
    candidates: Sequence[_Candidate], policy: Mapping[str, Any]
) -> tuple[_PairSignal, ...]:
    visual_threshold = float(policy["visual_change"]["min_hamming_ratio"])
    ocr_threshold = float(policy["ocr_change"]["min_jaccard_distance"])
    output: list[_PairSignal] = []
    for left, right in pairwise(candidates):
        visual = difference_hash_distance(left.visual_hash, right.visual_hash)
        ocr = normalized_ocr_token_jaccard_distance(
            left.ocr_status,
            left.ocr_text,
            right.ocr_status,
            right.ocr_text,
        )
        output.append(
            _PairSignal(
                left_id=left.keyframe_id,
                right_id=right.keyframe_id,
                visual_change=visual,
                ocr_change=ocr,
                crossed_visual=visual >= visual_threshold,
                crossed_ocr=ocr is not None and ocr >= ocr_threshold,
            )
        )
    return tuple(output)


def _select_temporal_sources(
    candidates: Sequence[_Candidate],
    *,
    representative_id: str,
    supplemental_ids: set[str],
    crossed_pairs: Sequence[_PairSignal],
    maximum: int,
) -> tuple[_Candidate, ...]:
    by_id = {item.keyframe_id: item for item in candidates}
    selected: list[str] = [representative_id]
    endpoint_strength: dict[str, float] = {}
    for pair in crossed_pairs:
        endpoint_strength[pair.left_id] = max(
            endpoint_strength.get(pair.left_id, 0.0), pair.strength
        )
        endpoint_strength[pair.right_id] = max(
            endpoint_strength.get(pair.right_id, 0.0), pair.strength
        )

    def add(keyframe_id: str) -> None:
        if keyframe_id not in selected and len(selected) < maximum:
            selected.append(keyframe_id)

    supplementals = [
        item for item in candidates if item.keyframe_id in supplemental_ids
    ]
    for item in sorted(
        supplementals,
        key=lambda candidate: (
            -endpoint_strength.get(candidate.keyframe_id, 0.0),
            candidate.timestamp_sec,
            candidate.frame_id,
        ),
    ):
        add(item.keyframe_id)
    for pair in sorted(
        crossed_pairs,
        key=lambda item: (
            -item.strength,
            by_id[item.left_id].timestamp_sec,
            by_id[item.left_id].frame_id,
        ),
    ):
        add(pair.left_id)
        add(pair.right_id)

    return tuple(
        sorted(
            (by_id[keyframe_id] for keyframe_id in selected),
            key=lambda item: (item.timestamp_sec, item.frame_id),
        )
    )


def _render_evidence_body(
    shot: Mapping[str, Any], candidates: Sequence[_Candidate], *, mode: str
) -> str:
    lines = [
        f"CAPTION_MODE: {mode}",
        f"SHOT_ID: {shot['shot_id']}",
        f"SHOT_TIME: {float(shot['start_sec']):.6f}-{float(shot['end_sec']):.6f}",
        f"SOURCE_FRAME_COUNT: {len(candidates)}",
        "",
        "ORDERED_SOURCE_FRAMES:",
    ]
    for index, candidate in enumerate(candidates, start=1):
        if candidate.ocr_status == "failed" or candidate.ocr_status == "unavailable":
            ocr_text = "<UNAVAILABLE>"
        elif candidate.ocr_text:
            ocr_text = candidate.ocr_text
        else:
            ocr_text = "<NONE>"
        lines.extend(
            [
                "",
                f"FRAME_{index:02d}",
                f"KEYFRAME_ID: {candidate.keyframe_id}",
                f"TIMESTAMP_SEC: {candidate.timestamp_sec:.6f}",
                f"ROLE: {candidate.row['keyframe_role']}",
                f"OCR_STATUS: {candidate.ocr_status}",
                f"OCR_TEXT: {ocr_text}",
            ]
        )
    return "\n".join(lines)


def _write_storyboard(output: Path, candidates: Sequence[_Candidate]) -> None:
    tile_width = 448
    tile_height = 320
    label_height = 32
    columns = 2 if len(candidates) > 1 else 1
    rows = math.ceil(len(candidates) / columns)
    canvas = Image.new(
        "RGB",
        (columns * tile_width, rows * (tile_height + label_height)),
        color=(24, 24, 24),
    )
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default()
    for index, candidate in enumerate(candidates):
        column = index % columns
        row = index // columns
        x = column * tile_width
        y = row * (tile_height + label_height)
        with Image.open(candidate.image_path) as source:
            contained = ImageOps.contain(
                source.convert("RGB"),
                (tile_width, tile_height),
                method=Image.Resampling.LANCZOS,
            )
        tile = Image.new(
            "RGB",
            (tile_width, tile_height),
            color=(24, 24, 24),
        )
        tile.paste(
            contained,
            (
                (tile_width - contained.width) // 2,
                (tile_height - contained.height) // 2,
            ),
        )
        canvas.paste(tile, (x, y + label_height))
        role = str(candidate.row["keyframe_role"])
        label = f"#{index + 1} {role} {candidate.timestamp_sec:.3f}s"
        draw.text((x + 8, y + 9), label, fill=(255, 255, 255), font=font)
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(
        output,
        format="JPEG",
        quality=90,
        subsampling=0,
        optimize=False,
        progressive=False,
    )


def _source_keyframe(candidate: _Candidate) -> dict[str, Any]:
    return {
        "keyframe_id": candidate.keyframe_id,
        "frame_id": candidate.frame_id,
        "timestamp_sec": candidate.timestamp_sec,
        "keyframe_role": str(candidate.row["keyframe_role"]),
        "is_representative": bool(candidate.row["is_representative"]),
        "selection_reason": str(candidate.row["selection_reason"]),
        "image_sha256": candidate.image_sha256,
        "ocr_status": candidate.ocr_status,
        "ocr_text": candidate.ocr_text,
    }


def _candidate_identity(candidate: _Candidate) -> dict[str, Any]:
    return _source_keyframe(candidate)


def _normalized_tokens(text: str) -> set[str]:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return set(re.findall(r"\w+", normalized, flags=re.UNICODE))


def _validate_unit_interval(value: Any, label: str) -> None:
    if isinstance(value, bool):
        raise TypeError(f"{label} must be numeric")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"{label} must be numeric") from exc
    if not 0.0 <= number <= 1.0:
        raise ValueError(f"{label} must be within [0, 1]")
