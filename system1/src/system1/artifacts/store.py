from __future__ import annotations

import json
import os
import shutil
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ArtifactStore:
    root: Path

    def path(self, relative_path: str | Path) -> Path:
        relative = Path(relative_path)
        if relative.is_absolute():
            raise ValueError("Artifact path must be relative")

        resolved = (self.root / relative).resolve()
        try:
            resolved.relative_to(self.root)
        except ValueError as exc:
            raise ValueError("Artifact path escapes store root") from exc
        return resolved

    def exists(self, relative_path: str | Path) -> bool:
        return self.path(relative_path).exists()

    def upload_file(self, source: Path, relative_path: str | Path) -> Path:
        if not source.exists():
            raise FileNotFoundError(source)
        if not source.is_file():
            raise ValueError(f"Source must be a file: {source}")

        destination = self.path(relative_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temp_path = destination.with_name(f".{destination.name}.tmp.{os.getpid()}")
        shutil.copyfile(source, temp_path)
        os.replace(temp_path, destination)
        return destination

    def upload_files(
        self,
        files: Sequence[tuple[Path, str | Path]],
        *,
        commit_message: str,
        num_threads: int = 2,
    ) -> list[Path]:
        """Store a logical file group through the same API as the HF backend."""

        del commit_message, num_threads
        return [
            self.upload_file(source, relative_path)
            for source, relative_path in files
        ]

    def download_file(self, relative_path: str | Path, target: Path) -> Path:
        source = self.path(relative_path)
        if not source.exists():
            raise FileNotFoundError(source)
        if not source.is_file():
            raise ValueError(f"Artifact source must be a file: {source}")

        target.parent.mkdir(parents=True, exist_ok=True)
        temp_path = target.with_name(f".{target.name}.tmp.{os.getpid()}")
        shutil.copyfile(source, temp_path)
        os.replace(temp_path, target)
        return target

    def read_json(self, relative_path: str | Path) -> dict[str, Any]:
        source = self.path(relative_path)
        if not source.exists():
            raise FileNotFoundError(source)
        if not source.is_file():
            raise ValueError(f"Artifact JSON source must be a file: {source}")

        with source.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, dict):
            raise ValueError("Artifact JSON payload must be an object")
        return payload

    def write_json(self, relative_path: str | Path, payload: dict[str, Any]) -> Path:
        if not isinstance(payload, dict):
            raise ValueError("Artifact JSON payload must be a dict")

        destination = self.path(relative_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temp_path = destination.with_name(f".{destination.name}.tmp.{os.getpid()}")
        serialized = json.dumps(payload, indent=2, sort_keys=True) + "\n"
        with temp_path.open("w", encoding="utf-8") as handle:
            handle.write(serialized)
        os.replace(temp_path, destination)
        return destination

    def list_files(self, prefix: str | Path = "") -> list[Path]:
        target = self.path(prefix)
        if not target.exists():
            return []
        if target.is_file():
            return [target.relative_to(self.root)]

        files = [path.relative_to(self.root) for path in target.rglob("*") if path.is_file()]
        return sorted(files)



def make_artifact_store(root: str | Path) -> ArtifactStore:
    resolved_root = Path(root).expanduser().resolve()
    resolved_root.mkdir(parents=True, exist_ok=True)
    return ArtifactStore(root=resolved_root)
