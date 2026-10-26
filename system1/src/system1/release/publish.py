"""Upload a built release to a Hugging Face Storage Bucket (ADR 0025, plan Step 5b item 7).

Order: `db/`, `indexes/`, `manifest.json`, then `media/`, then `READY.json`
last. A reader treats a prefix without `READY.json` as incomplete. Uploads go
in batches; finished batches are recorded in `{release_dir}/.upload-state.json`
so a rerun skips them. Pattern follows `mvp-app/tools/upload_release.py`.

`client` is any object with `batch_add(list[(local_path, remote_path)])` and
`exists(remote_paths) -> set[str]`, and `list_folders(prefix) -> set[str]` for
the media sink resume; `BucketClient` wraps huggingface_hub.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, Protocol

BATCH_SIZE = 200
RETRIES = 5
STATE_FILE = ".upload-state.json"
READY_FILE = "READY.json"


class Client(Protocol):
    def batch_add(self, files: Sequence[tuple[Path, str]]) -> None: ...

    def exists(self, remote_paths: Sequence[str]) -> set[str]: ...

    def list_folders(self, prefix: str) -> set[str]: ...


class BucketClient:
    """huggingface_hub bucket calls, as in mvp-app/tools/upload_release.py."""

    def __init__(self, bucket_id: str, token: str | None = None) -> None:
        self.bucket_id = bucket_id
        self.token = token

    def batch_add(self, files: Sequence[tuple[Path, str]]) -> None:
        from huggingface_hub import HfApi

        HfApi(token=self.token).batch_bucket_files(self.bucket_id, add=[(str(local), remote)
                                                                        for local, remote in files])

    def exists(self, remote_paths: Sequence[str]) -> set[str]:
        from huggingface_hub import get_bucket_paths_info

        return {item.path for item in get_bucket_paths_info(self.bucket_id, list(remote_paths))}

    def list_folders(self, prefix: str) -> set[str]:
        """Names of the direct subfolders of `prefix`."""
        from huggingface_hub import BucketFolder, list_bucket_tree

        return {item.path.rstrip("/").rsplit("/", 1)[-1]
                for item in list_bucket_tree(self.bucket_id, prefix, recursive=False, token=self.token)
                if isinstance(item, BucketFolder)}


def publish_release(
    release_dir: Path,
    *,
    bucket_id: str,
    prefix: str,
    client: Client,
    batch_size: int = BATCH_SIZE,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Upload `release_dir` under `prefix`; returns the READY.json payload."""

    release_dir = Path(release_dir)
    prefix = prefix.strip("/")
    manifest_path = release_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    ready_remote = f"{prefix}/{READY_FILE}"
    control = [path for folder in ("db", "indexes") for path in _files(release_dir / folder)] + [manifest_path]
    ready = {
        "release_id": manifest["release_id"],
        "manifest_sha256": _sha256(manifest_path),
        # Media may have been uploaded and deleted during the build, so count it from the manifest.
        "file_count": len(control) + 2 * int(manifest["counts"]["keyframes"]),
    }
    if ready_remote in client.exists([ready_remote]):
        return ready

    state_path = release_dir / STATE_FILE
    state = _load_state(state_path, bucket_id=bucket_id, prefix=prefix, manifest_sha256=ready["manifest_sha256"])
    files = [*control, *_files(release_dir / "media")]
    pairs = [(path, f"{prefix}/{path.relative_to(release_dir).as_posix()}") for path in files]
    for start in range(0, len(pairs), batch_size):
        batch = pairs[start:start + batch_size]
        key = _batch_key(batch)
        if key in state["completed_batches"]:
            continue
        _with_retry(lambda: client.batch_add(batch), sleep=sleep)
        state["completed_batches"].append(key)
        _save_state(state_path, state)

    manifest_remote = f"{prefix}/manifest.json"
    if manifest_remote not in client.exists([manifest_remote]):
        raise RuntimeError(f"{manifest_remote} is not visible after upload")
    ready_path = release_dir / READY_FILE
    ready_path.write_text(json.dumps(ready, indent=1), encoding="utf-8")
    _with_retry(lambda: client.batch_add([(ready_path, ready_remote)]), sleep=sleep)
    return ready


def media_sink_for(
    client: Client,
    prefix: str,
    *,
    batch_size: int = BATCH_SIZE,
    sleep: Callable[[float], None] = time.sleep,
) -> Callable[[str, Path], None]:
    """A `build_release` media sink: upload one video's media under `prefix/media/`, then delete it.

    Videos whose `media/keyframes/{video_id}` folder is already in the bucket when the sink is
    created are not uploaded again; `sink.stats` counts uploaded and skipped videos. If listing
    fails, every video is uploaded.
    """

    prefix = prefix.strip("/")
    try:
        published = client.list_folders(f"{prefix}/media/keyframes")
    except Exception as exc:
        print(f"Media listing failed, uploading every video: {exc}", flush=True)
        published = set()
    if published:
        print(f"Media already in bucket for {len(published)} videos; skipping them", flush=True)
    stats = {"uploaded": 0, "skipped": 0}

    def sink(video_id: str, media_root: Path) -> None:
        folders = [media_root / kind / video_id for kind in ("keyframes", "thumbnails")]
        if video_id in published:
            stats["skipped"] += 1
            for folder in folders:
                shutil.rmtree(folder, ignore_errors=True)
            return
        pairs = [(path, f"{prefix}/media/{path.relative_to(media_root).as_posix()}")
                 for folder in folders for path in _files(folder)]
        for start in range(0, len(pairs), batch_size):
            batch = pairs[start:start + batch_size]
            _with_retry(lambda: client.batch_add(batch), sleep=sleep)
        for folder in folders:
            shutil.rmtree(folder, ignore_errors=True)
        stats["uploaded"] += 1

    sink.stats = stats  # type: ignore[attr-defined]
    return sink


def _with_retry(call: Callable[[], None], *, sleep: Callable[[float], None], retries: int = RETRIES) -> None:
    for attempt in range(retries + 1):
        try:
            call()
            return
        except Exception as exc:
            if attempt == retries:
                raise
            delay = min(60, 5 * 2**attempt)
            print(f"Upload retry {attempt + 1}/{retries} in {delay}s: {exc}", flush=True)
            sleep(delay)


def _files(folder: Path) -> list[Path]:
    return sorted(path for path in folder.rglob("*") if path.is_file()) if folder.is_dir() else []


def _batch_key(batch: Sequence[tuple[Path, str]]) -> str:
    return hashlib.sha256("\n".join(remote for _, remote in batch).encode()).hexdigest()


def _load_state(path: Path, **expected: str) -> dict[str, Any]:
    if path.is_file():
        state = json.loads(path.read_text(encoding="utf-8"))
        if all(state.get(key) == value for key, value in expected.items()):
            return state
    return {**expected, "completed_batches": []}


def _save_state(path: Path, state: dict[str, Any]) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, indent=1), encoding="utf-8")
    temporary.replace(path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
