from __future__ import annotations

import base64
import hashlib
import json
import random
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from jsonschema import ValidationError, validate


class JsonCache(Protocol):
    def exists(self, relative_path: str | Path) -> bool: ...

    def read_json(self, relative_path: str | Path) -> dict[str, Any]: ...

    def write_json(self, relative_path: str | Path, payload: dict[str, Any]) -> Path: ...


@dataclass(frozen=True)
class StructuredRequest:
    request_kind: str
    video_id: str
    prompt: str
    prompt_version: str
    response_schema_version: str
    response_schema: dict[str, Any]
    image_paths: tuple[Path, ...] = ()
    identity: Mapping[str, Any] | None = None


def build_request_hash(
    request: StructuredRequest,
    *,
    model_id: str,
    cache_identity: Mapping[str, Any] | None = None,
) -> str:
    images = [
        {
            "name": path.name,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        for path in request.image_paths
    ]
    payload = {
        "request_kind": request.request_kind,
        "video_id": request.video_id,
        "prompt": request.prompt,
        "prompt_version": request.prompt_version,
        "response_schema_version": request.response_schema_version,
        "response_schema": request.response_schema,
        "model_id": model_id,
        "images": images,
        "identity": request.identity or {},
        "cache_identity": cache_identity or {},
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class GeminiStructuredClient:
    def __init__(
        self,
        *,
        model_id: str,
        api_config: Mapping[str, Any],
        client_factory: Callable[[], Any] | None = None,
        cache: JsonCache | None = None,
        cache_prefix: str | Path = "cache/gemini",
        sleep: Callable[[float], None] = time.sleep,
        random_uniform: Callable[[float, float], float] = random.uniform,
    ) -> None:
        self.model_id = model_id
        self.api_config = dict(api_config)
        self.client_factory = client_factory or (
            lambda: _default_client_factory(
                timeout_seconds=float(self.api_config.get("timeout_seconds", 120))
            )
        )
        self.cache = cache
        self.cache_prefix = Path(cache_prefix)
        self.sleep = sleep
        self.random_uniform = random_uniform
        self._cache_lock = threading.Lock()

    def request(self, request: StructuredRequest) -> dict[str, Any]:
        request_hash = build_request_hash(
            request,
            model_id=self.model_id,
            cache_identity={
                "thinking_level": self.api_config.get("thinking_level", "medium"),
                "schema_repair_prompt_version": self.api_config.get(
                    "schema_repair_prompt_version"
                ),
            },
        )
        cache_path = self.cache_prefix / f"{request_hash}.json"
        if self.cache is not None:
            with self._cache_lock:
                if self.cache.exists(cache_path):
                    cached = self.cache.read_json(cache_path)
                    response = cached.get("normalized_response")
                    if isinstance(response, dict):
                        validate(response, request.response_schema)
                        return response

        raw_text = self._transport_request(request)
        try:
            normalized = self._parse_and_validate(raw_text, request.response_schema)
            repaired = False
        except (json.JSONDecodeError, ValidationError, ValueError):
            if int(self.api_config.get("schema_repair_attempts", 1)) < 1:
                raise
            raw_text = self._repair_schema(request, raw_text)
            normalized = self._parse_and_validate(raw_text, request.response_schema)
            repaired = True
        if self.cache is not None:
            with self._cache_lock:
                self.cache.write_json(
                    cache_path,
                    {
                        "schema_version": "gemini_cache_entry_v1",
                        "request_hash": request_hash,
                        "request_kind": request.request_kind,
                        "video_id": request.video_id,
                        "model_id": self.model_id,
                        "prompt_version": request.prompt_version,
                        "response_schema_version": request.response_schema_version,
                        "schema_repaired": repaired,
                        "normalized_response": normalized,
                    },
                )
        return normalized

    def request_many(
        self, requests: list[StructuredRequest]
    ) -> list[dict[str, Any]]:
        # Gemini fallback stays serial. GPU batching belongs to local clients,
        # and this interface must not increase API concurrency.
        return [self.request(request) for request in requests]

    def _transport_request(self, request: StructuredRequest) -> str:
        return self._transport_call(
            prompt=request.prompt,
            image_paths=request.image_paths,
            response_schema=request.response_schema,
        )

    def _transport_call(
        self,
        *,
        prompt: str,
        image_paths: tuple[Path, ...],
        response_schema: dict[str, Any],
    ) -> str:
        attempts = int(self.api_config["total_attempts"])
        delay = float(self.api_config["backoff_initial_seconds"])
        maximum = float(self.api_config["backoff_max_seconds"])
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                return self._call_api(
                    prompt=prompt,
                    image_paths=image_paths,
                    response_schema=response_schema,
                )
            except Exception as exc:
                last_error = exc
                if not _retryable_transport_error(exc, self.api_config):
                    raise
                if attempt == attempts:
                    break
                jitter = self.random_uniform(0.0, delay) if self.api_config.get("jitter") else 0.0
                self.sleep(min(maximum, delay + jitter))
                delay = min(maximum, delay * 2)
        raise RuntimeError(f"Gemini transport failed after {attempts} attempts: {last_error}") from last_error

    def _repair_schema(self, request: StructuredRequest, invalid_text: str) -> str:
        prompt_version = str(self.api_config["schema_repair_prompt_version"])
        prompt_path = (
            Path(__file__).resolve().parents[3] / "prompts" / f"{prompt_version}.txt"
        )
        repair_instruction = prompt_path.read_text(encoding="utf-8").strip()
        repair_prompt = (
            repair_instruction + "\n\nINVALID RESPONSE:\n" + invalid_text
        )
        return self._transport_call(
            prompt=repair_prompt,
            image_paths=(),
            response_schema=request.response_schema,
        )

    def _call_api(
        self,
        *,
        prompt: str,
        image_paths: tuple[Path, ...],
        response_schema: dict[str, Any],
    ) -> str:
        input_parts: list[dict[str, Any]] = []
        for path in image_paths:
            mime_type = "image/webp" if path.suffix.lower() == ".webp" else "image/jpeg"
            input_parts.append(
                {
                    "type": "image",
                    "mime_type": mime_type,
                    "data": base64.b64encode(path.read_bytes()).decode("ascii"),
                }
            )
        input_parts.append({"type": "text", "text": prompt})
        client = self.client_factory()
        try:
            interaction = client.interactions.create(
                model=self.model_id,
                input=input_parts,
                response_format={
                    "type": "text",
                    "mime_type": "application/json",
                    "schema": response_schema,
                },
                generation_config={
                    "thinking_level": str(self.api_config.get("thinking_level", "medium")),
                },
                timeout=float(self.api_config.get("timeout_seconds", 120)),
            )
            output_text = getattr(interaction, "output_text", None)
            if not isinstance(output_text, str) or not output_text.strip():
                raise ValueError("Gemini returned an empty structured response")
            return output_text
        finally:
            close = getattr(client, "close", None)
            if callable(close):
                close()

    @staticmethod
    def _parse_and_validate(raw_text: str, schema: dict[str, Any]) -> dict[str, Any]:
        payload = json.loads(raw_text)
        if not isinstance(payload, dict):
            raise TypeError("Gemini structured response must be an object")
        validate(payload, schema)
        return payload


def _default_client_factory(*, timeout_seconds: float):
    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:  # pragma: no cover - production preflight
        raise RuntimeError("google-genai is required for Phase01 Gemini stages") from exc
    return genai.Client(
        http_options=types.HttpOptions(
            timeout=int(timeout_seconds * 1000),
            retry_options=types.HttpRetryOptions(attempts=1),
        )
    )


def _retryable_transport_error(exc: Exception, config: Mapping[str, Any]) -> bool:
    status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    if status in set(config.get("terminal_http_statuses", ())):
        return False
    if status in set(config.get("retryable_http_statuses", ())):
        return True
    message = str(exc).lower()
    return isinstance(exc, TimeoutError) or any(
        marker in message
        for marker in ("timeout", "timed out", "connection reset", "temporarily unavailable")
    )


# Backward-compatible import while structured requests become provider-neutral.
GeminiRequest = StructuredRequest
