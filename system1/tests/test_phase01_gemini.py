from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from system1.artifacts.store import ArtifactStore
from system1.gemini.client import (
    GeminiRequest,
    GeminiStructuredClient,
    build_request_hash,
)

SCHEMA = {
    "type": "object",
    "properties": {"caption_vi": {"type": "string"}, "caption_en": {"type": "string"}},
    "required": ["caption_vi", "caption_en"],
    "additionalProperties": False,
}


class ApiError(RuntimeError):
    def __init__(self, message: str, status_code: int):
        super().__init__(message)
        self.status_code = status_code


class FakeInteractions:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return SimpleNamespace(output_text=response)


class FakeClient:
    def __init__(self, interactions):
        self.interactions = interactions
        self.closed = False

    def close(self):
        self.closed = True


def api_config() -> dict:
    return {
        "total_attempts": 4,
        "backoff_initial_seconds": 2,
        "backoff_max_seconds": 30,
        "jitter": False,
        "retryable_http_statuses": [408, 429, 500, 502, 503, 504],
        "terminal_http_statuses": [400, 401, 403, 404],
        "schema_repair_attempts": 1,
        "schema_repair_prompt_version": "schema_repair_v1",
    }


def request(image: Path | None = None) -> GeminiRequest:
    return GeminiRequest(
        request_kind="shot_caption",
        video_id="L21_V001",
        prompt="Caption this shot",
        prompt_version="shot_caption_v1",
        response_schema_version="shot_caption_response_v1",
        response_schema=SCHEMA,
        image_paths=(image,) if image else (),
        identity={"shot_id": "L21_V001_SH00000"},
    )


def test_request_hash_changes_with_image_content(tmp_path: Path) -> None:
    image = tmp_path / "frame.jpg"
    image.write_bytes(b"one")
    first = build_request_hash(request(image), model_id="gemini-3.6-flash")
    image.write_bytes(b"two")
    second = build_request_hash(request(image), model_id="gemini-3.6-flash")
    assert first != second


def test_request_hash_changes_with_generation_or_repair_policy() -> None:
    first = build_request_hash(
        request(),
        model_id="gemini-3.6-flash",
        cache_identity={"thinking_level": "medium", "repair": "v1"},
    )
    second = build_request_hash(
        request(),
        model_id="gemini-3.6-flash",
        cache_identity={"thinking_level": "high", "repair": "v1"},
    )
    assert first != second


def test_valid_response_is_cached_and_reused(tmp_path: Path) -> None:
    interactions = FakeInteractions([json.dumps({"caption_vi": "Một người", "caption_en": "A person"})])
    client = GeminiStructuredClient(
        model_id="gemini-3.6-flash",
        api_config=api_config(),
        client_factory=lambda: FakeClient(interactions),
        cache=ArtifactStore(tmp_path / "cache"),
    )
    assert client.request(request())["caption_en"] == "A person"
    assert client.request(request())["caption_vi"] == "Một người"
    assert len(interactions.calls) == 1
    assert "temperature" not in interactions.calls[0]
    assert interactions.calls[0]["timeout"] == 120
    assert interactions.calls[0]["generation_config"] == {"thinking_level": "medium"}
    assert interactions.calls[0]["response_format"]["mime_type"] == "application/json"


def test_retryable_429_retries_but_terminal_401_does_not() -> None:
    sleeps = []
    interactions = FakeInteractions(
        [ApiError("rate limited", 429), json.dumps({"caption_vi": "x", "caption_en": "y"})]
    )
    client = GeminiStructuredClient(
        model_id="gemini-3.6-flash",
        api_config=api_config(),
        client_factory=lambda: FakeClient(interactions),
        sleep=sleeps.append,
    )
    assert client.request(request())["caption_en"] == "y"
    assert sleeps == [2]

    terminal = FakeInteractions([ApiError("unauthorized", 401)])
    client = GeminiStructuredClient(
        model_id="gemini-3.6-flash",
        api_config=api_config(),
        client_factory=lambda: FakeClient(terminal),
    )
    with pytest.raises(ApiError):
        client.request(request())
    assert len(terminal.calls) == 1


def test_invalid_schema_gets_exactly_one_repair_request() -> None:
    interactions = FakeInteractions(
        [
            json.dumps({"caption_vi": "missing english"}),
            json.dumps({"caption_vi": "đúng", "caption_en": "correct"}),
        ]
    )
    client = GeminiStructuredClient(
        model_id="gemini-3.6-flash",
        api_config=api_config(),
        client_factory=lambda: FakeClient(interactions),
    )
    assert client.request(request())["caption_en"] == "correct"
    assert len(interactions.calls) == 2


def test_schema_repair_call_uses_the_same_bounded_transport_retry() -> None:
    interactions = FakeInteractions(
        [
            json.dumps({"caption_vi": "missing english"}),
            ApiError("rate limited", 429),
            json.dumps({"caption_vi": "đúng", "caption_en": "correct"}),
        ]
    )
    sleeps: list[float] = []
    client = GeminiStructuredClient(
        model_id="gemini-3.6-flash",
        api_config=api_config(),
        client_factory=lambda: FakeClient(interactions),
        sleep=sleeps.append,
    )

    assert client.request(request())["caption_en"] == "correct"
    assert len(interactions.calls) == 3
    assert sleeps == [2]
