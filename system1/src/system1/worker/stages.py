"""Stage checkpoints for one video.

A stage is skipped on rerun when its marker records a passing run with the same
fingerprint. The fingerprint covers the stage name, its configuration, and the
outcome fingerprints of the stages it reads, so a configuration change or a
different upstream result reruns only the affected stage and the stages after
it. Failed and fallback stages always run again.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

StageReport = dict[str, Any]
RETRY_STATUSES = {"failed", "fallback"}  # rerun these stages on the next attempt


class StageRunner:
    def __init__(self, marker_dir: Path) -> None:
        self.marker_dir = marker_dir
        self.marker_dir.mkdir(parents=True, exist_ok=True)
        self.fingerprints: dict[str, str] = {}
        self.reports: dict[str, StageReport] = {}

    def run(
        self,
        name: str,
        *,
        config: Mapping[str, Any] | None,
        upstream: Sequence[str],
        fn: Callable[[], StageReport],
        degrade: bool = False,
    ) -> StageReport:
        """Run `fn` unless a passing marker with the same fingerprint exists.

        With `degrade=True` an exception is recorded as a failed stage and the
        video continues (ADR 0024); otherwise it propagates.
        """

        fingerprint = _fingerprint(name, config, [self.fingerprints[stage] for stage in upstream])
        marker = self.marker_dir / f"{name}.json"
        if marker.exists():
            saved = json.loads(marker.read_text(encoding="utf-8"))
            if saved["fingerprint"] == fingerprint and saved["report"]["status"] not in RETRY_STATUSES:
                return self._remember(name, fingerprint, saved["report"])
        start = time.monotonic()
        try:
            report = fn()
        except Exception as exc:
            if not degrade:
                raise
            report = {"status": "failed", "error": f"{type(exc).__name__}: {exc}"[:500]}
        report["seconds"] = round(time.monotonic() - start, 1)
        marker.write_text(json.dumps({"fingerprint": fingerprint, "report": report},
                                     ensure_ascii=False, indent=1), encoding="utf-8")
        return self._remember(name, fingerprint, report)

    def _remember(self, name: str, fingerprint: str, report: StageReport) -> StageReport:
        # Downstream stages see the result too, so a rerun with a different
        # outcome (for example a cut fallback that now passes) reruns them.
        outcome = {key: value for key, value in report.items() if key != "seconds"}
        self.fingerprints[name] = _fingerprint(name, outcome, [fingerprint])
        self.reports[name] = report
        return report


def _fingerprint(name: str, config: Mapping[str, Any] | None, upstream: Sequence[str]) -> str:
    payload = json.dumps({"stage": name, "config": config, "upstream": list(upstream)},
                         sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
