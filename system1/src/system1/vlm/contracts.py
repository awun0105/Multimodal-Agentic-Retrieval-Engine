from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Literal


TEXT_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "text": {
            "type": "string",
            "minLength": 1,
        },
    },
    "required": ["text"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class ModelRequest:
    request_kind: str
    video_id: str

    prompt: str
    prompt_version: str

    response_schema_version: str
    response_schema: dict[str, Any]

    image_paths: tuple[Path, ...] = ()

    # Qwen có thể nhận nhiều ảnh.
    # Vintern fallback có thể cần một contact-sheet duy nhất.
    fallback_image_paths: tuple[Path, ...] | None = None

    identity: Mapping[str, Any] | None = None

    response_mode: Literal["json", "text"] = "json"

    # Dùng cho output classification strict như scene boundary.
    allowed_text_values: tuple[str, ...] = ()


def build_request_hash(
    request: ModelRequest,
    *,
    model_id: str,
    cache_identity: Mapping[str, Any] | None = None,
) -> str:
    images = [
        {
            "name": path.name,
            "sha256": hashlib.sha256(
                path.read_bytes()
            ).hexdigest(),
        }
        for path in request.image_paths
    ]

    payload = {
        "request_kind": request.request_kind,
        "video_id": request.video_id,
        "prompt": request.prompt,
        "prompt_version": request.prompt_version,
        "response_schema_version":
            request.response_schema_version,
        "response_schema": request.response_schema,
        "response_mode": request.response_mode,
        "allowed_text_values": list(
            request.allowed_text_values
        ),
        "model_id": model_id,
        "images": images,
        "identity": request.identity or {},
        "cache_identity": cache_identity or {},
    }

    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )

    return hashlib.sha256(
        encoded.encode("utf-8")
    ).hexdigest()


def normalize_text_response(
    raw_text: str,
    request: ModelRequest,
) -> dict[str, Any]:
    text = raw_text.strip()

    if not text:
        raise ValueError(
            f"{request.request_kind} returned empty text"
        )

    if request.allowed_text_values:
        normalized = text.upper()

        allowed = {
            value.upper()
            for value in request.allowed_text_values
        }

        if normalized not in allowed:
            raise ValueError(
                f"{request.request_kind} returned "
                f"invalid label {text!r}; expected "
                f"one of {sorted(allowed)}"
            )

        text = normalized

    return {"text": text}
