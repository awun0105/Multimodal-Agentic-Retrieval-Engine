from __future__ import annotations

from pathlib import Path

from system1.config import ProviderPlan
from system1.features.providers import MockEmbeddingProvider, MockTextProvider, RealEmbeddingUnavailable, RealProviderUnavailable


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
    caption_text = text_provider.caption(keyframe_path, text)
    return (
        {"embedding_id": embedding_id, "keyframe_id": keyframe_id, "video_id": video_id, "frame_id": frame_id, "embedding_model": embedding_provider.model_slug, "embedding_dim": embedding_provider.embedding_dim, "provider": plan.embedding, "embedding_status": visual_status},
        {"ocr_id": f"{keyframe_id}:ocr", "keyframe_id": keyframe_id, "text": ocr_text, "provider": plan.ocr, "status": "empty" if not ocr_text else "pass"},
        {"object_id": f"{keyframe_id}:object", "keyframe_id": keyframe_id, "label": objects[0], "confidence": 0.0, "provider": plan.object_detection},
        {"caption_id": f"{keyframe_id}:caption", "keyframe_id": keyframe_id, "caption": caption_text, "provider": plan.image_caption},
        {"caption": caption_text, "provider": plan.shot_caption},
        {"summary": text, "provider": plan.scene_summary},
        {"summary": text_provider.summarize("scene", text), "provider": plan.scene_summary, "status": "mock"},
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
