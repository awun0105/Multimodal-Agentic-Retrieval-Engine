from __future__ import annotations

import hashlib
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
        {"source_type": "metadata", "entity_id": video_id, "normalized_text": metadata_text_value},
        {"source_type": "ocr", "entity_id": keyframe_id, "normalized_text": ocr_text},
        {"source_type": "asr", "entity_id": video_id, "normalized_text": asr_text},
    ]


def text_document_row(document_id: str, video_id: str, text: str) -> dict[str, object]:
    return {
        "doc_id": document_id,
        "document_id": document_id,
        "level": "video",
        "entity_type": "video",
        "entity_id": video_id,
        "source_type": "metadata",
        "normalized_text": text,
        "normalized_no_diacritics": text,
        "text": text,
    }
