from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol


class JsonListingStore(Protocol):
    def list_files(self, prefix: str | Path = "") -> list[Path]: ...

    def read_json(self, relative_path: str | Path) -> dict[str, Any]: ...


@dataclass(frozen=True)
class Phase00Candidate:
    release_id: str
    completed_at: datetime | None
    manifest_path: str
    manifest: dict[str, Any]


def discover_phase00_candidates(store: JsonListingStore) -> list[Phase00Candidate]:
    suffix = "/phase00_ingestion/reports/phase00_sync_manifest.json"
    candidates: list[Phase00Candidate] = []
    for path in store.list_files(""):
        normalized = path.as_posix()
        if not normalized.endswith(suffix):
            continue
        release_id = normalized[: -len(suffix)]
        if not release_id or "/" in release_id:
            continue
        manifest = store.read_json(path)
        if manifest.get("status") != "complete":
            continue
        if str(manifest.get("release_id", "")) != release_id:
            raise ValueError(
                f"Phase00 manifest release mismatch at {normalized}: "
                f"{manifest.get('release_id')!r} != {release_id!r}"
            )
        candidates.append(
            Phase00Candidate(
                release_id=release_id,
                completed_at=_parse_timestamp(manifest.get("completed_at"), normalized),
                manifest_path=normalized,
                manifest=manifest,
            )
        )
    return sorted(candidates, key=lambda item: item.release_id)


def resolve_phase00_release(
    candidates: list[Phase00Candidate],
    *,
    release_id_override: str | None = None,
) -> Phase00Candidate:
    override = str(release_id_override or "").strip()
    if override:
        matches = [candidate for candidate in candidates if candidate.release_id == override]
        if len(matches) != 1:
            raise ValueError(
                f"Phase00 release override is not a unique completed release: {override}"
            )
        return matches[0]
    if not candidates:
        raise ValueError("No completed Phase00 release was found")
    without_timestamp = [candidate.release_id for candidate in candidates if candidate.completed_at is None]
    if without_timestamp:
        raise ValueError(
            "Cannot auto-resolve Phase00 because completed_at is missing; set "
            "release_id_override. Affected releases: " + ", ".join(without_timestamp)
        )
    latest_time = max(candidate.completed_at for candidate in candidates)
    latest = [candidate for candidate in candidates if candidate.completed_at == latest_time]
    if len(latest) != 1:
        raise ValueError(
            "Cannot auto-resolve Phase00 because multiple completed releases share the "
            f"latest completed_at={latest_time.isoformat()}: "
            + ", ".join(candidate.release_id for candidate in latest)
        )
    return latest[0]


def _parse_timestamp(value: Any, manifest_path: str) -> datetime | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise TypeError(f"Phase00 completed_at must be a string at {manifest_path}")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"Invalid Phase00 completed_at at {manifest_path}: {value}") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"Phase00 completed_at must contain a timezone at {manifest_path}")
    return parsed
