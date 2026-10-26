"""Run the caption pass over one batch of worker packages with remote storage.

Remote layout (ADR 0025, docs/architecture/system1-target.md):

    {release_id}/worker/artifacts/{batch_id}/{video_id}.zip     read from the worker store
    {release_id}/captions/artifacts/{batch_id}/{video_id}.zip   written to the output store
    {release_id}/captions/reports/{batch_id}_{worker_id}.json

A video whose caption package already exists is skipped. Worker ZIPs are
downloaded one at a time and removed after each video. With `persist_dir` the
report is also written there after every video, so it survives a dead session.
"""

from __future__ import annotations

import json
import shutil
import traceback
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from system1.captions.video import Captioner, TextEmbedder, caption_video
from system1.worker.batch import Store


@dataclass(frozen=True)
class CaptionPaths:
    release_id: str
    batch_id: str
    worker_id: str

    @property
    def worker_artifacts(self) -> str:
        return f"{self.release_id}/worker/artifacts/{self.batch_id}"

    @property
    def artifacts(self) -> str:
        return f"{self.release_id}/captions/artifacts/{self.batch_id}"

    @property
    def report(self) -> str:
        return f"{self.release_id}/captions/reports/{self.batch_id}_{self.worker_id}.json"


def run_caption_batch(
    paths: CaptionPaths,
    *,
    config: Mapping[str, Any],
    captioner: Captioner,
    text_embedder: TextEmbedder,
    worker_store: Store,
    output_store: Store,
    work_root: Path,
    limit: int | None = None,
    persist_dir: Path | None = None,
) -> dict[str, Any]:
    work_root.mkdir(parents=True, exist_ok=True)
    packages = sorted(Path(path) for path in worker_store.list_files(paths.worker_artifacts)
                      if Path(path).suffix == ".zip")
    done = {Path(path).name for path in output_store.list_files(paths.artifacts)}

    report: dict[str, Any] = {"release_id": paths.release_id, "batch_id": paths.batch_id,
                              "worker_id": paths.worker_id, "started_at": _now(),
                              "completed": [], "skipped": [], "failed": {}, "seconds": {}}
    for remote in packages[:limit]:
        video_id = remote.stem
        if remote.name in done:
            report["skipped"].append(video_id)
            continue
        started = datetime.now(UTC)
        try:
            worker_zip = worker_store.download_file(str(remote), work_root / "packages" / remote.name)
            zip_path = caption_video(worker_zip, config=config, captioner=captioner, text_embedder=text_embedder,
                                     work_root=work_root / "work", batch_id=paths.batch_id,
                                     worker_id=paths.worker_id)
            remote_zip = f"{paths.artifacts}/{video_id}.zip"
            if output_store.exists(remote_zip):  # another session uploaded it meanwhile
                report["skipped"].append(video_id)
            else:
                output_store.upload_file(zip_path, remote_zip)
                report["completed"].append(video_id)
        except Exception as exc:
            report["failed"][video_id] = f"{type(exc).__name__}: {exc}"[:500]
            traceback.print_exc()
        report["seconds"][video_id] = round((datetime.now(UTC) - started).total_seconds(), 1)
        for path in (work_root / "packages", work_root / "work", work_root / ".hf_cache"):
            shutil.rmtree(path, ignore_errors=True)
        if persist_dir is not None:
            _write_report(persist_dir / "report.json", report)
    report["finished_at"] = _now()

    report_path = _write_report(work_root / "report.json", report)
    if persist_dir is not None:
        _write_report(persist_dir / "report.json", report)
    output_store.upload_file(report_path, paths.report)
    shutil.rmtree(work_root, ignore_errors=True)
    return report


def _write_report(path: Path, report: Mapping[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
