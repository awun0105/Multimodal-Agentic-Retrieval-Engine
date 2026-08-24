from __future__ import annotations

import copy
import hashlib
import json
import tempfile
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any, Protocol

from jsonschema import validate

from system1.artifacts.checkpoint import sha256_file
from system1.artifacts.reports import utc_now

STAGES = (
    "shots",
    "keyframes",
    "asr",
    "ocr",
    "shot_captions",
    "shot_transcript_links",
    "scenes",
    "scene_summaries",
    "package",
    "sync",
)
STAGE_DEPENDENCIES: dict[str, tuple[str, ...]] = {
    "shots": (),
    "keyframes": ("shots",),
    "asr": (),
    "ocr": ("keyframes",),
    "shot_captions": ("keyframes", "ocr"),
    "shot_transcript_links": ("shots", "asr"),
    "scenes": ("shots", "keyframes", "ocr", "shot_captions", "shot_transcript_links"),
    "scene_summaries": ("scenes", "keyframes", "ocr", "shot_captions", "shot_transcript_links"),
    "package": (
        "shots",
        "keyframes",
        "asr",
        "ocr",
        "shot_captions",
        "shot_transcript_links",
        "scenes",
        "scene_summaries",
    ),
    "sync": ("package",),
}


class CheckpointStore(Protocol):
    def exists(self, relative_path: str | Path) -> bool: ...

    def upload_file(self, source: Path, relative_path: str | Path) -> Path: ...

    def upload_files(
        self,
        files: Sequence[tuple[Path, str | Path]],
        *,
        commit_message: str,
        num_threads: int = 2,
    ) -> list[Path]: ...

    def download_file(self, relative_path: str | Path, target: Path) -> Path: ...

    def read_json(self, relative_path: str | Path) -> dict[str, Any]: ...

    def write_json(self, relative_path: str | Path, payload: dict[str, Any]) -> Path: ...


def checkpoint_root(
    release_id: str,
    video_id: str,
    template: str = "phase01_checkpoints/{release_id}/{video_id}",
) -> Path:
    root = Path(template.format(release_id=release_id, video_id=video_id))
    if root.is_absolute() or ".." in root.parts:
        raise ValueError("Checkpoint root template must resolve to a safe relative path")
    return root


def compute_fingerprint(*values: Any) -> str:
    encoded = json.dumps(values, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def downstream_stages(stage: str) -> tuple[str, ...]:
    if stage not in STAGE_DEPENDENCIES:
        raise ValueError(f"Unknown Phase01 stage: {stage}")
    found: set[str] = set()
    changed = True
    while changed:
        changed = False
        for candidate, dependencies in STAGE_DEPENDENCIES.items():
            if candidate in found or candidate == stage:
                continue
            if stage in dependencies or any(dependency in found for dependency in dependencies):
                found.add(candidate)
                changed = True
    return tuple(candidate for candidate in STAGES if candidate in found)


class CheckpointManager:
    """Promote immutable stage outputs, then update state in a separate commit."""

    def __init__(
        self,
        store: CheckpointStore,
        *,
        release_id: str,
        video_id: str,
        config_hash: str,
        stage_config_hashes: Mapping[str, str],
        verify_remote_checksum: bool = True,
        root_template: str = "phase01_checkpoints/{release_id}/{video_id}",
        state_filename: str = "state.json",
    ) -> None:
        self.store = store
        self.release_id = release_id
        self.video_id = video_id
        self.config_hash = config_hash
        self.stage_config_hashes = dict(stage_config_hashes)
        self.verify_remote_checksum = verify_remote_checksum
        self.root = checkpoint_root(release_id, video_id, root_template)
        if Path(state_filename).name != state_filename:
            raise ValueError("Checkpoint state filename must be a basename")
        self.state_filename = state_filename
        self.active_stage = "shots"
        self._state_cache: dict[str, Any] | None = None
        unknown = sorted(set(self.stage_config_hashes) - set(STAGES))
        if unknown:
            raise ValueError(f"Unknown stage config hashes: {', '.join(unknown)}")

    @property
    def state_path(self) -> Path:
        return self.root / self.state_filename

    def load_state(self) -> dict[str, Any]:
        if self._state_cache is not None:
            return copy.deepcopy(self._state_cache)
        if not self.store.exists(self.state_path):
            self._state_cache = self._empty_state()
            return copy.deepcopy(self._state_cache)
        payload = self.store.read_json(self.state_path)
        _validate_checkpoint_state(payload)
        self._validate_state_identity(payload)
        self._state_cache = payload
        return copy.deepcopy(payload)

    def is_reusable(
        self,
        stage: str,
        *,
        input_fingerprint: str,
        restore_dir: Path | None = None,
    ) -> bool:
        state = self.load_state()
        record = state["stages"][stage]
        expected_config_hash = self.stage_config_hashes[stage]
        if not (
            record["status"] == "complete"
            and record["input_fingerprint"] == input_fingerprint
            and record["config_hash"] == expected_config_hash
            and record["output_checksums"]
        ):
            if record["status"] == "complete":
                self._invalidate_stage(stage, state)
            return False
        with tempfile.TemporaryDirectory(prefix="phase01_checkpoint_verify_") as tmp:
            root = restore_dir or Path(tmp)
            for remote_name, expected_checksum in record["output_checksums"].items():
                target = root / Path(remote_name).name
                try:
                    self.store.download_file(remote_name, target)
                except FileNotFoundError:
                    self._invalidate_stage(stage, state)
                    return False
                if sha256_file(target) != expected_checksum:
                    self._invalidate_stage(stage, state)
                    return False
        return True

    def restore_stage(self, stage: str, target_dir: Path) -> list[Path]:
        state = self.load_state()
        record = state["stages"][stage]
        if record["status"] != "complete":
            raise ValueError(f"Stage is not complete: {stage}")
        restored: list[Path] = []
        for remote_name, expected_checksum in record["output_checksums"].items():
            relative_name = Path(remote_name).name
            target = target_dir / relative_name
            self.store.download_file(remote_name, target)
            if sha256_file(target) != expected_checksum:
                raise ValueError(f"Checkpoint checksum mismatch: {remote_name}")
            restored.append(target)
        return restored

    def stage_output_fingerprint(self, stage: str) -> str:
        state = self.load_state()
        record = state["stages"][stage]
        if record["status"] != "complete" or not record["output_checksums"]:
            raise ValueError(f"Stage has no complete output fingerprint: {stage}")
        return compute_fingerprint(record["output_checksums"])

    def promote_stage(
        self,
        stage: str,
        *,
        input_fingerprint: str,
        outputs: Iterable[Path],
        model: Mapping[str, str | None] | None = None,
        prompt_version: str | None = None,
        schema_version: str,
    ) -> dict[str, Any]:
        if stage not in STAGES:
            raise ValueError(f"Unknown Phase01 stage: {stage}")
        files = [Path(path) for path in outputs]
        if not files or any(not path.is_file() for path in files):
            raise FileNotFoundError("Every checkpoint stage requires existing file outputs")
        if len({path.name for path in files}) != len(files):
            raise ValueError("Checkpoint output basenames must be unique within a stage")
        generation_root = self.root / "stages" / stage / input_fingerprint
        checksums: dict[str, str] = {}
        uploads: list[tuple[Path, Path]] = []
        for source in files:
            remote_path = generation_root / source.name
            expected = sha256_file(source)
            uploads.append((source, remote_path))
            checksums[remote_path.as_posix()] = expected
        state = self.load_state()
        changed_record = state["stages"][stage]
        changed_record.update(
            {
                "status": "complete",
                "input_fingerprint": input_fingerprint,
                "config_hash": self.stage_config_hashes[stage],
                "model": {
                    "model_id": (model or {}).get("model_id"),
                    "model_revision": (model or {}).get("model_revision"),
                },
                "prompt_version": prompt_version,
                "schema_version": schema_version,
                "output_checksums": checksums,
                "completed_at": utc_now(),
                "error": None,
            }
        )
        for dependent in downstream_stages(stage):
            record = state["stages"][dependent]
            if record["status"] == "complete":
                record.update(self._empty_stage(dependent, status="invalidated"))
        state["status"] = self._video_status(state)
        state["config_hash"] = self.config_hash
        state["updated_at"] = utc_now()
        _validate_checkpoint_state(state)

        with tempfile.TemporaryDirectory(prefix="phase01_checkpoint_state_") as tmp:
            state_source = Path(tmp) / self.state_filename
            state_source.write_text(
                json.dumps(state, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            self.store.upload_files(
                [*uploads, (state_source, self.state_path)],
                commit_message=(
                    f"Promote Phase01 {stage} checkpoint "
                    f"for {self.release_id}/{self.video_id}"
                ),
                num_threads=min(2, len(uploads) + 1),
            )
        for source, remote_path in uploads:
            expected = checksums[remote_path.as_posix()]
            if self.verify_remote_checksum:
                with tempfile.TemporaryDirectory(prefix="phase01_checkpoint_upload_") as tmp:
                    downloaded = Path(tmp) / source.name
                    self.store.download_file(remote_path, downloaded)
                    actual = sha256_file(downloaded)
                if actual != expected:
                    raise ValueError(f"Remote checkpoint checksum mismatch: {remote_path}")

        self._state_cache = copy.deepcopy(state)
        return changed_record

    def mark_failed(
        self,
        stage: str,
        *,
        input_fingerprint: str | None,
        retryable: bool,
        error: Mapping[str, Any],
    ) -> None:
        state = self.load_state()
        status = "failed_retryable" if retryable else "failed_terminal"
        state["stages"][stage].update(
            {
                "status": status,
                "input_fingerprint": input_fingerprint,
                "config_hash": self.stage_config_hashes[stage],
                "completed_at": None,
                "output_checksums": {},
                "error": dict(error),
            }
        )
        for dependent in downstream_stages(stage):
            record = state["stages"][dependent]
            if record["status"] == "complete":
                record.update(self._empty_stage(dependent, status="invalidated"))
        state["status"] = status
        state["updated_at"] = utc_now()
        _validate_checkpoint_state(state)
        self.store.write_json(self.state_path, state)
        self._state_cache = copy.deepcopy(state)

    def _empty_state(self) -> dict[str, Any]:
        return {
            "schema_version": "phase01_checkpoint_state_v1",
            "release_id": self.release_id,
            "video_id": self.video_id,
            "config_hash": self.config_hash,
            "status": "pending",
            "stages": {stage: self._empty_stage(stage) for stage in STAGES},
            "updated_at": utc_now(),
        }

    def _empty_stage(self, stage: str, *, status: str = "pending") -> dict[str, Any]:
        return {
            "stage": stage,
            "status": status,
            "input_fingerprint": None,
            "config_hash": self.stage_config_hashes[stage],
            "model": {"model_id": None, "model_revision": None},
            "prompt_version": None,
            "schema_version": "unresolved",
            "output_checksums": {},
            "completed_at": None,
            "error": None,
        }

    def _validate_state_identity(self, payload: Mapping[str, Any]) -> None:
        if payload.get("schema_version") != "phase01_checkpoint_state_v1":
            raise ValueError("Unsupported Phase01 checkpoint schema")
        if payload.get("release_id") != self.release_id or payload.get("video_id") != self.video_id:
            raise ValueError("Checkpoint identity does not match requested release/video")
        stages = payload.get("stages")
        if not isinstance(stages, dict) or set(stages) != set(STAGES):
            raise ValueError("Checkpoint state has an invalid stage set")

    def _invalidate_stage(self, stage: str, state: dict[str, Any]) -> None:
        state["stages"][stage].update(self._empty_stage(stage, status="invalidated"))
        for dependent in downstream_stages(stage):
            record = state["stages"][dependent]
            if record["status"] == "complete":
                record.update(self._empty_stage(dependent, status="invalidated"))
        state["status"] = self._video_status(state)
        state["config_hash"] = self.config_hash
        state["updated_at"] = utc_now()
        _validate_checkpoint_state(state)
        self.store.write_json(self.state_path, state)
        self._state_cache = copy.deepcopy(state)

    @staticmethod
    def _video_status(state: Mapping[str, Any]) -> str:
        statuses = [record["status"] for record in state["stages"].values()]
        if statuses[-1] == "complete":
            return "complete"
        if "failed_terminal" in statuses:
            return "failed_terminal"
        if "failed_retryable" in statuses:
            return "failed_retryable"
        return "running" if "complete" in statuses else "pending"


def _validate_checkpoint_state(payload: Mapping[str, Any]) -> None:
    schema_path = (
        Path(__file__).resolve().parents[3]
        / "schemas"
        / "phase01_checkpoint_state.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validate(dict(payload), schema)
