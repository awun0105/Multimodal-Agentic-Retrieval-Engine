from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

import pandas as pd

from system1.artifacts.hf_store import HuggingFaceDatasetArtifactStore
from system1.config import load_provider_plan
from system1.features.builder import capability_states, feature_rows, providers_for_plan, release_capability_rows
from system1.ingest.discovery import discover_paired_inputs, read_metadata
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
    mode: str = "debug_small_sample",
    canonical_hf_repo_id: str | None = None,
    canonical_hf_prefix: str = "",
    canonical_hf_repo_type: str = "dataset",
    canonical_hf_revision: str = "main",
    canonical_staging_root: Path | str | None = None,
) -> Path:
    if canonical_hf_repo_id:
        return run_canonical_hf_ingestion(
            output_dir,
            mode=mode,
            repo_id=canonical_hf_repo_id,
            prefix=canonical_hf_prefix,
            repo_type=canonical_hf_repo_type,
            revision=canonical_hf_revision,
            staging_root=canonical_staging_root,
        )

    release_dir = release_root(output_dir)
    tables_dir = release_dir / "tables"
    manifests_dir = release_dir / "manifests"
    raw_mapping_dir = release_dir / "raw_mapping"
    tables_dir.mkdir(parents=True, exist_ok=True)
    manifests_dir.mkdir(parents=True, exist_ok=True)
    raw_mapping_dir.mkdir(parents=True, exist_ok=True)

    pairs = discover_paired_inputs(input_dir or default_input_dir())
    video_rows: list[dict[str, Any]] = []
    mapping_rows: list[dict[str, Any]] = []
    error_records: list[dict[str, Any]] = []

    for pair in pairs:
        video_path = Path(pair["video_path"])
        metadata_path = Path(pair["metadata_path"])
        video_id = pair["video_id"]
        metadata = read_metadata(metadata_path)
        probe = probe_video(video_path)
        video_ref = f"media://raw_videos/{video_path.name}"
        metadata_ref = f"media://metadata/{metadata_path.name}"
        estimated_compute_cost = probe.duration_seconds or probe.frame_count or 1
        video_rows.append(
            {
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
        )
        mapping_rows.append(
            {
                "video_id": video_id,
                "video_ref": video_ref,
                "metadata_ref": metadata_ref,
                "video_filename": video_path.name,
                "metadata_filename": metadata_path.name,
                "video_local_path": str(video_path.resolve()),
                "metadata_local_path": str(metadata_path.resolve()),
                "video_size_bytes": video_path.stat().st_size,
                "metadata_size_bytes": metadata_path.stat().st_size,
            }
        )
        if probe.fps_detected is None or probe.duration_seconds is None:
            error_records.append(
                {
                    "video_id": video_id,
                    "level": "warning",
                    "kind": "probe_partial",
                    "message": "ffprobe metadata incomplete; some fields unavailable",
                }
            )

    videos_df = pd.DataFrame(video_rows).drop_duplicates(subset=["video_id"]).sort_values("video_id")
    mapping_df = pd.DataFrame(mapping_rows).drop_duplicates(subset=["video_id"]).sort_values("video_id")
    videos_df.to_parquet(tables_dir / "videos.parquet", index=False)
    mapping_df.to_parquet(raw_mapping_dir / "media_store_manifest.parquet", index=False)
    errors_path = manifests_dir / "ingestion_errors.jsonl"
    errors_path.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in error_records),
        encoding="utf-8",
    )
    report_path = manifests_dir / "dataset_report.json"
    write_json(
        report_path,
        {
            "release_id": release_dir.name,
            "mode": mode,
            "video_count": int(len(videos_df)),
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

    video_rows: list[dict[str, Any]] = []
    mapping_rows: list[dict[str, Any]] = []
    error_records: list[dict[str, Any]] = []

    with tempfile.TemporaryDirectory(prefix="system1_canonical_ingest_", dir=staging_parent) as tmp:
        tmp_path = Path(tmp)
        manifest_path = store.download_file("manifests/canonical_file_manifest.jsonl", tmp_path / "canonical_file_manifest.jsonl")
        rows = _read_canonical_manifest(manifest_path)
        for row in rows:
            if row.get("status") not in {None, "pass", "skipped"}:
                continue
            video_id = str(row["video_id"])
            video_remote_path = str(row["video_path"])
            metadata_remote_path = str(row["metadata_path"])
            video_filename = str(row.get("video_filename") or Path(video_remote_path).name)
            metadata_filename = str(row.get("metadata_filename") or Path(metadata_remote_path).name)
            video_path = store.download_file(video_remote_path, tmp_path / "raw_videos" / video_filename)
            metadata_path = store.download_file(metadata_remote_path, tmp_path / "metadata" / metadata_filename)
            metadata = read_metadata(metadata_path)
            probe = probe_video(video_path)
            video_ref = f"media://raw_videos/{video_filename}"
            metadata_ref = f"media://metadata/{metadata_filename}"
            estimated_compute_cost = probe.duration_seconds or probe.frame_count or 1
            video_rows.append(
                {
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
            )
            mapping_rows.append(
                {
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
            )
            if probe.fps_detected is None or probe.duration_seconds is None:
                error_records.append(
                    {
                        "video_id": video_id,
                        "level": "warning",
                        "kind": "probe_partial",
                        "message": "ffprobe metadata incomplete; some fields unavailable",
                    }
                )

    videos_df = pd.DataFrame(video_rows).drop_duplicates(subset=["video_id"]).sort_values("video_id")
    mapping_df = pd.DataFrame(mapping_rows).drop_duplicates(subset=["video_id"]).sort_values("video_id")
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


def build_tables(
    pairs: list[dict[str, str]],
    release_dir: Path,
    options: BuildOptions,
    previous_checkpoint: dict[str, Any] | None,
) -> dict[str, pd.DataFrame]:
    """Legacy dev helper for `build-mini-seed` only.

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
