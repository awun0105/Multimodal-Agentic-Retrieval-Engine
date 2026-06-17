from __future__ import annotations

import json
from pathlib import Path

import pytest

from system1.artifacts import ArtifactStore, make_artifact_store


def test_make_artifact_store_creates_root(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"

    store = make_artifact_store(root)

    assert store == ArtifactStore(root=root.resolve())
    assert root.exists()
    assert root.is_dir()


def test_upload_file_then_download_file_preserves_bytes(tmp_path: Path) -> None:
    store = make_artifact_store(tmp_path / "artifacts")
    source = tmp_path / "source.bin"
    source.write_bytes(b"\x00\x01artifact-bytes\xff")

    uploaded = store.upload_file(source, "checkpoints/a.bin")
    downloaded = store.download_file("checkpoints/a.bin", tmp_path / "downloads" / "copy.bin")

    assert uploaded == store.root / "checkpoints" / "a.bin"
    assert downloaded == tmp_path / "downloads" / "copy.bin"
    assert downloaded.read_bytes() == source.read_bytes()


def test_write_json_then_read_json_preserves_dict(tmp_path: Path) -> None:
    store = make_artifact_store(tmp_path / "artifacts")
    payload = {"z": [1, 2], "a": {"nested": True}}

    written = store.write_json("metadata/sample.json", payload)
    loaded = store.read_json("metadata/sample.json")

    assert written == store.root / "metadata" / "sample.json"
    assert loaded == payload
    assert written.read_text(encoding="utf-8").endswith("\n")
    assert json.loads(written.read_text(encoding="utf-8")) == payload


def test_read_json_rejects_non_dict_json(tmp_path: Path) -> None:
    store = make_artifact_store(tmp_path / "artifacts")
    path = store.root / "list.json"
    path.write_text('[1, 2, 3]\n', encoding="utf-8")

    with pytest.raises(ValueError):
        store.read_json("list.json")


def test_path_rejects_absolute_paths(tmp_path: Path) -> None:
    store = make_artifact_store(tmp_path / "artifacts")

    with pytest.raises(ValueError):
        store.path("/tmp/evil.txt")



def test_path_rejects_parent_traversal(tmp_path: Path) -> None:
    store = make_artifact_store(tmp_path / "artifacts")

    with pytest.raises(ValueError):
        store.path("../evil.txt")



def test_list_files_returns_sorted_relative_paths_and_ignores_directories(tmp_path: Path) -> None:
    store = make_artifact_store(tmp_path / "artifacts")
    store.write_json("zeta/b.json", {"value": 2})
    store.write_json("alpha/a.json", {"value": 1})
    (store.root / "empty_dir").mkdir()

    files = store.list_files()

    assert files == [Path("alpha/a.json"), Path("zeta/b.json")]
    assert store.list_files("missing") == []
    assert store.list_files("alpha/a.json") == [Path("alpha/a.json")]



def test_exists_works(tmp_path: Path) -> None:
    store = make_artifact_store(tmp_path / "artifacts")

    assert store.exists("missing.txt") is False
    store.write_json("present.json", {"ok": True})
    assert store.exists("present.json") is True
