from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

import pandas as pd

from system1.artifacts.hf_store import HuggingFaceDatasetArtifactStore
from system1.config import load_provider_plan
from system1.features.builder import capability_states, feature_rows, providers_for_plan, release_capability_rows
from system1.ingest.discovery import discover_media_inputs_tolerant, discover_paired_inputs, read_metadata
from system1.keyframes.builder import keyframe_id, keyframe_refs, materialize_keyframe
from system1.media.probe import probe_video
from system1.release.types import DEFAULT_FRAME_ID, BuildOptions, config_dir, default_input_dir, release_root, write_json
from system1.scenes.builder import scene_id, scene_row
from system1.shots.builder import shot_id, shot_row
from system1.text.builder import doc_id, metadata_text, text_document_row, text_source_rows


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
    tables_dir.mkdir(parents=True, exist_ok=True)
    manifests_dir.mkdir(parents=True, exist_ok=True)
    raw_mapping_dir.mkdir(parents=True, exist_ok=True)

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
    error_records: list[dict[str, Any]] = []

    # --- HÀM TRỢ LÝ ĐA LUỒNG XỬ LÝ CHO TỪNG CẶP DỮ LIỆU ĐẦU VÀO ---
    def _process_single_pair(pair: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any] | None]:
        video_path = Path(pair["video_path"])
        video_id = pair["video_id"]
        metadata_path = Path(pair["metadata_path"]) if pair.get("metadata_path") else None
        metadata_missing = bool(pair.get("metadata_missing"))
        metadata = (
            _minimal_metadata(video_id)
            if metadata_path is None
            else read_metadata(metadata_path)
        )
        probe = probe_video(video_path)
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
        return v_row, m_row, err_rec

    # --- TỐI ƯU BỘ NHỚ: Ghi dữ liệu cuốn chiếu ra DataFrame thay vì List Dictionaries ---
    CHUNK_SIZE = 2000
    v_buffer: list[dict[str, Any]] = []
    m_buffer: list[dict[str, Any]] = []

    with ThreadPoolExecutor(max_workers=resolved_max_workers) as executor:
        for v_row, m_row, err_rec in executor.map(_process_single_pair, pairs):
            v_buffer.append(v_row)
            m_buffer.append(m_row)
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
    tables_dir.mkdir(parents=True, exist_ok=True)
    manifests_dir.mkdir(parents=True, exist_ok=True)
    raw_mapping_dir.mkdir(parents=True, exist_ok=True)

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
    error_records: list[dict[str, Any]] = []

    with tempfile.TemporaryDirectory(prefix="system1_canonical_ingest_", dir=staging_parent) as tmp:
        tmp_path = Path(tmp)
        manifest_path = store.download_file("manifests/canonical_file_manifest.jsonl", tmp_path / "canonical_file_manifest.jsonl")
        rows = _read_canonical_manifest(manifest_path)
        valid_rows = [row for row in rows if row.get("status") in {None, "pass", "skipped"}]

        # --- HÀM TRỢ LÝ ĐA LUỒNG CHO HUGGING FACE ---
        def _process_hf_pair(row: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any] | None]:
            video_id = str(row["video_id"])
            video_remote_path = str(row["video_path"])
            metadata_remote_path = str(row["metadata_path"])
            video_filename = str(row.get("video_filename") or Path(video_remote_path).name)
            metadata_filename = str(row.get("metadata_filename") or Path(metadata_remote_path).name)

            video_path = tmp_path / "raw_videos" / video_filename
            metadata_path = tmp_path / "metadata" / metadata_filename
            video_path.parent.mkdir(parents=True, exist_ok=True)
            metadata_path.parent.mkdir(parents=True, exist_ok=True)

            store.download_file(video_remote_path, video_path)
            store.download_file(metadata_remote_path, metadata_path)

            metadata = read_metadata(metadata_path)
            probe = probe_video(video_path)
            video_ref = f"media://raw_videos/{video_filename}"
            metadata_ref = f"media://metadata/{metadata_filename}"
            estimated_compute_cost = probe.duration_seconds or probe.frame_count or 1

            v_row = {
                "video_id": video_id,
                "video_ref": video_ref,
                "metadata_ref": metadata_ref,
                "source_filename": video_filename,
                "source_extension": Path(video_filename).suffix.lower(),
                "fps_detected": probe.fps_detected,
                "fps_source": probe.fps_source,
                "duration_seconds": probe.duration_seconds,
                "width": probe.width,
                "height": probe.height,
                "frame_count": probe.frame_count,
                "frame_count_estimated": probe.frame_count_estimated,
                "frame_count_method": probe.frame_count_method,
                "estimated_compute_cost": estimated_compute_cost,
                "metadata_title": metadata.get("title") if isinstance(metadata, dict) else None,
            }
            m_row = {
                "video_id": video_id,
                "video_ref": video_ref,
                "metadata_ref": metadata_ref,
                "video_filename": video_filename,
                "metadata_filename": metadata_filename,
                "video_size_bytes": row.get("video_size_bytes"),
                "metadata_size_bytes": row.get("metadata_size_bytes"),
                "canonical_backend": "hf_dataset",
                "canonical_repo_id": repo_id,
                "canonical_repo_type": repo_type,
                "canonical_revision": revision,
                "canonical_prefix": prefix,
                "canonical_video_path": video_remote_path,
                "canonical_metadata_path": metadata_remote_path,
            }

            err_rec = None
            if probe.fps_detected is None or probe.duration_seconds is None:
                err_rec = {
                    "video_id": video_id,
                    "level": "warning",
                    "kind": "probe_partial",
                    "message": "ffprobe metadata incomplete; some fields unavailable",
                }

            # TỐI ƯU LƯU TRỮ: Xóa tệp tạm cuốn chiếu ngăn tràn bộ nhớ ổ cứng
            try:
                if video_path.exists():
                    video_path.unlink()
                if metadata_path.exists():
                    metadata_path.unlink()
            except Exception:
                pass

            return v_row, m_row, err_rec

        # --- TỐI ƯU BỘ NHỚ VÀ MẠNG: Đa luồng tải và Chunking bộ nhớ ---
        CHUNK_SIZE = 2000
        v_buffer: list[dict[str, Any]] = []
        m_buffer: list[dict[str, Any]] = []

        with ThreadPoolExecutor(max_workers=resolved_max_workers) as executor:
            for v_row, m_row, err_rec in executor.map(_process_hf_pair, valid_rows):
                v_buffer.append(v_row)
                m_buffer.append(m_row)
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
            "ingestion_error_count": len(error_records),
            "videos_table": "tables/videos.parquet",
            "media_store_manifest": "raw_mapping/media_store_manifest.parquet",
        },
    )
    return report_path


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


def build_tables(
    pairs: list[dict[str, str]],
    release_dir: Path,
    options: BuildOptions,
    previous_checkpoint: dict[str, Any] | None,
) -> dict[str, pd.DataFrame]:
    """Legacy dev helper for build-mini-seed only.

    Do not use this monolithic builder for the phase-based worker pipeline.
    The main MVP path runs dedicated phase commands and merges outputs later.
    """
    plan = options.provider_plan or load_provider_plan(config_dir(), options.providers)
    embedding_provider, text_provider = providers_for_plan(plan)
    rows: dict[str, list[dict[str, Any]]] = {name: [] for name in (
        "videos", "media_store_manifest", "asr_segments", "shots", "scenes", "frame_timeline", "keyframes",
        "shot_transcript_links", "scene_transcript_links", "embeddings_meta", "ocr", "objects", "image_captions",
        "shot_captions", "scene_summaries_initial", "scene_summaries_enriched", "text_sources", "feature_availability",
        "text_documents", "vector_map", "release_capabilities",
    )}
    embeddings: list[list[float]] = []
    reuse_rows: list[dict[str, Any]] = []
    visual_status, visual_reason, asr_status, ocr_status, enrichment_status = capability_states(options.mode, plan)

    for vector_id, pair in enumerate(pairs):
        video_id = pair["video_id"]
        video_path = Path(pair["video_path"])
        metadata = read_metadata(Path(pair["metadata_path"]))
        text = metadata_text(video_id, metadata)
        probe = probe_video(video_path)
        frame_id = DEFAULT_FRAME_ID
        shot_identifier = shot_id(video_id)
        scene_identifier = scene_id(video_id)
        document_id = doc_id("video", video_id, text)

        keyframe_row, reuse_row, keyframe_path = materialize_keyframe(
            release_dir=release_dir,
            video_id=video_id,
            video_path=video_path,
            frame_id=frame_id,
            options=options,
            previous_checkpoint=previous_checkpoint,
        )
        keyframe_identifier = keyframe_row["keyframe_id"]
        keyframe_ref, thumbnail_ref = keyframe_refs(video_id, frame_id)

        embedding_meta, ocr_row, object_row, image_caption_row, shot_caption_partial, scene_initial_partial, scene_enriched_partial, embedding, ocr_text, caption_text = feature_rows(
            keyframe_id=keyframe_identifier,
            video_id=video_id,
            frame_id=frame_id,
            keyframe_path=keyframe_path,
            text=text,
            plan=plan,
            embedding_provider=embedding_provider,
            text_provider=text_provider,
            visual_status=visual_status,
        )
        asr_text = text_provider.transcribe(video_path)
        extension = video_path.suffix.lower()
        rows["videos"].append({
            "video_id": video_id,
            "video_ref": f"media://raw_videos/{video_id}{extension}",
            "source_stem": video_id,
            "metadata_ref": f"media://metadata/{video_id}.json",
            "fps_detected": probe.fps_detected,
            "fps_source": probe.fps_source,
            "frame_count": probe.frame_count,
            "frame_count_estimated": probe.frame_count_estimated,
            "frame_count_method": probe.frame_count_method,
            "frame_id_method": "decoded_original_frame_index",
            "is_vfr": probe.is_vfr,
            "duration_seconds": probe.duration_seconds,
            "width": probe.width,
            "height": probe.height,
        })
        rows["media_store_manifest"].append({"video_id": video_id, "media_kind": "raw_video", "media_ref": f"media://raw_videos/{video_id}{extension}", "source_path": video_path.name, "storage_backend": "local_sample"})
        rows["asr_segments"].append({"asr_segment_id": f"{video_id}_ASR00000", "video_id": video_id, "start_seconds": 0.0, "end_seconds": probe.duration_seconds or 0.0, "text": asr_text, "provider": plan.asr, "status": asr_status if not asr_text else "pass"})
        rows["shots"].append(shot_row(video_id, frame_id, probe.duration_seconds))
        rows["scenes"].append(scene_row(video_id, frame_id, probe.duration_seconds))
        rows["frame_timeline"].append({"video_id": video_id, "frame_id": frame_id, "time_seconds": 0.0, "mapping_method": probe.frame_count_method})
        rows["keyframes"].append({**keyframe_row, "shot_id": shot_identifier, "scene_id": scene_identifier, "keyframe_ref": keyframe_ref, "thumbnail_ref": thumbnail_ref})
        rows["shot_transcript_links"].append({"shot_id": shot_identifier, "asr_segment_id": f"{video_id}_ASR00000", "video_id": video_id})
        rows["scene_transcript_links"].append({"scene_id": scene_identifier, "asr_segment_id": f"{video_id}_ASR00000", "video_id": video_id})
        rows["embeddings_meta"].append(embedding_meta)
        rows["ocr"].append(ocr_row)
        rows["objects"].append(object_row)
        rows["image_captions"].append(image_caption_row)
        rows["shot_captions"].append({"shot_id": shot_identifier, **shot_caption_partial})
        rows["scene_summaries_initial"].append({"scene_id": scene_identifier, **scene_initial_partial})
        rows["scene_summaries_enriched"].append({"scene_id": scene_identifier, **scene_enriched_partial})
        rows["text_sources"].extend(text_source_rows(video_id, keyframe_identifier, text, ocr_text, asr_text))
        feature_status = "pass" if options.mode in {"bronze_fast", "silver_balanced", "gold_full"} else "degraded_mock"
        rows["feature_availability"].append({"entity_type": "keyframe", "entity_id": keyframe_identifier, "has_caption": True, "has_embedding": True, "has_ocr": bool(ocr_text), "has_asr": bool(asr_text), "status": feature_status})
        rows["text_documents"].append(text_document_row(document_id, video_id, text))
        rows["vector_map"].append({"index_name": "visual", "index_version": "v001", "embedding_model": embedding_provider.model_slug, "vector_id": vector_id, "embedding_id": embedding_meta["embedding_id"], "keyframe_id": keyframe_identifier, "video_id": video_id, "frame_id": frame_id, "shot_id": shot_identifier, "scene_id": scene_identifier})
        embeddings.append(embedding)
        reuse_rows.append(reuse_row)

    rows["release_capabilities"].extend(release_capability_rows(options.mode, plan, visual_status, visual_reason, asr_status, ocr_status, enrichment_status))
    rows["_embeddings"] = [{"vector": embedding} for embedding in embeddings]
    rows["_reuse"] = reuse_rows
    return {name: pd.DataFrame(data) for name, data in rows.items()}
