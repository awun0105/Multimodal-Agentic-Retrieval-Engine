from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from system1.runtime.environment import detect_environment

REQUIRED_CONFIGS = (
    "artifact.yaml",
    "dataset.yaml",
    "frame.yaml",
    "media.yaml",
    "models.yaml",
    "phase01.yaml",
    "preprocessing.yaml",
    "release.yaml",
    "storage.yaml",
)

_PHASE01_USER_SETTING_KEYS = {
    "batch_id",
    "asr_provider",
    "checkpoint_prefix",
    "checkpoint_revision",
    "hf_checkpoint_repo",
    "hf_release_prefix",
    "hf_release_repo",
    "hf_repo_type",
    "hf_release_revision",
    "release_id_override",
    "scratch_dir",
    "worker_id",
}
_PHASE01_REQUIRED_USER_SETTINGS = {"batch_id", "worker_id"}
_SECRET_SETTING_KEYS = {
    "aic_hf_token",
    "hf_token",
    "huggingface_hub_token",
}


@dataclass(frozen=True)
class ProviderPlan:
    asr: str
    ocr: str
    embedding: str
    object_detection: str
    shot_caption: str
    scene_summary: str

    @property
    def uses_only_mock_providers(self) -> bool:
        values = {self.asr, self.ocr, self.embedding, self.object_detection, self.shot_caption, self.scene_summary}
        return values == {"mock"}


@dataclass(frozen=True)
class ResolvedPhase01Config:
    """Secret-free, deterministic Phase01 runtime configuration."""

    payload: dict[str, Any]
    config_hash: str
    stage_config_hashes: dict[str, str]
    unresolved_required_fields: tuple[str, ...]

    @property
    def production_ready(self) -> bool:
        return not self.unresolved_required_fields

    def to_dict(self) -> dict[str, Any]:
        return {
            **copy.deepcopy(self.payload),
            "config_hash": self.config_hash,
            "stage_config_hashes": dict(self.stage_config_hashes),
            "production_ready": self.production_ready,
            "unresolved_required_fields": list(self.unresolved_required_fields),
        }


def load_configs(config_dir: Path | str) -> dict[str, dict[str, Any]]:
    root = Path(config_dir)
    configs: dict[str, dict[str, Any]] = {}
    for name in REQUIRED_CONFIGS:
        path = root / name
        if not path.exists():
            raise FileNotFoundError(f"missing config file: {path}")
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            raise TypeError(f"config must be a mapping: {path}")
        configs[path.stem] = data
    return configs


def load_provider_plan(config_dir: Path | str, provider_profile: str) -> ProviderPlan:
    configs = load_configs(config_dir)
    provider_defaults = configs["models"].get("providers", {})
    if provider_profile == "mock":
        return ProviderPlan(**{key: "mock" for key in _provider_keys()})
    if provider_profile == "real":
        return ProviderPlan(
            asr="whisper",
            ocr="paddleocr",
            embedding="openclip",
            object_detection="yolo",
            shot_caption="vlm",
            scene_summary="llm",
        )
    if provider_profile == "rule_based":
        return ProviderPlan(
            asr=provider_defaults.get("asr", "mock"),
            ocr=provider_defaults.get("ocr", "mock"),
            embedding=provider_defaults.get("embedding", "mock"),
            object_detection=provider_defaults.get("object_detection", "mock"),
            shot_caption="rule_based",
            scene_summary="rule_based",
        )
    if provider_profile == "vlm":
        return ProviderPlan(
            asr=provider_defaults.get("asr", "mock"),
            ocr=provider_defaults.get("ocr", "mock"),
            embedding=provider_defaults.get("embedding", "mock"),
            object_detection=provider_defaults.get("object_detection", "mock"),
            shot_caption="vlm",
            scene_summary="llm",
        )
    if provider_profile == "config":
        phase01_models = configs["models"].get("phase01", {})
        if phase01_models:
            return ProviderPlan(
                asr=str(phase01_models.get("asr", {}).get("provider", "unconfigured")),
                ocr=str(phase01_models.get("ocr", {}).get("provider", "unconfigured")),
                embedding="unconfigured",
                object_detection="unconfigured",
                shot_caption=str(
                    phase01_models.get("shot_caption", {}).get("provider", "unconfigured")
                ),
                scene_summary=str(
                    phase01_models.get("scene_summary", {}).get("provider", "unconfigured")
                ),
            )
        return ProviderPlan(**{key: str(provider_defaults.get(key, "mock")) for key in _provider_keys()})
    raise ValueError(f"unsupported provider profile: {provider_profile}")


def resolve_phase01_config(
    config_dir: Path | str,
    *,
    user_settings: dict[str, Any],
    phase00_release_id: str | None,
    environment: str | None = None,
) -> ResolvedPhase01Config:
    """Merge repository policy with minimal operator/runtime settings.

    Phase00 discovery happens outside this pure merge function. Its result is
    passed as ``phase00_release_id``; a non-empty user override wins.
    """

    normalized_settings = dict(user_settings)
    lowered_keys = {str(key).lower() for key in normalized_settings}
    secret_keys = sorted(lowered_keys & _SECRET_SETTING_KEYS)
    if secret_keys:
        raise ValueError(
            "secret values are not valid Phase01 config fields; use the runtime secret store: "
            + ", ".join(secret_keys)
        )

    unknown = sorted(set(normalized_settings) - _PHASE01_USER_SETTING_KEYS)
    if unknown:
        raise ValueError(f"unsupported Phase01 user settings: {', '.join(unknown)}")
    missing = sorted(
        key for key in _PHASE01_REQUIRED_USER_SETTINGS if not str(normalized_settings.get(key, "")).strip()
    )
    if missing:
        raise ValueError(f"missing Phase01 user settings: {', '.join(missing)}")
    batch_id = _validated_runtime_identifier(
        normalized_settings["batch_id"], field_name="batch_id"
    )
    worker_id = _validated_runtime_identifier(
        normalized_settings["worker_id"], field_name="worker_id"
    )

    release_override = str(normalized_settings.get("release_id_override") or "").strip()
    discovered_release = str(phase00_release_id or "").strip()
    release_id = release_override or discovered_release
    if not release_id:
        raise ValueError(
            "Phase00 release could not be resolved; supply phase00_release_id "
            "or an explicit release_id_override"
        )

    configs = load_configs(config_dir)
    storage = copy.deepcopy(configs["storage"])
    release_storage = storage.setdefault("release", {})
    checkpoint_storage = storage.setdefault("checkpoint", {})
    model_artifact_storage = storage.setdefault("model_artifacts", {})
    for target, overrides in (
        (
            release_storage,
            {
                "repo_id": normalized_settings.get("hf_release_repo"),
                "repo_type": normalized_settings.get("hf_repo_type"),
                "revision": normalized_settings.get("hf_release_revision"),
                "prefix": normalized_settings.get("hf_release_prefix"),
            },
        ),
        (
            checkpoint_storage,
            {
                "repo_id": normalized_settings.get("hf_checkpoint_repo"),
                "repo_type": normalized_settings.get("hf_repo_type"),
                "revision": normalized_settings.get("checkpoint_revision"),
                "prefix": normalized_settings.get("checkpoint_prefix"),
            },
        ),
    ):
        for key, value in overrides.items():
            if value is not None:
                target[key] = value
    if normalized_settings.get("scratch_dir") is not None:
        storage["scratch"]["root_override"] = str(normalized_settings["scratch_dir"])
    # Project-owned TransNet and Flashlight runtime artifacts live in the
    # checkpoint repository by default. A repository/revision override must
    # therefore move both stores; their independent prefixes remain versioned
    # in storage.yaml.
    for key, setting in (
        ("repo_id", "hf_checkpoint_repo"),
        ("repo_type", "hf_repo_type"),
        ("revision", "checkpoint_revision"),
    ):
        if normalized_settings.get(setting) is not None:
            model_artifact_storage[key] = normalized_settings[setting]

    payload: dict[str, Any] = {
        "schema_version": "resolved_config_v1",
        "phase01": copy.deepcopy(configs["phase01"]),
        "models": copy.deepcopy(configs["models"].get("phase01", {})),
        "media": copy.deepcopy(configs["media"]),
        "artifact": copy.deepcopy(configs["artifact"]),
        "storage": storage,
        "runtime": {
            "environment": environment or detect_environment(),
            "release_id": release_id,
            "release_id_source": "user_override" if release_override else "phase00_auto_resolve",
            "batch_id": batch_id,
            "worker_id": worker_id,
        },
    }
    asr_provider = str(normalized_settings.get("asr_provider") or "").strip()
    if asr_provider:
        _apply_phase01_asr_provider(payload, asr_provider)
    required_paths = payload["phase01"].get("production_readiness", {}).get(
        "required_non_null_paths", []
    )
    unresolved = tuple(
        sorted(path for path in required_paths if _value_at_path(payload, str(path)) is None)
    )
    digest = _sha256_json(payload)
    stage_config_hashes = _stage_config_hashes(payload)
    return ResolvedPhase01Config(
        payload=payload,
        config_hash=digest,
        stage_config_hashes=stage_config_hashes,
        unresolved_required_fields=unresolved,
    )


def require_phase01_production_ready(config: ResolvedPhase01Config) -> None:
    if not config.production_ready:
        raise ValueError(
            "Phase01 production config has unresolved required fields: "
            + ", ".join(config.unresolved_required_fields)
        )
    _validate_phase01_runtime_invariants(config.payload)


def rebuild_resolved_phase01_config(
    payload: dict[str, Any],
) -> ResolvedPhase01Config:
    """Recompute deterministic identity after a controlled config clone.

    Runtime launchers use this after applying isolated execution storage.  It
    deliberately repeats the production-readiness calculation so no caller can
    retain a stale config or stage hash after changing a store prefix.
    """

    cloned = copy.deepcopy(payload)
    required_paths = cloned["phase01"].get("production_readiness", {}).get(
        "required_non_null_paths", []
    )
    unresolved = tuple(
        sorted(
            path
            for path in required_paths
            if _value_at_path(cloned, str(path)) is None
        )
    )
    return ResolvedPhase01Config(
        payload=cloned,
        config_hash=_sha256_json(cloned),
        stage_config_hashes=_stage_config_hashes(cloned),
        unresolved_required_fields=unresolved,
    )


def persist_resolved_phase01_config(config: ResolvedPhase01Config, path: Path | str) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.partial")
    temporary.write_text(
        json.dumps(config.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(target)
    return target


def _value_at_path(payload: dict[str, Any], dotted_path: str) -> Any:
    value: Any = payload
    for component in dotted_path.split("."):
        if not isinstance(value, dict) or component not in value:
            return None
        value = value[component]
    return value


def _sha256_json(payload: Any) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _stage_config_hashes(payload: dict[str, Any]) -> dict[str, str]:
    """Hash only policy relevant to a stage so independent work stays reusable."""

    phase01 = payload["phase01"]
    models = payload["models"]
    schemas = phase01["schemas"]
    asr_stage_policy = copy.deepcopy(phase01["asr"])
    interval_assignment = asr_stage_policy["alignment"].pop(
        "interval_assignment"
    )
    stage_payloads: dict[str, Any] = {
        "shots": {
            "model": models["shot_detection"],
            "policy": phase01["shot_detection"],
            "schema": schemas["shots"],
        },
        "keyframes": {
            "media": payload["media"],
            "schema": schemas["keyframes"],
        },
        "asr": {
            "model": models["asr"],
            "policy": asr_stage_policy,
            "retry": phase01["retry"],
            "schemas": [schemas["asr_segments"], schemas["asr_words"]],
        },
        "ocr": {
            "model": models["ocr"],
            "policy": phase01["ocr"],
            "retry": phase01["retry"],
            "schema": schemas["ocr"],
        },
        "shot_captions": {
            "model": models["shot_caption"],
            "ocr_model": models["ocr"],
            "api": phase01["api"],
            "retry": phase01["retry"],
            "schema": schemas["shot_captions"],
        },
        "shot_transcript_links": {
            "schema": schemas["shot_transcript_links"],
            "assignment": interval_assignment,
        },
        "scenes": {
            "model": _resolved_semantic_model(models, "scene_boundary"),
            "policy": models["scene_boundary"],
            "ocr_model": models["ocr"],
            "api": phase01["api"],
            "retry": phase01["retry"],
            "grouping": phase01["scene_grouping"],
            "schema": schemas["scenes"],
        },
        "scene_transcript_links": {
            "schema": schemas["scene_transcript_links"],
            "assignment": interval_assignment,
        },
        "scene_summaries": {
            "model": _resolved_semantic_model(models, "scene_summary"),
            "provider_policy": models["scene_summary"],
            "ocr_model": models["ocr"],
            "api": phase01["api"],
            "retry": phase01["retry"],
            "policy": phase01["scene_summary"],
            "schema": schemas["scene_summaries"],
        },
        "package": {
            "artifact": payload["artifact"]["package"],
            "schemas": schemas,
            "batch_id": payload["runtime"]["batch_id"],
            "worker_id": payload["runtime"]["worker_id"],
        },
        "sync": {
            "release": payload["storage"]["release"],
            "artifact": payload["artifact"]["package"],
        },
    }
    return {stage: _sha256_json(value) for stage, value in stage_payloads.items()}


def _provider_keys() -> tuple[str, ...]:
    return ("asr", "ocr", "embedding", "object_detection", "shot_caption", "scene_summary")


def _resolved_semantic_model(
    models: dict[str, Any], stage_key: str
) -> dict[str, Any]:
    stage = copy.deepcopy(models[stage_key])
    model_key = stage.pop("model_key", None)
    if not model_key:
        return stage
    if str(model_key) not in models:
        raise ValueError(f"unknown Phase01 semantic model_key: {model_key}")
    return {**copy.deepcopy(models[str(model_key)]), **stage}


def _validated_runtime_identifier(value: Any, *, field_name: str) -> str:
    text = str(value)
    if (
        not text
        or text != text.strip()
        or text in {".", ".."}
        or any(separator in text for separator in ("/", "\\"))
        or any(ord(character) < 32 for character in text)
    ):
        raise ValueError(
            f"Phase01 {field_name} must be a non-empty path-safe identifier"
        )
    return text


def _validate_phase01_runtime_invariants(payload: dict[str, Any]) -> None:
    execution = payload["phase01"]["execution"]
    expected_execution = {
        "max_concurrent_videos": 1,
        "gpu_heavy_models_resident": 1,
        "checkpoint_after_each_stage": True,
        "release_gpu_objects_before_empty_cache": True,
    }
    for key, expected in expected_execution.items():
        if execution.get(key) != expected:
            raise ValueError(
                f"Phase01 execution.{key} is an enforced invariant and must be "
                f"{expected!r}"
            )

    _validate_semantic_sampling_policy(payload)
    _validate_scene_grouping_policy(payload)
    _validate_asr_alignment_policy(payload)

    models = payload["models"]
    
    caption_model = _resolved_semantic_model(
        models,
        "shot_caption",
    )

    if (
        str(caption_model.get("provider"))
        != "qwen_local"
    ):
        raise ValueError(
            "Phase01 semantic primary must be qwen_local"
        )

    fallbacks = caption_model.get(
        "fallbacks",
        [],
    )

    if (
        not isinstance(fallbacks, list)
        or len(fallbacks) != 1
    ):
        raise ValueError(
            "Phase01 semantic runtime requires "
            "exactly one local fallback"
        )

    fallback = fallbacks[0]

    if (
        str(fallback.get("provider"))
        != "vintern_reasoning_local"
    ):
        raise ValueError(
            "Phase01 semantic fallback must be "
            "vintern_reasoning_local"
        )

    for field in (
        "model_id",
        "model_revision",
    ):
        if not str(
            fallback.get(field, "")
        ).strip():
            raise ValueError(
                "Phase01 semantic fallback "
                f"requires {field}"
            )

    caption_signature = _semantic_runtime_signature(
        caption_model
    )
    for stage_key in ("scene_boundary", "scene_summary"):
        signature = _semantic_runtime_signature(
            _resolved_semantic_model(models, stage_key)
        )
        if signature != caption_signature:
            raise ValueError(
                "Phase01 shared semantic runtime mismatch: "
                f"shot_caption and {stage_key} must use the same primary/fallback "
                "client chain"
            )


def _validate_asr_alignment_policy(payload: dict[str, Any]) -> None:
    policy = payload["phase01"]["asr"].get("alignment")
    if not isinstance(policy, dict):
        raise TypeError("Phase01 asr.alignment must be a mapping")
    if policy.get("required_for_accepted_segments") is not True:
        raise ValueError(
            "Phase01 asr.alignment.required_for_accepted_segments must be true"
        )
    if str(policy.get("policy")) != "ctc_word_alignment_v1":
        raise ValueError("Unsupported Phase01 asr.alignment.policy")
    interval = policy.get("interval_assignment")
    if not isinstance(interval, dict):
        raise TypeError("Phase01 asr.alignment.interval_assignment must be a mapping")
    if str(interval.get("policy")) != "max_overlap_midpoint_v1":
        raise ValueError("Unsupported Phase01 ASR interval assignment policy")
    if str(interval.get("interval_convention")) != "[start_sec, end_sec)":
        raise ValueError("Unsupported Phase01 ASR interval convention")
    reconstruction = policy.get("text_reconstruction")
    if not isinstance(reconstruction, dict) or str(
        reconstruction.get("normalization")
    ) != "unicode_word_v1":
        raise ValueError("Unsupported Phase01 ASR text reconstruction policy")
    asr_model = payload["models"]["asr"]
    if str(asr_model.get("provider")) == "faster_whisper" and asr_model.get(
        "word_timestamps"
    ) is not True:
        raise ValueError(
            "Phase01 faster_whisper ASR requires word_timestamps=true"
        )


def _validate_semantic_sampling_policy(payload: dict[str, Any]) -> None:
    phase01 = payload["phase01"]
    policy = payload["media"]["keyframe"]["semantic_sampling"]
    if str(policy.get("policy")) != "temporal_visual_text_v1":
        raise ValueError("Unsupported Phase01 keyframe semantic sampling policy")
    positive_fields = (
        "target_max_probe_gap_seconds",
        "max_probe_candidates_per_shot",
        "max_supplemental_keyframes_per_shot",
    )
    for field in positive_fields:
        if float(policy.get(field, 0)) <= 0:
            raise ValueError(
                f"Phase01 keyframe semantic_sampling.{field} must be positive"
            )
    if float(policy.get("min_supplemental_separation_seconds", -1)) < 0:
        raise ValueError(
            "Phase01 keyframe semantic_sampling."
            "min_supplemental_separation_seconds must be non-negative"
        )

    visual = policy["visual_novelty"]
    text = policy["text_change"]
    if str(visual.get("policy")) != "dhash_v1" or int(
        visual.get("hash_size", 0)
    ) < 1:
        raise ValueError("Invalid Phase01 dHash semantic sampling config")
    if str(text.get("policy")) != "mser_masked_edge_jaccard_v1":
        raise ValueError("Invalid Phase01 text-change semantic sampling policy")
    for field, value in (
        ("visual_novelty.min_hamming_ratio", visual.get("min_hamming_ratio")),
        ("text_change.min_jaccard_distance", text.get("min_jaccard_distance")),
    ):
        if value is None or not 0 <= float(value) <= 1:
            raise ValueError(
                f"Phase01 keyframe semantic_sampling.{field} must be in [0, 1]"
            )
    for field in (
        "max_long_side",
        "signature_width",
        "signature_height",
        "min_plausible_regions",
    ):
        if int(text.get(field, 0)) < 1:
            raise ValueError(
                f"Phase01 keyframe semantic_sampling.text_change.{field} "
                "must be positive"
            )
    canny_low = int(text.get("canny_low", -1))
    canny_high = int(text.get("canny_high", -1))
    if canny_low < 0 or canny_high <= canny_low:
        raise ValueError(
            "Phase01 keyframe semantic_sampling.text_change Canny thresholds "
            "must satisfy 0 <= canny_low < canny_high"
        )

    if bool(policy.get("enabled", False)):
        ocr_roles = {
            str(role) for role in phase01["ocr"]["run_on_keyframe_roles"]
        }
        focused_roles = {
            str(role)
            for role in phase01["scene_grouping"][
                "focused_review_keyframe_roles"
            ]
        }
        if "supplemental" not in ocr_roles:
            raise ValueError(
                "Enabled semantic sampling requires supplemental OCR evidence"
            )
        if not {"early", "late", "supplemental"}.issubset(focused_roles):
            raise ValueError(
                "Enabled semantic sampling requires early/late/supplemental "
                "focused scene evidence"
            )


def _validate_scene_grouping_policy(payload: dict[str, Any]) -> None:
    grouping = payload["phase01"]["scene_grouping"]
    non_boundary = float(grouping.get("non_boundary_threshold", -1))
    boundary = float(grouping.get("boundary_threshold", -1))
    if not 0 <= non_boundary < boundary <= 1:
        raise ValueError(
            "Phase01 scene_grouping thresholds must satisfy "
            "0 <= non_boundary_threshold < boundary_threshold <= 1"
        )
    if int(grouping.get("max_consistency_review_rounds", -1)) < 0:
        raise ValueError(
            "Phase01 scene_grouping.max_consistency_review_rounds must be "
            "non-negative"
        )

    quality = grouping.get("quality_guard")
    if not isinstance(quality, dict):
        raise TypeError("Phase01 scene_grouping.quality_guard must be a mapping")
    if type(quality.get("enabled")) is not bool:
        raise ValueError(
            "Phase01 scene_grouping.quality_guard.enabled must be bool"
        )
    if int(quality.get("min_shot_count", 0)) < 2:
        raise ValueError(
            "Phase01 scene_grouping.quality_guard.min_shot_count must be >= 2"
        )
    for field in (
        "suspicious_boundary_density",
        "suspicious_one_shot_scene_rate",
    ):
        value = float(quality.get(field, 0))
        if not 0 < value <= 1:
            raise ValueError(
                f"Phase01 scene_grouping.quality_guard.{field} must be in (0, 1]"
            )
    if str(quality.get("unresolved_action")) != "fail_terminal":
        raise ValueError(
            "Phase01 scene_grouping.quality_guard.unresolved_action must be "
            "fail_terminal"
        )

    review = quality.get("degenerate_review")
    if not isinstance(review, dict):
        raise TypeError(
            "Phase01 scene_grouping.quality_guard.degenerate_review must be a mapping"
        )
    if type(review.get("enabled")) is not bool:
        raise ValueError(
            "Phase01 scene_grouping.quality_guard.degenerate_review.enabled must be bool"
        )
    if int(review.get("focus_gap_count", 0)) < 1:
        raise ValueError(
            "Phase01 scene_grouping.quality_guard.degenerate_review."
            "focus_gap_count must be positive"
        )
    if int(review.get("context_shots_each_side", -1)) < 0:
        raise ValueError(
            "Phase01 scene_grouping.quality_guard.degenerate_review."
            "context_shots_each_side must be non-negative"
        )
    if int(review.get("max_rounds", -1)) < 0:
        raise ValueError(
            "Phase01 scene_grouping.quality_guard.degenerate_review.max_rounds "
            "must be non-negative"
        )


def _semantic_runtime_signature(model: dict[str, Any]) -> dict[str, Any]:
    runtime_keys = (
        "provider",
        "sdk",
        "sdk_version",
        "model_id",
        "model_revision",
        "thinking_level",
        "trust_remote_code",
        "torch_dtype",
        "device_map",
        "padding_side",
        "quantization",
        "low_cpu_mem_usage",
        "use_fast_tokenizer",
        "use_flash_attn",
        "max_new_tokens",
        "image_size",
        "max_dynamic_patches",
        "use_thumbnail",
        "do_sample",
        "num_beams",
        "repetition_penalty",
    )
    # Note: generation_contract_version is intentionally excluded. It is a
    # task/output contract that legitimately differs between shot_caption and
    # scene_summary; it must not participate in the shared-runtime invariant.

    def client_signature(config: dict[str, Any]) -> dict[str, Any]:
        return {
            key: copy.deepcopy(config[key])
            for key in runtime_keys
            if key in config
        }

    return {
        "primary": client_signature(model),
        "fallbacks": [
            client_signature(dict(fallback))
            for fallback in model.get("fallbacks", [])
        ],
    }


def _apply_phase01_asr_provider(payload: dict[str, Any], provider: str) -> None:
    providers = payload["models"].get("asr_providers", {})
    if provider not in providers:
        available = ", ".join(sorted(providers)) or "none"
        raise ValueError(
            f"unsupported Phase01 ASR provider override: {provider}; available: {available}"
        )
    payload["models"]["asr"] = copy.deepcopy(providers[provider])
