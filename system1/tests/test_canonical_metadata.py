from __future__ import annotations

import json
from pathlib import Path

import pytest

from system1.ingest.canonical_metadata import (
    CANONICAL_METADATA_SCHEMA_VERSION,
    CanonicalMetadataError,
    build_canonical_metadata,
    canonical_inventory_projection,
    validate_canonical_metadata,
)
from system1.media.probe import VideoProbe


def _probe(
    *,
    duration: float | None = 12.5,
    fps: float | None = 25.0,
    frame_count: int | None = 313,
    width: int | None = 1920,
    height: int | None = 1080,
    is_vfr: bool | None = False,
) -> VideoProbe:
    return VideoProbe(
        fps,
        "test",
        frame_count,
        False,
        "test",
        duration,
        width,
        height,
        is_vfr,
    )


def test_build_canonical_metadata_normalizes_organizer_and_projects_inventory(tmp_path):
    video = tmp_path / "L21_V001.mp4"
    video.write_bytes(b"video")
    organizer = tmp_path / "L21_V001.json"
    organizer.write_text(
        json.dumps(
            {
                "author": " HTV ",
                "keywords": [" news ", ""],
                "length": 13,
                "publish_date": "01/08/2024",
                "title": " Sample ",
            }
        ),
        encoding="utf-8",
    )

    result = build_canonical_metadata(
        video,
        video_id="L21_V001",
        organizer_metadata_path=organizer,
        organizer_source_ref="metadata.zip::metadata/L21_V001.json",
        probe_fn=lambda _path: _probe(),
        sleep_fn=lambda _seconds: None,
    )

    payload = result.payload
    assert payload["schema_version"] == CANONICAL_METADATA_SCHEMA_VERSION
    assert payload["organizer_metadata_present"] is True
    assert payload["author"] == "HTV"
    assert payload["keywords"] == ["news"]
    assert payload["publish_date"] == "2024-08-01"
    assert payload["description"] is None
    assert payload["media"]["probe_status"] == "pass"
    assert (
        payload["provenance"]["organizer_metadata_source_ref"]
        == "metadata.zip::metadata/L21_V001.json"
    )
    assert len(payload["provenance"]["organizer_metadata_sha256"]) == 64
    assert payload["provenance"]["metadata_generated"] is False
    projection = canonical_inventory_projection(payload)
    assert projection["duration_sec"] == 12.5
    assert projection["organizer_metadata_present"] is True
    assert projection["metadata_schema_version"] == CANONICAL_METADATA_SCHEMA_VERSION


def test_build_canonical_metadata_without_organizer_uses_null_empty_fields(tmp_path):
    video = tmp_path / "L21_V002.mp4"
    video.write_bytes(b"video")

    result = build_canonical_metadata(
        video,
        video_id="L21_V002",
        probe_fn=lambda _path: _probe(is_vfr=None),
        sleep_fn=lambda _seconds: None,
    )

    payload = result.payload
    assert payload["organizer_metadata_present"] is False
    assert payload["title"] is None
    assert payload["watch_url"] is None
    assert payload["keywords"] == []
    assert payload["provenance"] == {
        "organizer_metadata_source_ref": None,
        "organizer_metadata_sha256": None,
        "technical_metadata_source": "ffprobe",
        "metadata_generated": True,
    }


def test_build_canonical_metadata_retries_probe_then_allows_partial(tmp_path):
    video = tmp_path / "L21_V003.mp4"
    video.write_bytes(b"video")
    attempts: list[int] = []
    sleeps: list[float] = []

    def partial_probe(_path: Path) -> VideoProbe:
        attempts.append(1)
        return _probe(frame_count=None, width=None, height=None, is_vfr=None)

    result = build_canonical_metadata(
        video,
        video_id="L21_V003",
        probe_fn=partial_probe,
        sleep_fn=sleeps.append,
    )

    assert len(attempts) == 3
    assert sleeps == [0.5, 1.0]
    assert result.payload["media"]["probe_status"] == "partial"
    assert result.payload["media"]["probe_attempts"] == 3
    assert result.payload["media"]["frame_count"] is None


def test_build_canonical_metadata_rejects_invalid_organizer_json(tmp_path):
    video = tmp_path / "L21_V004.mp4"
    video.write_bytes(b"video")
    organizer = tmp_path / "L21_V004.json"
    organizer.write_text("{bad-json", encoding="utf-8")

    with pytest.raises(CanonicalMetadataError, match="invalid organizer metadata"):
        build_canonical_metadata(
            video,
            video_id="L21_V004",
            organizer_metadata_path=organizer,
            probe_fn=lambda _path: _probe(),
            sleep_fn=lambda _seconds: None,
        )


def test_validate_canonical_metadata_requires_all_contract_fields(tmp_path):
    video = tmp_path / "L21_V009.mp4"
    video.write_bytes(b"video")
    payload = build_canonical_metadata(
        video,
        video_id="L21_V009",
        probe_fn=lambda _path: _probe(),
        sleep_fn=lambda _seconds: None,
    ).payload

    del payload["watch_url"]
    with pytest.raises(CanonicalMetadataError, match="missing fields: watch_url"):
        validate_canonical_metadata(payload)


def test_legacy_missing_placeholder_is_not_treated_as_organizer_evidence(tmp_path):
    video = tmp_path / "L21_V005.mp4"
    video.write_bytes(b"video")
    organizer = tmp_path / "L21_V005.json"
    organizer.write_text(
        json.dumps(
            {
                "video_id": "L21_V005",
                "title": "L21_V005",
                "watch_url": "/source/archive.zip",
                "metadata_missing": True,
            }
        ),
        encoding="utf-8",
    )

    result = build_canonical_metadata(
        video,
        video_id="L21_V005",
        organizer_metadata_path=organizer,
        probe_fn=lambda _path: _probe(),
        sleep_fn=lambda _seconds: None,
    )

    assert result.payload["organizer_metadata_present"] is False
    assert result.payload["title"] is None
    assert result.payload["watch_url"] is None


def test_validate_canonical_metadata_rejects_fabricated_missing_fields(tmp_path):
    video = tmp_path / "L21_V006.mp4"
    video.write_bytes(b"video")
    payload = build_canonical_metadata(
        video,
        video_id="L21_V006",
        probe_fn=lambda _path: _probe(),
        sleep_fn=lambda _seconds: None,
    ).payload
    payload["title"] = "L21_V006"

    with pytest.raises(CanonicalMetadataError, match="requires title=None"):
        validate_canonical_metadata(payload)
