from __future__ import annotations

import json
from pathlib import Path

import pytest

from system1.artifacts.hf_store import HF_EXPECTED_ERRORS, HuggingFaceDatasetArtifactStore


class MissingEntryError(Exception):
    pass


def test_upload_file_calls_hf_api(monkeypatch, tmp_path: Path) -> None:
    calls = {}

    class FakeApi:
        def __init__(self, token=None):
            calls["token"] = token

        def upload_file(self, **kwargs):
            calls.update(kwargs)
            return "ok"

    monkeypatch.setattr("system1.artifacts.hf_store.HfApi", FakeApi)
    store = HuggingFaceDatasetArtifactStore(repo_id="org/repo", token="secret")
    source = tmp_path / "artifact.zip"
    source.write_bytes(b"zip")

    uploaded = store.upload_file(source, "checkpoints/a.zip")

    assert str(uploaded) == "hf:/org/repo/checkpoints/a.zip"
    assert calls["repo_id"] == "org/repo"
    assert calls["repo_type"] == "dataset"
    assert calls["path_in_repo"] == "checkpoints/a.zip"
    assert calls["path_or_fileobj"] == str(source)


def test_upload_files_uses_single_create_commit(monkeypatch, tmp_path: Path) -> None:
    calls = {}

    class FakeApi:
        def __init__(self, token=None):
            calls["token"] = token

        def create_commit(self, **kwargs):
            calls.update(kwargs)
            return "ok"

    monkeypatch.setattr("system1.artifacts.hf_store.HfApi", FakeApi)
    store = HuggingFaceDatasetArtifactStore(repo_id="org/repo", token="secret")
    first = tmp_path / "first.bin"
    second = tmp_path / "second.bin"
    first.write_bytes(b"first")
    second.write_bytes(b"second")

    uploaded = store.upload_files(
        [(first, "raw/first.bin"), (second, "raw/second.bin")],
        commit_message="Upload raw batch",
    )

    assert [str(path) for path in uploaded] == ["hf:/org/repo/raw/first.bin", "hf:/org/repo/raw/second.bin"]
    assert calls["repo_id"] == "org/repo"
    assert calls["repo_type"] == "dataset"
    assert calls["commit_message"] == "Upload raw batch"
    assert [operation.path_in_repo for operation in calls["operations"]] == ["raw/first.bin", "raw/second.bin"]


def test_download_file_uses_hf_hub_download_and_copies(monkeypatch, tmp_path: Path) -> None:
    cached = tmp_path / "cached.bin"
    cached.write_bytes(b"payload")

    def fake_download(**kwargs):
        return str(cached)

    monkeypatch.setattr("system1.artifacts.hf_store.hf_hub_download", fake_download)
    store = HuggingFaceDatasetArtifactStore(repo_id="org/repo")
    target = tmp_path / "downloads" / "copy.bin"

    downloaded = store.download_file("checkpoints/a.zip", target)

    assert downloaded == target
    assert target.read_bytes() == b"payload"


def test_exists_returns_true_when_download_succeeds(monkeypatch) -> None:
    monkeypatch.setattr("system1.artifacts.hf_store.hf_hub_download", lambda **kwargs: "/tmp/file")
    store = HuggingFaceDatasetArtifactStore(repo_id="org/repo")
    assert store.exists("checkpoints/a.zip") is True


def test_exists_returns_false_when_missing(monkeypatch) -> None:
    monkeypatch.setattr("system1.artifacts.hf_store.EntryNotFoundError", MissingEntryError)

    def fake_download(**kwargs):
        raise MissingEntryError("missing")

    monkeypatch.setattr("system1.artifacts.hf_store.hf_hub_download", fake_download)
    store = HuggingFaceDatasetArtifactStore(repo_id="org/repo")
    assert store.exists("checkpoints/a.zip") is False


def test_exists_reraises_repo_style_error(monkeypatch) -> None:
    class FakeHubError(Exception):
        pass

    monkeypatch.setattr("system1.artifacts.hf_store.HfHubHTTPError", FakeHubError)

    def fake_download(**kwargs):
        raise FakeHubError("auth failed")

    monkeypatch.setattr("system1.artifacts.hf_store.hf_hub_download", fake_download)
    store = HuggingFaceDatasetArtifactStore(repo_id="org/repo")
    with pytest.raises(FakeHubError):
        store.exists("checkpoints/a.zip")


def test_hf_expected_errors_includes_installed_hfhubhttperror() -> None:
    from system1.artifacts import hf_store as hf_store_module

    assert hf_store_module.HfHubHTTPError in HF_EXPECTED_ERRORS


def test_write_json_uploads_json_object(monkeypatch, tmp_path: Path) -> None:
    uploaded = {}

    def fake_upload(self, source: Path, relative_path):
        uploaded["payload"] = json.loads(source.read_text(encoding="utf-8"))
        uploaded["relative_path"] = str(relative_path)
        return Path("hf:/org/repo") / str(relative_path)

    monkeypatch.setattr(HuggingFaceDatasetArtifactStore, "upload_file", fake_upload)
    store = HuggingFaceDatasetArtifactStore(repo_id="org/repo")
    store.write_json("manifests/registry.json", {"ok": True})
    assert uploaded["payload"] == {"ok": True}
    assert uploaded["relative_path"] == "manifests/registry.json"


def test_read_json_downloads_and_parses_dict(monkeypatch, tmp_path: Path) -> None:
    def fake_download(self, relative_path, target: Path):
        target.write_text('{"ok": true}\n', encoding="utf-8")
        return target

    monkeypatch.setattr(HuggingFaceDatasetArtifactStore, "download_file", fake_download)
    store = HuggingFaceDatasetArtifactStore(repo_id="org/repo")
    assert store.read_json("manifests/registry.json") == {"ok": True}


def test_read_json_rejects_non_dict(monkeypatch, tmp_path: Path) -> None:
    def fake_download(self, relative_path, target: Path):
        target.write_text('[1, 2, 3]\n', encoding="utf-8")
        return target

    monkeypatch.setattr(HuggingFaceDatasetArtifactStore, "download_file", fake_download)
    store = HuggingFaceDatasetArtifactStore(repo_id="org/repo")
    with pytest.raises(ValueError):
        store.read_json("manifests/list.json")


def test_path_traversal_rejected(tmp_path: Path) -> None:
    store = HuggingFaceDatasetArtifactStore(repo_id="org/repo")
    with pytest.raises(ValueError):
        store.path("../evil.txt")
