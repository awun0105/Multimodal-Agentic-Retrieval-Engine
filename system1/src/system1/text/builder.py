from __future__ import annotations

import hashlib
import unicodedata
from typing import Any


def metadata_text(video_id: str, metadata: dict[str, Any]) -> str:
    values: list[str] = [video_id]
    for key in ("title", "description", "caption", "watch_url"):
        value = metadata.get(key)
        if value:
            values.append(str(value))
    keywords = metadata.get("keywords") or metadata.get("tags") or []
    if isinstance(keywords, list):
        values.extend(str(item) for item in keywords)
    elif keywords:
        values.append(str(keywords))
    return " ".join(part.strip() for part in values if part and part.strip()) or video_id


def doc_id(source_type: str, entity_id: str, normalized_text: str) -> str:
    digest = hashlib.sha256(f"{source_type}|{entity_id}|{normalized_text}".encode("utf-8")).hexdigest()[:16]
    return f"doc:{digest}"


def text_source_rows(video_id: str, keyframe_id: str, metadata_text_value: str, ocr_text: str, asr_text: str) -> list[dict[str, object]]:
    return [
        text_source_row(video_id, "video", video_id, "metadata", metadata_text_value, "metadata", "pass"),
        text_source_row(video_id, "keyframe", keyframe_id, "ocr", ocr_text, "ocr", "pass"),
        text_source_row(video_id, "video", video_id, "asr", asr_text, "asr", "pass"),
    ]


def text_source_row(
    video_id: str,
    entity_type: str,
    entity_id: str,
    source_type: str,
    raw_text: str,
    provider: str,
    status: str,
    language: str = "vi",
) -> dict[str, object]:
    normalized_text = raw_text or ""
    normalized_no_diacritics = "".join(
        char for char in unicodedata.normalize("NFD", normalized_text) if unicodedata.category(char) != "Mn"
    )
    digest = hashlib.sha256(f"{entity_type}|{entity_id}|{provider}|{raw_text}".encode("utf-8")).hexdigest()[:12]
    return {
        "source_id": f"{video_id}:{entity_type}:{source_type}:{provider}:{digest}",
        "video_id": video_id,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "source_type": source_type,
        "raw_text": raw_text,
        "normalized_text": normalized_text,
        "normalized_no_diacritics": normalized_no_diacritics,
        "language": language,
        "provider": provider,
        "status": status,
    }


def text_document_row(document_id: str, video_id: str, text: str) -> dict[str, object]:
    normalized_no_diacritics = "".join(
        char for char in unicodedata.normalize("NFD", text) if unicodedata.category(char) != "Mn"
    )
    return {
        "doc_id": document_id,
        "document_id": document_id,
        "level": "video",
        "entity_type": "video",
        "entity_id": video_id,
        "source_type": "metadata",
        "normalized_text": text,
        "normalized_no_diacritics": normalized_no_diacritics,
        "text": text,
    }
