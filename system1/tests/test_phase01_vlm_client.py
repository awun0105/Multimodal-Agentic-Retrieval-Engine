from __future__ import annotations

from pathlib import Path

import pytest

from system1.gemini import GeminiRequest
from system1.vlm.client import FallbackStructuredClient, LocalVisionStructuredClient


def test_fallback_client_releases_failed_provider_before_next_provider() -> None:
    events: list[str] = []

    class FailingClient:
        def request(self, _request):
            events.append("fail_request")
            raise RuntimeError("provider failed")

        def close(self) -> None:
            events.append("fail_close")

    class PassingClient:
        def request(self, _request):
            events.append("pass_request")
            return {"value": "ok"}

    request = GeminiRequest(
        request_kind="test",
        video_id="L21_V001",
        prompt="return json",
        prompt_version="test_prompt",
        response_schema_version="test_schema",
        response_schema={
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
            "additionalProperties": False,
        },
    )

    response = FallbackStructuredClient([FailingClient(), PassingClient()]).request(
        request
    )

    assert response == {"value": "ok"}
    assert events == ["fail_request", "fail_close", "pass_request"]


def test_local_vlm_client_close_releases_loaded_model_handles() -> None:
    client = LocalVisionStructuredClient(
        model_config={
            "provider": "qwen_local",
            "model_id": "Qwen/Qwen2.5-VL-7B-Instruct",
            "model_revision": "test",
        }
    )
    client._loaded = (object(), object())

    client.close()

    assert client._loaded is None


def test_fallback_client_reports_all_provider_failures() -> None:
    class FailingClient:
        def __init__(self, name: str) -> None:
            self.name = name

        def request(self, _request):
            raise RuntimeError(self.name)

    request = GeminiRequest(
        request_kind="test",
        video_id="L21_V001",
        prompt="return json",
        prompt_version="test_prompt",
        response_schema_version="test_schema",
        response_schema={},
        image_paths=(Path("missing.jpg"),),
    )

    with pytest.raises(RuntimeError, match="first.*second"):
        FallbackStructuredClient(
            [FailingClient("first"), FailingClient("second")]
        ).request(request)
