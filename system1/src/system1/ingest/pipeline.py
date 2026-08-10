from __future__ import annotations

import json
import math
import os
import shutil
import tempfile
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pandas as pd

from system1.artifacts.hf_store import HuggingFaceDatasetArtifactStore
from system1.ingest.canonical_metadata import (
    CANONICAL_METADATA_SCHEMA_VERSION,
    canonical_inventory_projection,
    validate_canonical_metadata,
)
from system1.ingest.discovery import (
    discover_media_inputs_tolerant,
    discover_paired_inputs,
    read_metadata,
)
from system1.media.probe import probe_video_with_timeline
from system1.release.types import default_input_dir, release_root, write_json


def run_ingestion(
    output_dir: Path | str,
    *,
    input_dir: Path | str | None = None,
    source_uri: Path | str | None = None,
    mode: str = "debug_small_sample",
    max_workers: int | None = None,
    pairing_policy: str = "video-primary",
    quarantine_unmatched_metadata: bool = False,
    canonical_hf_repo_id: str | None = None,
    canonical_hf_prefix: str = "",
    canonical_hf_repo_type: str = "dataset",
    canonical_hf_revision: str = "main",
    canonical_staging_root: Path | str | None = None,
) -> Path:
    if source_uri is not None and canonical_hf_repo_id:
        raise ValueError(
            "pass only one source: --source-uri for local standardized input "
            "or --canonical-hf-repo-id for HF fallback"
        )
    if canonical_hf_repo_id:
        return run_canonical_hf_ingestion(
            output_dir,
            mode=mode,
            repo_id=canonical_hf_repo_id,
            prefix=canonical_hf_prefix,
            repo_type=canonical_hf_repo_type,
            revision=canonical_hf_revision,
            staging_root=canonical_staging_root,
            max_workers=max_workers,
        )

    release_dir = release_root(output_dir)
    tables_dir = release_dir / "tables"
    manifests_dir = release_dir / "manifests"
    raw_mapping_dir = release_dir / "raw_mapping"
    frame_timeline_dir = release_dir / "frame_timeline"
    tables_dir.mkdir(parents=True, exist_ok=True)
    manifests_dir.mkdir(parents=True, exist_ok=True)
    raw_mapping_dir.mkdir(parents=True, exist_ok=True)
    frame_timeline_dir.mkdir(parents=True, exist_ok=True)

    source_root = _resolve_local_source_root(input_dir=input_dir, source_uri=source_uri)
    resolved_max_workers = _resolve_ingest_max_workers(source_root, max_workers)
    resolved_pairing_policy = _resolve_pairing_policy(pairing_policy)
    print(
        f"[ingest] source_backend=local source_root={source_root} "
        f"max_workers={resolved_max_workers} pairing_policy={resolved_pairing_policy}",
        flush=True,
    )

    discovery = _discover_local_inputs(source_root, resolved_pairing_policy)
    pairs = discovery["pairs"]
    missing_metadata = discovery["missing_metadata"]
    unmatched_metadata = discovery["unmatched_metadata"]
    quarantine_records = (
        _quarantine_unmatched_metadata(source_root, unmatched_metadata)
        if quarantine_unmatched_metadata and unmatched_metadata
        else []
    )

    video_dfs: list[pd.DataFrame] = []
    mapping_dfs: list[pd.DataFrame] = []
    frame_timeline_manifest_records: list[dict[str, Any]] = []
    error_records: list[dict[str, Any]] = []

    # --- HÀM TRỢ LÝ ĐA LUỒNG XỬ LÝ CHO TỪNG CẶP DỮ LIỆU ĐẦU VÀO ---
    def _process_single_pair(
        pair: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any] | None, dict[str, Any]]:
        video_path = Path(pair["video_path"])
        video_id = pair["video_id"]
        metadata_path = Path(pair["metadata_path"]) if pair.get("metadata_path") else None
        metadata_missing = bool(pair.get("metadata_missing"))
        metadata = (
            _minimal_metadata(video_id)
            if metadata_path is None
            else read_metadata(metadata_path)
        )
        probe_result = probe_video_with_timeline(video_path, video_id=video_id)
        probe = probe_result.probe
        timeline_record = _write_frame_timeline(
            frame_timeline_dir,
            video_id=video_id,
            rows=probe_result.frame_timeline,
            error=None if probe_result.frame_timeline else "decoded frame timeline unavailable",
        )
        video_ref = f"media://raw_videos/{video_path.name}"
        metadata_filename = metadata_path.name if metadata_path else f"{video_id}.json"
        metadata_ref = f"media://metadata/{metadata_filename}"
        estimated_compute_cost = probe.duration_seconds or probe.frame_count or 1

        v_row = {
            "video_id": video_id,
            "video_ref": video_ref,
            "metadata_ref": metadata_ref,
            "source_filename": video_path.name,
            "source_extension": video_path.suffix.lower(),
            "fps_detected": probe.fps_detected,
            "fps_source": probe.fps_source,
            "duration_seconds": probe.duration_seconds,
            "width": probe.width,
            "height": probe.height,
            "frame_count": probe.frame_count,
            "frame_count_estimated": probe.frame_count_estimated,
            "frame_count_method": probe.frame_count_method,
            "is_vfr": probe.is_vfr,
            "has_frame_timeline": timeline_record["status"] == "pass",
            "frame_timeline_ref": timeline_record.get("frame_timeline_ref"),
            "estimated_compute_cost": estimated_compute_cost,
            "metadata_title": metadata.get("title") if isinstance(metadata, dict) else None,
        }

        m_row = {
            "video_id": video_id,
            "video_ref": video_ref,
            "metadata_ref": metadata_ref,
            "video_filename": video_path.name,
            "metadata_filename": metadata_filename,
            "metadata_missing": metadata_missing,
            "metadata_generated": metadata_missing,
            "video_local_path": str(video_path.resolve()),
            "metadata_local_path": str(metadata_path.resolve()) if metadata_path else None,
            "video_size_bytes": video_path.stat().st_size,
            "metadata_size_bytes": metadata_path.stat().st_size if metadata_path else None,
        }

        err_rec = None
        if probe.fps_detected is None or probe.duration_seconds is None:
            err_rec = {
                "video_id": video_id,
                "level": "warning",
                "kind": "probe_partial",
                "message": "ffprobe metadata incomplete; some fields unavailable",
            }
        return v_row, m_row, err_rec, timeline_record

    # --- TỐI ƯU BỘ NHỚ: Ghi dữ liệu cuốn chiếu ra DataFrame thay vì List Dictionaries ---
    CHUNK_SIZE = 2000
    v_buffer: list[dict[str, Any]] = []
    m_buffer: list[dict[str, Any]] = []

    with ThreadPoolExecutor(max_workers=resolved_max_workers) as executor:
        for v_row, m_row, err_rec, timeline_record in executor.map(_process_single_pair, pairs):
            v_buffer.append(v_row)
            m_buffer.append(m_row)
            frame_timeline_manifest_records.append(timeline_record)
            if err_rec:
                error_records.append(err_rec)

            if len(v_buffer) >= CHUNK_SIZE:
                video_dfs.append(pd.DataFrame(v_buffer))
                mapping_dfs.append(pd.DataFrame(m_buffer))
                v_buffer.clear()
                m_buffer.clear()

    if v_buffer:
        video_dfs.append(pd.DataFrame(v_buffer))
        mapping_dfs.append(pd.DataFrame(m_buffer))

    if video_dfs:
        videos_df = pd.concat(video_dfs, ignore_index=True).drop_duplicates(subset=["video_id"]).sort_values("video_id")
        mapping_df = pd.concat(mapping_dfs, ignore_index=True).drop_duplicates(subset=["video_id"]).sort_values("video_id")
    else:
        videos_df = pd.DataFrame()
        mapping_df = pd.DataFrame()

    videos_df.to_parquet(tables_dir / "videos.parquet", index=False)
    mapping_df.to_parquet(raw_mapping_dir / "media_store_manifest.parquet", index=False)
    _write_frame_timeline_manifest(manifests_dir, frame_timeline_manifest_records)

    errors_path = manifests_dir / "ingestion_errors.jsonl"
    errors_path.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in error_records),
        encoding="utf-8",
    )
    missing_metadata_path = manifests_dir / "missing_metadata.json"
    unmatched_metadata_path = manifests_dir / "unmatched_metadata.json"
    write_json(
        missing_metadata_path,
        {
            "missing_metadata": missing_metadata,
            "count": len(missing_metadata),
        },
    )
    write_json(
        unmatched_metadata_path,
        {
            "unmatched_metadata": unmatched_metadata,
            "count": len(unmatched_metadata),
            "quarantine_enabled": quarantine_unmatched_metadata,
            "quarantine_records": quarantine_records,
        },
    )

    report_path = manifests_dir / "dataset_report.json"
    matched_metadata_count = int(sum(1 for pair in pairs if not pair.get("metadata_missing")))
    write_json(
        report_path,
        {
            "release_id": release_dir.name,
            "mode": mode,
            "source_backend": "local",
            "source_root": str(source_root),
            "max_workers": resolved_max_workers,
            "pairing_policy": _report_pairing_policy(resolved_pairing_policy),
            "video_count": int(len(videos_df)),
            "metadata_count": matched_metadata_count,
            "missing_metadata_count": len(missing_metadata),
            "missing_metadata": missing_metadata[:100],
            "missing_metadata_manifest": "manifests/missing_metadata.json",
            "unmatched_metadata_count": len(unmatched_metadata),
            "unmatched_metadata": unmatched_metadata[:100],
            "unmatched_metadata_manifest": "manifests/unmatched_metadata.json",
            "ingestion_error_count": len(error_records),
            "videos_table": "tables/videos.parquet",
            "media_store_manifest": "raw_mapping/media_store_manifest.parquet",
            "frame_timeline_manifest": "manifests/frame_timeline_manifest.parquet",
        },
    )
    return report_path


def run_canonical_hf_ingestion(
    output_dir: Path | str,
    *,
    mode: str,
    repo_id: str,
    prefix: str = "",
    repo_type: str = "dataset",
    revision: str = "main",
    staging_root: Path | str | None = None,
    max_workers: int | None = None,
) -> Path:
    release_dir = release_root(output_dir)
    tables_dir = release_dir / "tables"
    manifests_dir = release_dir / "manifests"
    raw_mapping_dir = release_dir / "raw_mapping"
    frame_timeline_dir = release_dir / "frame_timeline"
    tables_dir.mkdir(parents=True, exist_ok=True)
    manifests_dir.mkdir(parents=True, exist_ok=True)
    raw_mapping_dir.mkdir(parents=True, exist_ok=True)
    frame_timeline_dir.mkdir(parents=True, exist_ok=True)

    store = HuggingFaceDatasetArtifactStore(
        repo_id=repo_id,
        repo_type=repo_type,
        revision=revision,
        token=os.environ.get("AIC_HF_TOKEN") or os.environ.get("HF_TOKEN"),
        prefix=prefix,
    )
    staging_parent = Path(staging_root).expanduser().resolve() if staging_root else None
    if staging_parent:
        staging_parent.mkdir(parents=True, exist_ok=True)
    resolved_max_workers = _resolve_ingest_max_workers(None, max_workers)
    print(
        "[ingest] "
        f"source_backend=hf_dataset repo_id={repo_id} prefix={prefix} "
        f"max_workers={resolved_max_workers}",
        flush=True,
    )

    video_dfs: list[pd.DataFrame] = []
    mapping_dfs: list[pd.DataFrame] = []
    frame_timeline_manifest_records: list[dict[str, Any]] = []
    error_records: list[dict[str, Any]] = []

    keep_staging = _keep_canonical_staging()
    tmp_context = (
        nullcontext(tempfile.mkdtemp(prefix="system1_canonical_ingest_", dir=staging_parent))
        if keep_staging
        else tempfile.TemporaryDirectory(prefix="system1_canonical_ingest_", dir=staging_parent)
    )
    with tmp_context as tmp:
        tmp_path = Path(tmp)
        manifest_cache_dir = tmp_path / "manifest_hf_cache"
        manifest_path = store.download_file(
            "manifests/canonical_file_manifest.jsonl",
            tmp_path / "canonical_file_manifest.jsonl",
            cache_dir=manifest_cache_dir,
        )
        inventory_by_video_id: dict[str, dict[str, Any]] | None = None
        try:
            inventory_path = store.download_file(
                "manifests/canonical_video_inventory.parquet",
                tmp_path / "canonical_video_inventory.parquet",
                cache_dir=manifest_cache_dir,
            )
            inventory_by_video_id = _read_canonical_video_inventory(inventory_path, prefix)
        except Exception as exc:
            if not _allow_hf_video_download_for_probe():
                raise FileNotFoundError(
                    "HF canonical ingest requires manifests/canonical_video_inventory.parquet "
                    "so it can avoid downloading raw_videos/*.mp4 for probing. "
                    "Regenerate the raw repo with upload-standardized-raw, or set "
                    "AIC_ALLOW_HF_VIDEO_DOWNLOAD_FOR_PROBE=1 to allow the legacy fallback."
                ) from exc
        missing_metadata_audit = _download_or_write_canonical_pairing_audit(
            store,
            "missing_metadata",
            tmp_path / "missing_metadata.json",
            manifests_dir / "missing_metadata.json",
            manifest_cache_dir,
        )
        unmatched_metadata_audit = _download_or_write_canonical_pairing_audit(
            store,
            "unmatched_metadata",
            tmp_path / "unmatched_metadata.json",
            manifests_dir / "unmatched_metadata.json",
            manifest_cache_dir,
        )
        rows = _read_canonical_manifest(manifest_path)
        valid_rows = [row for row in rows if row.get("status") in {None, "pass", "skipped"}]
        pair_parent = tmp_path / "pairs"
        pair_parent.mkdir(parents=True, exist_ok=True)

        # --- HÀM TRỢ LÝ ĐA LUỒNG CHO HUGGING FACE ---
        def _process_hf_pair(
            row: dict[str, Any],
        ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any] | None, dict[str, Any]]:
            video_id = str(row["video_id"])
            video_remote_path = _normalize_canonical_manifest_path(str(row["video_path"]), prefix)
            metadata_remote_path = _normalize_canonical_manifest_path(str(row["metadata_path"]), prefix)
            video_filename = str(row.get("video_filename") or Path(video_remote_path).name)
            metadata_filename = str(row.get("metadata_filename") or Path(metadata_remote_path).name)
            inventory = (inventory_by_video_id or {}).get(video_id)

            pair_root = Path(tempfile.mkdtemp(prefix="pair_", dir=pair_parent))
            pair_stage_dir = pair_root / "stage"
            pair_cache_dir = pair_root / "hf_cache"
            video_path = pair_stage_dir / "raw_videos" / video_filename
            metadata_path = pair_stage_dir / "metadata" / metadata_filename
            try:
                video_path.parent.mkdir(parents=True, exist_ok=True)
                metadata_path.parent.mkdir(parents=True, exist_ok=True)
                pair_cache_dir.mkdir(parents=True, exist_ok=True)

                store.download_file(metadata_remote_path, metadata_path, cache_dir=pair_cache_dir)

                metadata = read_metadata(metadata_path)
                validate_canonical_metadata(metadata, expected_video_id=video_id)
                if inventory is not None:
                    _validate_canonical_inventory_match(
                        metadata,
                        inventory,
                        video_remote_path=video_remote_path,
                        metadata_remote_path=metadata_remote_path,
                    )
                probe = None
                timeline_record = _frame_timeline_unavailable_record(video_id, "canonical inventory reused without local raw video")
                if inventory is None:
                    if not _allow_hf_video_download_for_probe():
                        raise FileNotFoundError(
                            f"canonical video inventory has no row for video_id={video_id}; "
                            "HF ingest will not download raw video for probing unless "
                            "AIC_ALLOW_HF_VIDEO_DOWNLOAD_FOR_PROBE=1"
                        )
                    store.download_file(video_remote_path, video_path, cache_dir=pair_cache_dir)
                    probe_result = probe_video_with_timeline(video_path, video_id=video_id)
                    probe = probe_result.probe
                    timeline_record = _write_frame_timeline(
                        frame_timeline_dir,
                        video_id=video_id,
                        rows=probe_result.frame_timeline,
                        error=None if probe_result.frame_timeline else "decoded frame timeline unavailable",
                    )
                video_ref = f"media://raw_videos/{video_filename}"
                metadata_ref = f"media://metadata/{metadata_filename}"
                duration_seconds = _inventory_number(inventory, "duration_sec") if inventory is not None else probe.duration_seconds
                fps_detected = _inventory_number(inventory, "fps") if inventory is not None else probe.fps_detected
                frame_count = _inventory_int(inventory, "frame_count") if inventory is not None else probe.frame_count
                file_size_bytes = _inventory_int(inventory, "file_size_bytes") if inventory is not None else row.get("video_size_bytes")
                estimated_compute_cost = duration_seconds or frame_count or 1

                v_row = {
                    "video_id": video_id,
                    "video_ref": video_ref,
                    "metadata_ref": metadata_ref,
                    "source_filename": video_filename,
                    "source_extension": Path(video_filename).suffix.lower(),
                    "fps_detected": fps_detected,
                    "fps_source": "canonical_video_inventory" if inventory is not None else probe.fps_source,
                    "duration_seconds": duration_seconds,
                    "width": _inventory_int(inventory, "width") if inventory is not None else probe.width,
                    "height": _inventory_int(inventory, "height") if inventory is not None else probe.height,
                    "frame_count": frame_count,
                    "frame_count_estimated": False if inventory is not None else probe.frame_count_estimated,
                    "frame_count_method": "canonical_video_inventory" if inventory is not None else probe.frame_count_method,
                    "is_vfr": _inventory_bool(inventory, "is_vfr") if inventory is not None else probe.is_vfr,
                    "has_frame_timeline": timeline_record["status"] == "pass",
                    "frame_timeline_ref": timeline_record.get("frame_timeline_ref"),
                    "estimated_compute_cost": estimated_compute_cost,
                    "metadata_title": metadata.get("title") if isinstance(metadata, dict) else None,
                }
                m_row = {
                    "video_id": video_id,
                    "video_ref": video_ref,
                    "metadata_ref": metadata_ref,
                    "video_filename": video_filename,
                    "metadata_filename": metadata_filename,
                    "video_size_bytes": file_size_bytes,
                    "metadata_size_bytes": row.get("metadata_size_bytes"),
                    "canonical_backend": "hf_dataset",
                    "canonical_repo_id": repo_id,
                    "canonical_repo_type": repo_type,
                    "canonical_revision": revision,
                    "canonical_prefix": prefix,
                    "canonical_video_path": video_remote_path,
                    "canonical_metadata_path": metadata_remote_path,
                    "metadata_schema_version": metadata["schema_version"],
                    "organizer_metadata_present": metadata["organizer_metadata_present"],
                    "metadata_generated": metadata["provenance"]["metadata_generated"],
                    "organizer_metadata_source_ref": metadata["provenance"]["organizer_metadata_source_ref"],
                    "organizer_metadata_sha256": metadata["provenance"]["organizer_metadata_sha256"],
                    "probe_status": metadata["media"]["probe_status"],
                    "probe_attempts": metadata["media"]["probe_attempts"],
                }

                err_rec = None
                if metadata["media"]["probe_status"] != "pass":
                    err_rec = {
                        "video_id": video_id,
                        "level": "warning",
                        "kind": "probe_partial",
                        "message": (
                            "canonical media probe status is "
                            f"{metadata['media']['probe_status']}; some technical fields may be unavailable"
                        ),
                    }

                return v_row, m_row, err_rec, timeline_record
            finally:
                if not keep_staging:
                    shutil.rmtree(pair_root, ignore_errors=True)

        # --- TỐI ƯU BỘ NHỚ VÀ MẠNG: Đa luồng tải và Chunking bộ nhớ ---
        CHUNK_SIZE = 2000
        v_buffer: list[dict[str, Any]] = []
        m_buffer: list[dict[str, Any]] = []

        with ThreadPoolExecutor(max_workers=resolved_max_workers) as executor:
            for v_row, m_row, err_rec, timeline_record in executor.map(_process_hf_pair, valid_rows):
                v_buffer.append(v_row)
                m_buffer.append(m_row)
                frame_timeline_manifest_records.append(timeline_record)
                if err_rec:
                    error_records.append(err_rec)

                if len(v_buffer) >= CHUNK_SIZE:
                    video_dfs.append(pd.DataFrame(v_buffer))
                    mapping_dfs.append(pd.DataFrame(m_buffer))
                    v_buffer.clear()
                    m_buffer.clear()

        if v_buffer:
            video_dfs.append(pd.DataFrame(v_buffer))
            mapping_dfs.append(pd.DataFrame(m_buffer))

    if video_dfs:
        videos_df = pd.concat(video_dfs, ignore_index=True).drop_duplicates(subset=["video_id"]).sort_values("video_id")
        mapping_df = pd.concat(mapping_dfs, ignore_index=True).drop_duplicates(subset=["video_id"]).sort_values("video_id")
    else:
        videos_df = pd.DataFrame()
        mapping_df = pd.DataFrame()

    videos_df.to_parquet(tables_dir / "videos.parquet", index=False)
    mapping_df.to_parquet(raw_mapping_dir / "media_store_manifest.parquet", index=False)
    _write_frame_timeline_manifest(manifests_dir, frame_timeline_manifest_records)

    (manifests_dir / "ingestion_errors.jsonl").write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in error_records),
        encoding="utf-8",
    )
    report_path = manifests_dir / "dataset_report.json"
    write_json(
        report_path,
        {
            "release_id": release_dir.name,
            "mode": mode,
            "source_backend": "hf_dataset",
            "source_repo_id": repo_id,
            "source_prefix": prefix,
            "max_workers": resolved_max_workers,
            "video_count": int(len(videos_df)),
            "metadata_schema_version": CANONICAL_METADATA_SCHEMA_VERSION,
            "organizer_metadata_present_count": int(
                mapping_df.get("organizer_metadata_present", pd.Series(dtype=bool)).fillna(False).sum()
            ),
            "metadata_generated_count": int(
                mapping_df.get("metadata_generated", pd.Series(dtype=bool)).fillna(False).sum()
            ),
            "probe_status_counts": {
                status: int(
                    (mapping_df.get("probe_status", pd.Series(dtype=str)) == status).sum()
                )
                for status in ("pass", "partial", "failed")
            },
            "missing_metadata_count": int(missing_metadata_audit.get("count", 0)),
            "missing_metadata_manifest": "manifests/missing_metadata.json",
            "unmatched_metadata_count": int(unmatched_metadata_audit.get("count", 0)),
            "unmatched_metadata_manifest": "manifests/unmatched_metadata.json",
            "ingestion_error_count": len(error_records),
            "videos_table": "tables/videos.parquet",
            "media_store_manifest": "raw_mapping/media_store_manifest.parquet",
            "frame_timeline_manifest": "manifests/frame_timeline_manifest.parquet",
        },
    )
    return report_path


def _download_or_write_canonical_pairing_audit(
    store: HuggingFaceDatasetArtifactStore,
    kind: str,
    cache_target: Path,
    output_path: Path,
    cache_dir: Path,
) -> dict[str, Any]:
    remote_path = f"manifests/{kind}.json"
    try:
        downloaded = store.download_file(remote_path, cache_target, cache_dir=cache_dir)
        payload = json.loads(downloaded.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"{remote_path} must contain a JSON object")
    except Exception as exc:
        key = kind
        payload = {
            "kind": kind,
            "source": "canonical_hf_ingest_missing_raw_audit",
            "description": (
                f"Raw repo did not provide manifests/{kind}.json during HF ingest; "
                "this empty compatibility report was generated by ingest."
            ),
            "count": 0,
            key: [],
            "warning": f"missing raw audit: {type(exc).__name__}: {exc}",
        }
        if kind == "missing_metadata":
            payload["missing_video_ids"] = []
        elif kind == "unmatched_metadata":
            payload["unmatched_metadata_ids"] = []
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload


def _read_canonical_manifest(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        payload = json.loads(line)
        required = {"video_id", "video_path", "metadata_path"}
        missing = sorted(required - set(payload))
        if missing:
            raise ValueError(f"canonical manifest line {line_number} missing fields: {', '.join(missing)}")
        rows.append(payload)
    if not rows:
        raise ValueError("canonical manifest is empty")
    return rows


def _read_canonical_video_inventory(path: Path, prefix: str) -> dict[str, dict[str, Any]]:
    inventory = pd.read_parquet(path)
    required = {
        "video_id",
        "canonical_video_path",
        "canonical_metadata_path",
        "metadata_schema_version",
        "organizer_metadata_present",
        "metadata_generated",
        "duration_sec",
        "fps",
        "frame_count",
        "width",
        "height",
        "is_vfr",
        "file_size_bytes",
        "probe_status",
        "probe_attempts",
    }
    missing = sorted(required - set(inventory.columns))
    if missing:
        raise ValueError(f"canonical video inventory missing fields: {', '.join(missing)}")
    schema_versions = {
        str(value)
        for value in inventory["metadata_schema_version"].dropna().unique().tolist()
    }
    if schema_versions != {CANONICAL_METADATA_SCHEMA_VERSION}:
        raise ValueError(
            "canonical video inventory metadata_schema_version must contain only "
            f"{CANONICAL_METADATA_SCHEMA_VERSION!r}; found={sorted(schema_versions)}"
        )
    rows: dict[str, dict[str, Any]] = {}
    for record in inventory.to_dict("records"):
        video_id = str(record["video_id"])
        if video_id in rows:
            raise ValueError(f"canonical video inventory has duplicate video_id={video_id}")
        rows[video_id] = {
            **record,
            "canonical_video_path": _normalize_canonical_manifest_path(str(record["canonical_video_path"]), prefix),
            "canonical_metadata_path": _normalize_canonical_manifest_path(str(record["canonical_metadata_path"]), prefix),
        }
    if not rows:
        raise ValueError("canonical video inventory is empty")
    return rows


def _validate_canonical_inventory_match(
    metadata: dict[str, Any],
    inventory: dict[str, Any],
    *,
    video_remote_path: str,
    metadata_remote_path: str,
) -> None:
    video_id = metadata["video_id"]
    if inventory.get("canonical_video_path") != video_remote_path:
        raise ValueError(f"canonical inventory video path mismatch for video_id={video_id}")
    if inventory.get("canonical_metadata_path") != metadata_remote_path:
        raise ValueError(f"canonical inventory metadata path mismatch for video_id={video_id}")
    if Path(video_remote_path).name != metadata["media"]["filename"]:
        raise ValueError(f"canonical metadata filename mismatch for video_id={video_id}")
    projection = canonical_inventory_projection(metadata)
    for key, expected in projection.items():
        actual = _inventory_scalar(inventory.get(key))
        if isinstance(expected, float) and isinstance(actual, (int, float)):
            matches = math.isclose(float(expected), float(actual), rel_tol=1e-9, abs_tol=1e-9)
        else:
            matches = actual == expected
        if not matches:
            raise ValueError(
                f"canonical inventory mismatch for video_id={video_id} field={key}: "
                f"metadata={expected!r} inventory={actual!r}"
            )


def _inventory_scalar(value: Any) -> Any:
    if value is None:
        return None
    if not isinstance(value, (list, tuple, dict)) and pd.isna(value):
        return None
    if hasattr(value, "item"):
        return value.item()
    return value


def _normalize_canonical_manifest_path(remote_path: str, prefix: str) -> str:
    normalized_path = remote_path.strip().lstrip("/")
    normalized_prefix = prefix.strip().strip("/")
    if normalized_prefix and normalized_path.startswith(f"{normalized_prefix}/"):
        return normalized_path[len(normalized_prefix) + 1 :]
    return normalized_path


def _inventory_number(inventory: dict[str, Any] | None, key: str) -> float | None:
    if inventory is None:
        return None
    value = inventory.get(key)
    if value in (None, "") or pd.isna(value):
        return None
    return float(value)


def _inventory_int(inventory: dict[str, Any] | None, key: str) -> int | None:
    value = _inventory_number(inventory, key)
    return int(value) if value is not None else None


def _inventory_bool(inventory: dict[str, Any] | None, key: str) -> bool | None:
    if inventory is None:
        return None
    value = inventory.get(key)
    if value is None:
        return None
    if isinstance(value, str) and value == "":
        return None
    if not isinstance(value, (list, tuple, dict)) and pd.isna(value):
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes"}:
            return True
        if lowered in {"false", "0", "no"}:
            return False
    return bool(value)


def _write_frame_timeline(
    frame_timeline_dir: Path,
    *,
    video_id: str,
    rows: list[dict[str, float | int | str | None]],
    error: str | None,
) -> dict[str, Any]:
    relative_path = Path("frame_timeline") / f"{video_id}.parquet"
    target = frame_timeline_dir / f"{video_id}.parquet"
    if rows:
        frame_timeline_dir.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(rows, columns=["video_id", "frame_id", "pts_time", "duration_time"]).to_parquet(target, index=False)
        return {
            "video_id": video_id,
            "frame_timeline_ref": relative_path.as_posix(),
            "row_count": len(rows),
            "status": "pass",
            "error": None,
        }
    if target.exists():
        target.unlink()
    return _frame_timeline_unavailable_record(video_id, error or "decoded frame timeline unavailable")


def _frame_timeline_unavailable_record(video_id: str, error: str) -> dict[str, Any]:
    return {
        "video_id": video_id,
        "frame_timeline_ref": None,
        "row_count": 0,
        "status": "unavailable",
        "error": error,
    }


def _write_frame_timeline_manifest(manifests_dir: Path, records: list[dict[str, Any]]) -> None:
    columns = ["video_id", "frame_timeline_ref", "row_count", "status", "error"]
    frame_timeline_manifest = pd.DataFrame(records, columns=columns)
    if not frame_timeline_manifest.empty:
        frame_timeline_manifest = frame_timeline_manifest.sort_values("video_id")
    frame_timeline_manifest.to_parquet(manifests_dir / "frame_timeline_manifest.parquet", index=False)


def _keep_canonical_staging() -> bool:
    return os.environ.get("AIC_KEEP_CANONICAL_STAGING", "0") == "1"


def _allow_hf_video_download_for_probe() -> bool:
    return os.environ.get("AIC_ALLOW_HF_VIDEO_DOWNLOAD_FOR_PROBE", "0") == "1"


def _discover_local_inputs(source_root: Path, pairing_policy: str) -> dict[str, Any]:
    if pairing_policy == "strict":
        pairs = discover_paired_inputs(source_root)
        return {
            "pairs": [
                {**pair, "metadata_missing": False}
                for pair in pairs
            ],
            "missing_metadata": [],
            "unmatched_metadata": [],
        }
    if pairing_policy == "video-primary":
        return discover_media_inputs_tolerant(source_root)
    raise ValueError(f"unsupported pairing_policy={pairing_policy!r}; expected strict or video-primary")


def _minimal_metadata(video_id: str) -> dict[str, Any]:
    return {
        "video_id": video_id,
        "source": "generated_minimal",
        "metadata_missing": True,
    }


def _resolve_pairing_policy(pairing_policy: str) -> str:
    normalized = pairing_policy.strip().lower().replace("_", "-")
    if normalized in {"strict", "video-primary"}:
        return normalized
    raise ValueError(f"unsupported pairing_policy={pairing_policy!r}; expected strict or video-primary")


def _report_pairing_policy(pairing_policy: str) -> str:
    return "video_primary_tolerant" if pairing_policy == "video-primary" else "strict"


def _quarantine_unmatched_metadata(source_root: Path, unmatched_metadata: list[str]) -> list[dict[str, str]]:
    quarantine_root = source_root / "_unmatched_metadata"
    quarantine_root.mkdir(parents=True, exist_ok=True)
    records = []
    for source_text in unmatched_metadata:
        source = Path(source_text)
        target = _unique_quarantine_path(quarantine_root / source.name)
        shutil.move(str(source), str(target))
        records.append({"source": str(source), "target": str(target)})
    return records


def _unique_quarantine_path(target: Path) -> Path:
    if not target.exists():
        return target
    for index in range(1, 10000):
        candidate = target.with_name(f"{target.stem}_{index}{target.suffix}")
        if not candidate.exists():
            return candidate
    raise FileExistsError(f"unable to choose unique quarantine target for {target}")


def _resolve_local_source_root(
    *,
    input_dir: Path | str | None,
    source_uri: Path | str | None,
) -> Path:
    if source_uri is not None and input_dir is not None:
        raise ValueError("pass only one local input option: --source-uri or --input")
    selected = source_uri if source_uri is not None else input_dir
    if selected is None:
        selected = default_input_dir()

    selected_text = str(selected)
    parsed = urlparse(selected_text)
    if parsed.scheme and parsed.scheme != "file":
        raise ValueError(
            "local ingest --source-uri must be a local path or file:// URI; "
            "use --canonical-hf-repo-id for HF Dataset fallback"
        )
    source_root = Path(parsed.path if parsed.scheme == "file" else selected_text).expanduser().resolve()
    if not source_root.exists() or not source_root.is_dir():
        raise FileNotFoundError(f"local ingest source directory does not exist: {source_root}")
    return source_root


def _resolve_ingest_max_workers(source_root: Path | None, requested_max_workers: int | None) -> int:
    if requested_max_workers is not None:
        workers = requested_max_workers
    else:
        env_value = os.environ.get("AIC_INGEST_MAX_WORKERS")
        if env_value:
            try:
                workers = int(env_value)
            except ValueError as exc:
                raise ValueError(f"AIC_INGEST_MAX_WORKERS must be a positive integer, got {env_value!r}") from exc
        else:
            workers = 1 if _is_content_drive_source(source_root) else 4

    if workers < 1:
        raise ValueError(f"ingest max_workers must be >= 1, got {workers}")
    if _is_content_drive_source(source_root):
        return min(workers, 2)
    return workers


def _is_content_drive_source(source_root: Path | None) -> bool:
    if source_root is None:
        return False
    parts = source_root.resolve().parts
    return len(parts) >= 3 and parts[1:3] == ("content", "drive")
