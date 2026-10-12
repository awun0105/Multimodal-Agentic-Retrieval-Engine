"""Durable, asynchronous review of suspicious Phase01 scene partitions."""
from __future__ import annotations

import json
import tempfile
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from system1.artifacts.reports import utc_now
from system1.phase01.checkpoint import checkpoint_root, compute_fingerprint

CANDIDATE_SCHEMA_VERSION = "scene_partition_review_candidate_v1"
DECISION_SCHEMA_VERSION = "scene_partition_manual_review_v1"
DEFAULT_CHECKPOINT_ROOT = "phase01_checkpoints/{release_id}/{video_id}"
_CANDIDATE_FIELDS = {
    "schema_version",
    "candidate_fingerprint",
    "release_id",
    "video_id",
    "scenes_input_fingerprint",
    "scenes_stage_config_hash",
    "grouping_version",
    "decisions",
    "scenes",
    "initial_quality",
    "final_quality",
    "grouping_metadata",
    "created_at",
}
_DECISION_FIELDS = {
    "schema_version",
    "release_id",
    "video_id",
    "candidate_fingerprint",
    "decision",
    "reviewer",
    "reviewed_at",
    "notes",
}


class SceneReviewStore(Protocol):
    def exists(self, relative_path: str | Path) -> bool: ...

    def read_json(self, relative_path: str | Path) -> dict[str, Any]: ...

    def write_json(
        self, relative_path: str | Path, payload: dict[str, Any]
    ) -> Path: ...

    def upload_files(
        self,
        files: Sequence[tuple[Path, str | Path]],
        *,
        commit_message: str,
        num_threads: int = 2,
    ) -> list[Path]: ...

    def list_files(self, prefix: str | Path = "") -> list[Path]: ...


def build_scene_review_candidate(
    *,
    release_id: str,
    video_id: str,
    scenes_input_fingerprint: str,
    scenes_stage_config_hash: str,
    grouping_version: str,
    decisions: Sequence[Mapping[str, Any]],
    scenes: Sequence[Mapping[str, Any]],
    initial_quality: Mapping[str, Any],
    final_quality: Mapping[str, Any],
    grouping_metadata: Mapping[str, Any],
) -> dict[str, Any]:
    stable = {
        "release_id": release_id,
        "video_id": video_id,
        "scenes_input_fingerprint": scenes_input_fingerprint,
        "scenes_stage_config_hash": scenes_stage_config_hash,
        "grouping_version": grouping_version,
        "decisions": sorted(
            (dict(row) for row in decisions), key=lambda row: int(row["gap_index"])
        ),
        "scenes": sorted(
            (dict(row) for row in scenes), key=lambda row: int(row["scene_index"])
        ),
        "initial_quality": dict(initial_quality),
        "final_quality": dict(final_quality),
        "grouping_metadata": dict(grouping_metadata),
    }
    fingerprint = compute_fingerprint(stable)
    return {
        "schema_version": CANDIDATE_SCHEMA_VERSION,
        "candidate_fingerprint": fingerprint,
        **stable,
        "created_at": utc_now(),
    }


def persist_scene_review_candidate(
    store: SceneReviewStore,
    candidate: Mapping[str, Any],
    *,
    evidence_files: Sequence[Path] = (),
    root_template: str = DEFAULT_CHECKPOINT_ROOT,
) -> str:
    _validate_candidate(candidate)
    release_id = str(candidate["release_id"])
    video_id = str(candidate["video_id"])
    fingerprint = str(candidate["candidate_fingerprint"])
    root = _candidate_root(
        release_id, video_id, fingerprint, root_template=root_template
    )
    candidate_ref = root / "candidate.json"
    evidence: list[Path] = []
    seen = {"candidate.json"}
    for source in evidence_files:
        path = Path(source)
        if not path.is_file():
            raise FileNotFoundError(path)
        if path.name in seen:
            raise ValueError("Scene review evidence basenames must be unique")
        seen.add(path.name)
        evidence.append(path)
    if store.exists(candidate_ref):
        existing = store.read_json(candidate_ref)
        _validate_candidate(existing)
        if existing["candidate_fingerprint"] != fingerprint:
            raise ValueError("Stored scene review candidate identity mismatch")
        missing = [path.name for path in evidence if not store.exists(root / path.name)]
        if missing:
            raise ValueError(
                "Stored scene review candidate is missing evidence: "
                + ", ".join(sorted(missing))
            )
        return candidate_ref.as_posix()
    with tempfile.TemporaryDirectory(prefix="phase01_scene_review_") as temp_dir:
        candidate_path = Path(temp_dir) / "candidate.json"
        candidate_path.write_text(
            json.dumps(dict(candidate), ensure_ascii=False, indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        # Candidate JSON is the durable completion marker for stores whose
        # multi-file implementation is sequential rather than transactional.
        uploads = [(path, root / path.name) for path in evidence]
        uploads.append((candidate_path, root / "candidate.json"))
        store.upload_files(
            uploads,
            commit_message=(
                "Persist Phase01 scene review candidate "
                f"{release_id}/{video_id}/{fingerprint}"
            ),
            num_threads=min(2, len(uploads)),
        )
    return candidate_ref.as_posix()


def list_pending_scene_reviews(
    store: SceneReviewStore,
    *,
    release_id: str,
    video_id: str | None = None,
    root_template: str = DEFAULT_CHECKPOINT_ROOT,
) -> list[dict[str, Any]]:
    pending: list[dict[str, Any]] = []
    for path in _candidate_paths(
        store,
        release_id=release_id,
        video_id=video_id,
        root_template=root_template,
    ):
        decision_path = path.parent / "decision.json"
        if store.exists(decision_path):
            continue
        candidate = store.read_json(path)
        _validate_candidate(candidate)
        pending.append(
            {
                "release_id": str(candidate["release_id"]),
                "video_id": str(candidate["video_id"]),
                "candidate_fingerprint": str(candidate["candidate_fingerprint"]),
                "status": "review_required",
                "candidate_ref": path.as_posix(),
                "final_quality": dict(candidate["final_quality"]),
            }
        )
    return sorted(
        pending,
        key=lambda row: (row["video_id"], row["candidate_fingerprint"]),
    )


def get_scene_review_candidate(
    store: SceneReviewStore,
    *,
    release_id: str,
    video_id: str,
    candidate_fingerprint: str,
    root_template: str = DEFAULT_CHECKPOINT_ROOT,
) -> dict[str, Any]:
    path = _candidate_root(
        release_id,
        video_id,
        candidate_fingerprint,
        root_template=root_template,
    ) / "candidate.json"
    candidate = store.read_json(path)
    _validate_candidate(candidate)
    if (
        candidate["release_id"] != release_id
        or candidate["video_id"] != video_id
        or candidate["candidate_fingerprint"] != candidate_fingerprint
    ):
        raise ValueError("Scene review candidate identity mismatch")
    return candidate


def find_scene_review_candidate(
    store: SceneReviewStore,
    *,
    release_id: str,
    video_id: str,
    scenes_input_fingerprint: str,
    scenes_stage_config_hash: str,
    root_template: str = DEFAULT_CHECKPOINT_ROOT,
) -> dict[str, Any] | None:
    candidates: list[tuple[dict[str, Any], dict[str, Any] | None]] = []
    for path in _candidate_paths(
        store,
        release_id=release_id,
        video_id=video_id,
        root_template=root_template,
    ):
        candidate = store.read_json(path)
        _validate_candidate(candidate)
        if (
            candidate["scenes_input_fingerprint"] != scenes_input_fingerprint
            or candidate["scenes_stage_config_hash"] != scenes_stage_config_hash
        ):
            continue
        decision = get_scene_review_decision(
            store,
            release_id=release_id,
            video_id=video_id,
            candidate_fingerprint=str(candidate["candidate_fingerprint"]),
            root_template=root_template,
        )
        candidates.append((candidate, decision))
    if not candidates:
        return None
    approved = [item for item in candidates if item[1] and item[1]["decision"] == "approve"]
    if len(approved) > 1:
        raise ValueError("Multiple approved scene review candidates match one scene input")
    selected = approved[0] if approved else sorted(
        candidates, key=lambda item: str(item[0]["candidate_fingerprint"])
    )[0]
    return {**selected[0], "manual_review_decision": selected[1]}


def get_scene_review_decision(
    store: SceneReviewStore,
    *,
    release_id: str,
    video_id: str,
    candidate_fingerprint: str,
    root_template: str = DEFAULT_CHECKPOINT_ROOT,
) -> dict[str, Any] | None:
    path = _candidate_root(
        release_id,
        video_id,
        candidate_fingerprint,
        root_template=root_template,
    ) / "decision.json"
    if not store.exists(path):
        return None
    decision = store.read_json(path)
    _validate_decision(decision)
    if (
        decision["release_id"] != release_id
        or decision["video_id"] != video_id
        or decision["candidate_fingerprint"] != candidate_fingerprint
    ):
        raise ValueError("Scene review decision identity mismatch")
    return decision


def approve_scene_partition(
    store: SceneReviewStore,
    *,
    release_id: str,
    video_id: str,
    candidate_fingerprint: str,
    reviewer: str,
    notes: str | None = None,
    reviewed_at: str | None = None,
    root_template: str = DEFAULT_CHECKPOINT_ROOT,
) -> dict[str, Any]:
    return _write_decision(
        store,
        release_id=release_id,
        video_id=video_id,
        candidate_fingerprint=candidate_fingerprint,
        decision="approve",
        reviewer=reviewer,
        notes=notes,
        reviewed_at=reviewed_at,
        root_template=root_template,
    )


def reject_scene_partition(
    store: SceneReviewStore,
    *,
    release_id: str,
    video_id: str,
    candidate_fingerprint: str,
    reviewer: str,
    notes: str | None = None,
    reviewed_at: str | None = None,
    root_template: str = DEFAULT_CHECKPOINT_ROOT,
) -> dict[str, Any]:
    return _write_decision(
        store,
        release_id=release_id,
        video_id=video_id,
        candidate_fingerprint=candidate_fingerprint,
        decision="reject",
        reviewer=reviewer,
        notes=notes,
        reviewed_at=reviewed_at,
        root_template=root_template,
    )


def scene_review_decision_ref(
    *,
    release_id: str,
    video_id: str,
    candidate_fingerprint: str,
    root_template: str = DEFAULT_CHECKPOINT_ROOT,
) -> str:
    return (
        _candidate_root(
            release_id,
            video_id,
            candidate_fingerprint,
            root_template=root_template,
        )
        / "decision.json"
    ).as_posix()


def scene_review_candidate_ref(
    *,
    release_id: str,
    video_id: str,
    candidate_fingerprint: str,
    root_template: str = DEFAULT_CHECKPOINT_ROOT,
) -> str:
    return (
        _candidate_root(
            release_id,
            video_id,
            candidate_fingerprint,
            root_template=root_template,
        )
        / "candidate.json"
    ).as_posix()


def _write_decision(
    store: SceneReviewStore,
    *,
    release_id: str,
    video_id: str,
    candidate_fingerprint: str,
    decision: str,
    reviewer: str,
    notes: str | None,
    reviewed_at: str | None,
    root_template: str,
) -> dict[str, Any]:
    get_scene_review_candidate(
        store,
        release_id=release_id,
        video_id=video_id,
        candidate_fingerprint=candidate_fingerprint,
        root_template=root_template,
    )
    payload = {
        "schema_version": DECISION_SCHEMA_VERSION,
        "release_id": release_id,
        "video_id": video_id,
        "candidate_fingerprint": candidate_fingerprint,
        "decision": decision,
        "reviewer": reviewer.strip(),
        "reviewed_at": reviewed_at or utc_now(),
        "notes": notes.strip() if isinstance(notes, str) and notes.strip() else None,
    }
    _validate_decision(payload)
    path = _candidate_root(
        release_id,
        video_id,
        candidate_fingerprint,
        root_template=root_template,
    ) / "decision.json"
    if store.exists(path):
        existing = store.read_json(path)
        _validate_decision(existing)
        comparable = ("decision", "reviewer", "notes")
        if all(existing.get(key) == payload.get(key) for key in comparable):
            return existing
        raise ValueError("Scene review decision is immutable")
    store.write_json(path, payload)
    return payload


def _candidate_paths(
    store: SceneReviewStore,
    *,
    release_id: str,
    video_id: str | None,
    root_template: str,
) -> list[Path]:
    if video_id is not None:
        prefix = checkpoint_root(release_id, video_id, root_template)
    else:
        marker = "__PHASE01_VIDEO__"
        prefix = checkpoint_root(release_id, marker, root_template).parent
    return sorted(
        path
        for path in store.list_files(prefix)
        if path.name == "candidate.json"
        and len(path.parts) >= 3
        and path.parent.parent.name == "scene_partition"
    )


def _candidate_root(
    release_id: str,
    video_id: str,
    candidate_fingerprint: str,
    *,
    root_template: str,
) -> Path:
    _validate_identifier(release_id, "release_id")
    _validate_identifier(video_id, "video_id")
    if len(candidate_fingerprint) != 64 or any(
        char not in "0123456789abcdef" for char in candidate_fingerprint
    ):
        raise ValueError("Scene review candidate fingerprint must be SHA-256 hex")
    return (
        checkpoint_root(release_id, video_id, root_template)
        / "reviews"
        / "scene_partition"
        / candidate_fingerprint
    )


def _validate_candidate(candidate: Mapping[str, Any]) -> None:
    _validate_exact_fields(candidate, _CANDIDATE_FIELDS, "candidate")
    if candidate.get("schema_version") != CANDIDATE_SCHEMA_VERSION:
        raise ValueError("Unsupported scene review candidate schema")
    for field in (
        "release_id",
        "video_id",
        "scenes_input_fingerprint",
        "scenes_stage_config_hash",
        "grouping_version",
        "candidate_fingerprint",
    ):
        if not isinstance(candidate.get(field), str) or not candidate[field]:
            raise ValueError(f"Scene review candidate requires {field}")
    _validate_identifier(str(candidate["release_id"]), "release_id")
    _validate_identifier(str(candidate["video_id"]), "video_id")
    for field in (
        "scenes_input_fingerprint",
        "scenes_stage_config_hash",
        "candidate_fingerprint",
    ):
        value = str(candidate[field])
        if len(value) != 64 or any(
            character not in "0123456789abcdef" for character in value
        ):
            raise ValueError(f"Scene review candidate {field} must be SHA-256 hex")
    created_at = candidate.get("created_at")
    if not isinstance(created_at, str):
        raise ValueError("Scene review candidate requires created_at")
    try:
        parsed = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Scene review candidate created_at must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise ValueError("Scene review candidate created_at must include timezone")
    expected = build_scene_review_candidate(
        release_id=str(candidate["release_id"]),
        video_id=str(candidate["video_id"]),
        scenes_input_fingerprint=str(candidate["scenes_input_fingerprint"]),
        scenes_stage_config_hash=str(candidate["scenes_stage_config_hash"]),
        grouping_version=str(candidate["grouping_version"]),
        decisions=_mapping_sequence(candidate.get("decisions"), "decisions"),
        scenes=_mapping_sequence(candidate.get("scenes"), "scenes"),
        initial_quality=_required_mapping(candidate, "initial_quality"),
        final_quality=_required_mapping(candidate, "final_quality"),
        grouping_metadata=_required_mapping(candidate, "grouping_metadata"),
    )["candidate_fingerprint"]
    if candidate["candidate_fingerprint"] != expected:
        raise ValueError("Scene review candidate fingerprint mismatch")


def _validate_decision(decision: Mapping[str, Any]) -> None:
    _validate_exact_fields(decision, _DECISION_FIELDS, "decision")
    if decision.get("schema_version") != DECISION_SCHEMA_VERSION:
        raise ValueError("Unsupported scene review decision schema")
    if decision.get("decision") not in {"approve", "reject"}:
        raise ValueError("Scene review decision must be approve or reject")
    for field in ("release_id", "video_id", "candidate_fingerprint", "reviewer"):
        if not isinstance(decision.get(field), str) or not decision[field].strip():
            raise ValueError(f"Scene review decision requires non-empty {field}")
    _validate_identifier(str(decision["release_id"]), "release_id")
    _validate_identifier(str(decision["video_id"]), "video_id")
    fingerprint = str(decision["candidate_fingerprint"])
    if len(fingerprint) != 64 or any(
        char not in "0123456789abcdef" for char in fingerprint
    ):
        raise ValueError("Scene review decision fingerprint must be SHA-256 hex")
    reviewed_at = decision.get("reviewed_at")
    if not isinstance(reviewed_at, str):
        raise ValueError("Scene review decision requires reviewed_at")
    try:
        parsed = datetime.fromisoformat(reviewed_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Scene review decision reviewed_at must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise ValueError("Scene review decision reviewed_at must include timezone")
    if decision.get("notes") is not None and not isinstance(decision["notes"], str):
        raise ValueError("Scene review decision notes must be text or null")


def _mapping_sequence(value: Any, field: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, list) or any(not isinstance(row, Mapping) for row in value):
        raise ValueError(f"Scene review candidate {field} must be a list of objects")
    return value


def _required_mapping(candidate: Mapping[str, Any], field: str) -> Mapping[str, Any]:
    value = candidate.get(field)
    if not isinstance(value, Mapping):
        raise ValueError(f"Scene review candidate {field} must be an object")
    return value


def _validate_exact_fields(
    payload: Mapping[str, Any], expected: set[str], record_name: str
) -> None:
    actual = set(payload)
    if actual != expected:
        missing = sorted(expected - actual)
        unexpected = sorted(actual - expected)
        raise ValueError(
            f"Scene review {record_name} fields do not match schema: "
            f"missing={missing}, unexpected={unexpected}"
        )


def _validate_identifier(value: str, field: str) -> None:
    if (
        not value
        or value != value.strip()
        or value in {".", ".."}
        or any(separator in value for separator in ("/", "\\"))
        or any(ord(character) < 32 for character in value)
    ):
        raise ValueError(f"Scene review {field} must be a path-safe identifier")
