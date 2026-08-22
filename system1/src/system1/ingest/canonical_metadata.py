from __future__ import annotations

import hashlib
import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from system1.media.probe import VideoProbe, probe_video

CANONICAL_METADATA_SCHEMA_VERSION = "1.0"
PROBE_MAX_ATTEMPTS = 3
PROBE_RETRY_DELAYS_SECONDS = (0.5, 1.0)
ORGANIZER_STRING_FIELDS = (
    "author",
    "channel_id",
    "channel_url",
    "description",
    "thumbnail_url",
    "title",
    "watch_url",
)
ORGANIZER_FIELDS = (
    "author",
    "channel_id",
    "channel_url",
    "description",
    "keywords",
    "length",
    "publish_date",
    "thumbnail_url",
    "title",
    "watch_url",
)
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class CanonicalMetadataError(ValueError):
    pass


@dataclass(frozen=True)
class CanonicalMetadataResult:
    payload: dict[str, Any]
    probe: VideoProbe
    probe_status: str
    probe_attempts: int
    organizer_metadata_present: bool
    metadata_generated: bool


def build_canonical_metadata(
    video_path: Path,
    *,
    video_id: str,
    organizer_metadata_path: Path | None = None,
    organizer_source_ref: str | None = None,
    probe_fn: Callable[[Path], VideoProbe] | None = None,
    precomputed_probe: VideoProbe | None = None,
    precomputed_probe_attempts: int = 1,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> CanonicalMetadataResult:
    organizer = _read_organizer_metadata(
        organizer_metadata_path,
        video_id=video_id,
        organizer_source_ref=organizer_source_ref,
    )
    if precomputed_probe is not None:
        if precomputed_probe_attempts < 1:
            raise CanonicalMetadataError("precomputed_probe_attempts must be >= 1")
        probe = precomputed_probe
        probe_status = canonical_probe_status(probe)
        probe_attempts = precomputed_probe_attempts
    else:
        probe, probe_status, probe_attempts = probe_video_with_retry(
            video_path,
            probe_fn=probe_fn,
            sleep_fn=sleep_fn,
        )
    metadata_generated = not organizer["present"]
    payload: dict[str, Any] = {
        "schema_version": CANONICAL_METADATA_SCHEMA_VERSION,
        "video_id": video_id,
        "organizer_metadata_present": organizer["present"],
        **organizer["fields"],
        "media": {
            "filename": video_path.name,
            "file_size_bytes": video_path.stat().st_size,
            "duration_sec": probe.duration_seconds,
            "fps": probe.fps_detected,
            "frame_count": probe.frame_count,
            "width": probe.width,
            "height": probe.height,
            "is_vfr": probe.is_vfr,
            "probe_status": probe_status,
            "probe_attempts": probe_attempts,
        },
        "provenance": {
            "organizer_metadata_source_ref": organizer["source_ref"],
            "organizer_metadata_sha256": organizer["sha256"],
            "technical_metadata_source": "ffprobe",
            "metadata_generated": metadata_generated,
        },
    }
    validate_canonical_metadata(payload, expected_video_id=video_id)
    return CanonicalMetadataResult(
        payload=payload,
        probe=probe,
        probe_status=probe_status,
        probe_attempts=probe_attempts,
        organizer_metadata_present=organizer["present"],
        metadata_generated=metadata_generated,
    )


def probe_video_with_retry(
    video_path: Path,
    *,
    probe_fn: Callable[[Path], VideoProbe] | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> tuple[VideoProbe, str, int]:
    resolved_probe = probe_fn or probe_video
    last_probe = _empty_probe()
    for attempt in range(1, PROBE_MAX_ATTEMPTS + 1):
        try:
            last_probe = resolved_probe(video_path)
        except Exception:  # noqa: BLE001 - probing is a retry boundary for external ffprobe failures
            last_probe = _empty_probe()
        status = canonical_probe_status(last_probe)
        if status == "pass" or attempt == PROBE_MAX_ATTEMPTS:
            return last_probe, status, attempt
        sleep_fn(PROBE_RETRY_DELAYS_SECONDS[attempt - 1])
    raise AssertionError("unreachable")


def canonical_probe_status(probe: VideoProbe) -> str:
    required_values = (
        probe.duration_seconds,
        probe.fps_detected,
        probe.frame_count,
        probe.width,
        probe.height,
    )
    available = sum(value is not None for value in required_values)
    if available == len(required_values):
        return "pass"
    return "failed" if available == 0 else "partial"


def write_canonical_metadata(path: Path, payload: dict[str, Any]) -> None:
    validate_canonical_metadata(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def canonical_inventory_projection(payload: dict[str, Any]) -> dict[str, Any]:
    validate_canonical_metadata(payload)
    media = payload["media"]
    provenance = payload["provenance"]
    return {
        "metadata_schema_version": payload["schema_version"],
        "organizer_metadata_present": payload["organizer_metadata_present"],
        "metadata_generated": provenance["metadata_generated"],
        "duration_sec": media["duration_sec"],
        "fps": media["fps"],
        "frame_count": media["frame_count"],
        "width": media["width"],
        "height": media["height"],
        "is_vfr": media["is_vfr"],
        "file_size_bytes": media["file_size_bytes"],
        "probe_status": media["probe_status"],
        "probe_attempts": media["probe_attempts"],
    }


def validate_canonical_metadata(
    payload: dict[str, Any], *, expected_video_id: str | None = None
) -> None:
    if not isinstance(payload, dict):
        raise CanonicalMetadataError("canonical metadata must be a JSON object")
    required_top_level = {
        "schema_version",
        "video_id",
        "organizer_metadata_present",
        *ORGANIZER_FIELDS,
        "media",
        "provenance",
    }
    missing_top_level = sorted(required_top_level - payload.keys())
    if missing_top_level:
        raise CanonicalMetadataError(
            f"canonical metadata missing fields: {', '.join(missing_top_level)}"
        )
    if payload.get("schema_version") != CANONICAL_METADATA_SCHEMA_VERSION:
        raise CanonicalMetadataError(
            f"canonical metadata schema_version must be {CANONICAL_METADATA_SCHEMA_VERSION!r}"
        )
    video_id = payload.get("video_id")
    if not isinstance(video_id, str) or not video_id.strip():
        raise CanonicalMetadataError(
            "canonical metadata video_id must be a non-empty string"
        )
    if expected_video_id is not None and video_id != expected_video_id:
        raise CanonicalMetadataError(
            f"canonical metadata video_id mismatch: expected={expected_video_id} actual={video_id}"
        )
    organizer_present = payload.get("organizer_metadata_present")
    if not isinstance(organizer_present, bool):
        raise CanonicalMetadataError("organizer_metadata_present must be a boolean")
    for field in ORGANIZER_STRING_FIELDS:
        _validate_nullable_string(payload.get(field), field)
    keywords = payload.get("keywords")
    if not isinstance(keywords, list) or any(
        not isinstance(value, str) for value in keywords
    ):
        raise CanonicalMetadataError("keywords must be a list of strings")
    length = payload.get("length")
    if length is not None and (
        not isinstance(length, int) or isinstance(length, bool) or length < 0
    ):
        raise CanonicalMetadataError("length must be a non-negative integer or null")
    publish_date = payload.get("publish_date")
    _validate_nullable_string(publish_date, "publish_date")
    if publish_date is not None:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", publish_date) is None:
            raise CanonicalMetadataError("publish_date must use YYYY-MM-DD")
        try:
            date.fromisoformat(publish_date)
        except ValueError as exc:
            raise CanonicalMetadataError("publish_date must use YYYY-MM-DD") from exc

    media = payload.get("media")
    if not isinstance(media, dict):
        raise CanonicalMetadataError("media must be an object")
    required_media = {
        "filename",
        "file_size_bytes",
        "duration_sec",
        "fps",
        "frame_count",
        "width",
        "height",
        "is_vfr",
        "probe_status",
        "probe_attempts",
    }
    missing_media = sorted(required_media - media.keys())
    if missing_media:
        raise CanonicalMetadataError(
            f"canonical metadata media missing fields: {', '.join(missing_media)}"
        )
    if not isinstance(media.get("filename"), str) or not media["filename"]:
        raise CanonicalMetadataError("media.filename must be a non-empty string")
    _validate_number(
        media.get("file_size_bytes"), "media.file_size_bytes", integer=True, minimum=0
    )
    _validate_number(
        media.get("duration_sec"), "media.duration_sec", minimum=0, nullable=True
    )
    _validate_number(media.get("fps"), "media.fps", minimum=0, nullable=True)
    _validate_number(
        media.get("frame_count"),
        "media.frame_count",
        integer=True,
        minimum=0,
        nullable=True,
    )
    _validate_number(
        media.get("width"), "media.width", integer=True, minimum=1, nullable=True
    )
    _validate_number(
        media.get("height"), "media.height", integer=True, minimum=1, nullable=True
    )
    if media.get("is_vfr") is not None and not isinstance(media["is_vfr"], bool):
        raise CanonicalMetadataError("media.is_vfr must be a boolean or null")
    probe_status = media.get("probe_status")
    if probe_status not in {"pass", "partial", "failed"}:
        raise CanonicalMetadataError(
            "media.probe_status must be pass, partial, or failed"
        )
    _validate_number(
        media.get("probe_attempts"), "media.probe_attempts", integer=True, minimum=1
    )
    required_probe_values = [
        media.get(key)
        for key in ("duration_sec", "fps", "frame_count", "width", "height")
    ]
    expected_probe_status = (
        "pass"
        if all(value is not None for value in required_probe_values)
        else "failed"
        if all(value is None for value in required_probe_values)
        else "partial"
    )
    if probe_status != expected_probe_status:
        raise CanonicalMetadataError(
            f"media.probe_status mismatch: expected={expected_probe_status} actual={probe_status}"
        )

    provenance = payload.get("provenance")
    if not isinstance(provenance, dict):
        raise CanonicalMetadataError("provenance must be an object")
    required_provenance = {
        "organizer_metadata_source_ref",
        "organizer_metadata_sha256",
        "technical_metadata_source",
        "metadata_generated",
    }
    missing_provenance = sorted(required_provenance - provenance.keys())
    if missing_provenance:
        raise CanonicalMetadataError(
            "canonical metadata provenance missing fields: "
            f"{', '.join(missing_provenance)}"
        )
    source_ref = provenance.get("organizer_metadata_source_ref")
    _validate_nullable_string(source_ref, "provenance.organizer_metadata_source_ref")
    source_sha256 = provenance.get("organizer_metadata_sha256")
    if source_sha256 is not None and (
        not isinstance(source_sha256, str)
        or _SHA256_PATTERN.fullmatch(source_sha256) is None
    ):
        raise CanonicalMetadataError(
            "provenance.organizer_metadata_sha256 must be lowercase SHA-256 or null"
        )
    if provenance.get("technical_metadata_source") != "ffprobe":
        raise CanonicalMetadataError(
            "provenance.technical_metadata_source must be ffprobe"
        )
    if provenance.get("metadata_generated") is not (not organizer_present):
        raise CanonicalMetadataError(
            "provenance.metadata_generated must equal not organizer_metadata_present"
        )
    if not organizer_present:
        if source_ref is not None or source_sha256 is not None:
            raise CanonicalMetadataError(
                "missing organizer metadata must have null source provenance"
            )
        for field in ORGANIZER_FIELDS:
            expected = [] if field == "keywords" else None
            if payload.get(field) != expected:
                raise CanonicalMetadataError(
                    f"missing organizer metadata requires {field}={expected!r}"
                )


def _read_organizer_metadata(
    path: Path | None,
    *,
    video_id: str,
    organizer_source_ref: str | None,
) -> dict[str, Any]:
    empty = {
        "present": False,
        "fields": _empty_organizer_fields(),
        "source_ref": None,
        "sha256": None,
    }
    if path is None:
        return empty
    try:
        raw_bytes = path.read_bytes()
        payload = json.loads(raw_bytes.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CanonicalMetadataError(
            f"invalid organizer metadata for video_id={video_id}: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise CanonicalMetadataError(
            f"organizer metadata for video_id={video_id} must be a JSON object"
        )
    if payload.get("metadata_missing") is True:
        return empty
    if payload.get("schema_version") == CANONICAL_METADATA_SCHEMA_VERSION:
        validate_canonical_metadata(payload, expected_video_id=video_id)
        if not payload["organizer_metadata_present"]:
            return empty
        provenance = payload["provenance"]
        return {
            "present": True,
            "fields": {field: payload[field] for field in ORGANIZER_FIELDS},
            "source_ref": provenance.get("organizer_metadata_source_ref"),
            "sha256": provenance.get("organizer_metadata_sha256"),
        }
    source_video_id = payload.get("video_id")
    if source_video_id not in (None, video_id):
        raise CanonicalMetadataError(
            f"organizer metadata video_id mismatch: expected={video_id} actual={source_video_id}"
        )
    fields = _normalize_organizer_fields(payload)
    return {
        "present": True,
        "fields": fields,
        "source_ref": organizer_source_ref,
        "sha256": hashlib.sha256(raw_bytes).hexdigest(),
    }


def _normalize_organizer_fields(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = _empty_organizer_fields()
    for field in ORGANIZER_STRING_FIELDS:
        value = payload.get(field)
        if value is None:
            continue
        if not isinstance(value, str):
            raise CanonicalMetadataError(
                f"organizer field {field} must be a string or null"
            )
        normalized[field] = value.strip() or None
    keywords = payload.get("keywords")
    if keywords is not None:
        if not isinstance(keywords, list) or any(
            not isinstance(value, str) for value in keywords
        ):
            raise CanonicalMetadataError(
                "organizer field keywords must be a list of strings or null"
            )
        normalized["keywords"] = [value.strip() for value in keywords if value.strip()]
    length = payload.get("length")
    if length is not None:
        if not isinstance(length, int) or isinstance(length, bool) or length < 0:
            raise CanonicalMetadataError(
                "organizer field length must be a non-negative integer or null"
            )
        normalized["length"] = length
    normalized["publish_date"] = _normalize_publish_date(payload.get("publish_date"))
    return normalized


def _normalize_publish_date(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise CanonicalMetadataError(
            "organizer field publish_date must be a string or null"
        )
    stripped = value.strip()
    if not stripped:
        return None
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", stripped) is not None:
        try:
            return date.fromisoformat(stripped).isoformat()
        except ValueError:
            pass
    day_first = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", stripped)
    if day_first is not None:
        day, month, year = (int(value) for value in day_first.groups())
        try:
            return date(year, month, day).isoformat()
        except ValueError:
            pass
    raise CanonicalMetadataError(f"unsupported organizer publish_date: {value!r}")


def _empty_organizer_fields() -> dict[str, Any]:
    return {field: ([] if field == "keywords" else None) for field in ORGANIZER_FIELDS}


def _empty_probe() -> VideoProbe:
    return VideoProbe(
        None, "ffprobe_failed", None, True, "unavailable", None, None, None, None
    )


def _validate_nullable_string(value: Any, field: str) -> None:
    if value is not None and not isinstance(value, str):
        raise CanonicalMetadataError(f"{field} must be a string or null")


def _validate_number(
    value: Any,
    field: str,
    *,
    integer: bool = False,
    minimum: float = 0,
    nullable: bool = False,
) -> None:
    if value is None and nullable:
        return
    expected_type = int if integer else (int, float)
    if (
        isinstance(value, bool)
        or not isinstance(value, expected_type)
        or value < minimum
    ):
        suffix = " or null" if nullable else ""
        kind = "integer" if integer else "number"
        raise CanonicalMetadataError(f"{field} must be a {kind} >= {minimum}{suffix}")
