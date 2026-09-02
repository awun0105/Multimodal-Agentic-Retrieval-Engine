from __future__ import annotations

import importlib
import importlib.metadata
import importlib.util
import json
import os
import platform
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from huggingface_hub import HfApi

from system1.artifacts.hf_store import HuggingFaceDatasetArtifactStore
from system1.artifacts.reports import utc_now
from system1.asr.runtime_artifact import validate_installed_flashlight_runtime
from system1.config import ResolvedPhase01Config, require_phase01_production_ready
from system1.shots import load_transnet_artifact

_EXPECTED_TORCH_STACK = {
    "torch": "2.8.0",
    "torchaudio": "2.8.0",
    "torchvision": "0.23.0",
}


@dataclass(frozen=True)
class PreflightResult:
    environment: str
    release_id: str
    batch_id: str
    cuda_available: bool
    scratch_free_gb: float
    model_cache_free_gb: float | None
    versions: dict[str, str]


@dataclass(frozen=True)
class RuntimePreflightResult:
    environment: str
    release_id: str
    batch_id: str
    cuda_available: bool
    scratch_free_gb: float
    model_cache_free_gb: float | None
    versions: dict[str, str]


def run_phase01_preflight(
    config: ResolvedPhase01Config,
    *,
    release_dir: Path,
    transnet_artifact_dir: Path,
    scratch_root: Path,
    validate_remote: bool = True,
    runtime_result: RuntimePreflightResult | None = None,
) -> PreflightResult:
    require_phase01_production_ready(config)
    runtime = config.payload["runtime"]
    batch_path = release_dir / "manifests" / f"{runtime['batch_id']}.txt"
    required = [
        release_dir / "tables" / "videos.parquet",
        release_dir / "raw_mapping" / "media_store_manifest.parquet",
        batch_path,
    ]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError("Phase00 local handoff is incomplete: " + ", ".join(missing))
    _validate_phase00_batch(release_dir, batch_path)
    _validate_prompt_files(config)

    checked_runtime = runtime_result or run_phase01_runtime_preflight(
        config,
        scratch_root=scratch_root,
    )

    shot_model = config.payload["models"]["shot_detection"]
    load_transnet_artifact(
        transnet_artifact_dir,
        expected_commit=str(shot_model["model_revision"]),
        expected_source_sha256=str(shot_model["source_sha256"]),
        expected_weights_sha256=str(shot_model["weights_sha256"]),
        expected_conversion_verified=bool(shot_model.get("conversion_verified", True)),
    )
    if validate_remote:
        storage_cache = scratch_root / ".hf_cache" / "storage_preflight"
        try:
            run_phase01_storage_preflight(config, cache_dir=storage_cache)
        finally:
            shutil.rmtree(storage_cache, ignore_errors=True)

    return PreflightResult(
        environment=checked_runtime.environment,
        release_id=checked_runtime.release_id,
        batch_id=checked_runtime.batch_id,
        cuda_available=checked_runtime.cuda_available,
        scratch_free_gb=checked_runtime.scratch_free_gb,
        model_cache_free_gb=checked_runtime.model_cache_free_gb,
        versions=dict(checked_runtime.versions),
    )


def run_phase01_runtime_preflight(
    config: ResolvedPhase01Config,
    *,
    scratch_root: Path,
) -> RuntimePreflightResult:
    """Validate the fresh runtime without requiring a Phase00 handoff."""

    require_phase01_production_ready(config)
    runtime = config.payload["runtime"]
    if config.payload["phase01"]["api"].get("request_cache_backend") != "stage_local":
        raise RuntimeError("Phase01 request cache backend must be stage_local")
    for executable in ("ffmpeg", "ffprobe"):
        if shutil.which(executable) is None:
            raise RuntimeError(f"Required executable is unavailable: {executable}")
    if not os.environ.get("AIC_HF_TOKEN") and not os.environ.get("HF_TOKEN"):
        raise RuntimeError("AIC_HF_TOKEN or HF_TOKEN is required")

    scratch_root.mkdir(parents=True, exist_ok=True)
    scratch_free_gb = shutil.disk_usage(scratch_root).free / (1024**3)
    required_free_gb = float(config.payload["phase01"]["execution"]["min_scratch_free_gb"])
    if scratch_free_gb < required_free_gb:
        raise RuntimeError(
            f"Scratch free space is too low: {scratch_free_gb:.2f} GiB "
            f"< {required_free_gb:.2f} GiB"
        )
    models = config.payload["models"]
    model_cache_free_gb = _validate_model_cache_free_space(config, models)

    versions: dict[str, str] = {"python": platform.python_version()}
    for package in (
        "accelerate",
        "bitsandbytes",
        "einops",
        "faster-whisper",
        "huggingface-hub",
        "nemo-toolkit",
        "numpy",
        "onnx",
        "onnxruntime",
        "opencv-python-headless",
        "pandas",
        "pillow",
        "psutil",
        "pyarrow",
        "qwen-vl-utils",
        "sentencepiece",
        "timm",
        "torchaudio",
        "torchvision",
        "transformers",
    ):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = "missing"
    cuda_available = False
    try:
        import torch

        versions["torch"] = str(torch.__version__)
        cuda_available = bool(torch.cuda.is_available())
    except ImportError:
        versions["torch"] = "missing"
    for torch_package in ("torchaudio", "torchvision"):
        try:
            module = importlib.import_module(torch_package)
            versions[torch_package] = str(module.__version__)
        except (ImportError, OSError) as exc:
            raise RuntimeError(
                f"{torch_package} could not initialize; check PyTorch stack ABI compatibility"
            ) from exc
    for torch_package, expected_version in _EXPECTED_TORCH_STACK.items():
        actual_version = versions.get(torch_package, "missing").split("+")[0]
        if actual_version != expected_version:
            raise RuntimeError(
                f"Installed {torch_package} version {actual_version} differs from "
                f"required {expected_version}"
            )
    expected = models
    asr_model = expected["asr"]
    asr_provider = str(asr_model.get("provider", "nemo"))
    if asr_provider == "faster_whisper":
        if versions["faster-whisper"] != str(asr_model["package_version"]):
            raise RuntimeError("Installed faster-whisper version differs from resolved config")
    elif asr_provider == "nemo":
        if versions["nemo-toolkit"] != str(asr_model["package_version"]):
            raise RuntimeError("Installed nemo-toolkit version differs from resolved config")
        if versions["faster-whisper"] != "1.2.1":
            raise RuntimeError(
                "Installed faster-whisper version differs from the pinned Silero VAD runtime"
            )
        try:
            importlib.import_module("nemo.collections.asr")
            aligner_utils = importlib.import_module(
                "nemo.collections.asr.parts.utils.aligner_utils"
            )
        except (ImportError, AttributeError, RuntimeError, OSError) as exc:
            raise RuntimeError(
                "nemo_toolkit[asr] could not initialize for configured NeMo ASR"
            ) from exc
        if not callable(getattr(aligner_utils, "get_utt_obj", None)):
            raise RuntimeError(
                "Pinned NeMo runtime does not expose tokenizer-aware alignment"
            )
        _validate_nemo_asr_contract(asr_model)
        validate_installed_flashlight_runtime(
            artifact_config=asr_model["decoder"]["runtime_artifact"]
        )
    else:
        raise RuntimeError(f"Unsupported Phase01 ASR provider: {asr_provider}")
    _validate_dataframe_runtime_imports()
    _validate_transformers_runtime_imports()
    _validate_local_vlm_dependencies(expected, versions=versions)
    if versions["torch"] == "missing":
        raise RuntimeError("PyTorch is required for TransNet V2")
    return RuntimePreflightResult(
        environment=str(runtime["environment"]),
        release_id=str(runtime["release_id"]),
        batch_id=str(runtime["batch_id"]),
        cuda_available=cuda_available,
        scratch_free_gb=scratch_free_gb,
        model_cache_free_gb=model_cache_free_gb,
        versions=versions,
    )


def _validate_nemo_asr_contract(asr_model: dict[str, Any]) -> None:
    segmentation = asr_model.get("segmentation", {})
    decoder = asr_model.get("decoder", {})
    quality = asr_model.get("quality_gate", {})
    if segmentation.get("provider") != "silero_vad_onnx":
        raise RuntimeError("Production NeMo ASR requires Silero ONNX VAD")
    if float(segmentation.get("max_speech_seconds", 0)) > 30:
        raise RuntimeError("Production NeMo ASR speech segments may not exceed 30 seconds")
    if decoder.get("strategy") != "flashlight" or int(
        decoder.get("beam_size", 0)
    ) != 64:
        raise RuntimeError("Production NeMo ASR requires Flashlight beam size 64")
    for field in (
        "model_sha256",
        "model_revision",
        "model_file",
    ):
        _require_sha_or_value(asr_model, field)
    for field in (
        "language_model_sha256",
        "lexicon_sha256",
        "language_model_file",
        "lexicon_file",
    ):
        _require_sha_or_value(decoder, field)
    if not bool(quality.get("require_acoustic_metrics")):
        raise RuntimeError("Production NeMo ASR quality gate requires alignments")


def _require_sha_or_value(config: dict[str, Any], field: str) -> None:
    value = str(config.get(field, "")).strip()
    if not value:
        raise RuntimeError(f"Production NeMo ASR field is missing: {field}")
    if field.endswith("sha256") and (
        len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise RuntimeError(f"Production NeMo ASR checksum is invalid: {field}")


def run_phase01_storage_preflight(
    config: ResolvedPhase01Config,
    *,
    cache_dir: Path | str | None = None,
) -> None:
    """Prove release access and checkpoint write/read before heavy work."""

    storage = config.payload["storage"]
    token = os.environ.get("AIC_HF_TOKEN") or os.environ.get("HF_TOKEN")
    api = HfApi(token=token)
    release = storage["release"]
    checkpoint = storage["checkpoint"]
    api.repo_info(
        repo_id=release["repo_id"],
        repo_type=release["repo_type"],
        revision=release.get("revision", "main"),
    )
    checkpoint_info = api.repo_info(
        repo_id=checkpoint["repo_id"],
        repo_type=checkpoint["repo_type"],
        revision=checkpoint.get("revision", "main"),
    )
    if checkpoint.get("require_private") and not checkpoint_info.private:
        raise RuntimeError(
            "Phase01 checkpoint repository is public but require_private=true"
        )

    store = HuggingFaceDatasetArtifactStore(
        repo_id=str(checkpoint["repo_id"]),
        repo_type=str(checkpoint.get("repo_type", "dataset")),
        revision=str(checkpoint.get("revision", "main")),
        token=token,
        prefix=str(checkpoint.get("prefix", "")),
        cache_dir=cache_dir,
    )
    runtime = config.payload["runtime"]
    proof_path = (
        Path("phase01_checkpoints")
        / "_preflight"
        / f"{runtime['release_id']}_{runtime['worker_id']}.json"
    )
    payload = {
        "schema_version": "phase01_preflight_write_v1",
        "release_id": runtime["release_id"],
        "worker_id": runtime["worker_id"],
        "config_hash": config.config_hash,
        "checked_at": utc_now(),
    }
    store.write_json(proof_path, payload)
    restored = store.read_json(proof_path)
    if json.dumps(restored, sort_keys=True) != json.dumps(payload, sort_keys=True):
        raise RuntimeError("Checkpoint repository write/read proof did not round-trip")


def _validate_phase00_batch(release_dir: Path, batch_path: Path) -> None:
    import pandas as pd

    video_ids = [
        line.strip()
        for line in batch_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not video_ids:
        raise RuntimeError(f"Phase00 batch manifest is empty: {batch_path}")
    if len(video_ids) != len(set(video_ids)):
        raise RuntimeError(f"Phase00 batch manifest contains duplicate video IDs: {batch_path}")
    videos = pd.read_parquet(release_dir / "tables" / "videos.parquet")
    media = pd.read_parquet(release_dir / "raw_mapping" / "media_store_manifest.parquet")
    duplicate_videos = sorted(
        videos.loc[videos["video_id"].astype(str).duplicated(), "video_id"].astype(str).unique()
    )
    duplicate_media = sorted(
        media.loc[media["video_id"].astype(str).duplicated(), "video_id"].astype(str).unique()
    )
    if duplicate_videos or duplicate_media:
        raise RuntimeError(
            "Phase00 handoff contains duplicate IDs: "
            f"videos={duplicate_videos[:10]}, media={duplicate_media[:10]}"
        )
    missing_videos = sorted(set(video_ids) - set(videos["video_id"].astype(str)))
    missing_media = sorted(set(video_ids) - set(media["video_id"].astype(str)))
    video_rows = {
        str(row["video_id"]): row for row in videos.to_dict("records")
    }
    missing_timelines = []
    for video_id in video_ids:
        row = video_rows.get(video_id, {})
        ref = row.get("frame_timeline_ref")
        if ref is None or pd.isna(ref) or not str(ref).strip():
            ref = f"frame_timeline/{video_id}.parquet"
        if not (release_dir / str(ref)).is_file():
            missing_timelines.append(video_id)
    if missing_videos or missing_media or missing_timelines:
        raise RuntimeError(
            "Phase00 batch handoff is inconsistent: "
            f"missing_videos={missing_videos[:10]}, "
            f"missing_media={missing_media[:10]}, "
            f"missing_timelines={missing_timelines[:10]}"
        )
    canonical_required = {
        "canonical_repo_id",
        "canonical_repo_type",
        "canonical_revision",
        "canonical_prefix",
        "canonical_video_path",
        "canonical_metadata_path",
    }
    missing_columns = sorted(canonical_required - set(media.columns))
    if missing_columns:
        raise RuntimeError(
            "Phase00 media_store_manifest is missing canonical columns: "
            + ", ".join(missing_columns)
        )
    selected_media = media[media["video_id"].astype(str).isin(video_ids)]
    null_canonical: dict[str, list[str]] = {}
    for column in sorted(canonical_required):
        missing_mask = selected_media[column].isna() | (
            selected_media[column].astype(str).str.strip() == ""
        )
        if missing_mask.any():
            null_canonical[column] = sorted(
                selected_media.loc[missing_mask, "video_id"].astype(str).tolist()
            )[:10]
    if null_canonical:
        raise RuntimeError(
            f"Phase00 media_store_manifest has null canonical values: {null_canonical}"
        )


def _validate_prompt_files(config: ResolvedPhase01Config) -> None:
    models = config.payload["models"]
    versions = {
        str(models["ocr"]["prompt_version"]),
        *map(str, models["shot_caption"]["prompt_versions"].values()),
        str(models["scene_boundary"]["prompt_version"]),
        str(models["scene_boundary"]["focused_prompt_version"]),
        str(models["scene_boundary"]["consistency_prompt_version"]),
        str(models["scene_boundary"]["degenerate_prompt_version"]),
        *map(str, models["scene_summary"]["prompt_versions"].values()),
    }
    prompt_root = Path(__file__).resolve().parents[3] / "prompts"
    missing = []
    for version in sorted(versions):
        if Path(version).name != version:
            raise RuntimeError(f"Unsafe Phase01 prompt version: {version}")
        path = prompt_root / f"{version}.txt"
        if not path.is_file() or not path.read_text(encoding="utf-8").strip():
            missing.append(str(path))
    if missing:
        raise RuntimeError("Phase01 prompt files are missing or empty: " + ", ".join(missing))





LOCAL_VLM_PROVIDERS = {
    "qwen_local",
    "vintern_local",
    "vintern_reasoning_local",
}


def _validate_dataframe_runtime_imports() -> None:
    try:
        import numpy as np
        import pandas as pd
        import pyarrow as pa
    except (ImportError, RuntimeError, ValueError, OSError) as exc:
        raise RuntimeError(
            "NumPy/Pandas/PyArrow could not initialize; check the runtime ABI stack"
        ) from exc
    values = np.asarray([1, 2, 3], dtype=np.int64)
    frame = pd.DataFrame({"value": values})
    table = pa.Table.from_pandas(frame, preserve_index=False)
    if int(values.sum()) != 6 or table.num_rows != 3:
        raise RuntimeError("NumPy/Pandas/PyArrow runtime sanity check failed")


def _validate_transformers_runtime_imports() -> None:
    try:
        from transformers import (
            AutoModel,
            AutoProcessor,
            AutoTokenizer,
            GenerationConfig,
            LlamaForCausalLM,
            Qwen2_5_VLForConditionalGeneration,
            Qwen2ForCausalLM,
        )
    except (ImportError, RuntimeError, OSError) as exc:
        raise RuntimeError(
            "Transformers Phase01 model classes could not initialize"
        ) from exc
    required = (
        AutoModel,
        AutoProcessor,
        AutoTokenizer,
        GenerationConfig,
        LlamaForCausalLM,
        Qwen2ForCausalLM,
        Qwen2_5_VLForConditionalGeneration,
    )
    if any(value is None for value in required):  # pragma: no cover - import contract guard
        raise RuntimeError("Transformers Phase01 model class import returned None")


def _local_vlm_models(models: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        models.get("ocr", {}),
        models.get("shot_caption", {}),
        *models.get("shot_caption", {}).get("fallbacks", []),
    ]


def _validate_local_vlm_dependencies(
    models: dict[str, Any], *, versions: dict[str, str]
) -> None:
    local_models = _local_vlm_models(models)
    if not any(str(model.get("provider")) in LOCAL_VLM_PROVIDERS for model in local_models):
        return
    required_modules = {
        "transformers": "transformers",
        "accelerate": "accelerate",
        "torch": "torch",
        "torchvision": "torchvision",
        "PIL": "pillow",
    }
    if any(str(model.get("provider")) == "qwen_local" for model in local_models):
        required_modules["qwen_vl_utils"] = "qwen-vl-utils"
        required_modules["bitsandbytes"] = "bitsandbytes"
    missing = [
        package
        for module, package in required_modules.items()
        if importlib.util.find_spec(module) is None
    ]
    if missing:
        raise RuntimeError(
            "Local VLM dependencies are missing: "
            + ", ".join(sorted(missing))
            + ". Install system1[phase01-production]."
        )
    qwen_models = [
        model for model in local_models if str(model.get("provider")) == "qwen_local"
    ]
    if not qwen_models:
        return
    configured_versions = {
        str(model.get("quantization", {}).get("package_version", ""))
        for model in qwen_models
    }
    configured_versions.discard("")
    if configured_versions and versions["bitsandbytes"] not in configured_versions:
        raise RuntimeError(
            "Installed bitsandbytes version differs from resolved Qwen quantization config"
        )
    try:
        torch = importlib.import_module("torch")
        cextension = importlib.import_module("bitsandbytes.cextension")
    except (ImportError, RuntimeError) as exc:
        raise RuntimeError("bitsandbytes could not initialize for Qwen 4-bit") from exc
    if bool(torch.cuda.is_available()) and not bool(
        getattr(getattr(cextension, "lib", None), "compiled_with_cuda", False)
    ):
        raise RuntimeError(
            "bitsandbytes has no CUDA native backend for the installed PyTorch CUDA build"
        )


def _validate_model_cache_free_space(
    config: ResolvedPhase01Config, models: dict[str, Any]
) -> float | None:
    if not _uses_local_vlm(models):
        return None
    required_free_gb = float(
        config.payload["phase01"]["execution"].get("min_model_cache_free_gb", 0)
    )
    if required_free_gb <= 0:
        return None
    cache_root = _hf_model_cache_root()
    cache_root.mkdir(parents=True, exist_ok=True)
    free_gb = shutil.disk_usage(cache_root).free / (1024**3)
    if free_gb < required_free_gb:
        raise RuntimeError(
            f"Model cache free space is too low: {free_gb:.2f} GiB "
            f"< {required_free_gb:.2f} GiB. Set HF_HOME to a larger runtime disk."
        )
    return free_gb


def _uses_local_vlm(models: dict[str, Any]) -> bool:
    return any(
        str(model.get("provider")) in LOCAL_VLM_PROVIDERS
        for model in _local_vlm_models(models)
    )


def _hf_model_cache_root() -> Path:
    explicit = os.environ.get("HF_HOME") or os.environ.get("HF_HUB_CACHE")
    if explicit:
        return Path(explicit).expanduser()
    return Path("~/.cache/huggingface").expanduser()
