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
from pathlib import Path

UPSTREAM_REPO = "https://github.com/soCzech/TransNetV2.git"
UPSTREAM_COMMIT = "85cef72af9a916bdfd7cc94a670c9cdfbf12d1ed"
UPSTREAM_SOURCE_SHA256 = "f7c1d437465579a8ec28a5add19853d2cb2755248ea4a4207678210a609428e1"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(command: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )


def prepare(output_dir: Path) -> Path:
    output_dir = output_dir.resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise RuntimeError(f"TransNet output directory must be empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="transnetv2_prepare_") as temp:
        checkout = Path(temp) / "TransNetV2"
        run(["git", "clone", "--filter=blob:none", UPSTREAM_REPO, str(checkout)])
        run(["git", "checkout", "--detach", UPSTREAM_COMMIT], cwd=checkout)
        run(["git", "lfs", "pull"], cwd=checkout)
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


def upload_artifact(
    output_dir: Path,
    *,
    repo_id: str,
    repo_type: str,
    revision: str,
    path_in_repo: str,
) -> None:
    from huggingface_hub import HfApi

    token = os.environ.get("AIC_HF_TOKEN") or os.environ.get("HF_TOKEN")
    if not token:
        raise RuntimeError("Set AIC_HF_TOKEN or HF_TOKEN before uploading the artifact")
    api = HfApi(token=token)
    info = api.repo_info(repo_id=repo_id, repo_type=repo_type, revision=revision)
    if not info.private:
        raise RuntimeError("TransNet model artifact repository must be private")
    api.upload_folder(
        folder_path=str(output_dir.resolve()),
        path_in_repo=path_in_repo.strip("/"),
        repo_id=repo_id,
        repo_type=repo_type,
        revision=revision,
        commit_message=f"Upload verified TransNet V2 artifact {UPSTREAM_COMMIT}",
    )


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
    args = parser.parse_args()
    manifest_path = prepare(args.output_dir)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if args.repo_id:
        upload_artifact(
            args.output_dir,
            repo_id=args.repo_id,
            repo_type=args.repo_type,
            revision=args.revision,
            path_in_repo=args.path_in_repo,
        )
    print(
        json.dumps(
            {
                "manifest": str(manifest_path),
                "weights_sha256": manifest["weights_sha256"],
                "uploaded": bool(args.repo_id),
                "repo_id": args.repo_id,
                "revision": args.revision if args.repo_id else None,
                "path_in_repo": args.path_in_repo if args.repo_id else None,
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
