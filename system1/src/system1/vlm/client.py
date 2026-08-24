from __future__ import annotations

import gc
import json
import re
import threading
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Protocol

import numpy as np
from jsonschema import validate
from PIL import Image

from system1.gemini import GeminiRequest, build_request_hash


class JsonCache(Protocol):
    def exists(self, relative_path: str | Path) -> bool: ...

    def read_json(self, relative_path: str | Path) -> dict[str, Any]: ...

    def write_json(self, relative_path: str | Path, payload: dict[str, Any]) -> Path: ...


class StructuredClient(Protocol):
    def request(self, request: GeminiRequest) -> dict[str, Any]: ...


class MetadataStructuredClient:
    def __init__(
        self,
        client: StructuredClient,
        *,
        provider_name: str,
        model_id: str,
        model_revision: str,
    ) -> None:
        self.client = client
        self.provider_name = provider_name
        self.model_id = model_id
        self.model_revision = model_revision

    def request(self, request: GeminiRequest) -> dict[str, Any]:
        payload = dict(self.client.request(request))
        payload.setdefault("__provider", self.provider_name)
        payload.setdefault("__model_id", self.model_id)
        payload.setdefault("__model_revision", self.model_revision)
        return payload

    def close(self) -> None:
        _close_client(self.client)


class FallbackStructuredClient:
    def __init__(self, clients: list[StructuredClient]) -> None:
        if not clients:
            raise ValueError("at least one structured client is required")
        self.clients = clients

    def request(self, request: GeminiRequest) -> dict[str, Any]:
        errors: list[str] = []
        for client in self.clients:
            try:
                return client.request(request)
            except Exception as exc:  # noqa: BLE001 - preserve fallback behavior
                errors.append(f"{type(exc).__name__}: {exc}")
                _close_client(client)
                _release_torch_memory()
        raise RuntimeError("all structured providers failed: " + " | ".join(errors))

    def close(self) -> None:
        for client in self.clients:
            _close_client(client)
        _release_torch_memory()


class LocalVisionStructuredClient:
    def __init__(
        self,
        *,
        model_config: Mapping[str, Any],
        cache: JsonCache | None = None,
        cache_prefix: str | Path = "cache/local_vlm",
    ) -> None:
        self.model_config = dict(model_config)
        self.provider_name = str(self.model_config["provider"])
        self.model_id = str(self.model_config["model_id"])
        self.model_revision = str(self.model_config.get("model_revision") or self.model_id)
        self.cache = cache
        self.cache_prefix = Path(cache_prefix)
        self._cache_lock = threading.Lock()
        self._model_lock = threading.Lock()
        self._loaded: tuple[Any, ...] | None = None

    def request(self, request: GeminiRequest) -> dict[str, Any]:
        request_hash = build_request_hash(
            request,
            model_id=self.model_id,
            cache_identity={
                "provider": self.provider_name,
                "model_revision": self.model_revision,
                "max_new_tokens": self.model_config.get("max_new_tokens"),
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
                        return self._with_metadata(response)

        raw_text = self._call_model(request)
        normalized = _parse_json_object(raw_text, request.response_schema)
        if self.cache is not None:
            with self._cache_lock:
                self.cache.write_json(
                    cache_path,
                    {
                        "schema_version": "local_vlm_cache_entry_v1",
                        "request_hash": request_hash,
                        "request_kind": request.request_kind,
                        "video_id": request.video_id,
                        "provider": self.provider_name,
                        "model_id": self.model_id,
                        "model_revision": self.model_revision,
                        "prompt_version": request.prompt_version,
                        "response_schema_version": request.response_schema_version,
                        "normalized_response": normalized,
                    },
                )
        return self._with_metadata(normalized)

    def _with_metadata(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        response = dict(payload)
        response["__provider"] = self.provider_name
        response["__model_id"] = self.model_id
        response["__model_revision"] = self.model_revision
        return response

    def _call_model(self, request: GeminiRequest) -> str:
        if self.provider_name == "qwen_local":
            return self._call_qwen(request)
        if self.provider_name == "vintern_local":
            return self._call_vintern(request)
        raise RuntimeError(f"unsupported local VLM provider: {self.provider_name}")

    def _call_qwen(self, request: GeminiRequest) -> str:
        processor, model = self._load_qwen()
        try:
            from qwen_vl_utils import process_vision_info
        except ImportError as exc:  # pragma: no cover - production dependency guard
            raise RuntimeError("qwen-vl-utils is required for qwen_local") from exc

        messages = [
            {
                "role": "user",
                "content": [
                    *[
                        {"type": "image", "image": str(path)}
                        for path in request.image_paths
                    ],
                    {"type": "text", "text": request.prompt},
                ],
            }
        ]
        text = processor.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        image_inputs, video_inputs = process_vision_info(messages)
        inputs = processor(
            text=[text],
            images=image_inputs,
            videos=video_inputs,
            padding=True,
            return_tensors="pt",
        )
        device = _model_device(model)
        inputs = {
            key: value.to(device) if hasattr(value, "to") else value
            for key, value in inputs.items()
        }
        generated_ids = model.generate(
            **inputs,
            max_new_tokens=int(self.model_config.get("max_new_tokens", 768)),
            do_sample=False,
        )
        input_ids = inputs.get("input_ids")
        if input_ids is not None:
            generated_ids = generated_ids[:, input_ids.shape[1] :]
        return processor.batch_decode(
            generated_ids, skip_special_tokens=True, clean_up_tokenization_spaces=False
        )[0]

    def _call_vintern(self, request: GeminiRequest) -> str:
        if len(request.image_paths) != 1:
            raise RuntimeError("vintern_local expects exactly one image per request")
        tokenizer, model = self._load_vintern()
        import torch

        pixel_values = _vintern_pixel_values(request.image_paths[0]).to(_model_device(model))
        try:
            dtype = next(model.parameters()).dtype
            pixel_values = pixel_values.to(dtype=dtype)
        except StopIteration:  # pragma: no cover
            pass
        prompt = request.prompt
        if "<image>" not in prompt:
            prompt = "<image>\n" + prompt
        generation_config = {
            "max_new_tokens": int(self.model_config.get("max_new_tokens", 768)),
            "do_sample": False,
        }
        with torch.no_grad():
            output = model.chat(tokenizer, pixel_values, prompt, generation_config)
        if isinstance(output, tuple):
            output = output[0]
        if not isinstance(output, str) or not output.strip():
            raise ValueError("vintern_local returned an empty response")
        return output

    def _load_qwen(self) -> tuple[Any, Any]:
        with self._model_lock:
            if self._loaded is not None:
                return self._loaded  # type: ignore[return-value]
            try:
                from transformers import AutoProcessor
                try:
                    from transformers import (
                        Qwen2_5_VLForConditionalGeneration as AutoModel,
                    )
                except ImportError:
                    try:
                        from transformers import AutoModelForImageTextToText as AutoModel
                    except ImportError:
                        try:
                            from transformers import AutoModelForVision2Seq as AutoModel
                        except ImportError:
                            from transformers import AutoModel
            except ImportError as exc:  # pragma: no cover - production dependency guard
                raise RuntimeError("transformers is required for qwen_local") from exc
            processor = AutoProcessor.from_pretrained(
                self.model_id,
                revision=self.model_revision,
                trust_remote_code=bool(self.model_config.get("trust_remote_code", False)),
            )
            model = AutoModel.from_pretrained(
                self.model_id,
                revision=self.model_revision,
                torch_dtype=self.model_config.get("torch_dtype", "auto"),
                device_map=self.model_config.get("device_map", "auto"),
                low_cpu_mem_usage=bool(self.model_config.get("low_cpu_mem_usage", True)),
                trust_remote_code=bool(self.model_config.get("trust_remote_code", False)),
            )
            model.eval()
            self._loaded = (processor, model)
            return processor, model

    def _load_vintern(self) -> tuple[Any, Any]:
        with self._model_lock:
            if self._loaded is not None:
                return self._loaded  # type: ignore[return-value]
            try:
                from transformers import AutoModel, AutoTokenizer
            except ImportError as exc:  # pragma: no cover - production dependency guard
                raise RuntimeError("transformers is required for vintern_local") from exc
            tokenizer = AutoTokenizer.from_pretrained(
                self.model_id,
                revision=self.model_revision,
                trust_remote_code=bool(self.model_config.get("trust_remote_code", True)),
                use_fast=bool(self.model_config.get("use_fast_tokenizer", False)),
            )
            model = AutoModel.from_pretrained(
                self.model_id,
                revision=self.model_revision,
                torch_dtype=self.model_config.get("torch_dtype", "auto"),
                device_map=self.model_config.get("device_map", "auto"),
                low_cpu_mem_usage=bool(self.model_config.get("low_cpu_mem_usage", True)),
                trust_remote_code=bool(self.model_config.get("trust_remote_code", True)),
                use_flash_attn=bool(self.model_config.get("use_flash_attn", False)),
            )
            model.eval()
            self._loaded = (tokenizer, model)
            return tokenizer, model

    def close(self) -> None:
        with self._model_lock:
            self._loaded = None
        _release_torch_memory()


def _close_client(client: Any) -> None:
    close = getattr(client, "close", None)
    if callable(close):
        close()


def _release_torch_memory() -> None:
    gc.collect()
    try:
        import torch
    except ImportError:  # pragma: no cover - optional runtime dependency guard
        return
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        ipc_collect = getattr(torch.cuda, "ipc_collect", None)
        if callable(ipc_collect):
            ipc_collect()


def _parse_json_object(raw_text: str, schema: dict[str, Any]) -> dict[str, Any]:
    text = raw_text.strip()
    fence = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    if not text.startswith("{"):
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            text = text[start : end + 1]
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise TypeError("structured local VLM response must be an object")
    validate(payload, schema)
    return payload


def _model_device(model: Any):
    try:
        return next(model.parameters()).device
    except StopIteration:  # pragma: no cover
        return "cpu"


def _vintern_pixel_values(image_path: Path):
    import torch

    image = Image.open(image_path).convert("RGB").resize((448, 448))
    array = np.asarray(image).astype("float32") / 255.0
    tensor = torch.from_numpy(array).permute(2, 0, 1)
    mean = torch.tensor([0.485, 0.456, 0.406], dtype=tensor.dtype).view(3, 1, 1)
    std = torch.tensor([0.229, 0.224, 0.225], dtype=tensor.dtype).view(3, 1, 1)
    return ((tensor - mean) / std).unsqueeze(0)
