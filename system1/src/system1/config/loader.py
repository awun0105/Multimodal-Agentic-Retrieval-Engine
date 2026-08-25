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
    "gemini_api_key",
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
    # The project-owned TransNet bundle lives in the checkpoint repository by
    # default. A repository/revision override must therefore move both stores;
    # their independent prefixes remain versioned in storage.yaml.
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
            "policy": phase01["asr"],
            "retry": phase01["retry"],
            "schema": schemas["asr_segments"],
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
        },
        "scenes": {
            "model": _resolved_semantic_model(models, "scene_boundary"),
            "policy": models["scene_boundary"],
            "ocr_model": models["ocr"],
            "api": phase01["api"],
            "retry": phase01["retry"],
            "grouping": phase01["scene_grouping"],
            "schemas": [schemas["scenes"], schemas["scene_transcript_links"]],
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

    models = payload["models"]
    caption_signature = _semantic_runtime_signature(
        _resolved_semantic_model(models, "shot_caption")
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
    )

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
