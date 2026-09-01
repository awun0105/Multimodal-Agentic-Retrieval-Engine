from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from system1.asr import runtime_artifact


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_runtime_manifest_rejects_wrong_python_abi() -> None:
    artifact = {
        "package_name": "flashlight-text",
        "package_version": "0.0.7",
        "python_tag": "cp313",
    }
    manifest = {
        "schema_version": runtime_artifact.MANIFEST_SCHEMA,
        **artifact,
        "platform": "linux_x86_64",
        "wheel": {
            "filename": "flashlight_text-0.0.7-cp313-cp313-manylinux_2_17_x86_64.whl",
            "sha256": "a" * 64,
            "size_bytes": 10,
        },
    }
    with pytest.raises(RuntimeError, match="Python ABI"):
        runtime_artifact.validate_runtime_manifest(
            manifest,
            artifact_config=artifact,
            python_tag="cp312",
            platform_identity="linux_x86_64",
        )


def test_prepare_runtime_verifies_manifest_and_wheel_before_install(
    monkeypatch, tmp_path: Path
) -> None:
    wheel = tmp_path / "flashlight_text-0.0.7-cp313-cp313-manylinux_2_17_x86_64.whl"
    wheel.write_bytes(b"verified wheel")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": runtime_artifact.MANIFEST_SCHEMA,
                "package_name": "flashlight-text",
                "package_version": "0.0.7",
                "python_tag": "cp313",
                "platform": "linux_x86_64",
                "wheel": {
                    "filename": wheel.name,
                    "sha256": _sha(wheel),
                    "size_bytes": wheel.stat().st_size,
                },
            }
        ),
        encoding="utf-8",
    )
    downloads = iter([manifest, wheel])
    monkeypatch.setattr(
        runtime_artifact,
        "hf_hub_download",
        lambda **_kwargs: str(next(downloads)),
    )
    monkeypatch.setattr(runtime_artifact, "_python_tag", lambda: "cp313")
    monkeypatch.setattr(
        runtime_artifact, "_platform_identity", lambda: "linux_x86_64"
    )
    monkeypatch.setattr(runtime_artifact, "_validate_flashlight_import", lambda _v: None)
    commands: list[list[str]] = []

    def install(command, **_kwargs):
        commands.append(command)
        return SimpleNamespace(returncode=0, stdout="ok")

    receipt = runtime_artifact.prepare_flashlight_runtime(
        artifact_config={
            "package_name": "flashlight-text",
            "package_version": "0.0.7",
            "python_tag": "cp313",
            "platform": "linux_x86_64",
            "manifest_path": "runtime/manifest.json",
            "manifest_sha256": _sha(manifest),
        },
        storage_config={
            "repo_id": "owner/repo",
            "repo_type": "dataset",
            "revision": "main",
            "prefix": "model_artifacts",
        },
        cache_root=tmp_path / "runtime",
        installer=install,
    )
    payload = json.loads(receipt.read_text(encoding="utf-8"))
    assert payload["wheel_sha256"] == _sha(wheel)
    assert "--no-deps" in commands[0]
    assert "--force-reinstall" in commands[0]
