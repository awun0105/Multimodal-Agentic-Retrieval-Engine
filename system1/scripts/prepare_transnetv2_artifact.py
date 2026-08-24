#!/usr/bin/env python3
"""Build a project-owned TransNet V2 PyTorch artifact from official sources.

Run this once in a controlled preparation environment with TensorFlow and
PyTorch installed. Runtime notebooks consume only the verified output bundle.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

UPSTREAM_REPO = "https://github.com/soCzech/TransNetV2.git"
UPSTREAM_COMMIT = "85cef72af9a916bdfd7cc94a670c9cdfbf12d1ed"
UPSTREAM_SOURCE_SHA256 = "f7c1d437465579a8ec28a5add19853d2cb2755248ea4a4207678210a609428e1"
CLONE_ATTEMPTS_PER_STRATEGY = 3


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(
    command: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    retries: int = 1,
) -> subprocess.CompletedProcess[str]:
    last_result: subprocess.CompletedProcess[str] | None = None
    for attempt in range(1, retries + 1):
        result = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        if result.returncode == 0:
            return result
        last_result = result
        if attempt < retries:
            time.sleep(min(10, 2 * attempt))
    output = (last_result.stdout if last_result is not None else "") or ""
    tail = output[-6000:]
    raise RuntimeError(
        "Command failed "
        f"(exit={last_result.returncode if last_result is not None else 'unknown'}): "
        + " ".join(command)
        + ("\n\nCommand output tail:\n" + tail if tail else "\n\nCommand produced no output.")
    )


def clone_transnet(checkout: Path) -> None:
    clone_commands = (
        ["git", "-c", "http.version=HTTP/1.1", "clone", UPSTREAM_REPO, str(checkout)],
        [
            "git",
            "-c",
            "http.version=HTTP/1.1",
            "clone",
            "--filter=blob:none",
            UPSTREAM_REPO,
            str(checkout),
        ],
    )
    errors: list[str] = []
    for strategy_index, command in enumerate(clone_commands, start=1):
        for attempt_index in range(1, CLONE_ATTEMPTS_PER_STRATEGY + 1):
            if checkout.exists():
                shutil.rmtree(checkout)
            try:
                run(command)
                return
            except RuntimeError as exc:
                errors.append(
                    "Clone attempt failed "
                    f"(strategy={strategy_index}, attempt={attempt_index}):\n{exc}"
                )
                if attempt_index < CLONE_ATTEMPTS_PER_STRATEGY:
                    time.sleep(min(10, 2 * attempt_index))
    raise RuntimeError("Failed to clone TransNetV2 upstream.\n\n" + "\n\n".join(errors))


def transnet_lfs_budget_error(error: BaseException) -> bool:
    return "this repository exceeded its lfs budget" in str(error).lower()


def lfs_budget_message(error: BaseException) -> str:
    return (
        "Official TransNetV2 TensorFlow weights are currently unavailable because "
        "the upstream GitHub repository exceeded its Git LFS budget. This is an "
        "upstream Git LFS quota issue, not an HF_TOKEN issue and not a checkpoint "
        "dataset permission issue. If project policy allows the mirror-based "
        "unblock path, rerun with --preconverted-weights-repo-id, "
        "--preconverted-weights-filename, and --expected-weights-sha256.\n\n"
        f"Original failure:\n{error}"
    )


def ensure_empty_output_dir(output_dir: Path) -> Path:
    output_dir = output_dir.resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise RuntimeError(f"TransNet output directory must be empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def prepare(output_dir: Path) -> Path:
    output_dir = ensure_empty_output_dir(output_dir)
    with tempfile.TemporaryDirectory(prefix="transnetv2_prepare_") as temp:
        checkout = Path(temp) / "TransNetV2"
        clone_transnet(checkout)
        run(["git", "checkout", "--detach", UPSTREAM_COMMIT], cwd=checkout)
        run(["git", "lfs", "install", "--local"], cwd=checkout)
        try:
            run(["git", "lfs", "pull"], cwd=checkout, retries=3)
        except RuntimeError as exc:
            if transnet_lfs_budget_error(exc):
                raise RuntimeError(lfs_budget_message(exc)) from exc
            raise
        revision = run(["git", "rev-parse", "HEAD"], cwd=checkout).stdout.strip()
        if revision != UPSTREAM_COMMIT:
            raise RuntimeError(f"Unexpected TransNet revision: {revision}")

        inference_dir = checkout / "inference-pytorch"
        result = run(
            [
                sys.executable,
                "convert_weights.py",
                "--tf_weights",
                str(checkout / "inference" / "transnetv2-weights"),
                "--test",
            ],
            cwd=inference_dir,
        )
        if result.stdout.count("100.0% of 'single' predictions matching") != 10:
            raise RuntimeError("Official TransNet single-head parity test did not pass all cases")
        if result.stdout.count("100.0% of 'many' predictions matching") != 10:
            raise RuntimeError("Official TransNet many-head parity test did not pass all cases")

        weights = inference_dir / "transnetv2-pytorch-weights.pth"
        source = inference_dir / "transnetv2_pytorch.py"
        target_weights = output_dir / weights.name
        target_source = output_dir / source.name
        shutil.copy2(weights, target_weights)
        shutil.copy2(source, target_source)
        source_sha256 = sha256_file(target_source)
        if source_sha256 != UPSTREAM_SOURCE_SHA256:
            raise RuntimeError(
                "Pinned TransNet source checksum does not match the official commit"
            )
        manifest = {
            "schema_version": "transnetv2_model_artifact_v1",
            "upstream_repo": "soCzech/TransNetV2",
            "upstream_commit": UPSTREAM_COMMIT,
            "runtime": "pytorch",
            "conversion_script": "inference-pytorch/convert_weights.py",
            "conversion_verified": True,
            "weights_file": target_weights.name,
            "weights_sha256": sha256_file(target_weights),
            "source_file": target_source.name,
            "source_sha256": source_sha256,
        }
        manifest_path = output_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        return manifest_path


def prepare_preconverted(
    output_dir: Path,
    *,
    weights_repo_id: str,
    weights_filename: str,
    expected_weights_sha256: str,
) -> Path:
    from huggingface_hub import hf_hub_download

    if Path(weights_filename).name != weights_filename:
        raise RuntimeError("Preconverted weights filename must be a plain filename")

    output_dir = ensure_empty_output_dir(output_dir)
    with tempfile.TemporaryDirectory(prefix="transnetv2_prepare_") as temp:
        checkout = Path(temp) / "TransNetV2"
        env = os.environ.copy()
        env["GIT_LFS_SKIP_SMUDGE"] = "1"
        run(
            [
                "git",
                "-c",
                "http.version=HTTP/1.1",
                "clone",
                "--filter=blob:none",
                UPSTREAM_REPO,
                str(checkout),
            ],
            env=env,
        )
        run(["git", "checkout", "--detach", UPSTREAM_COMMIT], cwd=checkout, env=env)
        revision = run(["git", "rev-parse", "HEAD"], cwd=checkout, env=env).stdout.strip()
        if revision != UPSTREAM_COMMIT:
            raise RuntimeError(f"Unexpected TransNet revision: {revision}")

        source = checkout / "inference-pytorch" / "transnetv2_pytorch.py"
        target_source = output_dir / source.name
        shutil.copy2(source, target_source)
        source_sha256 = sha256_file(target_source)
        if source_sha256 != UPSTREAM_SOURCE_SHA256:
            raise RuntimeError(
                "Pinned TransNet source checksum does not match the official commit"
            )

        token = os.environ.get("AIC_HF_TOKEN") or os.environ.get("HF_TOKEN")
        downloaded_weights = Path(
            hf_hub_download(
                repo_id=weights_repo_id,
                filename=weights_filename,
                repo_type="model",
                token=token,
            )
        )
        target_weights = output_dir / weights_filename
        shutil.copy2(downloaded_weights, target_weights)
        weights_sha256 = sha256_file(target_weights)
        if weights_sha256 != expected_weights_sha256:
            raise RuntimeError(
                "Preconverted TransNet weights checksum mismatch: "
                f"{weights_sha256} != {expected_weights_sha256}"
            )

        manifest = {
            "schema_version": "transnetv2_model_artifact_v1",
            "artifact_origin": "preconverted_huggingface_mirror",
            "upstream_repo": "soCzech/TransNetV2",
            "upstream_commit": UPSTREAM_COMMIT,
            "runtime": "pytorch",
            "conversion_verified": False,
            "conversion_note": (
                "Canonical upstream Git LFS weights were unavailable because the "
                "upstream repository exceeded its LFS budget. PyTorch weights were "
                "downloaded from a Hugging Face mirror and verified by SHA-256."
            ),
            "mirror_repo_id": weights_repo_id,
            "weights_file": target_weights.name,
            "weights_sha256": weights_sha256,
            "source_file": target_source.name,
            "source_sha256": source_sha256,
        }
        manifest_path = output_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        return manifest_path


def upload_artifact(
    output_dir: Path,
    *,
    repo_id: str,
    repo_type: str,
    revision: str,
    path_in_repo: str,
    require_private: bool,
) -> None:
    from huggingface_hub import HfApi

    token = os.environ.get("AIC_HF_TOKEN") or os.environ.get("HF_TOKEN")
    if not token:
        raise RuntimeError("Set AIC_HF_TOKEN or HF_TOKEN before uploading the artifact")
    api = HfApi(token=token)
    info = api.repo_info(repo_id=repo_id, repo_type=repo_type, revision=revision)
    if require_private and not info.private:
        raise RuntimeError("TransNet model artifact repository must be private")
    manifest_path = output_dir / "manifest.json"
    commit_message = f"Upload verified TransNet V2 artifact {UPSTREAM_COMMIT}"
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("conversion_verified") is not True:
            commit_message = f"Upload TransNet V2 preconverted artifact {UPSTREAM_COMMIT}"
    api.upload_folder(
        folder_path=str(output_dir.resolve()),
        path_in_repo=path_in_repo.strip("/"),
        repo_id=repo_id,
        repo_type=repo_type,
        revision=revision,
        commit_message=commit_message,
    )


def repo_is_private(*, repo_id: str, repo_type: str, revision: str) -> bool:
    from huggingface_hub import HfApi

    token = os.environ.get("AIC_HF_TOKEN") or os.environ.get("HF_TOKEN")
    if not token:
        raise RuntimeError("Set AIC_HF_TOKEN or HF_TOKEN before checking the artifact repo")
    api = HfApi(token=token)
    return bool(api.repo_info(repo_id=repo_id, repo_type=repo_type, revision=revision).private)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--repo-id")
    parser.add_argument("--repo-type", default="dataset", choices=("dataset", "model"))
    parser.add_argument("--revision", default="main")
    parser.add_argument(
        "--path-in-repo",
        default=f"model_artifacts/transnetv2/{UPSTREAM_COMMIT}",
    )
    parser.add_argument(
        "--require-private",
        action="store_true",
        help="Fail upload unless the target Hugging Face repository is private.",
    )
    parser.add_argument(
        "--preconverted-weights-repo-id",
        help=(
            "Optional Hugging Face model repo containing preconverted PyTorch weights. "
            "This path is explicit and never selected automatically."
        ),
    )
    parser.add_argument(
        "--preconverted-weights-filename",
        help="Filename of the preconverted PyTorch weights in the Hugging Face model repo.",
    )
    parser.add_argument(
        "--expected-weights-sha256",
        help="Required SHA-256 checksum for the preconverted PyTorch weights.",
    )
    args = parser.parse_args()
    preconverted_args = (
        args.preconverted_weights_repo_id,
        args.preconverted_weights_filename,
        args.expected_weights_sha256,
    )
    if any(preconverted_args) and not all(preconverted_args):
        raise RuntimeError(
            "Preconverted weights mode requires --preconverted-weights-repo-id, "
            "--preconverted-weights-filename, and --expected-weights-sha256"
        )
    if all(preconverted_args):
        manifest_path = prepare_preconverted(
            args.output_dir,
            weights_repo_id=args.preconverted_weights_repo_id,
            weights_filename=args.preconverted_weights_filename,
            expected_weights_sha256=args.expected_weights_sha256,
        )
    else:
        manifest_path = prepare(args.output_dir)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    target_private = None
    if args.repo_id:
        upload_artifact(
            args.output_dir,
            repo_id=args.repo_id,
            repo_type=args.repo_type,
            revision=args.revision,
            path_in_repo=args.path_in_repo,
            require_private=args.require_private,
        )
        target_private = repo_is_private(
            repo_id=args.repo_id,
            repo_type=args.repo_type,
            revision=args.revision,
        )
    print(
        json.dumps(
            {
                "manifest": str(manifest_path),
                "source_sha256": manifest["source_sha256"],
                "weights_sha256": manifest["weights_sha256"],
                "artifact_origin": manifest.get("artifact_origin", "canonical_official_conversion"),
                "conversion_verified": manifest["conversion_verified"],
                "uploaded": bool(args.repo_id),
                "repo_id": args.repo_id,
                "revision": args.revision if args.repo_id else None,
                "path_in_repo": args.path_in_repo if args.repo_id else None,
                "require_private": args.require_private if args.repo_id else None,
                "target_private": target_private,
                "models_yaml_update": {
                    "phase01.shot_detection.source_sha256": manifest[
                        "source_sha256"
                    ],
                    "phase01.shot_detection.weights_sha256": manifest["weights_sha256"]
                },
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
