from __future__ import annotations

import argparse
import gc
import hashlib
import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import traceback
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import yaml

from system1.phase01_qualification import (
    allowlisted_environment,
    classify_pip_check,
    load_qualification_config,
    python_version_matches,
    runtime_identity,
    sanitize_payload,
    utc_now,
    write_json_atomic,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--context", required=True, type=Path)
    args = parser.parse_args()
    context = json.loads(args.context.read_text(encoding="utf-8"))
    report_path = Path(context["report_path"])
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["worker_pid"] = os.getpid()
    report["environment"] = {
        "python": platform.python_version(),
        "python_executable": str(Path(sys.executable).resolve()),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "allowlisted_environment": allowlisted_environment(),
    }
    report["runtime_identity"] = runtime_identity()
    report["git"] = _git_identity(Path(context["project_root"]))
    report["installer"] = context.get("installer", {})
    report["checks"] = {}
    report["resources"] = {}
    report["warnings"] = []
    report["failed_check"] = None
    report["error"] = None

    config = load_qualification_config(context["qualification_config_path"])
    candidate_profile = config["candidates"][context["candidate"]]
    run_dir = Path(context["run_dir"])
    models = yaml.safe_load(
        (Path(context["project_root"]) / "configs" / "models.yaml").read_text(
            encoding="utf-8"
        )
    )["phase01"]
    state: dict[str, Any] = {}

    def run_check(name: str, function: Callable[[], Mapping[str, Any] | None]) -> bool:
        started_at = utc_now()
        started = time.monotonic()
        try:
            details = dict(function() or {})
            report["checks"][name] = {
                "status": "pass",
                "started_at": started_at,
                "finished_at": utc_now(),
                "elapsed_seconds": round(time.monotonic() - started, 6),
                **sanitize_payload(details),
            }
            return True
        except Exception as exc:  # noqa: BLE001 - qualification must persist evidence
            error = {
                "type": type(exc).__name__,
                "message": str(exc),
                "traceback": traceback.format_exc(),
            }
            report["checks"][name] = {
                "status": "fail",
                "started_at": started_at,
                "finished_at": utc_now(),
                "elapsed_seconds": round(time.monotonic() - started, 6),
                "error": sanitize_payload(error),
            }
            if report["failed_check"] is None:
                report["failed_check"] = name
                report["error"] = sanitize_payload(error)
            return False

    try:
        run_check(
            "python_runtime",
            lambda: _check_python_runtime(str(candidate_profile["requires_python"])),
        )
        run_check("abi_parquet", _check_abi_parquet)
        run_check("transformers_imports", _check_transformers_imports)
        run_check("cuda", lambda: _check_cuda(state))
        run_check("fixture", lambda: _prepare_fixture(config["fixture"], run_dir, state))
        if _passed(report, "fixture") and _passed(report, "cuda"):
            run_check(
                "flashlight_runtime",
                lambda: _check_flashlight_runtime(models["asr"]),
            )
            if _passed(report, "flashlight_runtime"):
                run_check("nemo_restore", lambda: _check_nemo_restore(models["asr"], state))
            if _passed(report, "nemo_restore"):
                run_check("nemo_transcribe", lambda: _check_nemo_transcribe(models["asr"], state))
            if _passed(report, "nemo_transcribe"):
                run_check("nemo_normalize", lambda: _check_nemo_normalize(models["asr"], state))
            run_check("vintern_1b", lambda: _check_vintern_1b(models["ocr"], state))
            run_check(
                "vintern_3b",
                lambda: _check_vintern_3b(models["shot_caption"]["fallbacks"][0], state),
            )
            run_check("qwen25_vl", lambda: _check_qwen(models["shot_caption"], state))
        else:
            report["warnings"].append(
                "model inference checks were skipped because CUDA or fixture qualification failed"
            )
        run_check("gpu_cleanup", lambda: _check_gpu_cleanup(config["cleanup"], state))
        run_check("pip_check", lambda: _check_pip(report))
        report["installed_packages"] = _installed_packages()
        required = {
            "python_runtime",
            "abi_parquet",
            "transformers_imports",
            "cuda",
            "fixture",
            "flashlight_runtime",
            "nemo_restore",
            "nemo_transcribe",
            "nemo_normalize",
            "vintern_1b",
            "vintern_3b",
            "qwen25_vl",
            "gpu_cleanup",
            "pip_check",
        }
        passing = all(_passed(report, name) for name in required)
        report["status"] = "pass" if passing else "fail"
        report["ready_to_pin_production"] = passing
    except Exception as exc:  # noqa: BLE001 - retain controller-level failure
        report["status"] = "fail"
        report["ready_to_pin_production"] = False
        report["failed_check"] = report.get("failed_check") or "qualification_worker"
        report["error"] = sanitize_payload(
            {
                "type": type(exc).__name__,
                "message": str(exc),
                "traceback": traceback.format_exc(),
            }
        )
    finally:
        _release_gpu()
        report["finished_at"] = utc_now()
        write_json_atomic(report_path, report)
        _try_upload_report(report_path, config.get("report", {}), report)
        write_json_atomic(report_path, report)

    print(json.dumps({"status": report["status"], "report": str(report_path)}))
    raise SystemExit(0 if report["status"] == "pass" else 1)


def _check_python_runtime(specifier: str) -> dict[str, Any]:
    if not python_version_matches(specifier):
        raise RuntimeError(
            f"Python {platform.python_version()} does not satisfy candidate {specifier}"
        )
    return {"requires_python": specifier, "actual_python": platform.python_version()}


def _check_abi_parquet() -> dict[str, Any]:
    import numpy as np
    import pandas as pd
    import pyarrow as pa

    values = np.asarray([1.0, 2.0, 3.0], dtype=np.float64)
    if float(values.sum()) != 6.0:
        raise RuntimeError("NumPy numeric operation returned an unexpected result")
    frame = pd.DataFrame({"value": values, "label": ["a", "b", "c"]})
    table = pa.Table.from_pandas(frame, preserve_index=False)
    import tempfile

    with tempfile.TemporaryDirectory(prefix="phase01_qualification_parquet_") as tmp:
        path = Path(tmp) / "roundtrip.parquet"
        frame.to_parquet(path, index=False)
        restored = pd.read_parquet(path)
    if restored.to_dict("records") != frame.to_dict("records"):
        raise RuntimeError("Pandas/PyArrow Parquet round trip changed rows")
    return {
        "numpy": np.__version__,
        "pandas": pd.__version__,
        "pyarrow": pa.__version__,
        "rows": table.num_rows,
    }


def _check_transformers_imports() -> dict[str, Any]:
    import transformers
    from transformers import (
        AutoModel,
        AutoProcessor,
        AutoTokenizer,
        GenerationConfig,
        LlamaForCausalLM,
        Qwen2ForCausalLM,
        Qwen2_5_VLForConditionalGeneration,
    )

    symbols = (
        AutoModel,
        AutoProcessor,
        AutoTokenizer,
        GenerationConfig,
        LlamaForCausalLM,
        Qwen2ForCausalLM,
        Qwen2_5_VLForConditionalGeneration,
    )
    return {
        "transformers": transformers.__version__,
        "symbols": [symbol.__name__ for symbol in symbols],
    }


def _check_cuda(state: dict[str, Any]) -> dict[str, Any]:
    import bitsandbytes
    import torch
    import torchaudio
    import torchvision

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is unavailable")
    torch.cuda.synchronize()
    torch.cuda.empty_cache()
    baseline = _gpu_memory()
    state["gpu_baseline"] = baseline
    tensor = torch.ones((32, 32), device="cuda")
    total = float(tensor.sum().item())
    del tensor
    if total != 1024.0:
        raise RuntimeError("CUDA tensor operation returned an unexpected result")
    bitsandbytes_version = getattr(
        bitsandbytes,
        "__version__",
        importlib.metadata.version("bitsandbytes"),
    )
    return {
        "torch": torch.__version__,
        "torchvision": torchvision.__version__,
        "torchaudio": torchaudio.__version__,
        "bitsandbytes": str(bitsandbytes_version),
        "device": torch.cuda.get_device_name(0),
        "baseline": baseline,
    }


def _prepare_fixture(
    fixture: Mapping[str, Any], run_dir: Path, state: dict[str, Any]
) -> dict[str, Any]:
    import pandas as pd
    from huggingface_hub import hf_hub_download

    root = run_dir / "fixture"
    raw = fixture["raw"]
    release = fixture["release"]
    video = Path(
        hf_hub_download(
            repo_id=str(raw["repo_id"]),
            repo_type=str(raw.get("repo_type", "dataset")),
            revision=str(raw["revision"]),
            filename=str(raw["video_path"]),
            local_dir=root,
        )
    )
    metadata = Path(
        hf_hub_download(
            repo_id=str(raw["repo_id"]),
            repo_type=str(raw.get("repo_type", "dataset")),
            revision=str(raw["revision"]),
            filename=str(raw["metadata_path"]),
            local_dir=root,
        )
    )
    timeline_path = Path(
        hf_hub_download(
            repo_id=str(release["repo_id"]),
            repo_type=str(release.get("repo_type", "dataset")),
            revision=str(release["revision"]),
            filename=str(release["timeline_path"]),
            local_dir=root,
        )
    )
    for path, expected in (
        (video, raw["video_sha256"]),
        (metadata, raw["metadata_sha256"]),
        (timeline_path, release["timeline_sha256"]),
    ):
        actual = _sha256_file(path)
        if actual != str(expected):
            raise RuntimeError(f"fixture checksum mismatch for {path}: {actual}")

    timeline = pd.read_parquet(timeline_path)
    frame_policy = fixture["vlm_frame"]
    rows = timeline.loc[timeline["frame_id"] == int(frame_policy["frame_id"])]
    if len(rows) != 1:
        raise RuntimeError("qualification frame_id is absent or duplicated in timeline")
    actual_pts = float(rows.iloc[0]["pts_time"])
    if abs(actual_pts - float(frame_policy["pts_time"])) > 1e-6:
        raise RuntimeError("qualification frame pts_time differs from pinned config")

    audio_policy = fixture["audio"]
    audio = root / "qualification_audio.wav"
    frame = root / "qualification_frame.jpg"
    _run_ffmpeg(
        [
            "-ss",
            str(float(audio_policy["start_sec"])),
            "-i",
            str(video),
            "-t",
            str(float(audio_policy["end_sec"]) - float(audio_policy["start_sec"])),
            "-vn",
            "-acodec",
            "pcm_s16le",
            "-ar",
            "16000",
            "-ac",
            "1",
            str(audio),
        ]
    )
    _run_ffmpeg(
        [
            "-ss",
            str(actual_pts),
            "-i",
            str(video),
            "-frames:v",
            "1",
            str(frame),
        ]
    )
    if audio.stat().st_size == 0 or frame.stat().st_size == 0:
        raise RuntimeError("qualification fixture extraction produced an empty file")
    state.update(
        {
            "video_path": video,
            "metadata_path": metadata,
            "timeline_path": timeline_path,
            "timeline": timeline.to_dict("records"),
            "audio_path": audio,
            "frame_path": frame,
            "fixture_policy": fixture,
        }
    )
    return {
        "video_id": fixture["video_id"],
        "video_sha256": raw["video_sha256"],
        "metadata_sha256": raw["metadata_sha256"],
        "timeline_sha256": release["timeline_sha256"],
        "audio_start_sec": audio_policy["start_sec"],
        "audio_end_sec": audio_policy["end_sec"],
        "vlm_frame_id": frame_policy["frame_id"],
        "vlm_pts_time": frame_policy["pts_time"],
    }


def _check_nemo_restore(config: Mapping[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    from system1.asr.nemo import _load_pinned_nemo_model

    model = _load_pinned_nemo_model(str(config["model_id"]), config=config)
    if hasattr(model, "to"):
        model = model.to("cuda:0")
    if hasattr(model, "eval"):
        model.eval()
    state["nemo_model"] = model
    return {
        "model_id": config["model_id"],
        "model_revision": config["model_revision"],
        "model_file": config["model_file"],
        "model_type": type(model).__name__,
    }


def _check_flashlight_runtime(config: Mapping[str, Any]) -> dict[str, Any]:
    from system1.asr.runtime_artifact import validate_installed_flashlight_runtime

    receipt = validate_installed_flashlight_runtime(
        artifact_config=config["decoder"]["runtime_artifact"]
    )
    return {
        "package_name": receipt["package_name"],
        "package_version": receipt["package_version"],
        "manifest_sha256": receipt["manifest_sha256"],
        "wheel_sha256": receipt["wheel_sha256"],
    }


def _check_nemo_transcribe(config: Mapping[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    from system1.asr.nemo import _transcribe_one

    model = state["nemo_model"]
    hypothesis = _transcribe_one(model, Path(state["audio_path"]))
    state["nemo_output"] = hypothesis
    return {
        "return_type": type(hypothesis).__name__,
        "decoder_strategy": config["decoder"]["strategy"],
        "beam_size": config["decoder"]["beam_size"],
    }


def _check_nemo_normalize(config: Mapping[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    from system1.asr.nemo import _ctc_blank_index, _transcription_text
    from system1.asr.quality import alignment_metrics, evaluate_transcript

    audio = state["fixture_policy"]["audio"]
    hypothesis = state["nemo_output"]
    text = _transcription_text(hypothesis)
    metrics = alignment_metrics(
        hypothesis,
        blank_index=_ctc_blank_index(state["nemo_model"]),
    )
    decision = evaluate_transcript(
        text,
        duration_seconds=float(audio["end_sec"]) - float(audio["start_sec"]),
        acoustic_metrics=metrics,
        config=config["quality_gate"],
    )
    if not decision.accepted:
        raise RuntimeError(
            "actual NeMo Flashlight output failed the quality gate: "
            + ", ".join(decision.reason_codes)
        )
    state.pop("nemo_output", None)
    state.pop("nemo_model", None)
    _release_gpu()
    return {
        "sample": text[:240],
        "metrics": decision.metrics,
    }


def _check_vintern_1b(config: Mapping[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    schema = {
        "type": "object",
        "properties": {
            "full_text": {"type": "string"},
            "ocr_blocks": {"type": "array"},
            "language": {"type": "string"},
            "confidence": {"type": ["number", "null"]},
        },
        "required": ["full_text", "ocr_blocks"],
        "additionalProperties": False,
    }
    return _run_vlm(
        config={**config, "max_new_tokens": 64, "inference_batch_size": 1},
        state=state,
        request_kind="keyframe_ocr",
        prompt=(
            "Đọc chính xác chữ nhìn thấy trong ảnh. "
            "Chỉ trả về nội dung chữ."
        ),
        response_mode="json",
        response_schema=schema,
    )


def _check_vintern_3b(config: Mapping[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    from system1.vlm.contracts import TEXT_RESPONSE_SCHEMA

    return _run_vlm(
        config={**config, "max_new_tokens": 48, "inference_batch_size": 1},
        state=state,
        request_kind="qualification_caption",
        prompt="Mô tả ngắn nội dung chính của ảnh bằng tiếng Việt.",
        response_mode="text",
        response_schema=TEXT_RESPONSE_SCHEMA,
    )


def _check_qwen(config: Mapping[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    from system1.vlm.contracts import TEXT_RESPONSE_SCHEMA

    return _run_vlm(
        config={**config, "max_new_tokens": 48, "inference_batch_size": 1},
        state=state,
        request_kind="qualification_caption",
        prompt="Mô tả ngắn nội dung chính của ảnh bằng tiếng Việt.",
        response_mode="text",
        response_schema=TEXT_RESPONSE_SCHEMA,
    )


def _run_vlm(
    *,
    config: Mapping[str, Any],
    state: dict[str, Any],
    request_kind: str,
    prompt: str,
    response_mode: str,
    response_schema: dict[str, Any],
) -> dict[str, Any]:
    from system1.vlm.client import LocalVisionStructuredClient
    from system1.vlm.contracts import ModelRequest

    client = LocalVisionStructuredClient(model_config=config)
    try:
        response = client.request(
            ModelRequest(
                request_kind=request_kind,
                video_id=str(state["fixture_policy"]["video_id"]),
                prompt=prompt,
                prompt_version="phase01_runtime_qualification_v1",
                response_schema_version="phase01_runtime_qualification_v1",
                response_schema=response_schema,
                response_mode=response_mode,  # type: ignore[arg-type]
                image_paths=(Path(state["frame_path"]),),
            )
        )
        if response_mode == "text" and not str(response.get("text", "")).strip():
            raise RuntimeError(f"{config['provider']} returned empty qualification text")
        if request_kind == "keyframe_ocr":
            block_text = " ".join(
                str(block.get("text", "")).strip()
                for block in response.get("ocr_blocks", [])
                if isinstance(block, Mapping)
            ).strip()
            if not str(response.get("full_text", "")).strip() and not block_text:
                raise RuntimeError("Vintern-1B returned no visible text for pinned frame")
        return {
            "provider": config["provider"],
            "model_id": config["model_id"],
            "model_revision": config["model_revision"],
            "response": {
                key: value
                for key, value in response.items()
                if not key.startswith("__")
            },
        }
    finally:
        client.close()
        del client
        _release_gpu()


def _check_gpu_cleanup(config: Mapping[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    state.pop("nemo_model", None)
    state.pop("nemo_output", None)
    _release_gpu()
    baseline = state.get("gpu_baseline")
    if not baseline:
        raise RuntimeError("GPU cleanup cannot be evaluated without a baseline")
    post = _gpu_memory()
    allocated_delta = max(0, post["allocated_bytes"] - baseline["allocated_bytes"])
    reserved_delta = max(0, post["reserved_bytes"] - baseline["reserved_bytes"])
    allocated_tolerance = int(config["allocated_tolerance_bytes"])
    reserved_tolerance = int(config["reserved_tolerance_bytes"])
    if allocated_delta > allocated_tolerance:
        raise RuntimeError(
            f"post-cleanup allocated delta {allocated_delta} exceeds {allocated_tolerance}"
        )
    if reserved_delta > reserved_tolerance:
        raise RuntimeError(
            f"post-cleanup reserved delta {reserved_delta} exceeds {reserved_tolerance}"
        )
    return {
        "baseline": baseline,
        "post": post,
        "allocated_delta_bytes": allocated_delta,
        "reserved_delta_bytes": reserved_delta,
        "allocated_tolerance_bytes": allocated_tolerance,
        "reserved_tolerance_bytes": reserved_tolerance,
    }


def _check_pip(report: dict[str, Any]) -> dict[str, Any]:
    result = subprocess.run(
        [sys.executable, "-m", "pip", "check"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    classified = classify_pip_check(result.stdout)
    report["pip_check"] = sanitize_payload(classified)
    if classified["hard_failures"]:
        raise RuntimeError(
            f"Phase01-owned pip conflicts: {classified['hard_failures']}"
        )
    return {
        "returncode": result.returncode,
        "hard_failure_count": 0,
        "warning_count": len(classified["warnings"]),
    }


def _git_identity(project_root: Path) -> dict[str, Any]:
    repository = project_root.parent
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repository,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    status = subprocess.run(
        ["git", "status", "--short"],
        cwd=repository,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return {
        "commit": revision.stdout.strip() if revision.returncode == 0 else "unknown",
        "dirty": bool(status.stdout.strip()),
    }


def _installed_packages() -> dict[str, str]:
    return dict(
        sorted(
            (
                (distribution.metadata["Name"], distribution.version)
                for distribution in importlib.metadata.distributions()
                if distribution.metadata.get("Name")
            ),
            key=lambda item: item[0].lower(),
        )
    )


def _gpu_memory() -> dict[str, int]:
    import torch

    torch.cuda.synchronize()
    return {
        "allocated_bytes": int(torch.cuda.memory_allocated()),
        "reserved_bytes": int(torch.cuda.memory_reserved()),
        "peak_allocated_bytes": int(torch.cuda.max_memory_allocated()),
        "peak_reserved_bytes": int(torch.cuda.max_memory_reserved()),
    }


def _release_gpu() -> None:
    gc.collect()
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.synchronize()
    except Exception:  # noqa: BLE001 - cleanup cannot hide qualification evidence
        return


def _run_ffmpeg(arguments: list[str]) -> None:
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg is unavailable")
    result = subprocess.run(
        ["ffmpeg", "-y", "-v", "error", *arguments],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr.strip()}")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _passed(report: Mapping[str, Any], name: str) -> bool:
    return report.get("checks", {}).get(name, {}).get("status") == "pass"


def _try_upload_report(
    report_path: Path, config: Mapping[str, Any], report: dict[str, Any]
) -> None:
    repo_id = str(config.get("upload_repo_id") or "").strip()
    if not repo_id:
        return
    try:
        from huggingface_hub import HfApi

        token = os.environ.get("AIC_HF_TOKEN") or os.environ.get("HF_TOKEN")
        HfApi(token=token).upload_file(
            path_or_fileobj=str(report_path),
            path_in_repo=(
                f"{str(config.get('upload_prefix', '_qualification')).strip('/')}/"
                f"{report['run_id']}/{report_path.name}"
            ),
            repo_id=repo_id,
            repo_type=str(config.get("upload_repo_type", "dataset")),
            revision=str(config.get("upload_revision", "main")),
            commit_message=f"Upload Phase01 qualification {report['run_id']}",
        )
        report["report_upload"] = {"status": "pass", "repo_id": repo_id}
    except Exception as exc:  # noqa: BLE001 - local artifact remains authority
        report.setdefault("warnings", []).append(
            sanitize_payload(f"qualification report upload failed: {type(exc).__name__}: {exc}")
        )
        report["report_upload"] = {"status": "warning", "repo_id": repo_id}


if __name__ == "__main__":
    main()
