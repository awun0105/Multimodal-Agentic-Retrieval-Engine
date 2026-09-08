from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from system1.artifacts.store import ArtifactStore
from system1.phase01.production import (
    _resolve_scene_partition_review,
    _scene_partition_quality_payload,
)
from system1.phase01.review import (
    approve_scene_partition,
    build_scene_review_candidate,
    find_scene_review_candidate,
    get_scene_review_candidate,
    list_pending_scene_reviews,
    persist_scene_review_candidate,
    reject_scene_partition,
)
from system1.scenes import (
    BoundaryDecision,
    SceneGroupingResult,
    ScenePartitionQuality,
)


def _quality(*, suspicious: bool = True) -> ScenePartitionQuality:
    return ScenePartitionQuality(
        shot_count=10,
        gap_count=9,
        scene_count=10 if suspicious else 3,
        boundary_count=9 if suspicious else 2,
        one_shot_scene_count=10 if suspicious else 0,
        boundary_density=1.0 if suspicious else 2 / 9,
        one_shot_scene_rate=1.0 if suspicious else 0.0,
        mean_shots_per_scene=1.0 if suspicious else 10 / 3,
        median_shots_per_scene=1.0 if suspicious else 3.0,
        mean_scene_duration_sec=1.0 if suspicious else 10 / 3,
        median_scene_duration_sec=1.0 if suspicious else 3.0,
        longest_boundary_run=9 if suspicious else 1,
        suspicious=suspicious,
        flags=("all_gaps_are_boundaries",) if suspicious else (),
    )


def _result() -> SceneGroupingResult:
    quality = _quality()
    scenes = [
        {
            "scene_id": f"v_SC{index:05d}",
            "video_id": "v",
            "scene_index": index,
            "start_shot_id": f"v_SH{index:05d}",
            "end_shot_id": f"v_SH{index:05d}",
            "start_frame": index,
            "end_frame": index + 1,
            "start_sec": float(index),
            "end_sec": float(index + 1),
            "duration_sec": 1.0,
            "frame_count": 1,
            "shot_count": 1,
            "keyframe_count": 0,
            "scene_type": "semantic",
            "grouping_method": "multimodal_context_focus",
            "grouping_version": "scene_grouping_v4",
            "confidence": None,
            "boundary_convention": "[start_frame, end_frame)",
            "status": "pass",
        }
        for index in range(10)
    ]
    decisions = [
        BoundaryDecision(
            gap_index=index,
            after_shot_id=f"v_SH{index:05d}",
            is_boundary=True,
            primary_boundary_score=1.0,
            vote_count=1,
            true_vote_weight=1.0,
            false_vote_weight=0.0,
            review_route="degenerate_review",
            consistency_review_triggered=True,
            degenerate_review_triggered=True,
        )
        for index in range(9)
    ]
    return SceneGroupingResult(
        scenes=scenes,
        decisions=decisions,
        initial_quality=quality,
        final_quality=quality,
        consistency_review_rounds_run=1,
        degenerate_review_triggered=True,
        degenerate_review_rounds_run=1,
    )


def _candidate(**overrides: str) -> dict:
    result = _result()
    values = {
        "release_id": "release",
        "video_id": "v",
        "scenes_input_fingerprint": "a" * 64,
        "scenes_stage_config_hash": "b" * 64,
        "grouping_version": "scene_grouping_v4",
    }
    values.update(overrides)
    return build_scene_review_candidate(
        **values,
        decisions=[decision.__dict__ for decision in result.decisions],
        scenes=result.scenes,
        initial_quality=result.initial_quality.__dict__,
        final_quality=result.final_quality.__dict__,
        grouping_metadata={
            "consistency_review_rounds_run": 1,
            "degenerate_review_triggered": True,
            "degenerate_review_rounds_run": 1,
        },
    )


def _persist(store: ArtifactStore, candidate: dict, tmp_path: Path) -> None:
    quality = tmp_path / "scene_partition_quality.json"
    diagnostics = tmp_path / "scene_boundary_diagnostics.jsonl"
    quality.write_text("{}\n", encoding="utf-8")
    diagnostics.write_text("{}\n", encoding="utf-8")
    persist_scene_review_candidate(
        store,
        candidate,
        evidence_files=[quality, diagnostics],
    )


def test_candidate_fingerprint_is_stable_and_excludes_creation_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    timestamps = iter(("2026-09-08T10:00:00Z", "2026-09-08T11:00:00Z"))
    monkeypatch.setattr(
        "system1.phase01.review.utc_now",
        lambda: next(timestamps),
    )
    first = _candidate()
    second = _candidate()

    assert first["created_at"] != second["created_at"]
    assert first["candidate_fingerprint"] == second["candidate_fingerprint"]


def test_pending_candidate_can_be_listed_and_read(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path / "store")
    candidate = _candidate()
    _persist(store, candidate, tmp_path)

    pending = list_pending_scene_reviews(store, release_id="release")

    assert [row["candidate_fingerprint"] for row in pending] == [
        candidate["candidate_fingerprint"]
    ]
    loaded = get_scene_review_candidate(
        store,
        release_id="release",
        video_id="v",
        candidate_fingerprint=candidate["candidate_fingerprint"],
    )
    assert loaded["scenes"] == candidate["scenes"]


def test_existing_candidate_requires_complete_review_evidence(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path / "store")
    candidate = _candidate()
    _persist(store, candidate, tmp_path)
    diagnostics = next(
        path
        for path in store.list_files()
        if path.name == "scene_boundary_diagnostics.jsonl"
    )
    store.path(diagnostics).unlink()
    quality = tmp_path / "scene_partition_quality.json"
    boundary = tmp_path / "scene_boundary_diagnostics.jsonl"

    with pytest.raises(ValueError, match="missing evidence"):
        persist_scene_review_candidate(
            store,
            candidate,
            evidence_files=[quality, boundary],
        )


def test_exact_approval_is_immutable_and_removes_pending_candidate(
    tmp_path: Path,
) -> None:
    store = ArtifactStore(tmp_path / "store")
    candidate = _candidate()
    _persist(store, candidate, tmp_path)

    decision = approve_scene_partition(
        store,
        release_id="release",
        video_id="v",
        candidate_fingerprint=candidate["candidate_fingerprint"],
        reviewer="reviewer@example.com",
        reviewed_at="2026-09-08T10:00:00Z",
        notes="Rapid montage is semantically correct.",
    )

    assert decision["decision"] == "approve"
    assert list_pending_scene_reviews(store, release_id="release") == []
    assert approve_scene_partition(
        store,
        release_id="release",
        video_id="v",
        candidate_fingerprint=candidate["candidate_fingerprint"],
        reviewer="reviewer@example.com",
        notes="Rapid montage is semantically correct.",
    ) == decision
    with pytest.raises(ValueError, match="immutable"):
        reject_scene_partition(
            store,
            release_id="release",
            video_id="v",
            candidate_fingerprint=candidate["candidate_fingerprint"],
            reviewer="other@example.com",
        )


@pytest.mark.parametrize("reviewer", ["", "   "])
def test_manual_decision_rejects_empty_reviewer(
    tmp_path: Path, reviewer: str
) -> None:
    store = ArtifactStore(tmp_path / "store")
    candidate = _candidate()
    _persist(store, candidate, tmp_path)

    with pytest.raises(ValueError, match="reviewer"):
        approve_scene_partition(
            store,
            release_id="release",
            video_id="v",
            candidate_fingerprint=candidate["candidate_fingerprint"],
            reviewer=reviewer,
        )


def test_manual_decision_rejects_timezone_less_review_time(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path / "store")
    candidate = _candidate()
    _persist(store, candidate, tmp_path)

    with pytest.raises(ValueError, match="timezone"):
        approve_scene_partition(
            store,
            release_id="release",
            video_id="v",
            candidate_fingerprint=candidate["candidate_fingerprint"],
            reviewer="reviewer",
            reviewed_at="2026-09-08T10:00:00",
        )


def test_stale_approval_does_not_match_changed_scene_input(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path / "store")
    candidate = _candidate()
    _persist(store, candidate, tmp_path)
    approve_scene_partition(
        store,
        release_id="release",
        video_id="v",
        candidate_fingerprint=candidate["candidate_fingerprint"],
        reviewer="reviewer",
    )

    assert find_scene_review_candidate(
        store,
        release_id="release",
        video_id="v",
        scenes_input_fingerprint="c" * 64,
        scenes_stage_config_hash="b" * 64,
    ) is None


def test_reject_is_a_durable_non_pending_disposition(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path / "store")
    candidate = _candidate()
    _persist(store, candidate, tmp_path)

    reject_scene_partition(
        store,
        release_id="release",
        video_id="v",
        candidate_fingerprint=candidate["candidate_fingerprint"],
        reviewer="reviewer",
    )
    found = find_scene_review_candidate(
        store,
        release_id="release",
        video_id="v",
        scenes_input_fingerprint="a" * 64,
        scenes_stage_config_hash="b" * 64,
    )

    assert found is not None
    assert found["manual_review_decision"]["decision"] == "reject"
    assert list_pending_scene_reviews(store, release_id="release") == []


def test_review_resolution_resumes_only_after_exact_approval(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path / "store")
    manager = SimpleNamespace(store=store, release_id="release")
    config = SimpleNamespace(
        payload={
            "artifact": {
                "checkpoint": {
                    "root": "phase01_checkpoints/{release_id}/{video_id}"
                }
            }
        },
        stage_config_hashes={"scenes": "b" * 64},
    )
    result = _result()
    quality_path = tmp_path / "scene_partition_quality.json"
    diagnostics_path = tmp_path / "scene_boundary_diagnostics.jsonl"
    diagnostics_path.write_text("{}\n", encoding="utf-8")
    payload = _scene_partition_quality_payload(
        video_id="v",
        result=result,
        policy={
            "enabled": True,
            "min_shot_count": 8,
            "suspicious_boundary_density": 0.9,
            "suspicious_one_shot_scene_rate": 0.8,
            "unresolved_action": "review_required",
        },
    )

    review_result, pending_quality = _resolve_scene_partition_review(
        manager=manager,
        config=config,
        video_id="v",
        scenes_fingerprint="a" * 64,
        grouping_result=result,
        quality_payload=payload,
        scene_quality_path=quality_path,
        scene_diagnostics_path=diagnostics_path,
    )
    assert review_result["status"] == "review_required"
    approve_scene_partition(
        store,
        release_id="release",
        video_id="v",
        candidate_fingerprint=pending_quality["candidate_fingerprint"],
        reviewer="reviewer",
    )

    review_result, approved_quality = _resolve_scene_partition_review(
        manager=manager,
        config=config,
        video_id="v",
        scenes_fingerprint="a" * 64,
        grouping_result=result,
        quality_payload=payload,
        scene_quality_path=quality_path,
        scene_diagnostics_path=diagnostics_path,
    )

    assert review_result is None
    assert approved_quality["status"] == "pass_after_manual_review"
    assert approved_quality["final"]["suspicious"] is True
    assert approved_quality["manual_review"]["decision"] == "approve"


def test_review_resolution_surfaces_rejection_without_promoting(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path / "store")
    manager = SimpleNamespace(store=store, release_id="release")
    config = SimpleNamespace(
        payload={
            "artifact": {
                "checkpoint": {
                    "root": "phase01_checkpoints/{release_id}/{video_id}"
                }
            }
        },
        stage_config_hashes={"scenes": "b" * 64},
    )
    result = _result()
    quality_path = tmp_path / "scene_partition_quality.json"
    diagnostics_path = tmp_path / "scene_boundary_diagnostics.jsonl"
    diagnostics_path.write_text("{}\n", encoding="utf-8")
    payload = _scene_partition_quality_payload(
        video_id="v",
        result=result,
        policy={
            "enabled": True,
            "min_shot_count": 8,
            "suspicious_boundary_density": 0.9,
            "suspicious_one_shot_scene_rate": 0.8,
            "unresolved_action": "review_required",
        },
    )
    pending, pending_quality = _resolve_scene_partition_review(
        manager=manager,
        config=config,
        video_id="v",
        scenes_fingerprint="a" * 64,
        grouping_result=result,
        quality_payload=payload,
        scene_quality_path=quality_path,
        scene_diagnostics_path=diagnostics_path,
    )
    reject_scene_partition(
        store,
        release_id="release",
        video_id="v",
        candidate_fingerprint=pending_quality["candidate_fingerprint"],
        reviewer="reviewer",
    )

    rejected, rejected_quality = _resolve_scene_partition_review(
        manager=manager,
        config=config,
        video_id="v",
        scenes_fingerprint="a" * 64,
        grouping_result=result,
        quality_payload=payload,
        scene_quality_path=quality_path,
        scene_diagnostics_path=diagnostics_path,
    )

    assert pending["status"] == "review_required"
    assert rejected["status"] == "review_rejected"
    assert rejected["review_status"] == "rejected"
    assert rejected_quality["review_disposition"] == "rejected"


def test_candidate_tampering_is_detected(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path / "store")
    candidate = _candidate()
    _persist(store, candidate, tmp_path)
    path = next(path for path in store.list_files() if path.name == "candidate.json")
    payload = store.read_json(path)
    payload["scenes"][0]["end_sec"] = 999.0
    store.write_json(path, payload)

    with pytest.raises(ValueError, match="fingerprint mismatch"):
        get_scene_review_candidate(
            store,
            release_id="release",
            video_id="v",
            candidate_fingerprint=candidate["candidate_fingerprint"],
        )
