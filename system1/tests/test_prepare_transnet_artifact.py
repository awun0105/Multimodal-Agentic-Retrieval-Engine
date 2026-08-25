from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "prepare_transnetv2_artifact.py"


def load_script_module():
    spec = importlib.util.spec_from_file_location("prepare_transnetv2_artifact", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_transnet_artifact_upload_allows_public_repo_by_default(monkeypatch, tmp_path):
    module = load_script_module()
    uploaded: dict[str, object] = {}

    class FakeApi:
        def __init__(self, *, token):
            assert token == "token"

        def repo_info(self, **_kwargs):
            return SimpleNamespace(private=False)

        def upload_folder(self, **kwargs):
            uploaded.update(kwargs)

    monkeypatch.setenv("HF_TOKEN", "token")
    monkeypatch.setattr("huggingface_hub.HfApi", FakeApi)

    module.upload_artifact(
        tmp_path,
        repo_id="org/checkpoints",
        repo_type="dataset",
        revision="main",
        path_in_repo="model_artifacts/transnetv2/revision",
        require_private=False,
    )

    assert uploaded["repo_id"] == "org/checkpoints"
    assert uploaded["path_in_repo"] == "model_artifacts/transnetv2/revision"


def test_transnet_artifact_upload_can_require_private_repo(monkeypatch, tmp_path):
    module = load_script_module()

    class FakeApi:
        def __init__(self, *, token):
            assert token == "token"

        def repo_info(self, **_kwargs):
            return SimpleNamespace(private=False)

    monkeypatch.setenv("HF_TOKEN", "token")
    monkeypatch.setattr("huggingface_hub.HfApi", FakeApi)

    with pytest.raises(RuntimeError, match="must be private"):
        module.upload_artifact(
            tmp_path,
            repo_id="org/checkpoints",
            repo_type="dataset",
            revision="main",
            path_in_repo="model_artifacts/transnetv2/revision",
            require_private=True,
        )


def test_run_reports_command_output_tail(monkeypatch):
    module = load_script_module()
    monkeypatch.setattr(module.time, "sleep", lambda _seconds: None)

    def fake_run(command, **_kwargs):
        return subprocess.CompletedProcess(
            command,
            128,
            stdout="fatal: unable to access upstream repository\n",
        )

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    with pytest.raises(RuntimeError) as exc_info:
        module.run(["git", "clone", "https://example.invalid/repo.git"], retries=2)

    message = str(exc_info.value)
    assert "exit=128" in message
    assert "git clone https://example.invalid/repo.git" in message
    assert "fatal: unable to access upstream repository" in message


def test_clone_transnet_falls_back_to_filtered_clone_and_cleans_checkout(monkeypatch, tmp_path):
    module = load_script_module()
    checkout = tmp_path / "TransNetV2"
    calls: list[list[str]] = []
    run_kwargs: list[dict[str, object]] = []
    removed: list[Path] = []
    real_rmtree = module.shutil.rmtree

    def fake_rmtree(path):
        removed.append(Path(path))
        real_rmtree(path)

    def fake_run(command, **kwargs):
        calls.append(command)
        run_kwargs.append(kwargs)
        if "--filter=blob:none" not in command:
            checkout.mkdir(parents=True, exist_ok=True)
            raise RuntimeError("full clone failed")
        return SimpleNamespace(stdout="")

    monkeypatch.setattr(module.shutil, "rmtree", fake_rmtree)
    monkeypatch.setattr(module.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(module, "run", fake_run)

    module.clone_transnet(checkout)

    assert calls[0][:5] == ["git", "-c", "http.version=HTTP/1.1", "clone", module.UPSTREAM_REPO]
    assert len(calls) == 4
    assert all("--filter=blob:none" not in command for command in calls[:3])
    assert "--filter=blob:none" in calls[3]
    assert all("retries" not in kwargs for kwargs in run_kwargs)
    assert removed == [checkout, checkout, checkout]


def test_clone_transnet_reports_strategy_attempt_and_output_tail(monkeypatch, tmp_path):
    module = load_script_module()
    checkout = tmp_path / "TransNetV2"

    def fake_run(command, **_kwargs):
        checkout.mkdir(parents=True, exist_ok=True)
        strategy = "filtered" if "--filter=blob:none" in command else "normal"
        raise RuntimeError(
            "Command failed (exit=128): "
            + " ".join(command)
            + f"\n\nCommand output tail:\nfatal: {strategy} clone failed"
        )

    monkeypatch.setattr(module.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(module, "run", fake_run)

    with pytest.raises(RuntimeError) as exc_info:
        module.clone_transnet(checkout)

    message = str(exc_info.value)
    assert "strategy=1, attempt=1" in message
    assert "strategy=1, attempt=3" in message
    assert "strategy=2, attempt=1" in message
    assert "strategy=2, attempt=3" in message
    assert "Command output tail:" in message
    assert "fatal: normal clone failed" in message
    assert "fatal: filtered clone failed" in message


def test_canonical_prepare_explains_upstream_lfs_budget(monkeypatch, tmp_path):
    module = load_script_module()

    def fake_clone(checkout):
        checkout.mkdir(parents=True)

    def fake_run(command, **_kwargs):
        if command[:3] == ["git", "rev-parse", "HEAD"]:
            return SimpleNamespace(stdout=module.UPSTREAM_COMMIT)
        if command[:3] == ["git", "lfs", "pull"]:
            raise RuntimeError(
                "Command failed (exit=2): git lfs pull\n\n"
                "Command output tail:\n"
                "batch response: This repository exceeded its LFS budget."
            )
        return SimpleNamespace(stdout="")

    monkeypatch.setattr(module, "clone_transnet", fake_clone)
    monkeypatch.setattr(module, "run", fake_run)

    with pytest.raises(RuntimeError) as exc_info:
        module.prepare(tmp_path)

    message = str(exc_info.value)
    assert "upstream Git LFS quota issue" in message
    assert "not an HF_TOKEN issue" in message
    assert "--preconverted-weights-repo-id" in message


def test_prepare_preconverted_uses_official_source_and_hf_mirror(monkeypatch, tmp_path):
    module = load_script_module()
    weights_cache = tmp_path / "cache" / "transnetv2-pytorch-weights.pth"
    weights_cache.parent.mkdir()
    weights_cache.write_bytes(b"mirror-weights")
    weights_sha = module.sha256_file(weights_cache)
    calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        if command[3:5] == ["clone", "--filter=blob:none"]:
            checkout = Path(command[-1])
            source_dir = checkout / "inference-pytorch"
            source_dir.mkdir(parents=True)
            source_dir.joinpath("transnetv2_pytorch.py").write_bytes(b"official-source")
            return SimpleNamespace(stdout="")
        if command[:3] == ["git", "rev-parse", "HEAD"]:
            return SimpleNamespace(stdout=module.UPSTREAM_COMMIT)
        return SimpleNamespace(stdout="")

    def fake_download(**kwargs):
        assert kwargs["repo_id"] == "mirror/transnet"
        assert kwargs["filename"] == weights_cache.name
        assert kwargs["repo_type"] == "model"
        return str(weights_cache)

    monkeypatch.setattr(module, "run", fake_run)
    monkeypatch.setattr("huggingface_hub.hf_hub_download", fake_download)
    monkeypatch.setattr(module, "UPSTREAM_SOURCE_SHA256", hashlib.sha256(b"official-source").hexdigest())

    manifest_path = module.prepare_preconverted(
        tmp_path / "artifact",
        weights_repo_id="mirror/transnet",
        weights_filename=weights_cache.name,
        expected_weights_sha256=weights_sha,
    )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["artifact_origin"] == "preconverted_huggingface_mirror"
    assert manifest["conversion_verified"] is False
    assert manifest["mirror_repo_id"] == "mirror/transnet"
    assert manifest["weights_sha256"] == weights_sha
    assert calls[0][0][3:5] == ["clone", "--filter=blob:none"]
    assert calls[0][1]["env"]["GIT_LFS_SKIP_SMUDGE"] == "1"
