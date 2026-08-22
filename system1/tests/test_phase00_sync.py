from __future__ import annotations

import json
from pathlib import Path

from system1.release import sync as sync_module
from system1.release.sync import upload_phase00_ingestion_to_hf


class InMemoryPhase00Store:
    def __init__(self) -> None:
        self.remote: dict[str, bytes] = {}
        self.commits: list[dict[str, object]] = []

    def list_files(self, prefix: str = "") -> list[Path]:
        return [Path(path) for path in sorted(self.remote) if path.startswith(prefix)]

    def download_file(self, relative_path: str, target: Path, *, cache_dir=None) -> Path:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(self.remote[relative_path])
        return target

    def sync_files(
        self,
        files: list[tuple[Path, str]],
        *,
        delete_paths=(),
        commit_message: str,
        num_threads: int = 2,
    ) -> list[Path]:
        self.commits.append(
            {
                "adds": [remote_path for _source, remote_path in files],
                "deletes": list(delete_paths),
                "message": commit_message,
            }
        )
        for remote_path in delete_paths:
            self.remote.pop(str(remote_path), None)
        for source, remote_path in files:
            self.remote[remote_path] = source.read_bytes()
        return [self.path(remote_path) for _source, remote_path in files]

    def path(self, relative_path: str) -> Path:
        return Path("hf:/org/repo") / relative_path


def test_phase00_sync_skips_unchanged_and_reconciles_only_exact_prefix(monkeypatch, tmp_path: Path) -> None:
    release_dir = tmp_path / "canonical_release_v009"
    (release_dir / "tables").mkdir(parents=True)
    (release_dir / "manifests").mkdir(parents=True)
    (release_dir / "tables" / "videos.parquet").write_bytes(b"videos")
    (release_dir / "manifests" / "dataset_report.json").write_text('{"ok": true}\n', encoding="utf-8")
    store = InMemoryPhase00Store()
    monkeypatch.setattr(sync_module, "_store", lambda **_kwargs: store)

    first = upload_phase00_ingestion_to_hf(release_dir, repo_id="org/repo")
    assert first.file_count == 2
    root = "canonical_release_v009/phase00_ingestion"
    stale_path = f"{root}/manifests/batch_999.txt"
    outside_path = "canonical_release_v008/phase00_ingestion/manifests/batch_999.txt"
    store.remote[stale_path] = b"stale"
    store.remote[outside_path] = b"outside"
    store.commits.clear()

    second = upload_phase00_ingestion_to_hf(release_dir, repo_id="org/repo")

    assert second.file_count == 2
    assert stale_path not in store.remote
    assert outside_path in store.remote
    operation_commits = [commit for commit in store.commits if commit["message"] != "Complete canonical_release_v009 phase00 sync"]
    assert operation_commits == [
        {
            "adds": [],
            "deletes": [
                f"{root}/reports/phase00_sync_manifest.json",
                stale_path,
            ],
            "message": "Sync canonical_release_v009 phase00 batch 1/1",
        }
    ]
    completion = json.loads(
        store.remote[f"{root}/reports/phase00_sync_manifest.json"].decode("utf-8")
    )
    assert completion["status"] == "complete"
    assert completion["uploaded_count"] == 0
    assert completion["skipped_unchanged_count"] == 2
    assert completion["deleted_remote_paths"] == [stale_path]


def test_phase00_sync_retries_transient_commit_error(monkeypatch, tmp_path: Path) -> None:
    class Response:
        status_code = 429
        headers = {"Retry-After": "0"}

    class RateLimitError(RuntimeError):
        response = Response()

    class RetryStore(InMemoryPhase00Store):
        def __init__(self) -> None:
            super().__init__()
            self.attempts = 0

        def sync_files(self, files, *, delete_paths=(), commit_message, num_threads=2):
            self.attempts += 1
            if self.attempts < 3:
                raise RateLimitError("429 Too Many Requests")
            return super().sync_files(
                files,
                delete_paths=delete_paths,
                commit_message=commit_message,
                num_threads=num_threads,
            )

    store = RetryStore()
    sleeps: list[float] = []
    monkeypatch.setattr(sync_module.time, "sleep", sleeps.append)
    source = tmp_path / "a.bin"
    source.write_bytes(b"a")

    sync_module._sync_phase00_batch_with_retry(
        store,
        files=[(source, "root/a.bin")],
        delete_paths=[],
        commit_message="retry",
    )

    assert store.attempts == 3
    assert sleeps == [0.0, 0.0]


def test_phase00_sync_removes_old_completion_marker_before_partial_update(
    monkeypatch,
    tmp_path: Path,
) -> None:
    class FailingStore(InMemoryPhase00Store):
        fail_batch_two = False

        def sync_files(self, files, *, delete_paths=(), commit_message, num_threads=2):
            if self.fail_batch_two and "batch 2/2" in commit_message:
                raise ValueError("non-retryable batch failure")
            return super().sync_files(
                files,
                delete_paths=delete_paths,
                commit_message=commit_message,
                num_threads=num_threads,
            )

    release_dir = tmp_path / "canonical_release_v009"
    (release_dir / "tables").mkdir(parents=True)
    for index in range(3):
        (release_dir / "tables" / f"table_{index}.parquet").write_bytes(
            f"old-{index}".encode()
        )
    store = FailingStore()
    monkeypatch.setattr(sync_module, "_store", lambda **_kwargs: store)
    monkeypatch.setattr(sync_module, "PHASE00_SYNC_BATCH_SIZE", 2)
    upload_phase00_ingestion_to_hf(release_dir, repo_id="org/repo")

    for index in range(3):
        (release_dir / "tables" / f"table_{index}.parquet").write_bytes(
            f"new-{index}".encode()
        )
    store.fail_batch_two = True
    completion_path = (
        "canonical_release_v009/phase00_ingestion/"
        "reports/phase00_sync_manifest.json"
    )

    try:
        upload_phase00_ingestion_to_hf(release_dir, repo_id="org/repo")
    except ValueError as exc:
        assert "non-retryable" in str(exc)
    else:
        raise AssertionError("expected the second Phase00 batch to fail")

    assert completion_path not in store.remote
