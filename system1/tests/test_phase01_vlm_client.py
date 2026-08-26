from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
from PIL import Image

from system1.artifacts.store import ArtifactStore
from system1.vlm import (
    TEXT_RESPONSE_SCHEMA,
    ModelRequest,
    build_request_hash,
    normalize_text_response,
)
from system1.vlm.client import (
    BatchRequestError,
    ExclusiveLocalFallbackClient,
    LocalVisionStructuredClient,
    SystemicProviderError,
)
from system1.vlm.vintern_reasoning import split_dynamic_tiles


class _FakeTensor:
    dtype = "torch.float32"

    def to(self, *_args, **_kwargs):
        return self


def _install_fake_torch(monkeypatch):
    module = ModuleType("torch")
    module.float16 = "torch.float16"
    module.bfloat16 = "torch.bfloat16"
    module.float32 = "torch.float32"
    module.cat = lambda _tensors, dim=0: _FakeTensor()

    class NoGrad:
        def __enter__(self):
            return None

        def __exit__(self, *_args):
            return False

    module.no_grad = NoGrad
    module.cuda = SimpleNamespace(is_available=lambda: False)
    monkeypatch.setitem(sys.modules, "torch", module)
    return module


def test_request_error_activates_sticky_fallback() -> None:
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

    request = ModelRequest(
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

    client = ExclusiveLocalFallbackClient(FailingClient(), PassingClient())
    response = client.request(request)
    second = client.request(request)

    assert response == {"value": "ok"}
    assert second == {"value": "ok"}
    assert client.circuit_open is True
    assert events == [
        "fail_request",
        "fail_close",
        "pass_request",
        "pass_request",
    ]


def test_text_request_hash_differs_from_json_request_hash() -> None:
    base = {
        "request_kind": "semantic",
        "video_id": "L21_V001",
        "prompt": "describe",
        "prompt_version": "prompt_v1",
        "response_schema_version": "response_v1",
        "response_schema": TEXT_RESPONSE_SCHEMA,
    }
    text_request = ModelRequest(**base, response_mode="text")
    json_request = ModelRequest(**base, response_mode="json")

    assert build_request_hash(
        text_request, model_id="model"
    ) != build_request_hash(json_request, model_id="model")


@pytest.mark.parametrize("label", ["BOUNDARY", "same_scene"])
def test_boundary_label_normalization_accepts_exact_labels(label: str) -> None:
    request = ModelRequest(
        request_kind="scene_boundary_primary",
        video_id="L21_V001",
        prompt="classify",
        prompt_version="prompt_v1",
        response_schema_version="plain_text_response_v1",
        response_schema=TEXT_RESPONSE_SCHEMA,
        response_mode="text",
        allowed_text_values=("BOUNDARY", "SAME_SCENE"),
    )

    assert normalize_text_response(label, request) == {"text": label.upper()}


def test_boundary_label_normalization_rejects_extra_text() -> None:
    request = ModelRequest(
        request_kind="scene_boundary_primary",
        video_id="L21_V001",
        prompt="classify",
        prompt_version="prompt_v1",
        response_schema_version="plain_text_response_v1",
        response_schema=TEXT_RESPONSE_SCHEMA,
        response_mode="text",
        allowed_text_values=("BOUNDARY", "SAME_SCENE"),
    )

    with pytest.raises(ValueError, match="invalid label"):
        normalize_text_response("BOUNDARY because the view changed", request)


def test_systemic_failure_closes_primary_and_circuits_chunk() -> None:
    resident: list[str] = []
    telemetry = []
    primary_calls = 0
    fallback_calls = 0
    primary_close_calls = 0

    class FailingPrimary:
        def request(self, _request):
            nonlocal primary_calls
            primary_calls += 1
            assert not resident
            resident.append("qwen")
            raise SystemicProviderError("qwen failed")

        def close(self) -> None:
            nonlocal primary_close_calls
            primary_close_calls += 1
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

    request = ModelRequest(
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
    primary = FailingPrimary()
    primary.provider_name = "qwen_local"
    fallback = PassingFallback()
    fallback.provider_name = "vintern_reasoning_local"
    client = ExclusiveLocalFallbackClient(
        primary,
        fallback,
        telemetry_callback=lambda payload: telemetry.append(dict(payload)),
    )

    assert client.request(request) == {"value": "ok"}
    assert client.request(request) == {"value": "ok"}
    assert primary_calls == 1
    assert fallback_calls == 2
    assert client.circuit_open is True
    assert resident == ["vintern"]
    assert telemetry == [
        {
            "status": "semantic_fallback_activated",
            "event_kind": "lifecycle",
            "provider": "vintern_reasoning_local",
        }
    ]
    assert client.report_telemetry() == {
        "qwen_request_count": 1,
        "vintern_fallback_request_count": 2,
        "fallback_request_count": 2,
        "fallback_activation_count": 1,
    }

    client.close()
    assert resident == []
    assert primary_close_calls == 1


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

    request = ModelRequest(
        request_kind="test",
        video_id="L21_V001",
        prompt="return json",
        prompt_version="test_prompt",
        response_schema_version="test_schema",
        response_schema={},
        image_paths=(Path("missing.jpg"),),
    )

    with pytest.raises(RuntimeError, match="second"):
        ExclusiveLocalFallbackClient(
            FailingClient("first"), FailingClient("second")
        ).request(request)


def test_local_vlm_adaptive_oom_reduces_to_one(monkeypatch) -> None:
    lifecycle: list[dict[str, object]] = []
    releases: list[str] = []
    calls = 0
    client = LocalVisionStructuredClient(
        model_config={
            "provider": "qwen_local",
            "model_id": "Qwen/Qwen2.5-VL-7B-Instruct",
            "model_revision": "test",
            "total_attempts": 2,
            "inference_batch_size": 2,
        },
        lifecycle_callback=lambda payload: lifecycle.append(dict(payload)),
    )

    def call_models(requests) -> list[str]:
        nonlocal calls
        calls += 1
        if len(requests) > 1:
            raise RuntimeError("CUDA out of memory")
        return ['{"value": "ok"}']

    monkeypatch.setattr(client, "_call_models", call_models)
    monkeypatch.setattr(
        "system1.vlm.client._release_torch_memory",
        lambda: releases.append("released"),
    )
    request = ModelRequest(
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

    response = client.request_many([request, request])

    assert [item["value"] for item in response] == ["ok", "ok"]
    assert calls == 3
    assert releases == ["released"]
    assert [event["status"] for event in lifecycle] == [
        "batch_start",
        "oom_reduction",
        "batch_complete",
    ]
    assert lifecycle[1]["effective_batch_size"] == 1


def test_local_vlm_rejects_non_positive_inference_batching() -> None:
    with pytest.raises(ValueError, match="inference_batch_size must be positive"):
        LocalVisionStructuredClient(
            model_config={
                "provider": "qwen_local",
                "model_id": "Qwen/Qwen2.5-VL-7B-Instruct",
                "inference_batch_size": 0,
            }
        )


def test_two_qwen_requests_use_one_model_generate(
    tmp_path: Path, monkeypatch
) -> None:
    structured_prompts: list[str] = []

    class FakeTensor:
        shape = (2, 3)

        def to(self, _device):
            return self

        def __getitem__(self, _item):
            return self

    class FakeProcessor:
        def apply_chat_template(self, conversation, **_kwargs):
            structured_prompts.append(conversation[0]["content"][-1]["text"])
            return "prompt"

        def __call__(self, *, text, **_kwargs):
            assert len(text) == 2
            return {"input_ids": FakeTensor()}

        def batch_decode(self, _generated, **_kwargs):
            return ['{"value": "first"}', '{"value": "second"}']

    class FakeModel:
        generate_calls = 0

        def parameters(self):
            return iter([SimpleNamespace(device="cpu")])

        def generate(self, **_kwargs):
            self.generate_calls += 1
            return FakeTensor()

    model = FakeModel()
    client = LocalVisionStructuredClient(
        model_config={
            "provider": "qwen_local",
            "model_id": "Qwen/Qwen2.5-VL-7B-Instruct",
            "model_revision": "test",
            "inference_batch_size": 2,
        }
    )
    monkeypatch.setattr(client, "_load_qwen", lambda: (FakeProcessor(), model))
    qwen_utils = ModuleType("qwen_vl_utils")
    qwen_utils.process_vision_info = (  # type: ignore[attr-defined]
        lambda conversations: ([object() for _ in conversations], None)
    )
    monkeypatch.setitem(sys.modules, "qwen_vl_utils", qwen_utils)
    images = [tmp_path / "first.jpg", tmp_path / "second.jpg"]
    for image in images:
        image.write_bytes(image.name.encode())
    schema = {
        "type": "object",
        "properties": {"value": {"type": "string"}},
        "required": ["value"],
        "additionalProperties": False,
    }
    requests = [
        ModelRequest(
            request_kind="shot_caption",
            video_id="L21_V001",
            prompt=f"prompt {index}",
            prompt_version="test_prompt",
            response_schema_version="test_schema",
            response_schema=schema,
            image_paths=(image,),
        )
        for index, image in enumerate(images)
    ]

    responses = client.request_many(requests)

    assert [response["value"] for response in responses] == ["first", "second"]
    assert model.generate_calls == 1
    assert all("OUTPUT CONTRACT:" in prompt for prompt in structured_prompts)
    assert all('"type":"object"' in prompt for prompt in structured_prompts)


def test_qwen_text_mode_does_not_inject_json_contract_and_wraps_response(
    tmp_path: Path, monkeypatch
) -> None:
    prompts: list[str] = []

    class FakeTensor:
        shape = (1, 2)

        def to(self, _device):
            return self

        def __getitem__(self, _item):
            return self

    class FakeProcessor:
        def apply_chat_template(self, conversation, **_kwargs):
            prompts.append(conversation[0]["content"][-1]["text"])
            return "prompt"

        def __call__(self, **_kwargs):
            return {"input_ids": FakeTensor()}

        def batch_decode(self, _generated, **_kwargs):
            return ["  plain semantic answer  "]

    class FakeModel:
        def parameters(self):
            return iter([SimpleNamespace(device="cpu")])

        def generate(self, **_kwargs):
            return FakeTensor()

    client = LocalVisionStructuredClient(
        model_config={
            "provider": "qwen_local",
            "model_id": "qwen",
            "model_revision": "revision",
            "inference_batch_size": 1,
        }
    )
    monkeypatch.setattr(client, "_load_qwen", lambda: (FakeProcessor(), FakeModel()))
    qwen_utils = ModuleType("qwen_vl_utils")
    qwen_utils.process_vision_info = lambda _conversations: ([], None)  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "qwen_vl_utils", qwen_utils)
    image = tmp_path / "frame.jpg"
    image.write_bytes(b"fixture")
    request = ModelRequest(
        request_kind="shot_caption_caption_en",
        video_id="L21_V001",
        prompt="Describe the image in English.",
        prompt_version="shot_caption_en_v1",
        response_schema_version="plain_text_response_v1",
        response_schema=TEXT_RESPONSE_SCHEMA,
        image_paths=(image,),
        response_mode="text",
    )

    response = client.request(request)

    assert prompts == ["Describe the image in English."]
    assert "OUTPUT CONTRACT:" not in prompts[0]
    assert response["text"] == "plain semantic answer"


def test_request_many_preserves_order_and_only_batches_cache_misses(
    tmp_path: Path, monkeypatch
) -> None:
    cache = ArtifactStore(tmp_path / "cache")
    calls: list[list[str]] = []
    client = LocalVisionStructuredClient(
        model_config={
            "provider": "qwen_local",
            "model_id": "model",
            "model_revision": "revision",
            "inference_batch_size": 2,
        },
        cache=cache,
    )

    def call_models(requests):
        calls.append([request.prompt for request in requests])
        return [f'{{"value": "{request.prompt}"}}' for request in requests]

    monkeypatch.setattr(client, "_call_models", call_models)
    schema = {
        "type": "object",
        "properties": {"value": {"type": "string"}},
        "required": ["value"],
        "additionalProperties": False,
    }

    def make_request(prompt: str) -> ModelRequest:
        return ModelRequest(
            request_kind="shot_caption",
            video_id="L21_V001",
            prompt=prompt,
            prompt_version="prompt",
            response_schema_version="schema",
            response_schema=schema,
        )

    cached, missing = make_request("cached"), make_request("missing")
    assert client.request(cached)["value"] == "cached"
    calls.clear()

    responses = client.request_many([missing, cached])

    assert [response["value"] for response in responses] == ["missing", "cached"]
    assert calls == [["missing"]]


def test_qwen_loader_passes_explicit_nf4_quantization(monkeypatch) -> None:
    captured = {}
    _install_fake_torch(monkeypatch)

    class FakeBitsAndBytesConfig:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class FakeProcessor:
        def __init__(self):
            self.tokenizer = SimpleNamespace(padding_side="right")

    class FakeProcessorFactory:
        @staticmethod
        def from_pretrained(*_args, **_kwargs):
            return FakeProcessor()

    class FakeModel:
        def eval(self):
            return None

    class FakeModelFactory:
        @staticmethod
        def from_pretrained(*_args, **kwargs):
            captured.update(kwargs)
            return FakeModel()

    transformers = ModuleType("transformers")
    transformers.AutoProcessor = FakeProcessorFactory
    transformers.BitsAndBytesConfig = FakeBitsAndBytesConfig
    transformers.Qwen2_5_VLForConditionalGeneration = FakeModelFactory
    monkeypatch.setitem(sys.modules, "transformers", transformers)
    client = LocalVisionStructuredClient(
        model_config={
            "provider": "qwen_local",
            "model_id": "Qwen/Qwen2.5-VL-7B-Instruct",
            "model_revision": "revision",
            "torch_dtype": "float16",
            "device_map": "cuda",
            "quantization": {
                "method": "bitsandbytes",
                "mode": "4bit",
                "quant_type": "nf4",
                "compute_dtype": "float16",
                "double_quant": True,
            },
        }
    )

    client._load_qwen()

    quantization = captured["quantization_config"]
    assert quantization.kwargs["load_in_4bit"] is True
    assert quantization.kwargs["bnb_4bit_quant_type"] == "nf4"
    assert quantization.kwargs["bnb_4bit_use_double_quant"] is True
    assert str(quantization.kwargs["bnb_4bit_compute_dtype"]) == "torch.float16"
    assert captured["device_map"] == "cuda"


@pytest.mark.parametrize("offload_device", ["cpu", "disk"])
def test_qwen_loader_rejects_cpu_or_disk_offload(
    monkeypatch, offload_device: str
) -> None:
    _install_fake_torch(monkeypatch)

    class FakeBitsAndBytesConfig:
        def __init__(self, **_kwargs):
            pass

    class FakeProcessor:
        def __init__(self):
            self.tokenizer = SimpleNamespace(padding_side="right")

    class FakeProcessorFactory:
        @staticmethod
        def from_pretrained(*_args, **_kwargs):
            return FakeProcessor()

    class FakeModel:
        def __init__(self) -> None:
            self.hf_device_map = {"vision": 0, "language": offload_device}

        def eval(self):
            return None

    class FakeModelFactory:
        @staticmethod
        def from_pretrained(*_args, **_kwargs):
            return FakeModel()

    transformers = ModuleType("transformers")
    transformers.AutoProcessor = FakeProcessorFactory
    transformers.BitsAndBytesConfig = FakeBitsAndBytesConfig
    transformers.Qwen2_5_VLForConditionalGeneration = FakeModelFactory
    monkeypatch.setitem(sys.modules, "transformers", transformers)
    client = LocalVisionStructuredClient(
        model_config={
            "provider": "qwen_local",
            "model_id": "Qwen/Qwen2.5-VL-7B-Instruct",
            "model_revision": "revision",
            "torch_dtype": "float16",
            "device_map": "cuda",
            "quantization": {
                "method": "bitsandbytes",
                "mode": "4bit",
                "quant_type": "nf4",
                "compute_dtype": "float16",
                "double_quant": True,
            },
        }
    )

    with pytest.raises(SystemicProviderError, match="CPU/disk offload is forbidden"):
        client._load_qwen()

    assert client._loaded is None


@pytest.mark.parametrize("offload_device", ["cpu", "disk"])
def test_vintern_loader_rejects_cpu_or_disk_offload(
    monkeypatch, offload_device: str
) -> None:
    _install_fake_torch(monkeypatch)

    class FakeTokenizerFactory:
        @staticmethod
        def from_pretrained(*_args, **_kwargs):
            return object()

    class FakeModel:
        def __init__(self) -> None:
            self.hf_device_map = {"vision": 0, "language": offload_device}

        def eval(self):
            return None

    class FakeModelFactory:
        @staticmethod
        def from_pretrained(*_args, **_kwargs):
            return FakeModel()

    transformers = ModuleType("transformers")
    transformers.AutoTokenizer = FakeTokenizerFactory
    transformers.AutoModel = FakeModelFactory
    monkeypatch.setitem(sys.modules, "transformers", transformers)
    client = LocalVisionStructuredClient(
        model_config={
            "provider": "vintern_local",
            "model_id": "5CD-AI/Vintern-1B-v3_5",
            "model_revision": "revision",
            "device_map": "auto",
        }
    )

    with pytest.raises(
        SystemicProviderError,
        match="vintern_local CPU/disk offload is forbidden",
    ):
        client._load_vintern()

    assert client._loaded is None


def test_local_vlm_pre_load_guard_blocks_before_model_factory(monkeypatch) -> None:
    calls = []
    client = LocalVisionStructuredClient(
        model_config={
            "provider": "qwen_local",
            "model_id": "qwen",
            "model_revision": "revision",
        },
        pre_load_callback=lambda provider: (_ for _ in ()).throw(
            RuntimeError(f"blocked:{provider}")
        ),
        lifecycle_callback=lambda payload: calls.append(dict(payload)),
    )

    with pytest.raises(SystemicProviderError, match="pre-load guard failed"):
        client._load_qwen()

    assert client._loaded is None
    assert calls[-1]["status"] == "load_blocked"


def test_vintern_plain_text_ocr_uses_native_batch_chat(
    tmp_path: Path, monkeypatch
) -> None:
    torch = _install_fake_torch(monkeypatch)

    class FakeTokenizer:
        pass

    class FakeModel:
        batch_calls = 0

        def parameters(self):
            return iter([SimpleNamespace(device="cpu", dtype=torch.float32)])

        def batch_chat(
            self,
            _tokenizer,
            _pixels,
            questions,
            _generation_config,
            **_kwargs,
        ):
            self.batch_calls += 1
            assert all("OUTPUT CONTRACT:" not in question for question in questions)
            assert all("JSON Schema:" not in question for question in questions)
            return ["HTV9\n08:20:19", "<NO_TEXT>"]

    model = FakeModel()
    client = LocalVisionStructuredClient(
        model_config={
            "provider": "vintern_local",
            "model_id": "vintern",
            "model_revision": "revision",
            "inference_batch_size": 2,
            "structured_output_contract_version": "vintern_plain_text_ocr_v1",
        }
    )
    monkeypatch.setattr(client, "_load_vintern", lambda: (FakeTokenizer(), model))
    monkeypatch.setattr(
        "system1.vlm.client._vintern_pixel_values",
        lambda _path: _FakeTensor(),
    )
    schema = {
        "type": "object",
        "properties": {
            "full_text": {"type": "string"},
            "ocr_blocks": {"type": "array"},
            "language": {"type": "string"},
            "confidence": {"type": ["number", "null"]},
        },
        "required": ["full_text", "ocr_blocks"],
        "additionalProperties": False,
    }
    requests = []
    for index in range(2):
        image = tmp_path / f"image_{index}.jpg"
        image.write_bytes(b"image")
        requests.append(
            ModelRequest(
                request_kind="keyframe_ocr",
                video_id="L21_V001",
                prompt="Read visible text only.",
                prompt_version="keyframe_ocr_v3",
                response_schema_version="keyframe_ocr_response_v1",
                response_schema=schema,
                image_paths=(image,),
            )
        )

    responses = client.request_many(requests)

    assert model.batch_calls == 1
    assert responses[0]["full_text"] == "HTV9\n08:20:19"
    assert responses[0]["ocr_blocks"] == []
    assert responses[0]["language"] == "vi"
    assert responses[0]["confidence"] is None
    assert responses[1]["full_text"] == ""
    assert responses[1]["ocr_blocks"] == []


def test_local_vlm_cache_identity_includes_structured_output_contract() -> None:
    request = ModelRequest(
        request_kind="test",
        video_id="L21_V001",
        prompt="return json",
        prompt_version="prompt",
        response_schema_version="schema",
        response_schema={"type": "object"},
    )
    first = LocalVisionStructuredClient(
        model_config={
            "provider": "vintern_local",
            "model_id": "vintern",
            "model_revision": "revision",
            "structured_output_contract_version": "json_schema_prompt_v1",
        }
    )
    second = LocalVisionStructuredClient(
        model_config={
            "provider": "vintern_local",
            "model_id": "vintern",
            "model_revision": "revision",
            "structured_output_contract_version": "json_schema_prompt_v2",
        }
    )

    assert first._request_hash(request) != second._request_hash(request)


def test_structured_parse_error_telemetry_is_bounded(monkeypatch) -> None:
    lifecycle = []
    client = LocalVisionStructuredClient(
        model_config={
            "provider": "vintern_local",
            "model_id": "vintern",
            "model_revision": "revision",
            "inference_batch_size": 4,
        },
        lifecycle_callback=lambda payload: lifecycle.append(dict(payload)),
    )
    monkeypatch.setattr(
        client,
        "_call_models",
        lambda requests: [f"not-json-{index}" for index, _request in enumerate(requests)],
    )
    request = ModelRequest(
        request_kind="keyframe_ocr",
        video_id="L21_V001",
        prompt="ocr",
        prompt_version="prompt",
        response_schema_version="schema",
        response_schema={"type": "object"},
    )

    with pytest.raises(BatchRequestError):
        client.request_many([request, request, request, request])

    parse_errors = [
        event for event in lifecycle if event["status"] == "response_parse_error"
    ]
    assert len(parse_errors) == 3
    assert parse_errors[0]["request_kind"] == "keyframe_ocr"
    assert parse_errors[0]["error_type"] == "JSONDecodeError"
    assert parse_errors[0]["raw_response_preview"] == "not-json-0"


def test_vintern_without_native_batch_safely_uses_one_request(
    tmp_path: Path, monkeypatch
) -> None:
    torch = _install_fake_torch(monkeypatch)

    lifecycle = []

    class FakeModel:
        chat_calls = 0

        def parameters(self):
            return iter([SimpleNamespace(device="cpu", dtype=torch.float32)])

        def chat(self, _tokenizer, _pixels, prompt, _generation_config):
            self.chat_calls += 1
            return f'{{"value": "{prompt[-1]}"}}'

    model = FakeModel()
    client = LocalVisionStructuredClient(
        model_config={
            "provider": "vintern_local",
            "model_id": "vintern",
            "model_revision": "revision",
            "inference_batch_size": 2,
        },
        lifecycle_callback=lambda payload: lifecycle.append(dict(payload)),
    )
    monkeypatch.setattr(client, "_load_vintern", lambda: (object(), model))
    monkeypatch.setattr(
        "system1.vlm.client._vintern_pixel_values",
        lambda _path: _FakeTensor(),
    )

    responses = client.request_many(_image_requests(tmp_path, prompts=["a", "b"]))

    assert len(responses) == 2
    assert model.chat_calls == 2
    assert any(
        event["status"] == "batch_capability_fallback"
        and event["effective_batch_size"] == 1
        for event in lifecycle
    )


def _image_requests(tmp_path: Path, *, prompts: list[str]) -> list[ModelRequest]:
    schema = {
        "type": "object",
        "properties": {"value": {"type": "string"}},
        "required": ["value"],
        "additionalProperties": False,
    }
    requests = []
    for index, prompt in enumerate(prompts):
        image = tmp_path / f"image_{index}.jpg"
        image.write_bytes(prompt.encode())
        requests.append(
            ModelRequest(
                request_kind="keyframe_ocr",
                video_id="L21_V001",
                prompt=prompt,
                prompt_version="prompt",
                response_schema_version="schema",
                response_schema=schema,
                image_paths=(image,),
            )
        )
    return requests


def test_invalid_json_falls_back_only_failed_request_then_stays_on_fallback(
    monkeypatch,
) -> None:
    calls = []
    primary = LocalVisionStructuredClient(
        model_config={
            "provider": "qwen_local",
            "model_id": "qwen",
            "model_revision": "revision",
            "inference_batch_size": 2,
        }
    )

    def call_models(requests):
        calls.append([request.prompt for request in requests])
        return [
            '{"value": "primary"}' if request.prompt != "bad" else "not-json"
            for request in requests
        ]

    monkeypatch.setattr(primary, "_call_models", call_models)

    class VinternFallback:
        provider_name = "vintern_reasoning_local"

        def request(self, request):
            return {"value": f"fallback:{request.prompt}"}

    schema = {
        "type": "object",
        "properties": {"value": {"type": "string"}},
        "required": ["value"],
        "additionalProperties": False,
    }

    def make_request(prompt):
        return ModelRequest(
            request_kind="shot_caption",
            video_id="L21_V001",
            prompt=prompt,
            prompt_version="prompt",
            response_schema_version="schema",
            response_schema=schema,
        )

    client = ExclusiveLocalFallbackClient(primary, VinternFallback())
    responses = client.request_many([make_request("good"), make_request("bad")])
    next_response = client.request(make_request("next"))

    assert [response["value"] for response in responses] == [
        "primary",
        "fallback:bad",
    ]
    assert next_response["value"] == "fallback:next"
    assert client.circuit_open is True
    assert calls == [["good", "bad"]]


def test_batch_call_error_isolates_failure_then_stays_on_fallback(
    monkeypatch,
) -> None:
    calls: list[list[str]] = []
    primary = LocalVisionStructuredClient(
        model_config={
            "provider": "qwen_local",
            "model_id": "qwen",
            "model_revision": "revision",
            "inference_batch_size": 2,
        }
    )

    def call_models(requests):
        prompts = [request.prompt for request in requests]
        calls.append(prompts)
        if len(requests) > 1:
            raise ValueError("one request cannot be processed in this batch")
        if prompts == ["bad"]:
            raise ValueError("bad request")
        return ['{"value": "primary"}']

    monkeypatch.setattr(primary, "_call_models", call_models)

    class VinternFallback:
        provider_name = "vintern_reasoning_local"

        def request(self, request):
            return {"value": f"fallback:{request.prompt}"}

    schema = {
        "type": "object",
        "properties": {"value": {"type": "string"}},
        "required": ["value"],
        "additionalProperties": False,
    }

    def make_request(prompt):
        return ModelRequest(
            request_kind="shot_caption",
            video_id="L21_V001",
            prompt=prompt,
            prompt_version="prompt",
            response_schema_version="schema",
            response_schema=schema,
        )

    client = ExclusiveLocalFallbackClient(primary, VinternFallback())
    responses = client.request_many([make_request("good"), make_request("bad")])
    next_response = client.request(make_request("next"))

    assert [response["value"] for response in responses] == [
        "primary",
        "fallback:bad",
    ]
    assert next_response["value"] == "fallback:next"
    assert client.circuit_open is True
    assert calls == [["good", "bad"], ["good"], ["bad"]]


def test_multi_image_oom_reduces_evidence_evenly_before_circuit(
    tmp_path: Path, monkeypatch
) -> None:
    lifecycle: list[dict[str, object]] = []
    image_counts: list[int] = []
    final_images: list[Path] = []
    client = LocalVisionStructuredClient(
        model_config={
            "provider": "qwen_local",
            "model_id": "qwen",
            "model_revision": "revision",
            "inference_batch_size": 1,
            "total_attempts": 2,
        },
        lifecycle_callback=lambda payload: lifecycle.append(dict(payload)),
    )
    images = tuple(tmp_path / f"image_{index:02d}.jpg" for index in range(12))
    for image in images:
        image.write_bytes(image.name.encode())

    def call_models(requests):
        image_counts.append(len(requests[0].image_paths))
        if len(requests[0].image_paths) > 3:
            raise RuntimeError("CUDA out of memory")
        final_images.extend(requests[0].image_paths)
        return ['{"value": "local"}']

    monkeypatch.setattr(client, "_call_models", call_models)
    monkeypatch.setattr("system1.vlm.client._release_torch_memory", lambda: None)
    request = ModelRequest(
        request_kind="scene_summary",
        video_id="L21_V001",
        prompt="summary",
        prompt_version="prompt",
        response_schema_version="schema",
        response_schema={
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
            "additionalProperties": False,
        },
        image_paths=images,
    )

    response = client.request(request)

    assert response["value"] == "local"
    assert image_counts == [12, 6, 3]
    assert final_images[0] == images[0]
    assert final_images[-1] == images[-1]
    reductions = [
        event for event in lifecycle if event["status"] == "image_oom_reduction"
    ]
    assert [event["effective_image_count"] for event in reductions] == [6, 3]


def test_repeated_batch_one_oom_opens_circuit_and_uses_vintern(monkeypatch) -> None:
    attempts = 0
    primary = LocalVisionStructuredClient(
        model_config={
            "provider": "qwen_local",
            "model_id": "qwen",
            "model_revision": "revision",
            "inference_batch_size": 1,
            "total_attempts": 2,
        }
    )

    def oom(_requests):
        nonlocal attempts
        attempts += 1
        raise RuntimeError("CUDA out of memory")

    monkeypatch.setattr(primary, "_call_models", oom)

    class VinternFallback:
        provider_name = "vintern_reasoning_local"

        def request(self, _request):
            return {"value": "fallback"}

    request = ModelRequest(
        request_kind="scene_summary",
        video_id="L21_V001",
        prompt="summary",
        prompt_version="prompt",
        response_schema_version="schema",
        response_schema={
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
            "additionalProperties": False,
        },
    )
    client = ExclusiveLocalFallbackClient(primary, VinternFallback())

    response = client.request(request)

    assert response == {"value": "fallback"}
    assert attempts == 2
    assert client.circuit_open is True

def test_qwen_loader_sets_left_padding(monkeypatch) -> None:
    _install_fake_torch(monkeypatch)

    captured: dict[str, object] = {}

    class FakeBitsAndBytesConfig:
        def __init__(self, **_kwargs):
            pass

    class FakeProcessor:
        def __init__(self) -> None:
            self.tokenizer = SimpleNamespace(
                padding_side="right"
            )

    class FakeProcessorFactory:
        @staticmethod
        def from_pretrained(*_args, **_kwargs):
            processor = FakeProcessor()
            captured["processor"] = processor
            return processor

    class FakeModel:
        def eval(self):
            return None

    class FakeModelFactory:
        @staticmethod
        def from_pretrained(*_args, **_kwargs):
            return FakeModel()

    transformers = ModuleType("transformers")
    transformers.AutoProcessor = FakeProcessorFactory
    transformers.BitsAndBytesConfig = (
        FakeBitsAndBytesConfig
    )
    transformers.Qwen2_5_VLForConditionalGeneration = (
        FakeModelFactory
    )

    monkeypatch.setitem(
        sys.modules,
        "transformers",
        transformers,
    )

    client = LocalVisionStructuredClient(
        model_config={
            "provider": "qwen_local",
            "model_id": (
                "Qwen/Qwen2.5-VL-7B-Instruct"
            ),
            "model_revision": "revision",
            "torch_dtype": "float16",
            "device_map": "cuda",
            "padding_side": "left",
            "quantization": {
                "method": "bitsandbytes",
                "mode": "4bit",
                "quant_type": "nf4",
                "compute_dtype": "float16",
                "double_quant": True,
            },
        }
    )

    client._load_qwen()

    processor = captured["processor"]

    assert processor.tokenizer.padding_side == "left"

def test_qwen_cache_identity_includes_padding_side() -> None:
    client_left = LocalVisionStructuredClient(
        model_config={
            "provider": "qwen_local",
            "model_id": "qwen",
            "model_revision": "revision",
            "padding_side": "left",
        }
    )
    client_right = LocalVisionStructuredClient(
        model_config={
            "provider": "qwen_local",
            "model_id": "qwen",
            "model_revision": "revision",
            "padding_side": "right",
        }
    )
    request = ModelRequest(
        request_kind="test",
        video_id="video",
        prompt="prompt",
        prompt_version="1",
        response_schema_version="1",
        response_schema={},
    )
    hash_left = client_left._request_hash(request)
    hash_right = client_right._request_hash(request)
    assert hash_left != hash_right


def test_vintern_reasoning_loader_uses_pinned_revision(monkeypatch) -> None:
    captured: dict[str, dict[str, object]] = {}

    class FakeFactory:
        def __init__(self, key: str, value: object) -> None:
            self.key = key
            self.value = value

        def from_pretrained(self, _model_id, **kwargs):
            captured[self.key] = kwargs
            return self.value

    class FakeModel:
        def eval(self):
            return self

        def cuda(self):
            return self

    transformers = ModuleType("transformers")
    transformers.AutoTokenizer = FakeFactory("tokenizer", object())  # type: ignore[attr-defined]
    transformers.AutoModel = FakeFactory("model", FakeModel())  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "transformers", transformers)
    monkeypatch.setattr("system1.vlm.client._reset_cuda_peak_memory", lambda: None)
    revision = "4fd34d713dfca446cdecc00d921f5038909e3efb"
    client = LocalVisionStructuredClient(
        model_config={
            "provider": "vintern_reasoning_local",
            "model_id": "5CD-AI/Vintern-3B-R-beta",
            "model_revision": revision,
            "torch_dtype": "float16",
            "trust_remote_code": True,
            "use_fast_tokenizer": False,
            "use_flash_attn": False,
        }
    )

    client._load_vintern_reasoning()

    assert captured["tokenizer"]["revision"] == revision
    assert captured["model"]["revision"] == revision


def test_vintern_reasoning_dynamic_tiles_include_global_thumbnail() -> None:
    image = Image.new("RGB", (1600, 500), "white")

    tiles = split_dynamic_tiles(
        image,
        image_size=448,
        max_tiles=6,
        use_thumbnail=True,
    )

    assert 2 <= len(tiles) <= 7
    assert all(tile.size == (448, 448) for tile in tiles)


def test_vintern_reasoning_reduces_patch_count_on_oom(
    tmp_path: Path, monkeypatch
) -> None:
    patch_limits: list[int] = []
    lifecycle: list[dict[str, object]] = []

    class FakeTensor:
        def to(self, *_args, **_kwargs):
            return self

    class FakeModel:
        calls = 0

        def parameters(self):
            return iter([SimpleNamespace(device="cuda", dtype="float16")])

        def chat(self, *_args, **_kwargs):
            self.calls += 1
            if self.calls < 3:
                raise RuntimeError("CUDA out of memory")
            return "semantic answer"

    def load_image(_path, *, max_tiles, **_kwargs):
        patch_limits.append(max_tiles)
        return FakeTensor()

    client = LocalVisionStructuredClient(
        model_config={
            "provider": "vintern_reasoning_local",
            "model_id": "vintern",
            "model_revision": "revision",
            "max_dynamic_patches": 6,
            "image_size": 448,
            "use_thumbnail": True,
        },
        lifecycle_callback=lambda payload: lifecycle.append(dict(payload)),
    )
    model = FakeModel()
    monkeypatch.setattr(client, "_load_vintern_reasoning", lambda: (object(), model))
    monkeypatch.setattr(
        "system1.vlm.vintern_reasoning.load_vintern_reasoning_image", load_image
    )
    monkeypatch.setattr("system1.vlm.client._release_torch_memory", lambda: None)
    image = tmp_path / "fallback.jpg"
    image.write_bytes(b"fixture")
    request = ModelRequest(
        request_kind="scene_summary_vi",
        video_id="L21_V001",
        prompt="summarize",
        prompt_version="scene_summary_vi_v2",
        response_schema_version="plain_text_response_v1",
        response_schema=TEXT_RESPONSE_SCHEMA,
        image_paths=(image,),
        response_mode="text",
    )

    assert client.request(request)["text"] == "semantic answer"
    assert patch_limits == [6, 4, 2]
    assert [
        event["effective_patch_limit"]
        for event in lifecycle
        if event["status"] == "vintern_patch_oom_reduction"
    ] == [4, 2]


def test_vintern_fallback_uses_single_fallback_image(tmp_path: Path) -> None:
    received: list[tuple[Path, ...]] = []

    class FailingPrimary:
        def request(self, _request):
            raise RuntimeError("primary failed")

    class RecordingFallback:
        provider_name = "vintern_reasoning_local"

        def request(self, request):
            received.append(request.image_paths)
            return {"text": "fallback"}

    source_images = tuple(tmp_path / f"source-{index}.jpg" for index in range(3))
    fallback_image = tmp_path / "fallback.jpg"
    request = ModelRequest(
        request_kind="scene_summary_vi",
        video_id="L21_V001",
        prompt="summarize",
        prompt_version="scene_summary_vi_v2",
        response_schema_version="plain_text_response_v1",
        response_schema=TEXT_RESPONSE_SCHEMA,
        image_paths=source_images,
        fallback_image_paths=(fallback_image,),
        response_mode="text",
    )

    response = ExclusiveLocalFallbackClient(
        FailingPrimary(), RecordingFallback()
    ).request(request)

    assert response == {"text": "fallback"}
    assert received == [(fallback_image,)]
