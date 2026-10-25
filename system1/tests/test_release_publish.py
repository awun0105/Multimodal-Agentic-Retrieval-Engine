"""Behavior tests for uploading a built release to a bucket (plan Step 5b item 7)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from system1.release.publish import media_sink_for, publish_release

PREFIX = "releases_test/rel_v001"


class FakeBucket:
    """Records uploads; fails the first `fail` batch_add calls."""

    def __init__(self, fail: int = 0) -> None:
        self.fail = fail
        self.batches: list[list[str]] = []
        self.paths: set[str] = set()

    def batch_add(self, files):
        if self.fail:
            self.fail -= 1
            raise ConnectionError("bucket unavailable")
        self.batches.append([remote for _, remote in files])
        self.paths.update(remote for _, remote in files)

    def exists(self, remote_paths):
        return self.paths & set(remote_paths)


@pytest.fixture
def release(tmp_path) -> Path:
    root = tmp_path / "release"
    for relative in ("db/app.sqlite", "indexes/image_siglip2.faiss", "indexes/image_siglip2_vector_map.parquet",
                     *(f"media/keyframes/V1/V1_f{i:07d}.webp" for i in range(3)),
                     *(f"media/thumbnails/V1/V1_f{i:07d}.webp" for i in range(3))):
        (root / relative).parent.mkdir(parents=True, exist_ok=True)
        (root / relative).write_bytes(relative.encode())
    (root / "manifest.json").write_text(json.dumps({"release_id": "rel_v001", "counts": {"keyframes": 3}}))
    return root


def _uploads(bucket: FakeBucket) -> list[str]:
    return [path.removeprefix(PREFIX + "/") for batch in bucket.batches for path in batch]


def test_control_files_then_media_then_ready_last(release) -> None:
    bucket = FakeBucket()

    ready = publish_release(release, bucket_id="b", prefix=PREFIX, client=bucket, batch_size=4, sleep=lambda s: None)

    uploads = _uploads(bucket)
    kinds = ["control" if not p.startswith("media/") and p != "READY.json" else p.split("/")[0] for p in uploads]
    assert uploads[-1] == "READY.json"
    assert uploads.index("manifest.json") < min(uploads.index(p) for p in uploads if p.startswith("media/"))
    assert kinds == sorted(kinds, key=["control", "media", "READY.json"].index)
    assert bucket.batches[-1] == [f"{PREFIX}/READY.json"]
    assert len(uploads) == 4 + 6 + 1
    assert ready["release_id"] == "rel_v001"
    assert ready["file_count"] == 4 + 6
    assert ready["manifest_sha256"] == hashlib.sha256((release / "manifest.json").read_bytes()).hexdigest()
    assert json.loads((release / "READY.json").read_text()) == ready


class DyingBucket(FakeBucket):
    """Accepts `accept` batches, then fails every call, as when a session loses the network."""

    def __init__(self, accept: int) -> None:
        super().__init__()
        self.accept = accept

    def batch_add(self, files):
        if len(self.batches) == self.accept:
            raise ConnectionError("network gone")
        super().batch_add(files)


def test_rerun_skips_completed_batches(release) -> None:
    first = DyingBucket(accept=2)
    with pytest.raises(ConnectionError):
        publish_release(release, bucket_id="b", prefix=PREFIX, client=first, batch_size=4, sleep=lambda s: None)
    done = [path for batch in first.batches for path in batch]

    second = FakeBucket()
    second.paths = set(first.paths)  # same bucket, new session
    publish_release(release, bucket_id="b", prefix=PREFIX, client=second, batch_size=4, sleep=lambda s: None)

    resent = [path for batch in second.batches for path in batch]
    assert len(first.batches) == 2
    assert not set(done) & set(resent)
    assert set(done) | set(resent) == {f"{PREFIX}/{p}" for p in (
        "db/app.sqlite", "indexes/image_siglip2.faiss", "indexes/image_siglip2_vector_map.parquet",
        "manifest.json", "READY.json",
        *(f"media/{kind}/V1/V1_f{i:07d}.webp" for kind in ("keyframes", "thumbnails") for i in range(3)))}


def test_failed_batch_is_retried_with_backoff(release) -> None:
    bucket = FakeBucket(fail=2)
    sleeps: list[float] = []

    publish_release(release, bucket_id="b", prefix=PREFIX, client=bucket, batch_size=200, sleep=sleeps.append)

    assert sleeps == [5, 10]
    assert f"{PREFIX}/READY.json" in bucket.paths


def test_published_release_is_not_uploaded_again(release) -> None:
    bucket = FakeBucket()
    publish_release(release, bucket_id="b", prefix=PREFIX, client=bucket, sleep=lambda s: None)
    count = len(bucket.batches)

    publish_release(release, bucket_id="b", prefix=PREFIX, client=bucket, sleep=lambda s: None)

    assert len(bucket.batches) == count


def test_media_sink_uploads_one_video_then_deletes_it(release) -> None:
    bucket = FakeBucket()
    sink = media_sink_for(bucket, PREFIX, sleep=lambda s: None)

    sink("V1", release / "media")

    assert sorted(_uploads(bucket)) == sorted(
        f"media/{kind}/V1/V1_f{i:07d}.webp" for kind in ("keyframes", "thumbnails") for i in range(3))
    assert not (release / "media" / "keyframes" / "V1").exists()
    assert not (release / "media" / "thumbnails" / "V1").exists()
