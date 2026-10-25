"""Run one Phase00 batch through the per-video worker with remote storage.

Remote layout (docs/architecture/system1-target.md):

    {release_id}/phase00_ingestion/...                        read from the source store
    {release_id}/worker/artifacts/{batch_id}/{video_id}.zip   written to the output store
    {release_id}/worker/reports/{batch_id}_{worker_id}.json

A video whose package already exists in the output store is skipped, so a
restarted session continues where the last one stopped. A failed video is
recorded and the batch continues. Local files, including a Hugging Face
download cache at `work_root/.hf_cache`, are removed after each video.
"""

from __future__ import annotations

import json
import shutil
import traceback
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

import pandas as pd

from system1.worker.video import VideoInput, WorkerModels, process_video


class Store(Protocol):
    def download_file(self, relative_path: str, target: Path) -> Path: ...

    def upload_file(self, source: Path, relative_path: str) -> Path: ...

    def list_files(self, prefix: str = "") -> list[Path]: ...


@dataclass(frozen=True)
class BatchPaths:
    release_id: str
    batch_id: str
    worker_id: str

    @property
    def phase00(self) -> str:
        return f"{self.release_id}/phase00_ingestion"

    @property
    def artifacts(self) -> str:
        return f"{self.release_id}/worker/artifacts/{self.batch_id}"

    @property
    def report(self) -> str:
        return f"{self.release_id}/worker/reports/{self.batch_id}_{self.worker_id}.json"


def run_batch(
    paths: BatchPaths,
    *,
    config: Mapping[str, Any],
    models: WorkerModels,
    raw_store: Store,
    source_store: Store,
    output_store: Store,
    work_root: Path,
    limit: int | None = None,
) -> dict[str, Any]:
    work_root.mkdir(parents=True, exist_ok=True)
    inputs = work_root / "inputs"
    manifest = source_store.download_file(f"{paths.phase00}/manifests/{paths.batch_id}.txt",
                                          inputs / f"{paths.batch_id}.txt")
    video_ids = [line.strip() for line in manifest.read_text(encoding="utf-8").splitlines() if line.strip()]
    mapping = pd.read_parquet(source_store.download_file(
        f"{paths.phase00}/raw_mapping/media_store_manifest.parquet", inputs / "media_store_manifest.parquet",
    )).set_index("video_id")
    uploaded = {Path(path).name for path in output_store.list_files(paths.artifacts)}

    report: dict[str, Any] = {"release_id": paths.release_id, "batch_id": paths.batch_id,
                              "worker_id": paths.worker_id, "started_at": _now(),
                              "completed": [], "skipped": [], "failed": {}, "seconds": {}}
    for video_id in video_ids[:limit]:
        if f"{video_id}.zip" in uploaded:
            report["skipped"].append(video_id)
            continue
        started = datetime.now(UTC)
        try:
            video = _download_video(video_id, mapping.loc[video_id], raw_store, work_root / "videos")
            zip_path = process_video(video, config=config, models=models, work_root=work_root / "work",
                                     batch_id=paths.batch_id, worker_id=paths.worker_id)
            output_store.upload_file(zip_path, f"{paths.artifacts}/{video_id}.zip")
            report["completed"].append(video_id)
        except Exception as exc:
            report["failed"][video_id] = f"{type(exc).__name__}: {exc}"[:500]
            traceback.print_exc()
        report["seconds"][video_id] = round((datetime.now(UTC) - started).total_seconds(), 1)
        for path in (work_root / "videos", work_root / "work", work_root / ".hf_cache"):
            shutil.rmtree(path, ignore_errors=True)
    report["finished_at"] = _now()

    report_path = work_root / "report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    output_store.upload_file(report_path, paths.report)
    shutil.rmtree(work_root, ignore_errors=True)
    return report


def _download_video(video_id: str, row: Any, raw_store: Store, target: Path) -> VideoInput:
    prefix = str(row["canonical_prefix"]).strip("/")
    video = raw_store.download_file(f"{prefix}/{row['canonical_video_path']}", target / f"{video_id}.mp4")
    timeline = raw_store.download_file(f"{prefix}/{row['canonical_frame_timeline_path']}",
                                       target / f"{video_id}.parquet")
    rows = pd.read_parquet(timeline).sort_values("frame_id").to_dict("records")
    return VideoInput(video_id=video_id, video_path=video, timeline_rows=rows)


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
