from __future__ import annotations

import json
import os
import shutil
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

if os.environ.get("AIC_HF_PROGRESS", "0") != "1":
    os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
    os.environ.setdefault("HF_HUB_VERBOSITY", "error")

from huggingface_hub import (
    CommitOperationAdd,
    CommitOperationDelete,
    HfApi,
    RepoFile,
    hf_hub_download,
)

try:
    from huggingface_hub.utils import (
        EntryNotFoundError,
        HfHubHTTPError,
        LocalEntryNotFoundError,
        RepositoryNotFoundError,
        RevisionNotFoundError,
    )
except ImportError:  # pragma: no cover - compatibility fallback
    from huggingface_hub.utils import EntryNotFoundError, HfHubHTTPError

    LocalEntryNotFoundError = EntryNotFoundError
    RepositoryNotFoundError = HfHubHTTPError
    RevisionNotFoundError = HfHubHTTPError


HF_EXPECTED_ERRORS = (
    HfHubHTTPError,
    EntryNotFoundError,
    LocalEntryNotFoundError,
    RepositoryNotFoundError,
    RevisionNotFoundError,
)


def _normalize_relative_path(relative_path: str | Path) -> str:
    path = PurePosixPath(str(relative_path))
    if path.is_absolute():
        raise ValueError("Artifact path must be relative")
    parts = path.parts
    if any(part == ".." for part in parts):
        raise ValueError("Artifact path escapes store root")
    normalized = path.as_posix().lstrip("/")
    if normalized in {"", "."}:
        return ""
    return normalized


@dataclass(frozen=True)
class HuggingFaceDatasetArtifactStore:
    repo_id: str
    repo_type: str = "dataset"
    revision: str = "main"
    token: str | None = None
    prefix: str = ""
    cache_dir: Path | str | None = None

    def __post_init__(self) -> None:
        _normalize_relative_path(self.prefix)

    def _remote_path(self, relative_path: str | Path) -> str:
        normalized = _normalize_relative_path(relative_path)
        prefix = _normalize_relative_path(self.prefix)
        if prefix and normalized:
            return f"{prefix}/{normalized}"
        if prefix:
            return prefix
        return normalized

    def path(self, relative_path: str | Path) -> Path:
        remote_path = self._remote_path(relative_path)
        return Path(f"hf://{self.repo_id}") / remote_path

    def exists(self, relative_path: str | Path) -> bool:
        remote_path = self._remote_path(relative_path)
        try:
            api = HfApi(token=self.token)
            file_info = getattr(api, "file_info", None)
            if file_info is not None:
                file_info(
                    repo_id=self.repo_id,
                    repo_type=self.repo_type,
                    revision=self.revision,
                    filename=remote_path,
                )
            else:
                hf_hub_download(
                    repo_id=self.repo_id,
                    repo_type=self.repo_type,
                    revision=self.revision,
                    filename=remote_path,
                    token=self.token,
                    cache_dir=str(self.cache_dir) if self.cache_dir is not None else None,
                )
            return True
        except (EntryNotFoundError, LocalEntryNotFoundError):
            return False
        except HfHubHTTPError:
            raise

    def upload_file(self, source: Path, relative_path: str | Path) -> Path:
        if not source.exists():
            raise FileNotFoundError(source)
        if not source.is_file():
            raise ValueError(f"Source must be a file: {source}")
        remote_path = self._remote_path(relative_path)
        HfApi(token=self.token).upload_file(
            path_or_fileobj=str(source),
            path_in_repo=remote_path,
            repo_id=self.repo_id,
            repo_type=self.repo_type,
            revision=self.revision,
            commit_message=f"Upload artifact {remote_path}",
        )
        return self.path(relative_path)

    def upload_files(
        self,
        files: Sequence[tuple[Path, str | Path]],
        *,
        commit_message: str,
        num_threads: int = 2,
    ) -> list[Path]:
        operations: list[CommitOperationAdd] = []
        relative_paths: list[str | Path] = []
        for source, relative_path in files:
            if not source.exists():
                raise FileNotFoundError(source)
            if not source.is_file():
                raise ValueError(f"Source must be a file: {source}")
            remote_path = self._remote_path(relative_path)
            operations.append(CommitOperationAdd(path_in_repo=remote_path, path_or_fileobj=str(source)))
            relative_paths.append(relative_path)
        if not operations:
            return []
        HfApi(token=self.token).create_commit(
            repo_id=self.repo_id,
            operations=operations,
            commit_message=commit_message,
            repo_type=self.repo_type,
            revision=self.revision,
            num_threads=num_threads,
        )
        return [self.path(relative_path) for relative_path in relative_paths]

    def sync_files(
        self,
        files: Sequence[tuple[Path, str | Path]],
        *,
        delete_paths: Sequence[str | Path] = (),
        commit_message: str,
        num_threads: int = 2,
    ) -> list[Path]:
        operations: list[CommitOperationAdd | CommitOperationDelete] = []
        relative_paths: list[str | Path] = []
        for source, relative_path in files:
            if not source.exists():
                raise FileNotFoundError(source)
            if not source.is_file():
                raise ValueError(f"Source must be a file: {source}")
            operations.append(
                CommitOperationAdd(
                    path_in_repo=self._remote_path(relative_path),
                    path_or_fileobj=str(source),
                )
            )
            relative_paths.append(relative_path)
        for relative_path in delete_paths:
            operations.append(
                CommitOperationDelete(path_in_repo=self._remote_path(relative_path))
            )
        if not operations:
            return []
        HfApi(token=self.token).create_commit(
            repo_id=self.repo_id,
            operations=operations,
            commit_message=commit_message,
            repo_type=self.repo_type,
            revision=self.revision,
            num_threads=num_threads,
        )
        return [self.path(relative_path) for relative_path in relative_paths]

    def download_file(
        self,
        relative_path: str | Path,
        target: Path,
        *,
        cache_dir: Path | str | None = None,
    ) -> Path:
        remote_path = self._remote_path(relative_path)
        effective_cache_dir = cache_dir if cache_dir is not None else self.cache_dir
        try:
            cached_path = hf_hub_download(
                repo_id=self.repo_id,
                repo_type=self.repo_type,
                revision=self.revision,
                filename=remote_path,
                token=self.token,
                cache_dir=(
                    str(effective_cache_dir)
                    if effective_cache_dir is not None
                    else None
                ),
            )
        except (EntryNotFoundError, LocalEntryNotFoundError) as exc:
            raise FileNotFoundError(remote_path) from exc
        target.parent.mkdir(parents=True, exist_ok=True)
        temp_path = target.with_name(f".{target.name}.tmp.{os.getpid()}")
        shutil.copyfile(cached_path, temp_path)
        os.replace(temp_path, target)
        return target

    def read_json(self, relative_path: str | Path) -> dict[str, Any]:
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / Path(str(relative_path)).name
            self.download_file(relative_path, target)
            with target.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
        if not isinstance(payload, dict):
            raise ValueError("Artifact JSON payload must be an object")
        return payload

    def write_json(self, relative_path: str | Path, payload: dict[str, Any]) -> Path:
        if not isinstance(payload, dict):
            raise ValueError("Artifact JSON payload must be a dict")
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / Path(str(relative_path)).name
            source.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            return self.upload_file(source, relative_path)

    def list_files(self, prefix: str | Path = "") -> list[Path]:
        prefix_value = _normalize_relative_path(prefix)
        remote_prefix = self._remote_path(prefix_value)
        api = HfApi(token=self.token)
        list_repo_tree = getattr(api, "list_repo_tree", None)
        if list_repo_tree is not None and remote_prefix:
            try:
                entries = list_repo_tree(
                    repo_id=self.repo_id,
                    path_in_repo=remote_prefix,
                    recursive=True,
                    repo_type=self.repo_type,
                    revision=self.revision,
                )
                files = [entry.path for entry in entries if isinstance(entry, RepoFile)]
            except EntryNotFoundError:
                return []
        else:
            files = api.list_repo_files(
                repo_id=self.repo_id,
                repo_type=self.repo_type,
                revision=self.revision,
            )
        store_prefix = _normalize_relative_path(self.prefix)
        results: list[Path] = []
        for file_path in files:
            normalized = _normalize_relative_path(file_path)
            if store_prefix:
                if normalized == store_prefix:
                    relative = ""
                elif normalized.startswith(f"{store_prefix}/"):
                    relative = normalized[len(store_prefix) + 1 :]
                else:
                    continue
            else:
                relative = normalized
            if remote_prefix:
                local_prefix = prefix_value
                if local_prefix and relative != local_prefix and not relative.startswith(f"{local_prefix}/"):
                    continue
            if relative:
                results.append(Path(relative))
        return sorted(results)
