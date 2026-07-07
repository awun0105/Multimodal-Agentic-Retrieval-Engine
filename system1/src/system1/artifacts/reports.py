from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from system1.release.types import write_json


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def worker_report_relative_path(phase: str, batch_id: str, worker_id: str) -> Path:
    return Path("manifests") / "worker_reports" / f"{_safe_name(phase)}_{_safe_name(batch_id)}_{_safe_name(worker_id)}.json"


def write_worker_report(
    release_dir: Path,
    *,
    phase: str,
    batch_id: str,
    worker_id: str,
    started_at: str,
    finished_at: str,
    videos_processed: int,
    videos_failed: int,
    payload: dict[str, Any],
) -> Path:
    status = "completed" if videos_failed == 0 else "completed_with_warnings"
    report = {
        **payload,
        "phase": phase,
        "batch_id": batch_id,
        "worker_id": worker_id,
        "started_at": started_at,
        "finished_at": finished_at,
        "videos_processed": videos_processed,
        "videos_failed": videos_failed,
        "status": status,
    }
    report_path = release_dir / worker_report_relative_path(phase, batch_id, worker_id)
    write_json(report_path, report)
    return report_path


def _safe_name(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    return safe.strip("._") or "unknown"
