from __future__ import annotations

import importlib.metadata
import importlib.util
import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from huggingface_hub import HfApi

from system1.artifacts.hf_store import HuggingFaceDatasetArtifactStore
from system1.artifacts.reports import utc_now
from system1.config import ResolvedPhase01Config, require_phase01_production_ready
from system1.shots import load_transnet_artifact


@dataclass(frozen=True)
class PreflightResult:
    environment: str
    release_id: str
    batch_id: str
    cuda_available: bool
    scratch_free_gb: float
    versions: dict[str, str]


def run_phase01_preflight(
    config: ResolvedPhase01Config,
    *,
    release_dir: Path,
    transnet_artifact_dir: Path,
    scratch_root: Path,
    validate_remote: bool = True,
) -> PreflightResult:
    require_phase01_production_ready(config)
    runtime = config.payload["runtime"]
    if config.payload["phase01"]["api"].get("request_cache_backend") != "stage_local":
        raise RuntimeError("Phase01 Gemini request cache backend must be stage_local")
    batch_path = release_dir / "manifests" / f"{runtime['batch_id']}.txt"
    required = [
        release_dir / "tables" / "videos.parquet",
        release_dir / "raw_mapping" / "media_store_manifest.parquet",
        batch_path,
    ]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError("Phase00 local handoff is incomplete: " + ", ".join(missing))
    for executable in ("ffmpeg", "ffprobe"):
        if shutil.which(executable) is None:
            raise RuntimeError(f"Required executable is unavailable: {executable}")
    if not os.environ.get("GEMINI_API_KEY") and not os.environ.get("GOOGLE_API_KEY"):
        raise RuntimeError("GEMINI_API_KEY or GOOGLE_API_KEY is required")
    if not os.environ.get("AIC_HF_TOKEN") and not os.environ.get("HF_TOKEN"):
        raise RuntimeError("AIC_HF_TOKEN or HF_TOKEN is required")
    _validate_phase00_batch(release_dir, batch_path)
    _validate_prompt_files(config)

    scratch_root.mkdir(parents=True, exist_ok=True)
    scratch_free_gb = shutil.disk_usage(scratch_root).free / (1024**3)
    required_free_gb = float(config.payload["phase01"]["execution"]["min_scratch_free_gb"])
    if scratch_free_gb < required_free_gb:
        raise RuntimeError(
            f"Scratch free space is too low: {scratch_free_gb:.2f} GiB "
            f"< {required_free_gb:.2f} GiB"
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

    versions: dict[str, str] = {}
    for package in (
        "faster-whisper",
        "google-genai",
        "huggingface-hub",
        "opencv-python-headless",
        "pillow",
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
    expected = config.payload["models"]
    asr_model = expected["asr"]
    asr_provider = str(asr_model.get("provider", "faster_whisper"))
    if asr_provider == "faster_whisper":
        if versions["faster-whisper"] != str(asr_model["package_version"]):
            raise RuntimeError("Installed faster-whisper version differs from resolved config")
    elif asr_provider == "nemo":
        try:
            nemo_available = importlib.util.find_spec("nemo.collections.asr") is not None
        except ModuleNotFoundError:
            nemo_available = False
        if not nemo_available:
            raise RuntimeError("nemo_toolkit[asr] is required for configured NeMo ASR")
    else:
        raise RuntimeError(f"Unsupported Phase01 ASR provider: {asr_provider}")
    if versions["google-genai"] != str(expected["shot_caption"]["sdk_version"]):
        raise RuntimeError("Installed google-genai version differs from resolved config")
    if versions["torch"] == "missing":
        raise RuntimeError("PyTorch is required for TransNet V2")
    return PreflightResult(
        environment=str(runtime["environment"]),
        release_id=str(runtime["release_id"]),
        batch_id=str(runtime["batch_id"]),
        cuda_available=cuda_available,
        scratch_free_gb=scratch_free_gb,
        versions=versions,
    )


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
        str(config.payload["phase01"]["api"]["schema_repair_prompt_version"]),
        str(models["shot_caption"]["prompt_version"]),
        str(models["scene_boundary"]["prompt_version"]),
        str(models["scene_boundary"]["focused_prompt_version"]),
        str(models["scene_boundary"]["consistency_prompt_version"]),
        str(models["scene_summary"]["prompt_version"]),
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
