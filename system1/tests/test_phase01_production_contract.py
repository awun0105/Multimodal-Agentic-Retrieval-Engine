from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
from PIL import Image
from typer.testing import CliRunner

from system1.cli import app
from system1.config import (
    load_configs,
    persist_resolved_phase01_config,
    require_phase01_production_ready,
    resolve_phase01_config,
)
from system1.config.loader import _stage_config_hashes
from system1.phase01.production import (
    PARQUET_COLUMNS,
    _assemble_package,
    _build_captions,
    _build_scene_summaries,
    _checkpoint_error_payload,
    _keyframe_diagnostic_counts,
    _normalize_required_text,
    _require_scene_partition_quality,
    _required_text,
    _retryable_video_error,
    _scene_partition_quality_payload,
)
from system1.phase01.runner import _build_runtime_diagnostics
from system1.phase01.validation import (
    _validate_scene_partition_quality_report,
    validate_rows,
)
from system1.scenes import (
    SceneGroupingResult,
    ScenePartitionQuality,
    ScenePartitionQualityError,
)

SYSTEM1_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = SYSTEM1_ROOT / "configs"
SCHEMA_DIR = SYSTEM1_ROOT / "schemas"


def user_settings(**overrides: object) -> dict[str, object]:
    settings: dict[str, object] = {
        "batch_id": "batch_000",
        "worker_id": "worker_001",
        "hf_release_repo": "org/release",
    }
    settings.update(overrides)
    return settings


def _quality_metrics(*, shot_count: int = 1, scene_count: int = 1) -> dict:
    return {
        "shot_count": shot_count,
        "gap_count": max(0, shot_count - 1),
        "scene_count": scene_count,
        "boundary_count": max(0, scene_count - 1),
        "one_shot_scene_count": scene_count if shot_count == scene_count else 0,
        "boundary_density": 0.0 if shot_count == 1 else (scene_count - 1) / (shot_count - 1),
        "one_shot_scene_rate": 1.0 if shot_count == scene_count else 0.0,
        "mean_shots_per_scene": shot_count / scene_count,
        "median_shots_per_scene": shot_count / scene_count,
        "longest_boundary_run": max(0, scene_count - 1),
        "suspicious": False,
        "flags": [],
    }


def _passing_scene_quality_report(
    video_id: str,
    *,
    shot_count: int = 1,
    scene_count: int = 1,
) -> dict:
    metrics = _quality_metrics(shot_count=shot_count, scene_count=scene_count)
    return {
        "schema_version": "scene_partition_quality_v1",
        "video_id": video_id,
        "status": "pass",
        "guard_enabled": True,
        "consistency_review_rounds_run": 0,
        "degenerate_review_triggered": False,
        "degenerate_review_rounds_run": 0,
        "policy": {
            "min_shot_count": 8,
            "suspicious_boundary_density": 0.9,
            "suspicious_one_shot_scene_rate": 0.8,
            "unresolved_action": "fail_terminal",
        },
        "initial": dict(metrics),
        "final": dict(metrics),
    }


def _scene_quality(*, suspicious: bool) -> ScenePartitionQuality:
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
        longest_boundary_run=9 if suspicious else 1,
        suspicious=suspicious,
        flags=("all_gaps_are_boundaries",) if suspicious else (),
    )


def test_phase01_config_encodes_one_fixed_production_pipeline() -> None:
    configs = load_configs(CONFIG_DIR)
    phase01 = configs["phase01"]
    models = configs["models"]
    storage = configs["storage"]

    assert phase01["schema_version"] == "phase01_pipeline_v1_6"
    assert phase01["pipeline_id"] == "phase01_production_v1_6"
    assert phase01["execution"]["max_concurrent_videos"] == 1
    assert phase01["execution"]["gpu_heavy_models_resident"] == 1
    assert phase01["execution"]["min_model_cache_free_gb"] == 25
    assert phase01["execution"]["chunk_scheduler"] == {
        "max_chunk_videos": 4,
        "max_chunk_raw_bytes": 1610612736,
        "min_free_disk_gb": 20,
        "medium_free_disk_gb": 35,
        "medium_max_chunk_videos": 2,
        "low_disk_max_chunk_videos": 1,
        "ram": {
            "medium_available_gb": 8,
            "minimum_available_gb": 4,
            "medium_max_chunk_videos": 2,
            "low_max_chunk_videos": 1,
        },
    }
    assert phase01["execution"]["inference_batch_size"] == {
        "ocr": 4,
        "shot_captions": 2,
    }
    assert phase01["api"] == {"request_cache_backend": "stage_local"}
    assert phase01["stages"]["order"] == [
        "shots",
        "keyframes",
        "asr",
        "ocr",
        "shot_captions",
        "shot_transcript_links",
        "scenes",
        "scene_summaries",
        "package",
        "sync",
    ]
    assert "providers" not in models
    assert storage["checkpoint"]["require_private"] is False
    assert set(models["phase01"]) == {
        "shot_detection",
        "asr",
        "asr_providers",
        "ocr",
        "shot_caption",
        "scene_boundary",
        "scene_summary",
    }
    assert models["phase01"]["asr"]["provider"] == "nemo"
    assert models["phase01"]["asr"]["model_id"] == "nvidia/parakeet-ctc-0.6b-vi"
    assert models["phase01"]["ocr"]["provider"] == "vintern_local"
    assert models["phase01"]["ocr"]["model_id"] == "5CD-AI/Vintern-1B-v3_5"
    assert models["phase01"]["shot_caption"]["provider"] == "qwen_local"
    assert models["phase01"]["shot_caption"]["model_id"] == "Qwen/Qwen2.5-VL-7B-Instruct"
    assert models["phase01"]["shot_caption"]["quantization"] == {
        "method": "bitsandbytes",
        "package_version": "0.47.0",
        "mode": "4bit",
        "quant_type": "nf4",
        "compute_dtype": "float16",
        "double_quant": True,
    }
    assert models["phase01"]["scene_boundary"]["provider"] == "qwen_local"
    assert (
        models["phase01"]["scene_boundary"]["degenerate_prompt_version"]
        == "scene_boundary_degenerate_label_v1"
    )
    assert models["phase01"]["scene_summary"]["provider"] == "qwen_local"
    assert set(models["phase01"]["asr_providers"]) == {"faster_whisper", "nemo"}

    assert (
        phase01["schemas"]["shot_captions"]
        == "shot_captions_v4"
    )
    assert (
        phase01["schemas"]["scene_summaries"]
        == "scene_summaries_v3"
    )
    assert phase01["schemas"]["scenes"] == "scenes_v2"

    assert (
        models["phase01"]["shot_caption"][
            "response_schema_version"
        ]
        == "shot_caption_response_v3"
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("max_concurrent_videos", 2),
        ("gpu_heavy_models_resident", 2),
        ("checkpoint_after_each_stage", False),
        ("release_gpu_objects_before_empty_cache", False),
    ],
)
def test_fixed_execution_fields_are_validated_invariants(
    field: str, value: object
) -> None:
    resolved = resolve_phase01_config(
        CONFIG_DIR,
        user_settings=user_settings(),
        phase00_release_id="canonical_release_v001",
        environment="local",
    )
    resolved.payload["phase01"]["execution"][field] = value

    with pytest.raises(ValueError, match=f"execution.{field}.*enforced invariant"):
        require_phase01_production_ready(resolved)


def test_shared_semantic_runtime_rejects_fallback_config_drift() -> None:
    resolved = resolve_phase01_config(
        CONFIG_DIR,
        user_settings=user_settings(),
        phase00_release_id="canonical_release_v001",
        environment="local",
    )
    resolved.payload["models"]["scene_summary"]["fallbacks"] = [{
        **resolved.payload["models"]["shot_caption"]["fallbacks"][0],
        "model_id": "different-local-model",
    }]

    with pytest.raises(ValueError, match="shared semantic runtime mismatch"):
        require_phase01_production_ready(resolved)


def test_semantic_sampling_thresholds_and_downstream_roles_are_validated() -> None:
    resolved = resolve_phase01_config(
        CONFIG_DIR,
        user_settings=user_settings(),
        phase00_release_id="canonical_release_v001",
        environment="local",
    )
    resolved.payload["media"]["keyframe"]["semantic_sampling"][
        "visual_novelty"
    ]["min_hamming_ratio"] = 1.1
    with pytest.raises(ValueError, match=r"min_hamming_ratio.*\[0, 1\]"):
        require_phase01_production_ready(resolved)

    resolved = resolve_phase01_config(
        CONFIG_DIR,
        user_settings=user_settings(),
        phase00_release_id="canonical_release_v001",
        environment="local",
    )
    resolved.payload["phase01"]["ocr"]["run_on_keyframe_roles"] = [
        "early",
        "middle",
        "late",
    ]
    with pytest.raises(ValueError, match="supplemental OCR evidence"):
        require_phase01_production_ready(resolved)


@pytest.mark.parametrize(
    ("path", "value", "message"),
    [
        (("min_shot_count",), 1, "min_shot_count"),
        (("suspicious_boundary_density",), 1.1, "suspicious_boundary_density"),
        (("suspicious_one_shot_scene_rate",), -0.1, "suspicious_one_shot_scene_rate"),
        (("unresolved_action",), "accept", "unresolved_action"),
        (("degenerate_review", "max_rounds"), -1, "max_rounds"),
    ],
)
def test_scene_quality_guard_config_is_validated(
    path: tuple[str, ...], value: object, message: str
) -> None:
    resolved = resolve_phase01_config(
        CONFIG_DIR,
        user_settings=user_settings(),
        phase00_release_id="canonical_release_v001",
        environment="local",
    )
    target = resolved.payload["phase01"]["scene_grouping"]["quality_guard"]
    for component in path[:-1]:
        target = target[component]
    target[path[-1]] = value

    with pytest.raises(ValueError, match=message):
        require_phase01_production_ready(resolved)


def test_suspicious_scene_partition_fails_terminal_quality_gate() -> None:
    quality = _scene_quality(suspicious=True)
    result = SceneGroupingResult(
        scenes=[],
        decisions=[],
        initial_quality=quality,
        final_quality=quality,
        consistency_review_rounds_run=1,
        degenerate_review_triggered=True,
        degenerate_review_rounds_run=1,
    )
    payload = _scene_partition_quality_payload(
        video_id="v",
        result=result,
        policy={
            "enabled": True,
            "min_shot_count": 8,
            "suspicious_boundary_density": 0.9,
            "suspicious_one_shot_scene_rate": 0.8,
            "unresolved_action": "fail_terminal",
        },
    )

    with pytest.raises(ScenePartitionQualityError) as captured:
        _require_scene_partition_quality(
            video_id="v",
            result=result,
            payload=payload,
        )

    assert captured.value.details["manual_review_required"] is True
    assert captured.value.details["final"]["suspicious"] is True
    assert _retryable_video_error(captured.value) is False


def test_scene_quality_failure_persists_structured_checkpoint_details() -> None:
    final = {
        "shot_count": 10,
        "scene_count": 10,
        "boundary_density": 1.0,
        "one_shot_scene_rate": 1.0,
        "suspicious": True,
    }
    error = ScenePartitionQualityError(
        video_id="v",
        details={
            "quality_contract": "scene_partition_quality_v1",
            "manual_review_required": True,
            "initial": {"suspicious": True},
            "final": final,
            "degenerate_review_triggered": True,
        },
    )

    payload = _checkpoint_error_payload(error)

    assert payload["error_type"] == "ScenePartitionQualityError"
    assert payload["details"] == error.details
    assert payload["details"] is not error.details
    assert payload["failed_at"]


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("missing", "Missing scene partition quality report"),
        ("failed", "not passing"),
        ("suspicious", "remains suspicious"),
    ],
)
def test_package_quality_report_requires_passing_final_state(
    tmp_path: Path, mutation: str, message: str
) -> None:
    diagnostics = tmp_path / "diagnostics"
    diagnostics.mkdir()
    path = diagnostics / "scene_partition_quality.json"
    payload = _passing_scene_quality_report("v")
    if mutation == "failed":
        payload["status"] = "failed_quality_gate"
    elif mutation == "suspicious":
        payload["final"]["suspicious"] = True
    if mutation != "missing":
        path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises((FileNotFoundError, ValueError), match=message):
        _validate_scene_partition_quality_report(
            tmp_path,
            video_id="v",
            shot_count=1,
            scene_count=1,
        )


def test_package_quality_report_accepts_passing_final_state(tmp_path: Path) -> None:
    diagnostics = tmp_path / "diagnostics"
    diagnostics.mkdir()
    (diagnostics / "scene_partition_quality.json").write_text(
        json.dumps(_passing_scene_quality_report("v")),
        encoding="utf-8",
    )

    _validate_scene_partition_quality_report(
        tmp_path,
        video_id="v",
        shot_count=1,
        scene_count=1,
    )


def test_supplemental_keyframe_cannot_be_representative() -> None:
    row = {
        "keyframe_id": "L21_V001:1",
        "video_id": "L21_V001",
        "frame_id": 1,
        "timestamp_sec": 0.04,
        "shot_id": "L21_V001_SH00000",
        "scene_id": None,
        "keyframe_role": "supplemental",
        "quality_score": 1.0,
        "is_representative": True,
        "selection_reason": "visual_novelty",
        "keyframe_ref": "media://keyframes/L21_V001/L21_V001_f0000001.jpg",
        "thumbnail_ref": "media://thumbnails/L21_V001/L21_V001_f0000001.webp",
        "status": "pass",
    }

    with pytest.raises(ValueError, match="keyframes row 0 violates canonical schema"):
        validate_rows("keyframes", [row])


def test_supplemental_keyframe_rejects_non_novelty_selection_reason() -> None:
    row = {
        "keyframe_id": "L21_V001:1",
        "video_id": "L21_V001",
        "frame_id": 1,
        "timestamp_sec": 0.04,
        "shot_id": "L21_V001_SH00000",
        "scene_id": None,
        "keyframe_role": "supplemental",
        "quality_score": 1.0,
        "is_representative": False,
        "selection_reason": "best_valid_candidate_in_search_band",
        "keyframe_ref": "media://keyframes/L21_V001/L21_V001_f0000001.jpg",
        "thumbnail_ref": "media://thumbnails/L21_V001/L21_V001_f0000001.webp",
        "status": "pass",
    }

    with pytest.raises(ValueError, match="keyframes row 0 violates canonical schema"):
        validate_rows("keyframes", [row])


def test_keyframe_diagnostic_counts_separate_unique_frames_from_evaluations() -> None:
    anchor_diagnostics = [
        SimpleNamespace(frame_id=5, valid=True),
        SimpleNamespace(frame_id=5, valid=True),
        SimpleNamespace(frame_id=7, valid=False),
    ]
    semantic_diagnostics = [
        {"frame_id": 5, "valid": False},
        {"frame_id": 9, "valid": True},
    ]

    assert _keyframe_diagnostic_counts(
        anchor_diagnostics, semantic_diagnostics
    ) == {
        "candidate_count": 3,
        "valid_candidate_count": 2,
        "evaluation_count": 5,
        "valid_evaluation_count": 3,
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("batch_id", "../batch_000"),
        ("batch_id", "batch/000"),
        ("worker_id", "worker\\000"),
        ("worker_id", " worker_000"),
        ("worker_id", ".."),
    ],
)
def test_runtime_identifiers_must_be_path_safe(field: str, value: str) -> None:
    with pytest.raises(ValueError, match=f"{field}.*path-safe identifier"):
        resolve_phase01_config(
            CONFIG_DIR,
            user_settings=user_settings(**{field: value}),
            phase00_release_id="canonical_release_v001",
            environment="local",
        )


def test_runtime_diagnostics_reflect_resolved_config_and_git_identity(
    monkeypatch,
) -> None:
    configs = load_configs(CONFIG_DIR)
    resolved = resolve_phase01_config(
        CONFIG_DIR,
        user_settings=user_settings(),
        phase00_release_id="canonical_release_v001",
        environment="local",
    )
    monkeypatch.setenv("AIC_EXPECTED_GIT_BRANCH", "dev")
    monkeypatch.setattr(
        "system1.phase01.runner._git_identity",
        lambda: {
            "git_commit_sha": "a" * 40,
            "git_branch": "dev",
            "git_dirty": False,
        },
    )

    diagnostics = _build_runtime_diagnostics(configs, resolved)

    assert diagnostics["git_commit_sha"] == "a" * 40
    assert diagnostics["git_branch_matches_expected"] is True
    assert diagnostics["config_hash"] == resolved.config_hash
    assert diagnostics["pipeline_id"] == "phase01_production_v1_6"
    assert diagnostics["models_schema_version"] == "phase01_models_v1_4"
    assert diagnostics["asr"] == {
        "provider": "nemo",
        "model_id": "nvidia/parakeet-ctc-0.6b-vi",
    }
    assert diagnostics["ocr"]["model_id"] == "5CD-AI/Vintern-1B-v3_5"
    assert diagnostics["semantic"] == {
        "provider": "qwen_local",
        "model_id": "Qwen/Qwen2.5-VL-7B-Instruct",
        "quantization": "bitsandbytes:4bit:nf4",
        "stages": ["shot_captions", "scenes", "scene_summaries"],
    }
    assert diagnostics["semantic_fallback_providers"] == ["vintern_reasoning_local"]


def test_canonical_structured_text_rejects_whitespace_only_values() -> None:
    assert _required_text({"caption_vi": "  nội dung  "}, "caption_vi") == "nội dung"
    with pytest.raises(ValueError, match="non-whitespace"):
        _required_text({"caption_vi": "   "}, "caption_vi")


def test_build_captions_submits_all_shots_through_request_many(
    tmp_path: Path,
) -> None:
    class RequestManyOnlyClient:
        def __init__(self) -> None:
            self.batches = []

        def request_many(self, requests):
            self.batches.append(requests)
            responses = []
            for request_index, request in enumerate(requests):
                field = request.identity["field"]
                shot_index = request_index // 8
                if field == "caption_vi":
                    text = f"Cảnh {shot_index}"
                elif field == "caption_en":
                    text = f"Scene {shot_index}"
                elif field in {"objects_vi", "objects_en"}:
                    text = "người\nngười" if field.endswith("_vi") else "person"
                else:
                    text = "<NONE>"
                fallback_field = shot_index == 1 and field == "caption_en"
                responses.append({
                    "text": text,
                    "__provider": (
                        "vintern_reasoning_local" if fallback_field else "qwen_local"
                    ),
                    "__model_id": (
                        "5CD-AI/Vintern-3B-R-beta"
                        if fallback_field
                        else "Qwen/Qwen2.5-VL-7B-Instruct"
                    ),
                    "__model_revision": "fallback-revision" if fallback_field else "revision",
                })
            return responses

    client = RequestManyOnlyClient()
    shots = [{"shot_id": f"L21_V001_SH{index:05d}"} for index in range(2)]
    keyframes = [
        {
            "shot_id": shot["shot_id"],
            "keyframe_id": f"L21_V001:{index}",
            "keyframe_ref": f"media://keyframes/frame_{index:03d}.jpg",
            "timestamp_sec": float(index),
            "is_representative": True,
        }
        for index, shot in enumerate(shots)
    ]
    model_config = copy.deepcopy(
        load_configs(CONFIG_DIR)["models"]["phase01"]["shot_caption"]
    )
    model_config["prompt_versions"]["caption_vi"] = "shot_caption_en_v1"

    rows = _build_captions(
        video_id="L21_V001",
        shots=shots,
        keyframes=keyframes,
        ocr_rows=[],
        stage_dir=tmp_path,
        client=client,
        model_config=model_config,
    )

    assert len(client.batches) == 1
    assert len(client.batches[0]) == 16
    assert [request.identity["field"] for request in client.batches[0][:8]] == [
        "caption_vi",
        "caption_en",
        "objects_vi",
        "objects_en",
        "actions_vi",
        "actions_en",
        "visible_text_summary_vi",
        "visible_text_summary_en",
    ]
    assert client.batches[0][0].prompt_version == "shot_caption_en_v1"
    assert [row["caption_en"] for row in rows] == ["Scene 0", "Scene 1"]
    assert rows[0]["objects_vi"] == ["người"]
    assert rows[0]["actions_vi"] == []
    assert rows[0]["provider"] == "qwen_local"
    assert rows[1]["provider"] == "mixed"
    assert rows[1]["model_name"] == "mixed"
    provenance = [
        json.loads(line)
        for line in (tmp_path / "shot_caption_field_provenance.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert len(provenance) == 16
    assert {row["field"] for row in provenance} == {
        "caption_vi",
        "caption_en",
        "objects_vi",
        "objects_en",
        "actions_vi",
        "actions_en",
        "visible_text_summary_vi",
        "visible_text_summary_en",
    }


def test_required_caption_rejects_none_sentinel() -> None:
    with pytest.raises(ValueError, match="required semantic text is empty"):
        _normalize_required_text("<NONE>")


def test_scene_summary_generates_all_vi_before_en_and_en_references_vi(
    tmp_path: Path,
) -> None:
    class RecordingClient:
        def __init__(self) -> None:
            self.batches = []

        def request_many(self, requests):
            self.batches.append(requests)
            if requests[0].request_kind == "scene_summary_vi":
                return [{
                    "text": "Một người đang phát biểu.",
                    "__provider": "qwen_local",
                    "__model_id": "Qwen/Qwen2.5-VL-7B-Instruct",
                    "__model_revision": "qwen-revision",
                }]
            assert "VIETNAMESE_SUMMARY_REFERENCE:\nMột người đang phát biểu." in requests[0].prompt
            return [{
                "text": "A person is speaking.",
                "__provider": "vintern_reasoning_local",
                "__model_id": "5CD-AI/Vintern-3B-R-beta",
                "__model_revision": "vintern-revision",
            }]

    stage_dir = tmp_path
    (stage_dir / "keyframes").mkdir()
    image_name = "L21_V001_f0000000.jpg"
    Image.new("RGB", (16, 16), "white").save(stage_dir / "keyframes" / image_name)
    shot_id = "L21_V001_SH00000"
    scene_id = "L21_V001_SC00000"
    shots = [{"shot_id": shot_id, "start_sec": 0.0, "end_sec": 1.0}]
    scenes = [{
        "scene_id": scene_id,
        "start_shot_id": shot_id,
        "end_shot_id": shot_id,
        "start_sec": 0.0,
        "end_sec": 1.0,
    }]
    keyframes = [{
        "shot_id": shot_id,
        "keyframe_id": "L21_V001:0",
        "keyframe_ref": f"media://keyframes/L21_V001/{image_name}",
        "timestamp_sec": 0.0,
        "is_representative": True,
    }]
    captions = [{
        "shot_id": shot_id,
        "caption_vi": "Một người đang phát biểu.",
        "caption_en": "A person is speaking.",
        "objects_vi": ["người"],
        "objects_en": ["person"],
        "actions_vi": ["phát biểu"],
        "actions_en": ["speaking"],
        "visible_text_summary_vi": "",
        "visible_text_summary_en": "",
    }]
    resolved = resolve_phase01_config(
        CONFIG_DIR,
        user_settings=user_settings(),
        phase00_release_id="canonical_release_v001",
        environment="local",
    )
    client = RecordingClient()
    model_config = copy.deepcopy(resolved.payload["models"]["scene_summary"])
    model_config["prompt_versions"]["summary_vi"] = "scene_summary_en_v2"

    rows = _build_scene_summaries(
        video_id="L21_V001",
        scenes=scenes,
        shots=shots,
        keyframes=keyframes,
        ocr_rows=[],
        captions=captions,
        asr_rows=[],
        scene_links=[],
        stage_dir=stage_dir,
        client=client,
        model_config=model_config,
        summary_config=resolved.payload["phase01"]["scene_summary"],
    )

    assert [[request.request_kind for request in batch] for batch in client.batches] == [
        ["scene_summary_vi"],
        ["scene_summary_en"],
    ]
    assert client.batches[0][0].prompt_version == "scene_summary_en_v2"
    assert rows[0]["summary_vi"] == "Một người đang phát biểu."
    assert rows[0]["summary_en"] == "A person is speaking."
    assert rows[0]["provider"] == "mixed"
    provenance = (
        stage_dir / "scene_summary_field_provenance.jsonl"
    ).read_text(encoding="utf-8").splitlines()
    assert len(provenance) == 2


@pytest.mark.parametrize(
    "provider", ["qwen_local", "vintern_reasoning_local", "mixed"]
)
def test_scene_summaries_v3_accepts_local_and_fallback_provenance(
    provider: str,
) -> None:
    validate_rows(
        "scene_summaries",
        [{
            "scene_id": "L21_V001_SC00000",
            "video_id": "L21_V001",
            "summary_vi": "Một cảnh",
            "summary_en": "A scene",
            "provider": provider,
            "model_name": "model",
            "model_version": "revision",
            "prompt_version": "scene_summary_plain_text_v2",
            "schema_version": "scene_summary_response_v1",
            "confidence": None,
            "status": "pass",
        }],
    )


def test_keyframe_config_uses_search_bands_and_relative_representative_rule() -> None:
    media = load_configs(CONFIG_DIR)["media"]
    keyframe = media["keyframe"]

    assert keyframe["roles"] == {
        "early": {
            "search_start_ratio": 0.10,
            "target_ratio": 0.20,
            "search_end_ratio": 0.30,
        },
        "middle": {
            "search_start_ratio": 0.40,
            "target_ratio": 0.50,
            "search_end_ratio": 0.60,
        },
        "late": {
            "search_start_ratio": 0.70,
            "target_ratio": 0.80,
            "search_end_ratio": 0.90,
        },
    }
    assert keyframe["selection"]["max_candidates_per_band"] == 5
    assert keyframe["selection"]["deduplicate_frame_id"] is True
    assert keyframe["quality"]["metric"] == "variance_of_laplacian"
    assert keyframe["quality"]["absolute_blur_threshold"] is None
    assert keyframe["representative"]["preferred_role"] == "middle"
    assert keyframe["representative"]["preferred_min_ratio_of_best"] == 0.85
    assert keyframe["semantic_sampling"] == {
        "enabled": True,
        "policy": "temporal_visual_text_v1",
        "target_max_probe_gap_seconds": 3.0,
        "max_probe_candidates_per_shot": 24,
        "min_supplemental_separation_seconds": 1.0,
        "max_supplemental_keyframes_per_shot": 2,
        "visual_novelty": {
            "policy": "dhash_v1",
            "hash_size": 8,
            "min_hamming_ratio": 0.25,
        },
        "text_change": {
            "policy": "mser_masked_edge_jaccard_v1",
            "max_long_side": 480,
            "canny_low": 50,
            "canny_high": 150,
            "signature_width": 64,
            "signature_height": 36,
            "min_plausible_regions": 2,
            "min_jaccard_distance": 0.35,
        },
    }


def test_phase01_config_encodes_oom_and_dependency_invalidation_policy() -> None:
    configs = load_configs(CONFIG_DIR)
    phase01 = configs["phase01"]
    models = configs["models"]["phase01"]
    dependencies = phase01["stages"]["dependencies"]

    assert models["asr"]["model_id"] == "nvidia/parakeet-ctc-0.6b-vi"
    assert models["asr"]["model_file"] == "parakeet-ctc-0.6b-vi.nemo"
    assert phase01["asr"]["exhausted_oom_status"] == "failed_retryable"
    assert dependencies["keyframes"] == ["shots"]
    assert dependencies["ocr"] == ["keyframes"]
    assert set(dependencies["shot_captions"]) == {"keyframes", "ocr"}
    assert set(dependencies["shot_transcript_links"]) == {"shots", "asr"}
    assert set(dependencies["scenes"]) == {
        "shots",
        "keyframes",
        "ocr",
        "shot_captions",
        "shot_transcript_links",
    }
    assert dependencies["sync"] == ["package"]


def test_runtime_chunk_policy_does_not_change_stage_fingerprints() -> None:
    resolved = resolve_phase01_config(
        CONFIG_DIR,
        user_settings=user_settings(),
        phase00_release_id="canonical_release_v001",
        environment="local",
    )
    modified = copy.deepcopy(resolved.payload)
    modified["phase01"]["execution"]["chunk_scheduler"]["max_chunk_videos"] = 1
    modified["phase01"]["execution"]["chunk_scheduler"]["ram"][
        "minimum_available_gb"
    ] = 6
    modified["phase01"]["execution"]["inference_batch_size"] = {
        "ocr": 1,
        "shot_captions": 1,
    }

    assert _stage_config_hashes(modified) == resolved.stage_config_hashes


def test_semantic_policies_change_only_relevant_stage_hashes() -> None:
    resolved = resolve_phase01_config(
        CONFIG_DIR,
        user_settings=user_settings(),
        phase00_release_id="canonical_release_v001",
        environment="local",
    )

    ocr_changed = copy.deepcopy(resolved.payload)
    ocr_changed["phase01"]["ocr"]["text_presence_filter"][
        "max_no_text_gray_std"
    ] = 11
    ocr_hashes = _stage_config_hashes(ocr_changed)
    assert ocr_hashes["ocr"] != resolved.stage_config_hashes["ocr"]
    assert ocr_hashes["shots"] == resolved.stage_config_hashes["shots"]

    quant_changed = copy.deepcopy(resolved.payload)
    quant_changed["models"]["shot_caption"]["quantization"][
        "double_quant"
    ] = False
    quant_hashes = _stage_config_hashes(quant_changed)
    for stage in ("shot_captions", "scenes", "scene_summaries"):
        assert quant_hashes[stage] != resolved.stage_config_hashes[stage]

    boundary_changed = copy.deepcopy(resolved.payload)
    boundary_changed["models"]["scene_boundary"][
        "prompt_version"
    ] = "scene_boundary_primary_label_v999"
    boundary_hashes = _stage_config_hashes(boundary_changed)
    assert boundary_hashes["scenes"] != resolved.stage_config_hashes["scenes"]
    assert (
        boundary_hashes["scene_summaries"]
        == resolved.stage_config_hashes["scene_summaries"]
    )

    keyframe_changed = copy.deepcopy(resolved.payload)
    keyframe_changed["media"]["keyframe"]["semantic_sampling"][
        "target_max_probe_gap_seconds"
    ] = 2.5
    keyframe_hashes = _stage_config_hashes(keyframe_changed)
    assert keyframe_hashes["keyframes"] != resolved.stage_config_hashes["keyframes"]
    assert keyframe_hashes["shots"] == resolved.stage_config_hashes["shots"]
    assert keyframe_hashes["asr"] == resolved.stage_config_hashes["asr"]

    focused_roles_changed = copy.deepcopy(resolved.payload)
    focused_roles_changed["phase01"]["scene_grouping"][
        "focused_review_keyframe_roles"
    ] = ["early", "late"]
    focused_hashes = _stage_config_hashes(focused_roles_changed)
    assert focused_hashes["scenes"] != resolved.stage_config_hashes["scenes"]
    assert focused_hashes["keyframes"] == resolved.stage_config_hashes["keyframes"]

    quality_changed = copy.deepcopy(resolved.payload)
    quality_changed["phase01"]["scene_grouping"]["quality_guard"][
        "suspicious_boundary_density"
    ] = 0.95
    quality_hashes = _stage_config_hashes(quality_changed)
    assert quality_hashes["scenes"] != resolved.stage_config_hashes["scenes"]
    for stage in (
        "shots",
        "keyframes",
        "asr",
        "ocr",
        "shot_captions",
        "shot_transcript_links",
    ):
        assert quality_hashes[stage] == resolved.stage_config_hashes[stage]


def test_phase01_config_can_select_nemo_asr_provider() -> None:
    resolved = resolve_phase01_config(
        CONFIG_DIR,
        user_settings={
            **user_settings(),
            "asr_provider": "nemo",
        },
        phase00_release_id="canonical_release_v001",
        environment="local",
    )
    models = resolved.payload["models"]
    assert models["asr"]["provider"] == "nemo"
    assert models["asr"]["model_id"] == "nvidia/parakeet-ctc-0.6b-vi"
    assert models["asr"]["model_revision"] == "b0493142b49458810324e3db8be9e8e07b4ebc17"
    assert models["asr"]["model_file"] == "parakeet-ctc-0.6b-vi.nemo"
    assert models["asr"]["segmentation"]["provider"] == "silero_vad_onnx"
    assert models["asr"]["segmentation"]["max_speech_seconds"] == 30
    assert models["asr"]["decoder"]["strategy"] == "flashlight"
    assert models["asr"]["decoder"]["beam_size"] == 64


def test_phase01_config_can_select_faster_whisper_asr_provider() -> None:
    resolved = resolve_phase01_config(
        CONFIG_DIR,
        user_settings={**user_settings(), "asr_provider": "faster_whisper"},
        phase00_release_id="canonical_release_v001",
        environment="local",
    )

    asr = resolved.payload["models"]["asr"]
    assert asr["provider"] == "faster_whisper"
    assert asr["model_id"] == "Systran/faster-whisper-large-v3"
    assert asr["model_revision"] == "edaa852ec7e145841d8ffdb056a99866b5f0a478"


def test_resolved_config_is_stable_secret_free_and_auto_resolves_release(tmp_path: Path) -> None:
    first = resolve_phase01_config(
        CONFIG_DIR,
        user_settings=user_settings(),
        phase00_release_id="canonical_release_v001",
        environment="colab",
    )
    second = resolve_phase01_config(
        CONFIG_DIR,
        user_settings={
            "hf_release_repo": "org/release",
            "worker_id": "worker_001",
            "batch_id": "batch_000",
        },
        phase00_release_id="canonical_release_v001",
        environment="colab",
    )

    assert first.config_hash == second.config_hash
    assert len(first.config_hash) == 64
    assert first.payload["runtime"]["release_id"] == "canonical_release_v001"
    assert first.payload["runtime"]["release_id_source"] == "phase00_auto_resolve"
    assert first.production_ready is True
    assert first.unresolved_required_fields == ()

    output = persist_resolved_phase01_config(first, tmp_path / "resolved_config.json")
    persisted = json.loads(output.read_text(encoding="utf-8"))
    assert persisted["config_hash"] == first.config_hash
    assert persisted["production_ready"] is True
    assert persisted["storage"]["release"]["repo_id"] == "org/release"
    assert set(persisted["stage_config_hashes"]) == set(
        first.payload["phase01"]["stages"]["order"]
    )
    assert "secret-value" not in output.read_text(encoding="utf-8")
    assert not (tmp_path / ".resolved_config.json.partial").exists()


def test_release_override_wins_over_auto_resolved_phase00_release() -> None:
    resolved = resolve_phase01_config(
        CONFIG_DIR,
        user_settings=user_settings(release_id_override="canonical_release_v009"),
        phase00_release_id="canonical_release_v001",
        environment="kaggle",
    )

    assert resolved.payload["runtime"]["release_id"] == "canonical_release_v009"
    assert resolved.payload["runtime"]["release_id_source"] == "user_override"


def test_checkpoint_repository_override_also_moves_model_artifact_store() -> None:
    resolved = resolve_phase01_config(
        CONFIG_DIR,
        user_settings=user_settings(
            hf_checkpoint_repo="org/checkpoints",
            checkpoint_revision="artifacts-v2",
        ),
        phase00_release_id="canonical_release_v001",
        environment="colab",
    )

    assert resolved.payload["storage"]["checkpoint"]["repo_id"] == "org/checkpoints"
    assert resolved.payload["storage"]["model_artifacts"]["repo_id"] == "org/checkpoints"
    assert resolved.payload["storage"]["model_artifacts"]["revision"] == "artifacts-v2"


def test_process_batch_does_not_override_versioned_storage_defaults(
    monkeypatch, tmp_path: Path
) -> None:
    captured: dict = {}

    def run_pipeline(**kwargs):
        captured.update(kwargs["user_settings"])
        return SimpleNamespace(
            release_dir=tmp_path / "release",
            worker_report_path=tmp_path / "report.json",
        )

    monkeypatch.setattr(
        "system1.commands.pipeline._phase01_test_provider_profile", lambda: "config"
    )
    monkeypatch.setattr("system1.commands.pipeline.run_phase01_pipeline", run_pipeline)
    result = CliRunner().invoke(
        app,
        ["process-batch", "--batch-id", "batch_000", "--output", str(tmp_path)],
    )

    assert result.exit_code == 0, result.output
    assert "hf_release_repo" not in captured
    assert "hf_repo_type" not in captured
    assert "hf_release_revision" not in captured
    assert "hf_release_prefix" not in captured


def test_phase01_smoke_cli_runs_only_the_optional_smoke(
    monkeypatch, tmp_path: Path
) -> None:
    captured: dict = {}

    def run_smoke(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            report_path=tmp_path / "smoke.json",
        )

    monkeypatch.setattr(
        "system1.commands.pipeline.run_phase01_smoke", run_smoke
    )
    monkeypatch.setattr(
        "system1.commands.pipeline.run_phase01_pipeline",
        lambda **_kwargs: pytest.fail("optional smoke must not start production"),
    )
    result = CliRunner().invoke(
        app,
        [
            "phase01-smoke",
            "--hf-checkpoint-repo",
            "org/checkpoint",
            "--checkpoint-revision",
            "model-artifacts-v2",
            "--scratch-dir",
            str(tmp_path / "scratch"),
            "--delete-remote-artifacts",
            "--keep-local",
            "--output",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Smoke PASS" in result.output
    assert captured["user_settings"]["batch_id"] == "phase01_smoke"
    assert captured["user_settings"]["worker_id"] == "phase01_smoke"
    assert captured["user_settings"]["hf_checkpoint_repo"] == "org/checkpoint"
    assert captured["user_settings"]["checkpoint_revision"] == "model-artifacts-v2"
    assert captured["keep_remote_artifacts"] is False
    assert captured["cleanup_local"] is False


@pytest.mark.parametrize("secret_key", ["HF_TOKEN", "AIC_HF_TOKEN"])
def test_resolved_config_rejects_secret_values(secret_key: str) -> None:
    with pytest.raises(ValueError, match="secret values"):
        resolve_phase01_config(
            CONFIG_DIR,
            user_settings=user_settings(**{secret_key: "secret-value"}),
            phase00_release_id="canonical_release_v001",
            environment="local",
        )


@pytest.mark.parametrize("forbidden_key", ["mode", "providers", "provider_profile"])
def test_resolved_config_rejects_pipeline_or_provider_selectors(forbidden_key: str) -> None:
    with pytest.raises(ValueError, match="unsupported Phase01 user settings"):
        resolve_phase01_config(
            CONFIG_DIR,
            user_settings=user_settings(**{forbidden_key: "mock"}),
            phase00_release_id="canonical_release_v001",
            environment="local",
        )


def test_production_readiness_lists_missing_authority_instead_of_guessing(
    tmp_path: Path,
) -> None:
    temp_config_dir = tmp_path / "configs"
    shutil.copytree(CONFIG_DIR, temp_config_dir)
    models_yaml = temp_config_dir / "models.yaml"
    models_yaml.write_text(
        models_yaml.read_text(encoding="utf-8").replace(
            "weights_sha256: 834b10f25ae9e1b4e4f2652fe2843bd2b1388057a435d68b7c52635578fcc04d",
            "weights_sha256: null",
        ),
        encoding="utf-8",
    )
    resolved = resolve_phase01_config(
        temp_config_dir,
        user_settings=user_settings(),
        phase00_release_id="canonical_release_v001",
        environment="local",
    )

    assert resolved.unresolved_required_fields == ("models.shot_detection.weights_sha256",)
    with pytest.raises(ValueError, match="unresolved required fields"):
        require_phase01_production_ready(resolved)


def test_phase01_json_schemas_lock_checkpoint_and_keyframe_contracts() -> None:
    checkpoint = json.loads(
        (SCHEMA_DIR / "phase01_checkpoint_state.schema.json").read_text(encoding="utf-8")
    )
    resolved = json.loads(
        (SCHEMA_DIR / "resolved_config.schema.json").read_text(encoding="utf-8")
    )
    keyframes = json.loads(
        (SCHEMA_DIR / "keyframes.schema.json").read_text(encoding="utf-8")
    )

    expected_stages = {
        "shots",
        "keyframes",
        "asr",
        "ocr",
        "shot_captions",
        "shot_transcript_links",
        "scenes",
        "scene_summaries",
        "package",
        "sync",
    }
    assert set(checkpoint["properties"]["stages"]["required"]) == expected_stages
    assert {
        "status",
        "input_fingerprint",
        "config_hash",
        "model",
        "prompt_version",
        "schema_version",
        "output_checksums",
        "completed_at",
    }.issubset(checkpoint["$defs"]["stage"]["required"])
    assert resolved["properties"]["config_hash"]["pattern"] == "^[0-9a-f]{64}$"
    assert {"keyframe_role", "quality_score", "is_representative", "selection_reason"}.issubset(
        keyframes["required"]
    )
    assert keyframes["title"] == "keyframes_v3"
    assert keyframes["properties"]["keyframe_role"]["enum"] == [
        "early",
        "middle",
        "late",
        "supplemental",
    ]
    supplemental_contract = keyframes["allOf"][0]["then"]["properties"]
    assert supplemental_contract["selection_reason"]["enum"] == [
        "visual_novelty",
        "text_change",
        "visual_and_text_novelty",
    ]


def test_package_assembly_backfills_scene_ids_and_passes_strict_validation(
    tmp_path: Path,
) -> None:
    video_id = "L21_V001"
    shot_id = f"{video_id}_SH00000"
    scene_id = f"{video_id}_SC00000"
    stage = tmp_path / "stage"
    (stage / "keyframes").mkdir(parents=True)
    (stage / "thumbnails").mkdir()
    (stage / "keyframes" / f"{video_id}_f0000000.jpg").write_bytes(b"jpg")
    (stage / "thumbnails" / f"{video_id}_f0000000.webp").write_bytes(b"webp")
    (stage / "keyframes" / f"{video_id}_f0000001.jpg").write_bytes(b"jpg-1")
    (stage / "thumbnails" / f"{video_id}_f0000001.webp").write_bytes(b"webp-1")
    rows = {
        "shots": [{
            "shot_id": shot_id, "video_id": video_id, "scene_id": None,
            "shot_index": 0, "start_frame": 0, "end_frame": 2,
            "start_sec": 0.0, "end_sec": 0.08, "duration_sec": 0.08,
            "frame_count": 2, "boundary_convention": "[start_frame, end_frame)",
            "detection_method": "transnet_v2", "status": "transnet_v2_no_cut",
        }],
        "keyframes": [{
            "keyframe_id": f"{video_id}:0", "video_id": video_id, "frame_id": 0,
            "timestamp_sec": 0.0, "shot_id": shot_id, "scene_id": None,
            "keyframe_role": "middle", "quality_score": 10.0,
            "is_representative": True, "selection_reason": "middle_within_quality_ratio",
            "keyframe_ref": f"media://keyframes/{video_id}/{video_id}_f0000000.jpg",
            "thumbnail_ref": f"media://thumbnails/{video_id}/{video_id}_f0000000.webp",
            "status": "pass",
        }, {
            "keyframe_id": f"{video_id}:1", "video_id": video_id, "frame_id": 1,
            "timestamp_sec": 0.04, "shot_id": shot_id, "scene_id": None,
            "keyframe_role": "supplemental", "quality_score": 9.0,
            "is_representative": False, "selection_reason": "text_change",
            "keyframe_ref": f"media://keyframes/{video_id}/{video_id}_f0000001.jpg",
            "thumbnail_ref": f"media://thumbnails/{video_id}/{video_id}_f0000001.webp",
            "status": "pass",
        }],
        "ocr": [{
            "ocr_id": f"{video_id}:0:ocr", "video_id": video_id,
            "keyframe_id": f"{video_id}:0", "shot_id": shot_id,
            "frame_id": 0, "text": "", "raw_text": "",
            "provider": "vintern_local", "model_name": "5CD-AI/Vintern-1B-v3_5",
            "model_version": "b98f263eab246eb5269ade64edbdca8a887dc44d",
            "language": "vi", "confidence": None, "status": "empty",
        }],
        "shot_captions": [{
            "shot_caption_id": f"{shot_id}_caption", "video_id": video_id,
            "shot_id": shot_id, "representative_keyframe_id": f"{video_id}:0",
            "representative_timestamp_sec": 0.0, "caption_vi": "Một cảnh",
            "caption_en": "A scene", "objects_vi": ["cảnh"], "objects_en": ["scene"],
            "actions_vi": [], "actions_en": [], "visible_text_summary_vi": "",
            "visible_text_summary_en": "",
            "provider": "qwen_local",
            "model_name": "Qwen/Qwen2.5-VL-7B-Instruct",
            "model_version": "cc594898137f460bfe9f0759e9844b3ce807cfb5",
            "prompt_version": "shot_caption_plain_text_fields_v1",
            "schema_version": "shot_caption_response_v3", "confidence": None,
            "status": "pass",
        }],
        "scenes": [{
            "scene_id": scene_id, "video_id": video_id, "scene_index": 0,
            "start_shot_id": shot_id, "end_shot_id": shot_id,
            "start_frame": 0, "end_frame": 2, "start_sec": 0.0,
            "end_sec": 0.08, "duration_sec": 0.08, "frame_count": 2,
            "shot_count": 1, "keyframe_count": 0, "scene_type": "semantic",
            "grouping_method": "multimodal_context_focus",
            "grouping_version": "scene_grouping_v2", "confidence": None,
            "boundary_convention": "[start_frame, end_frame)", "status": "pass",
        }],
        "scene_summaries": [{
            "scene_id": scene_id, "video_id": video_id, "summary_vi": "Một cảnh",
            "summary_en": "A scene", "provider": "qwen_local",
            "model_name": "Qwen/Qwen2.5-VL-7B-Instruct",
            "model_version": "cc594898137f460bfe9f0759e9844b3ce807cfb5",
            "prompt_version": "scene_summary_plain_text_v2",
            "schema_version": "scene_summary_response_v1", "confidence": None,
            "status": "pass",
        }],
    }
    for name, values in rows.items():
        pd.DataFrame(values).to_parquet(stage / f"{name}.parquet", index=False)
    for name in ("asr_segments", "shot_transcript_links", "scene_transcript_links"):
        pd.DataFrame(columns=PARQUET_COLUMNS[name]).to_parquet(
            stage / f"{name}.parquet", index=False
        )
    (stage / "scene_partition_quality.json").write_text(
        json.dumps(_passing_scene_quality_report(video_id)),
        encoding="utf-8",
    )
    metadata = tmp_path / "metadata.json"
    metadata.write_text(json.dumps({"video_id": video_id}), encoding="utf-8")
    resolved = resolve_phase01_config(
        CONFIG_DIR,
        user_settings=user_settings(),
        phase00_release_id="canonical_release_v001",
        environment="local",
    )

    artifact = tmp_path / "artifact" / video_id
    _assemble_package(
        artifact_dir=artifact,
        video_id=video_id,
        metadata_path=metadata,
        stage_dir=stage,
        config=resolved,
    )

    assert (artifact / "errors.jsonl").read_text(encoding="utf-8") == ""
    assert pd.read_parquet(artifact / "shots.parquet").iloc[0]["scene_id"] == scene_id
    assert pd.read_parquet(artifact / "scenes.parquet").iloc[0]["keyframe_count"] == 2
    assert (artifact / "diagnostics" / "scene_partition_quality.json").is_file()

def test_shared_semantic_runtime_rejects_padding_side_drift() -> None:
    resolved = resolve_phase01_config(
        CONFIG_DIR,
        user_settings=user_settings(),
        phase00_release_id="canonical_release_v001",
        environment="local",
    )

    resolved.payload["models"]["scene_summary"][
        "padding_side"
    ] = "right"

    with pytest.raises(
        ValueError,
        match="shared semantic runtime mismatch",
    ):
        require_phase01_production_ready(resolved)
