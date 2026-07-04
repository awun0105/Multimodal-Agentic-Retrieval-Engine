from __future__ import annotations

import json
import hashlib
import unicodedata
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from system1.artifacts.package import discover_artifact_zip, extract_artifact_zip, write_artifact_zip
from system1.config import ProviderPlan, load_provider_plan
from system1.features.providers import MockEmbeddingProvider, MockTextProvider, RealEmbeddingUnavailable, RealProviderUnavailable
from system1.release.types import config_dir, release_root, write_json

FEATURE_ARTIFACT_FILES = (
    "visual_embeddings.npy",
    "embeddings_meta.parquet",
    "ocr.parquet",
    "objects.parquet",
    "image_captions.parquet",
    "shot_captions.parquet",
    "scene_summaries_enriched.parquet",
    "text_sources.parquet",
    "feature_manifest.json",
    "errors.jsonl",
)


def process_feature_batch(
    output_dir: Path | str,
    *,
    input_dir: Path | str | None = None,
    batch_id: str,
    mode: str = "debug_small_sample",
    providers: str = "mock",
    worker_id: str = "worker_000",
) -> Path:
    release_dir = release_root(output_dir)
    videos_path = release_dir / "tables" / "videos.parquet"
    media_manifest_path = release_dir / "raw_mapping" / "media_store_manifest.parquet"
    batch_path = release_dir / "manifests" / f"{batch_id}.txt"
    if not videos_path.exists():
        raise FileNotFoundError(f"missing ingestion output: {videos_path}")
    if not media_manifest_path.exists():
        raise FileNotFoundError(f"missing media mapping output: {media_manifest_path}")
    if not batch_path.exists():
        raise FileNotFoundError(f"missing batch manifest: {batch_path}")

    video_ids = [line.strip() for line in batch_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    videos_df = pd.read_parquet(videos_path)
    videos = {
        str(row["video_id"]): row
        for row in videos_df[videos_df["video_id"].isin(video_ids)].to_dict("records")
    }
    media_df = pd.read_parquet(media_manifest_path)
    media = {str(row["video_id"]): row for row in media_df.to_dict("records")}
    missing = sorted(set(video_ids) - set(videos))
    if missing:
        raise ValueError(f"batch references missing videos: {missing}")

    provider_plan = load_provider_plan(config_dir(), providers)
    embedding_provider, text_provider = providers_for_plan(provider_plan)
    artifact_paths: list[str] = []
    feature_errors: list[dict[str, Any]] = []

    for video_id in video_ids:
        structure_dir = _resolve_structure_artifact_dir(release_dir, video_id)
        artifact_dir = release_dir / "artifacts" / "features" / video_id
        if artifact_dir.exists():
            for path in artifact_dir.rglob("*"):
                if path.is_file():
                    path.unlink()
            for path in sorted((p for p in artifact_dir.rglob("*") if p.is_dir()), reverse=True):
                path.rmdir()
        artifact_dir.mkdir(parents=True, exist_ok=True)

        video_errors = _write_video_feature_artifact(
            artifact_dir=artifact_dir,
            structure_dir=structure_dir,
            video=videos[video_id],
            media=mapping_or_empty(media.get(video_id)),
            embedding_provider=embedding_provider,
            text_provider=text_provider,
            provider_plan=provider_plan,
            providers=providers,
            mode=mode,
            batch_id=batch_id,
            worker_id=worker_id,
        )
        feature_errors.extend(video_errors)
        zip_path = write_artifact_zip(
            artifact_dir=artifact_dir,
            zip_path=release_dir / "artifacts" / "features" / f"{video_id}_features.zip",
            video_id=video_id,
            artifact_type="features",
            batch_id=batch_id,
            worker_id=worker_id,
            status="complete" if not video_errors else "partial",
        )
        artifact_paths.append(str(zip_path.relative_to(release_dir)))

    report = {
        "worker_id": worker_id,
        "batch_id": batch_id,
        "phase": "features",
        "status": "pass" if not feature_errors else "partial",
        "artifact_paths": artifact_paths,
        "video_count": len(video_ids),
        "error_count": len(feature_errors),
    }
    report_path = release_dir / "manifests" / "worker_runtime_report_features.json"
    write_json(report_path, report)
    return report_path


def _resolve_structure_artifact_dir(release_dir: Path, video_id: str) -> Path:
    local_dir = release_dir / "artifacts" / "structure" / video_id
    if local_dir.exists():
        return local_dir
    zip_path = discover_artifact_zip(release_dir / "artifacts" / "structure", video_id=video_id, artifact_type="structure")
    if zip_path is None:
        raise FileNotFoundError(f"missing structure artifact folder or zip for video_id={video_id}: {local_dir}")
    return extract_artifact_zip(
        zip_path,
        release_dir / "staging" / "extracted_artifacts" / "structure",
        expected_video_id=video_id,
        expected_artifact_type="structure",
    )


def providers_for_plan(plan: ProviderPlan):
    embedding_provider = MockEmbeddingProvider() if plan.embedding == "mock" else RealEmbeddingUnavailable(plan.embedding)
    text_provider = MockTextProvider() if plan.mode == "mock" else RealProviderUnavailable("mixed_real_unavailable")
    return embedding_provider, text_provider


def capability_states(mode: str, plan: ProviderPlan) -> tuple[str, str, str, str, str]:
    visual_status = "degraded" if mode == "debug_small_sample" or plan.embedding != "mock" else "pass"
    visual_reason = (
        f"{plan.embedding} embedding adapter unavailable; using deterministic fallback vectors"
        if plan.embedding != "mock"
        else ("mock vectors; FAISS file is a stub in debug_small_sample" if mode == "debug_small_sample" else "deterministic ffmpeg keyframes + mock embeddings")
    )
    asr_status = "degraded" if mode in {"debug_small_sample", "bronze_fast"} or plan.asr != "mock" else "pass"
    ocr_status = "degraded" if mode in {"debug_small_sample", "bronze_fast"} or plan.ocr != "mock" else "pass"
    enrichment_status = "pass" if mode == "gold_full" else ("degraded" if mode == "debug_small_sample" else "pass")
    return visual_status, visual_reason, asr_status, ocr_status, enrichment_status


def feature_rows(
    *,
    keyframe_id: str,
    video_id: str,
    frame_id: int,
    keyframe_path: Path,
    text: str,
    plan: ProviderPlan,
    embedding_provider,
    text_provider,
    visual_status: str,
) -> tuple[dict[str, object], dict[str, object], dict[str, object], dict[str, object], dict[str, object], dict[str, object], dict[str, object], list[float], str, str]:
    embedding_id = f"{keyframe_id}_{embedding_provider.model_slug.replace('-', '_')}"
    embedding = embedding_provider.embed_image(keyframe_path)
    ocr_text = text_provider.read_text(keyframe_path)
    objects = text_provider.detect(keyframe_path)
    caption_text = text_provider.caption_image(keyframe_path, text)
    return (
        {"embedding_id": embedding_id, "keyframe_id": keyframe_id, "video_id": video_id, "frame_id": frame_id, "embedding_model": embedding_provider.model_slug, "model_slug": embedding_provider.model_slug, "embedding_dim": embedding_provider.embedding_dim, "vector_dim": embedding_provider.embedding_dim, "provider": plan.embedding, "embedding_status": visual_status, "status": visual_status},
        {"ocr_id": f"{keyframe_id}:ocr", "keyframe_id": keyframe_id, "text": ocr_text, "provider": plan.ocr, "status": "empty" if not ocr_text else "pass"},
        {"object_id": f"{keyframe_id}:object", "keyframe_id": keyframe_id, "label": objects[0], "confidence": 0.0, "provider": plan.object_detection},
        {"caption_id": f"{keyframe_id}:caption", "keyframe_id": keyframe_id, "caption": caption_text, "provider": plan.image_caption},
        {"caption": caption_text, "provider": plan.shot_caption},
        {"summary": text, "provider": plan.scene_summary},
        {"summary": text_provider.summarize_scene("scene", text), "provider": plan.scene_summary, "status": "mock"},
        embedding,
        ocr_text,
        caption_text,
    )


def release_capability_rows(mode: str, plan: ProviderPlan, visual_status: str, visual_reason: str, asr_status: str, ocr_status: str, enrichment_status: str) -> list[dict[str, object]]:
    return [
        {"capability": "core_runtime", "status": "pass", "reason": "app.sqlite and required tables built"},
        {"capability": "visual_search", "status": visual_status, "reason": visual_reason},
        {"capability": "text_search", "status": "pass", "reason": "text_documents and FTS5 built"},
        {"capability": "inspection_context", "status": "pass", "reason": "videos/shots/scenes/keyframes built"},
        {"capability": "asr", "status": asr_status, "reason": f"{plan.asr} ASR adapter unavailable; emitted schema-valid empty rows" if plan.asr != "mock" else ("mock empty ASR provider" if asr_status == "degraded" else "ASR provider contract emitted schema-valid rows")},
        {"capability": "ocr", "status": ocr_status, "reason": f"{plan.ocr} OCR adapter unavailable; emitted schema-valid empty rows" if plan.ocr != "mock" else ("mock empty OCR provider" if ocr_status == "degraded" else "OCR provider contract emitted schema-valid rows")},
        {"capability": "enrichment_overall", "status": enrichment_status, "reason": "mock providers ready for real adapters"},
        {"capability": "incremental_reuse", "status": "pass" if mode == "gold_full" else "degraded", "reason": "checkpoint manifest records checksums and reuse decisions"},
    ]


def _write_video_feature_artifact(
    *,
    artifact_dir: Path,
    structure_dir: Path,
    video: dict[str, Any],
    media: dict[str, Any],
    embedding_provider,
    text_provider,
    provider_plan: ProviderPlan,
    providers: str,
    mode: str,
    batch_id: str,
    worker_id: str,
) -> list[dict[str, Any]]:
    video_id = str(video["video_id"])
    errors: list[dict[str, Any]] = []
    keyframes = pd.read_parquet(structure_dir / "keyframes.parquet")
    metadata_payload = json.loads((structure_dir / "metadata_normalized.json").read_text(encoding="utf-8"))
    asr_df = pd.read_parquet(structure_dir / "asr_segments.parquet")
    shots_df = pd.read_parquet(structure_dir / "shots.parquet")
    scenes_df = pd.read_parquet(structure_dir / "scenes.parquet")

    visual_rows: list[list[float]] = []
    embeddings_meta_rows: list[dict[str, Any]] = []
    ocr_rows: list[dict[str, Any]] = []
    object_rows: list[dict[str, Any]] = []
    image_caption_rows: list[dict[str, Any]] = []
    text_source_rows: list[dict[str, Any]] = []

    visual_status, _, _, _, _ = capability_states(mode, provider_plan)
    for row in keyframes.to_dict("records"):
        keyframe_id = str(row["keyframe_id"])
        frame_id = int(row["frame_id"])
        keyframe_file = structure_dir / "keyframes" / Path(str(row["keyframe_ref"])).name
        try:
            embedding_meta, ocr_row, object_row, image_caption_row, _, _, _, embedding, ocr_text, caption_text = feature_rows(
                keyframe_id=keyframe_id,
                video_id=video_id,
                frame_id=frame_id,
                keyframe_path=keyframe_file,
                text=str(metadata_payload.get("normalized_text", video_id)),
                plan=provider_plan,
                embedding_provider=embedding_provider,
                text_provider=text_provider,
                visual_status=visual_status,
            )
        except Exception as exc:  # pragma: no cover
            errors.append({"video_id": video_id, "level": "warning", "kind": "feature_provider_failed", "message": str(exc)})
            embedding_dim = int(getattr(embedding_provider, "embedding_dim", 0) or 0)
            embedding_meta = {"embedding_id": f"{keyframe_id}_failed", "keyframe_id": keyframe_id, "video_id": video_id, "frame_id": frame_id, "embedding_model": getattr(embedding_provider, "model_slug", "unknown"), "model_slug": getattr(embedding_provider, "model_slug", "unknown"), "embedding_dim": embedding_dim, "vector_dim": embedding_dim, "provider": provider_plan.embedding, "status": "failed"}
            ocr_row = {"ocr_id": f"{keyframe_id}:ocr", "keyframe_id": keyframe_id, "text": "", "provider": provider_plan.ocr, "status": "failed"}
            object_row = {"object_id": f"{keyframe_id}:object", "keyframe_id": keyframe_id, "label": "", "confidence": 0.0, "provider": provider_plan.object_detection, "status": "failed"}
            image_caption_row = {"caption_id": f"{keyframe_id}:caption", "keyframe_id": keyframe_id, "caption": "", "provider": provider_plan.image_caption, "status": "failed"}
            embedding = [0.0] * embedding_dim
            ocr_text = ""
            caption_text = ""
        visual_rows.append(embedding)
        embeddings_meta_rows.append(
            {
                "embedding_id": embedding_meta["embedding_id"],
                "keyframe_id": keyframe_id,
                "video_id": video_id,
                "frame_id": frame_id,
                "model_slug": getattr(embedding_provider, "model_slug", embedding_meta.get("embedding_model", "unknown")),
                "embedding_model": embedding_meta.get("embedding_model", getattr(embedding_provider, "model_slug", "unknown")),
                "embedding_dim": embedding_meta.get("embedding_dim", getattr(embedding_provider, "embedding_dim", 0)),
                "vector_dim": getattr(embedding_provider, "embedding_dim", embedding_meta.get("embedding_dim", 0)),
                "status": embedding_meta.get("status", embedding_meta.get("embedding_status", "pass")),
                "provider": embedding_meta.get("provider", provider_plan.embedding),
            }
        )
        ocr_rows.append({
            "ocr_id": ocr_row["ocr_id"],
            "keyframe_id": keyframe_id,
            "video_id": video_id,
            "frame_id": frame_id,
            "raw_text": ocr_row.get("text", ""),
            "text": ocr_row.get("text", ""),
            "provider": ocr_row.get("provider", provider_plan.ocr),
            "status": ocr_row.get("status", "pass"),
        })
        object_rows.append({
            "object_id": object_row["object_id"],
            "keyframe_id": keyframe_id,
            "video_id": video_id,
            "frame_id": frame_id,
            "label": object_row.get("label", ""),
            "confidence": object_row.get("confidence", 0.0),
            "provider": object_row.get("provider", provider_plan.object_detection),
            "status": object_row.get("status", "pass"),
        })
        image_caption_rows.append({
            "caption_id": image_caption_row["caption_id"],
            "keyframe_id": keyframe_id,
            "video_id": video_id,
            "frame_id": frame_id,
            "caption": image_caption_row.get("caption", ""),
            "provider": image_caption_row.get("provider", provider_plan.image_caption),
            "status": image_caption_row.get("status", "pass"),
        })
        text_source_rows.extend([
            _text_source(video_id, "keyframe", keyframe_id, "ocr", ocr_text, provider_plan.ocr, ocr_row.get("status", "pass")),
            _text_source(video_id, "keyframe", keyframe_id, "image_caption", caption_text, provider_plan.image_caption, image_caption_row.get("status", "pass")),
            _text_source(video_id, "keyframe", keyframe_id, "object_labels", object_row.get("label", ""), provider_plan.object_detection, object_row.get("status", "pass")),
        ])

    shot_caption_rows = []
    for row in shots_df.to_dict("records"):
        caption = text_provider.caption_shot(str(row["shot_id"]), metadata_payload.get("normalized_text", video_id))
        shot_caption_rows.append({
            "shot_id": row["shot_id"],
            "video_id": video_id,
            "caption": caption,
            "provider": provider_plan.shot_caption,
            "status": "pass",
        })
        text_source_rows.append(_text_source(video_id, "shot", str(row["shot_id"]), "shot_caption", caption, provider_plan.shot_caption, "pass"))

    scene_summary_rows = []
    for row in scenes_df.to_dict("records"):
        summary = text_provider.summarize_scene(str(row["scene_id"]), metadata_payload.get("normalized_text", video_id))
        scene_summary_rows.append({
            "scene_id": row["scene_id"],
            "video_id": video_id,
            "summary": summary,
            "provider": provider_plan.scene_summary,
            "status": "pass",
        })
        text_source_rows.append(_text_source(video_id, "scene", str(row["scene_id"]), "scene_summary_enriched", summary, provider_plan.scene_summary, "pass"))

    metadata = metadata_payload.get("metadata", {}) if isinstance(metadata_payload.get("metadata"), dict) else {}
    text_source_rows.extend([
        _text_source(video_id, "video", video_id, "video_title", str(metadata.get("title", "")), "metadata", "pass"),
        _text_source(video_id, "video", video_id, "video_description", str(metadata.get("description", "")), "metadata", "pass"),
        _text_source(video_id, "video", video_id, "video_keywords", _keywords_text(metadata), "metadata", "pass"),
    ])
    for row in asr_df.to_dict("records"):
        text_source_rows.append(_text_source(video_id, "video", video_id, "asr", str(row.get("text", "")), str(row.get("provider", "asr")), str(row.get("status", "pass"))))

    vectors = np.array(visual_rows, dtype="float32") if visual_rows else np.zeros((0, 0), dtype="float32")
    np.save(artifact_dir / "visual_embeddings.npy", vectors)
    pd.DataFrame(embeddings_meta_rows).to_parquet(artifact_dir / "embeddings_meta.parquet", index=False)
    pd.DataFrame(ocr_rows).to_parquet(artifact_dir / "ocr.parquet", index=False)
    pd.DataFrame(object_rows).to_parquet(artifact_dir / "objects.parquet", index=False)
    pd.DataFrame(image_caption_rows).to_parquet(artifact_dir / "image_captions.parquet", index=False)
    pd.DataFrame(shot_caption_rows).to_parquet(artifact_dir / "shot_captions.parquet", index=False)
    pd.DataFrame(scene_summary_rows).to_parquet(artifact_dir / "scene_summaries_enriched.parquet", index=False)
    pd.DataFrame(text_source_rows).to_parquet(artifact_dir / "text_sources.parquet", index=False)
    (artifact_dir / "errors.jsonl").write_text("".join(json.dumps(err, ensure_ascii=False) + "\n" for err in errors), encoding="utf-8")
    write_json(
        artifact_dir / "feature_manifest.json",
        {
            "video_id": video_id,
            "status": "pass" if not errors else "partial",
            "counts": {
                "embeddings_meta": len(embeddings_meta_rows),
                "ocr": len(ocr_rows),
                "objects": len(object_rows),
                "image_captions": len(image_caption_rows),
                "shot_captions": len(shot_caption_rows),
                "scene_summaries_enriched": len(scene_summary_rows),
                "text_sources": len(text_source_rows),
                "embedding_rows": int(vectors.shape[0]) if vectors.ndim == 2 else 0,
            },
            "provider": providers,
            "mode": mode,
            "batch_id": batch_id,
            "worker_id": worker_id,
            "embedding_model_slug": getattr(embedding_provider, "model_slug", "unknown"),
            "source_structure_artifact": _relative_structure_artifact(structure_dir, artifact_dir),
            "visual_embeddings_shape": list(vectors.shape),
            "provider_plan": provider_plan.__dict__,
            "errors": errors,
        },
    )
    return errors


def _relative_structure_artifact(structure_dir: Path, artifact_dir: Path) -> str:
    release_dir = artifact_dir.parent.parent.parent
    try:
        return str(structure_dir.relative_to(release_dir))
    except ValueError:
        return str(structure_dir)


def _text_source(video_id: str, entity_type: str, entity_id: str, source_type: str, raw_text: str, provider: str, status: str) -> dict[str, Any]:
    normalized_text = raw_text or ""
    normalized_no_diacritics = "".join(
        char for char in unicodedata.normalize("NFD", normalized_text) if unicodedata.category(char) != "Mn"
    )
    digest = hashlib.sha256(f"{entity_type}|{entity_id}|{provider}|{raw_text}".encode("utf-8")).hexdigest()[:12]
    source_id = f"{video_id}:{entity_type}:{source_type}:{provider}:{digest}"
    return {
        "source_id": source_id,
        "video_id": video_id,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "source_type": source_type,
        "raw_text": raw_text,
        "normalized_text": normalized_text,
        "normalized_no_diacritics": normalized_no_diacritics,
        "language": "vi",
        "provider": provider,
        "status": status,
    }


def _keywords_text(metadata: dict[str, Any]) -> str:
    keywords = metadata.get("keywords") or metadata.get("tags") or []
    if isinstance(keywords, list):
        return " ".join(str(item) for item in keywords)
    return str(keywords or "")


def mapping_or_empty(value: dict[str, Any] | None) -> dict[str, Any]:
    return value or {}
