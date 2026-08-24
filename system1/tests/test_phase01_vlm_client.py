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


def test_fallback_client_stays_on_working_provider_without_model_overlap() -> None:
    resident: list[str] = []
    primary_calls = 0
    fallback_calls = 0

    class FailingPrimary:
        def request(self, _request):
            nonlocal primary_calls
            primary_calls += 1
            assert not resident
            resident.append("qwen")
            raise RuntimeError("qwen failed")

        def close(self) -> None:
            if "qwen" in resident:
                resident.remove("qwen")

    class PassingFallback:
        def request(self, _request):
            nonlocal fallback_calls
            fallback_calls += 1
            if not resident:
                resident.append("vintern")
            assert resident == ["vintern"]
            return {"value": "ok"}

        def close(self) -> None:
            if "vintern" in resident:
                resident.remove("vintern")

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
    client = FallbackStructuredClient([FailingPrimary(), PassingFallback()])

    assert client.request(request) == {"value": "ok"}
    assert client.request(request) == {"value": "ok"}
    assert primary_calls == 1
    assert fallback_calls == 2
    assert resident == ["vintern"]

    client.close()
    assert resident == []


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


def test_local_vlm_cuda_oom_releases_and_retries(monkeypatch) -> None:
    lifecycle: list[dict[str, object]] = []
    releases: list[str] = []
    calls = 0
    client = LocalVisionStructuredClient(
        model_config={
            "provider": "qwen_local",
            "model_id": "Qwen/Qwen2.5-VL-7B-Instruct",
            "model_revision": "test",
            "total_attempts": 2,
            "inference_batch_size": 1,
        },
        lifecycle_callback=lambda payload: lifecycle.append(dict(payload)),
    )

    def call_model(_request) -> str:
        nonlocal calls
        calls += 1
        client._loaded = (object(), object())
        if calls == 1:
            raise RuntimeError("CUDA out of memory")
        return '{"value": "ok"}'

    monkeypatch.setattr(client, "_call_model", call_model)
    monkeypatch.setattr(
        "system1.vlm.client._release_torch_memory",
        lambda: releases.append("released"),
    )
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

    response = client.request(request)

    assert response["value"] == "ok"
    assert calls == 2
    assert releases == ["released"]
    assert [event["status"] for event in lifecycle] == ["unloaded", "oom_retry"]


def test_local_vlm_rejects_inference_batching_above_one() -> None:
    with pytest.raises(ValueError, match="inference_batch_size must be 1"):
        LocalVisionStructuredClient(
            model_config={
                "provider": "qwen_local",
                "model_id": "Qwen/Qwen2.5-VL-7B-Instruct",
                "inference_batch_size": 2,
            }
        )
