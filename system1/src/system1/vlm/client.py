from __future__ import annotations

import gc
import json
import re
import threading
import time
import warnings
from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any, Protocol

import numpy as np
from jsonschema import validate
from PIL import Image

from .contracts import (
    ModelRequest,
    build_request_hash,
    normalize_text_response,
)


class JsonCache(Protocol):
    def exists(self, relative_path: str | Path) -> bool: ...

    def read_json(self, relative_path: str | Path) -> dict[str, Any]: ...

    def write_json(self, relative_path: str | Path, payload: dict[str, Any]) -> Path: ...


class StructuredClient(Protocol):
    def request(self, request: ModelRequest) -> dict[str, Any]: ...

    def request_many(
        self, requests: list[ModelRequest]
    ) -> list[dict[str, Any]]: ...


class SystemicProviderError(RuntimeError):
    """The provider runtime cannot safely serve more requests in this chunk."""


class BatchRequestError(RuntimeError):
    """Carries completed results while exposing request-specific errors."""

    def __init__(
        self,
        *,
        results: list[dict[str, Any] | None],
        errors: Mapping[int, Exception],
    ) -> None:
        self.results = results
        self.errors = dict(errors)
        details = " | ".join(
            f"request[{index}] {type(error).__name__}: {error}"
            for index, error in sorted(self.errors.items())
        )
        super().__init__(details or "structured request batch failed")


class _NativeBatchUnavailable(RuntimeError):
    pass


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

    def request(self, request: ModelRequest) -> dict[str, Any]:
        return self._with_metadata(self.client.request(request))

    def request_many(
        self, requests: list[ModelRequest]
    ) -> list[dict[str, Any]]:
        try:
            responses = _client_request_many(self.client, requests)
        except BatchRequestError as exc:
            raise BatchRequestError(
                results=[
                    self._with_metadata(result) if result is not None else None
                    for result in exc.results
                ],
                errors=exc.errors,
            ) from exc
        return [self._with_metadata(response) for response in responses]

    def _with_metadata(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        payload = dict(payload)
        payload.setdefault("__provider", self.provider_name)
        payload.setdefault("__model_id", self.model_id)
        payload.setdefault("__model_revision", self.model_revision)
        return payload

    def close(self) -> None:
        _close_client(self.client)


def _for_local_fallback(request: ModelRequest) -> ModelRequest:
    fallback_paths = request.fallback_image_paths
    if not fallback_paths:
        return request
    from dataclasses import replace
    return replace(request, image_paths=fallback_paths)

class ExclusiveLocalFallbackClient:
    """Sticky local failover with one GPU-heavy model resident."""

    def __init__(
        self,
        primary: StructuredClient,
        fallback: StructuredClient,
        *,
        telemetry_callback: Callable[[Mapping[str, Any]], None] | None = None,
    ) -> None:
        self.primary = primary
        self.fallback = fallback
        self.telemetry_callback = telemetry_callback
        self._request_lock = threading.Lock()
        self._fallback_active = False
        self._closed = False
        self._counts = {
            "qwen_request_count": 0,
            "vintern_fallback_request_count": 0,
            "fallback_request_count": 0,
            "fallback_activation_count": 0,
        }

    @property
    def circuit_open(self) -> bool:
        return self._fallback_active

    def request(self, request: ModelRequest) -> dict[str, Any]:
        try:
            return self.request_many([request])[0]
        except BatchRequestError as exc:
            raise RuntimeError(str(exc)) from exc

    def request_many(self, requests: list[ModelRequest]) -> list[dict[str, Any]]:
        if not requests:
            return []
        
        with self._request_lock:
            if self._closed:
                raise RuntimeError("client is closed")
                
            if self._fallback_active:
                fallback_reqs = [_for_local_fallback(r) for r in requests]
                self._record_provider_requests("vintern", len(requests))
                return _client_request_many(self.fallback, fallback_reqs)

            self._record_provider_requests("qwen", len(requests))
            try:
                return _client_request_many(self.primary, requests)
            except SystemicProviderError:
                self._activate_fallback()
                fallback_reqs = [_for_local_fallback(r) for r in requests]
                self._record_provider_requests("vintern", len(requests))
                self._counts["fallback_request_count"] += len(requests)
                return _client_request_many(self.fallback, fallback_reqs)
            except BatchRequestError as exc:
                results = list(exc.results)
                errors = exc.errors
                
                self._activate_fallback()
                
                failed_indices = [i for i, err in enumerate(errors) if err is not None]
                fallback_reqs = [_for_local_fallback(requests[i]) for i in failed_indices]
                
                if fallback_reqs:
                    self._record_provider_requests("vintern", len(fallback_reqs))
                    self._counts["fallback_request_count"] += len(fallback_reqs)
                    try:
                        fallback_results = _client_request_many(self.fallback, fallback_reqs)
                        for fallback_idx, original_idx in enumerate(failed_indices):
                            results[original_idx] = fallback_results[fallback_idx]
                            errors[original_idx] = None
                    except BatchRequestError as fallback_exc:
                        for fallback_idx, original_idx in enumerate(failed_indices):
                            results[original_idx] = fallback_exc.results[fallback_idx]
                            errors[original_idx] = fallback_exc.errors[fallback_idx]
                            
                if any(err is not None for err in errors):
                    raise BatchRequestError(
                        "exclusive fallback failed to repair all items",
                        tuple(results),
                        tuple(errors),
                    ) from exc
                
                return results

    def _activate_fallback(self) -> None:
        if not self._fallback_active:
            self._fallback_active = True
            self._counts["fallback_activation_count"] += 1
            if self.telemetry_callback:
                self.telemetry_callback(
                    {
                        "event": "semantic_fallback_activated",
                        "event_kind": "lifecycle",
                    }
                )
            try:
                self.primary.close()
            except Exception:
                pass
            _release_torch_memory()

    def _record_provider_requests(self, provider: str, count: int) -> None:
        if provider == "qwen":
            self._counts["qwen_request_count"] += count
        else:
            self._counts["vintern_fallback_request_count"] += count

    def report_telemetry(self) -> dict[str, int]:
        primary_counts = self.primary.report_telemetry()
        fallback_counts = self.fallback.report_telemetry()
        return {
            **primary_counts,
            **fallback_counts,
            **self._counts,
        }

    def close(self) -> None:
        with self._request_lock:
            self._closed = True
            try:
                self.primary.close()
            except Exception:
                pass
            try:
                self.fallback.close()
            except Exception:
                pass


class LocalVisionStructuredClient:
    def __init__(
        self,
        *,
        model_config: Mapping[str, Any],
        cache: JsonCache | None = None,
        cache_prefix: str | Path = "cache/local_vlm",
        lifecycle_callback: Callable[[Mapping[str, Any]], None] | None = None,
        pre_load_callback: Callable[[str], None] | None = None,
    ) -> None:
        self.model_config = dict(model_config)
        self.provider_name = str(self.model_config["provider"])
        self.model_id = str(self.model_config["model_id"])
        self.model_revision = str(self.model_config.get("model_revision") or self.model_id)
        self.cache = cache
        self.cache_prefix = Path(cache_prefix)
        self.lifecycle_callback = lifecycle_callback
        self.pre_load_callback = pre_load_callback
        self.total_attempts = int(self.model_config.get("total_attempts", 2))
        self.inference_batch_size = int(
            self.model_config.get("inference_batch_size", 1)
        )
        if self.total_attempts < 1:
            raise ValueError("local VLM total_attempts must be positive")
        if self.inference_batch_size < 1:
            raise ValueError("local VLM inference_batch_size must be positive")
        self._cache_lock = threading.Lock()
        self._model_lock = threading.Lock()
        self._loaded: tuple[Any, ...] | None = None
        self._last_requested_batch_size = 0
        self._last_effective_batch_size = 0
        self._total_oom_reductions = 0

    def request(self, request: ModelRequest) -> dict[str, Any]:
        try:
            return self.request_many([request])[0]
        except BatchRequestError as exc:
            raise next(iter(exc.errors.values())) from exc

    def request_many(
        self, requests: list[ModelRequest]
    ) -> list[dict[str, Any]]:
        if not requests:
            return []
        results: list[dict[str, Any] | None] = [None] * len(requests)
        active_requests = list(requests)
        errors: dict[int, Exception] = {}
        misses: list[int] = []
        cache_paths: dict[int, Path] = {}
        for index, request in enumerate(requests):
            request_hash = self._request_hash(request)
            cache_path = self.cache_prefix / f"{request_hash}.json"
            cache_paths[index] = cache_path
            cached = self._read_cached(cache_path, request)
            if cached is None:
                misses.append(index)
            else:
                results[index] = self._with_metadata(cached)

        requested_batch_size = min(self.inference_batch_size, max(1, len(misses)))
        effective_batch_size = requested_batch_size
        self._last_requested_batch_size = requested_batch_size
        self._last_effective_batch_size = effective_batch_size
        cache_hits = len(requests) - len(misses)
        self._emit_lifecycle(
            "batch_start",
            requested_batch_size=requested_batch_size,
            effective_batch_size=effective_batch_size,
            request_count=len(requests),
            cache_hits=cache_hits,
            cache_misses=len(misses),
            quantization_mode=self._quantization_mode(),
        )
        cursor = 0
        oom_reductions = 0
        batch_one_oom_attempts = 0
        systemic_attempts = 0
        structured_parse_error_count = 0
        while cursor < len(misses):
            batch_indices = misses[cursor : cursor + effective_batch_size]
            batch_requests = [active_requests[index] for index in batch_indices]
            try:
                raw_texts = self._call_models(batch_requests)
            except _NativeBatchUnavailable:
                if effective_batch_size == 1:
                    raise
                previous = effective_batch_size
                effective_batch_size = 1
                self._emit_lifecycle(
                    "batch_capability_fallback",
                    requested_batch_size=requested_batch_size,
                    previous_batch_size=previous,
                    effective_batch_size=1,
                    quantization_mode=self._quantization_mode(),
                )
                continue
            except Exception as exc:
                if _is_cuda_oom(exc):
                    _release_torch_memory()
                    if effective_batch_size > 1:
                        previous = effective_batch_size
                        effective_batch_size = max(1, effective_batch_size // 2)
                        self._last_effective_batch_size = effective_batch_size
                        oom_reductions += 1
                        self._total_oom_reductions += 1
                        self._emit_lifecycle(
                            "oom_reduction",
                            requested_batch_size=requested_batch_size,
                            previous_batch_size=previous,
                            effective_batch_size=effective_batch_size,
                            oom_reductions=oom_reductions,
                            error_type=type(exc).__name__,
                            quantization_mode=self._quantization_mode(),
                        )
                        continue
                    reduced_request = _reduce_multimage_request(batch_requests[0])
                    if reduced_request is not None:
                        index = batch_indices[0]
                        previous_image_count = len(batch_requests[0].image_paths)
                        active_requests[index] = reduced_request
                        reduced_hash = self._request_hash(reduced_request)
                        reduced_cache_path = self.cache_prefix / f"{reduced_hash}.json"
                        cache_paths[index] = reduced_cache_path
                        cached = self._read_cached(reduced_cache_path, reduced_request)
                        self._emit_lifecycle(
                            "image_oom_reduction",
                            requested_batch_size=requested_batch_size,
                            effective_batch_size=1,
                            previous_image_count=previous_image_count,
                            effective_image_count=len(reduced_request.image_paths),
                            request_kind=reduced_request.request_kind,
                            cache_hit=cached is not None,
                            quantization_mode=self._quantization_mode(),
                        )
                        if cached is not None:
                            results[index] = self._with_metadata(cached)
                            cursor += 1
                        batch_one_oom_attempts = 0
                        systemic_attempts = 0
                        continue
                    batch_one_oom_attempts += 1
                    if batch_one_oom_attempts < self.total_attempts:
                        self.close()
                        self._emit_lifecycle(
                            "oom_retry",
                            requested_batch_size=requested_batch_size,
                            effective_batch_size=1,
                            attempt=batch_one_oom_attempts,
                            total_attempts=self.total_attempts,
                            oom_reductions=oom_reductions,
                            error_type=type(exc).__name__,
                            quantization_mode=self._quantization_mode(),
                        )
                        continue
                    self.close()
                    systemic = SystemicProviderError(
                        f"{self.provider_name} CUDA OOM at batch_size=1: {exc}"
                    )
                    for index in misses[cursor:]:
                        errors[index] = systemic
                    raise BatchRequestError(results=results, errors=errors) from exc
                if _is_systemic_runtime_error(exc):
                    systemic_attempts += 1
                    if systemic_attempts < self.total_attempts:
                        self.close()
                        self._emit_lifecycle(
                            "runtime_retry",
                            requested_batch_size=requested_batch_size,
                            effective_batch_size=effective_batch_size,
                            attempt=systemic_attempts,
                            total_attempts=self.total_attempts,
                            error_type=type(exc).__name__,
                            quantization_mode=self._quantization_mode(),
                        )
                        continue
                    self.close()
                    systemic = SystemicProviderError(
                        f"{self.provider_name} runtime unavailable: {exc}"
                    )
                    for index in misses[cursor:]:
                        errors[index] = systemic
                    raise BatchRequestError(results=results, errors=errors) from exc
                if effective_batch_size > 1:
                    previous = effective_batch_size
                    effective_batch_size = 1
                    self._last_effective_batch_size = 1
                    self._emit_lifecycle(
                        "batch_error_isolation",
                        requested_batch_size=requested_batch_size,
                        previous_batch_size=previous,
                        effective_batch_size=1,
                        error_type=type(exc).__name__,
                        quantization_mode=self._quantization_mode(),
                    )
                    continue
                for index in batch_indices:
                    errors[index] = exc
                cursor += len(batch_indices)
                continue

            if len(raw_texts) != len(batch_requests):
                exc = ValueError(
                    f"local VLM returned {len(raw_texts)} responses for "
                    f"{len(batch_requests)} requests"
                )
                if effective_batch_size > 1:
                    previous = effective_batch_size
                    effective_batch_size = 1
                    self._last_effective_batch_size = 1
                    self._emit_lifecycle(
                        "batch_error_isolation",
                        requested_batch_size=requested_batch_size,
                        previous_batch_size=previous,
                        effective_batch_size=1,
                        error_type=type(exc).__name__,
                        quantization_mode=self._quantization_mode(),
                    )
                    continue
                errors[batch_indices[0]] = exc
                cursor += 1
                continue
            for index, request, raw_text in zip(
                batch_indices, batch_requests, raw_texts, strict=True
            ):
                try:
                    if self._uses_vintern_plain_text_ocr(request):
                        normalized = _normalize_vintern_ocr_text(raw_text)
                        validate(normalized, request.response_schema)
                    elif request.response_mode == "text":
                        normalized = normalize_text_response(raw_text, request)
                        validate(normalized, request.response_schema)
                    else:
                        normalized = _parse_json_object(
                            raw_text, request.response_schema
                        )
                    self._write_cached(
                        cache_paths[index], request=request, normalized=normalized
                    )
                    results[index] = self._with_metadata(normalized)
                except Exception as exc:  # noqa: BLE001 - request-scoped fallback
                    errors[index] = exc
                    structured_parse_error_count += 1
                    if structured_parse_error_count <= 3:
                        self._emit_lifecycle(
                            "response_parse_error",
                            request_index=index,
                            request_kind=request.request_kind,
                            response_mode=request.response_mode,
                            error_type=type(exc).__name__,
                            error_message=str(exc)[:500],
                            raw_response_preview=str(raw_text)[:500],
                            quantization_mode=self._quantization_mode(),
                        )
            cursor += len(batch_indices)
            batch_one_oom_attempts = 0
            systemic_attempts = 0

        self._emit_lifecycle(
            "batch_complete",
            requested_batch_size=requested_batch_size,
            effective_batch_size=effective_batch_size,
            request_count=len(requests),
            cache_hits=cache_hits,
            cache_misses=len(misses),
            oom_reductions=oom_reductions,
            failed_request_count=len(errors),
            quantization_mode=self._quantization_mode(),
        )
        if errors:
            raise BatchRequestError(results=results, errors=errors)
        return _complete_batch_or_raise(results)

    def _uses_vintern_plain_text_ocr(self, request: ModelRequest) -> bool:
        return (
            self.provider_name == "vintern_local"
            and request.request_kind == "keyframe_ocr"
            and str(
                self.model_config.get(
                    "structured_output_contract_version",
                    "",
                )
            )
            == "vintern_plain_text_ocr_v1"
        )

    def _request_hash(self, request: ModelRequest) -> str:
        if request.response_mode == "text":
            contract_version = self.model_config.get(
                "generation_contract_version",
                "plain_text_v1",
            )
        else:
            contract_version = self.model_config.get(
                "structured_output_contract_version",
                "json_schema_prompt_v1",
            )

        cache_identity: dict[str, Any] = {
            "provider": self.provider_name,
            "model_revision": self.model_revision,
            "max_new_tokens": self.model_config.get("max_new_tokens"),
            "quantization": self.model_config.get("quantization"),
            "generation_contract_version": contract_version,
        }

        if self.provider_name == "qwen_local":
            cache_identity["padding_side"] = self.model_config.get(
                "padding_side",
                "left",
            )

        if self.provider_name == "vintern_reasoning_local":
            cache_identity.update(
                {
                    "image_size": self.model_config.get("image_size"),
                    "max_dynamic_patches": self.model_config.get("max_dynamic_patches"),
                    "use_thumbnail": self.model_config.get("use_thumbnail"),
                    "num_beams": self.model_config.get("num_beams"),
                    "do_sample": self.model_config.get("do_sample"),
                    "repetition_penalty": self.model_config.get("repetition_penalty"),
                }
            )

        request_hash = build_request_hash(
            request,
            model_id=self.model_id,
            cache_identity=cache_identity,
        )

        return request_hash

    def _read_cached(
        self, cache_path: Path, request: ModelRequest
    ) -> dict[str, Any] | None:
        if self.cache is None:
            return None
        with self._cache_lock:
            if not self.cache.exists(cache_path):
                return None
            cached = self.cache.read_json(cache_path)
            response = cached.get("normalized_response")
            if not isinstance(response, dict):
                return None
            try:
                validate(response, request.response_schema)
            except Exception:  # noqa: BLE001 - corrupt cache entries are misses
                return None
            return response

    def _write_cached(
        self,
        cache_path: Path,
        *,
        request: ModelRequest,
        normalized: dict[str, Any],
    ) -> None:
        if self.cache is None:
            return
        with self._cache_lock:
            self.cache.write_json(
                cache_path,
                {
                    "schema_version": "local_vlm_cache_entry_v1",
                    "request_hash": cache_path.stem,
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

    def _with_metadata(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        response = dict(payload)
        response["__provider"] = self.provider_name
        response["__model_id"] = self.model_id
        response["__model_revision"] = self.model_revision
        return response

    def _call_models(self, requests: list[ModelRequest]) -> list[str]:
        if self.provider_name == "qwen_local":
            return self._call_qwen_many(requests)
        if self.provider_name == "vintern_local":
            return self._call_vintern_many(requests)
        if self.provider_name == "vintern_reasoning_local":
            return self._call_vintern_reasoning_many(requests)
        raise SystemicProviderError(
            f"unsupported local VLM provider: {self.provider_name}"
        )

    def _call_qwen_many(self, requests: list[ModelRequest]) -> list[str]:
        processor, model = self._load_qwen()
        try:
            from qwen_vl_utils import process_vision_info
        except ImportError as exc:  # pragma: no cover - production dependency guard
            raise SystemicProviderError(
                "qwen-vl-utils is required for qwen_local"
            ) from exc

        inputs: Any = None
        generated_ids: Any = None
        image_inputs: Any = None
        video_inputs: Any = None
        try:
            conversations = [
                [
                    {
                        "role": "user",
                        "content": [
                            *[
                                {"type": "image", "image": str(path)}
                                for path in request.image_paths
                            ],
                            {
                                "type": "text",
                                "text": (
                                    request.prompt
                                    if request.response_mode == "text"
                                    else _structured_prompt(request)
                                ),
                            },
                        ],
                    }
                ]
                for request in requests
            ]
            texts = [
                processor.apply_chat_template(
                    conversation, tokenize=False, add_generation_prompt=True
                )
                for conversation in conversations
            ]
            image_inputs, video_inputs = process_vision_info(conversations)
            inputs = processor(
                text=texts,
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
                generated_ids,
                skip_special_tokens=True,
                clean_up_tokenization_spaces=False,
            )
        finally:
            del inputs, generated_ids, image_inputs, video_inputs

    def _call_vintern_many(self, requests: list[ModelRequest]) -> list[str]:
        if any(len(request.image_paths) != 1 for request in requests):
            raise RuntimeError("vintern_local expects exactly one image per request")
        tokenizer, model = self._load_vintern()
        import torch

        native_batch = getattr(model, "batch_chat", None)
        if len(requests) > 1 and not callable(native_batch):
            raise _NativeBatchUnavailable("Vintern runtime has no batch_chat")
        pixel_values: Any = None
        try:
            tensors = [
                _vintern_pixel_values(request.image_paths[0]) for request in requests
            ]
            pixel_values = torch.cat(tensors, dim=0).to(_model_device(model))
            try:
                dtype = next(model.parameters()).dtype
                pixel_values = pixel_values.to(dtype=dtype)
            except StopIteration:  # pragma: no cover
                pass
            prompts: list[str] = []
            for request in requests:
                if self._uses_vintern_plain_text_ocr(request):
                    model_prompt = request.prompt
                elif request.response_mode == "text":
                    model_prompt = request.prompt
                else:
                    model_prompt = _structured_prompt(request)
                prompts.append(
                    model_prompt
                    if "<image>" in model_prompt
                    else "<image>\n" + model_prompt
                )
            generation_config = {
                "max_new_tokens": int(self.model_config.get("max_new_tokens", 768)),
                "do_sample": False,
            }
            with torch.no_grad():
                if len(requests) > 1:
                    outputs = native_batch(
                        tokenizer,
                        pixel_values,
                        prompts,
                        generation_config,
                        num_patches_list=[1] * len(requests),
                    )
                else:
                    output = model.chat(
                        tokenizer,
                        pixel_values,
                        prompts[0],
                        generation_config,
                    )
                    outputs = [output[0] if isinstance(output, tuple) else output]
            if not isinstance(outputs, Sequence) or isinstance(outputs, str):
                raise TypeError("vintern_local returned an invalid batch response")
            normalized = [str(output).strip() for output in outputs]
            if any(not output for output in normalized):
                raise ValueError("vintern_local returned an empty response")
            return normalized
        finally:
            del pixel_values


    def _call_vintern_reasoning_many(self, requests: list[ModelRequest]) -> list[str]:
        if len(requests) > 1:
            raise _NativeBatchUnavailable(
                "vintern_reasoning_local starts with serial inference"
            )

        request = requests[0]

        if request.response_mode != "text":
            raise ValueError(
                "vintern_reasoning_local only supports text mode in Phase01"
            )

        tokenizer, model = self._load_vintern_reasoning()
        import torch
        from system1.vlm.vintern_reasoning import load_vintern_reasoning_image

        image_path = (request.fallback_image_paths[0] if request.fallback_image_paths else request.image_paths[0])
        
        configured_max_tiles = int(self.model_config.get("max_dynamic_patches", 6))
        patch_plan = _vintern_patch_plan(configured_max_tiles)

        model_prompt = request.prompt
        if "<image>" not in model_prompt:
            model_prompt = "<image>\n" + model_prompt

        generation_config = {
            "max_new_tokens": int(self.model_config.get("max_new_tokens", 256)),
            "do_sample": False,
            "num_beams": int(self.model_config.get("num_beams", 1)),
            "repetition_penalty": float(self.model_config.get("repetition_penalty", 1.0)),
        }

        for i, max_tiles in enumerate(patch_plan):
            pixel_values = None
            try:
                pixel_values = load_vintern_reasoning_image(
                    image_path,
                    image_size=int(self.model_config.get("image_size", 448)),
                    max_tiles=max_tiles,
                    use_thumbnail=bool(self.model_config.get("use_thumbnail", True)),
                ).unsqueeze(0).to(_model_device(model))

                try:
                    dtype = next(model.parameters()).dtype
                    pixel_values = pixel_values.to(dtype=dtype)
                except StopIteration:
                    pass

                with torch.no_grad():
                    output = model.chat(
                        tokenizer,
                        pixel_values,
                        model_prompt,
                        generation_config,
                    )
                    output_text = output[0] if isinstance(output, tuple) else output

                if not str(output_text).strip():
                    raise ValueError("vintern_reasoning_local returned an empty response")

                return [str(output_text).strip()]

            except Exception as exc:
                if _is_cuda_oom(exc):
                    self._emit_lifecycle(
                        "vintern_patch_oom_reduction",
                        previous_patch_limit=max_tiles,
                        effective_patch_limit=patch_plan[i + 1] if i + 1 < len(patch_plan) else 0,
                    )
                    _release_torch_memory()
                    if i + 1 < len(patch_plan):
                        continue
                raise
            finally:
                del pixel_values

    def _load_qwen(self) -> tuple[Any, Any]:
        with self._model_lock:
            if self._loaded is not None:
                return self._loaded  # type: ignore[return-value]
            self._run_pre_load_callback()
            started = time.monotonic()
            _reset_cuda_peak_memory()
            try:
                import torch
                from transformers import AutoProcessor, BitsAndBytesConfig
                try:
                    from transformers import (
                        Qwen2_5_VLForConditionalGeneration as AutoModel,
                    )
                except ImportError:
                    try:
                        from transformers import (
                            AutoModelForImageTextToText as AutoModel,
                        )
                    except ImportError:
                        try:
                            from transformers import AutoModelForVision2Seq as AutoModel
                        except ImportError:
                            from transformers import AutoModel
            except ImportError as exc:  # pragma: no cover - production dependency guard
                raise SystemicProviderError(
                    "transformers, torch, and bitsandbytes are required for qwen_local"
                ) from exc
            quantization_config = _qwen_quantization_config(
                self.model_config, BitsAndBytesConfig, torch
            )
            try:
                processor = AutoProcessor.from_pretrained(
                    self.model_id,
                    revision=self.model_revision,
                    trust_remote_code=bool(
                        self.model_config.get("trust_remote_code", False)
                    ),
                )

                padding_side = str(
                    self.model_config.get("padding_side", "left")
                )

                if padding_side != "left":
                    raise ValueError(
                        "qwen_local requires padding_side='left' "
                        "for batched decoder-only generation"
                    )

                tokenizer = getattr(processor, "tokenizer", None)
                if tokenizer is None:
                    raise RuntimeError(
                        "qwen_local processor does not expose a tokenizer"
                    )

                tokenizer.padding_side = padding_side
                model = AutoModel.from_pretrained(
                    self.model_id,
                    revision=self.model_revision,
                    torch_dtype=_torch_dtype(
                        self.model_config.get("torch_dtype", "float16"), torch
                    ),
                    device_map=self.model_config.get("device_map", "cuda"),
                    quantization_config=quantization_config,
                    low_cpu_mem_usage=bool(
                        self.model_config.get("low_cpu_mem_usage", True)
                    ),
                    trust_remote_code=bool(
                        self.model_config.get("trust_remote_code", False)
                    ),
                )
                model.eval()
                _reject_cpu_disk_offload(model, provider_name="qwen_local")
                self._loaded = (processor, model)
            except Exception as exc:
                _release_torch_memory()
                self._emit_lifecycle(
                    "load_failed",
                    load_seconds=round(time.monotonic() - started, 3),
                    error_type=type(exc).__name__,
                    quantization_mode=self._quantization_mode(),
                )
                raise SystemicProviderError(
                    f"failed to load qwen_local {self.model_id}: {exc}"
                ) from exc
            self._emit_lifecycle(
                "loaded",
                load_seconds=round(time.monotonic() - started, 3),
                quantization_mode=self._quantization_mode(),
            )
            return processor, model

    def _load_vintern(self) -> tuple[Any, Any]:
        with self._model_lock:
            if self._loaded is not None:
                return self._loaded  # type: ignore[return-value]
            self._run_pre_load_callback()
            started = time.monotonic()
            _reset_cuda_peak_memory()
            try:
                from transformers import AutoModel, AutoTokenizer
            except ImportError as exc:  # pragma: no cover - production dependency guard
                raise SystemicProviderError(
                    "transformers is required for vintern_local"
                ) from exc
            try:
                tokenizer = AutoTokenizer.from_pretrained(
                    self.model_id,
                    revision=self.model_revision,
                    trust_remote_code=bool(
                        self.model_config.get("trust_remote_code", True)
                    ),
                    use_fast=bool(
                        self.model_config.get("use_fast_tokenizer", False)
                    ),
                )
                model = AutoModel.from_pretrained(
                    self.model_id,
                    revision=self.model_revision,
                    torch_dtype=self.model_config.get("torch_dtype", "auto"),
                    device_map=self.model_config.get("device_map", "auto"),
                    low_cpu_mem_usage=bool(
                        self.model_config.get("low_cpu_mem_usage", True)
                    ),
                    trust_remote_code=bool(
                        self.model_config.get("trust_remote_code", True)
                    ),
                    use_flash_attn=bool(
                        self.model_config.get("use_flash_attn", False)
                    ),
                )
                model.eval()
                _reject_cpu_disk_offload(model, provider_name="vintern_local")
                self._loaded = (tokenizer, model)
            except Exception as exc:
                _release_torch_memory()
                self._emit_lifecycle(
                    "load_failed",
                    load_seconds=round(time.monotonic() - started, 3),
                    error_type=type(exc).__name__,
                    quantization_mode="none",
                )
                raise SystemicProviderError(
                    f"failed to load vintern_local {self.model_id}: {exc}"
                ) from exc
            self._emit_lifecycle(
                "loaded",
                load_seconds=round(time.monotonic() - started, 3),
                quantization_mode="none",
                native_batch_capable=callable(getattr(model, "batch_chat", None)),
            )
            return tokenizer, model


    def _load_vintern_reasoning(self) -> tuple[Any, Any]:
        with self._model_lock:
            if self._loaded is not None:
                return self._loaded  # type: ignore[return-value]
            self._run_pre_load_callback()
            started = time.monotonic()
            _reset_cuda_peak_memory()
            try:
                from transformers import AutoModel, AutoTokenizer
            except ImportError as exc:
                raise SystemicProviderError(
                    "transformers is required for vintern_reasoning_local"
                ) from exc
            try:
                import torch
                tokenizer = AutoTokenizer.from_pretrained(
                    self.model_id,
                    revision=self.model_revision,
                    trust_remote_code=True,
                    use_fast=False,
                )
                model = AutoModel.from_pretrained(
                    self.model_id,
                    revision=self.model_revision,
                    torch_dtype=torch.float16,
                    low_cpu_mem_usage=True,
                    trust_remote_code=True,
                    use_flash_attn=False,
                )
                model = model.eval().cuda()
                self._loaded = (tokenizer, model)
            except Exception as exc:
                _release_torch_memory()
                self._emit_lifecycle(
                    "load_failed",
                    load_seconds=round(time.monotonic() - started, 3),
                    error_type=type(exc).__name__,
                    quantization_mode="none",
                )
                raise SystemicProviderError(
                    f"failed to load vintern_reasoning_local {self.model_id}: {exc}"
                ) from exc
            self._emit_lifecycle(
                "loaded",
                load_seconds=round(time.monotonic() - started, 3),
                quantization_mode="none",
                native_batch_capable=False,
            )
            return tokenizer, model

    def _quantization_mode(self) -> str:
        quantization = self.model_config.get("quantization", {})
        if not isinstance(quantization, Mapping):
            return "none"
        return str(quantization.get("mode", "none"))

    def close(self) -> None:
        with self._model_lock:
            was_loaded = self._loaded is not None
            self._loaded = None
        _release_torch_memory()
        if was_loaded:
            self._emit_lifecycle(
                "unloaded",
                quantization_mode=self._quantization_mode(),
                requested_batch_size=self._last_requested_batch_size,
                effective_batch_size=self._last_effective_batch_size,
                oom_reductions=self._total_oom_reductions,
            )

    def _run_pre_load_callback(self) -> None:
        if self.pre_load_callback is None:
            return
        try:
            self.pre_load_callback(self.provider_name)
        except Exception as exc:
            self._emit_lifecycle(
                "load_blocked",
                error_type=type(exc).__name__,
                quantization_mode=self._quantization_mode(),
            )
            raise SystemicProviderError(
                f"{self.provider_name} pre-load guard failed: {exc}"
            ) from exc

    def _emit_lifecycle(self, status: str, **details: Any) -> None:
        if self.lifecycle_callback is None:
            return
        try:
            self.lifecycle_callback(
                {
                    "status": status,
                    "provider": self.provider_name,
                    "model": self.model_id,
                    "model_revision": self.model_revision,
                    **details,
                }
            )
        except Exception:  # noqa: BLE001, S110 - telemetry cannot break inference
            pass


def _qwen_quantization_config(
    model_config: Mapping[str, Any], factory: Any, torch: Any
):
    quantization = model_config.get("quantization")
    if not isinstance(quantization, Mapping):
        raise SystemicProviderError("qwen_local requires explicit quantization config")
    if str(quantization.get("method")) != "bitsandbytes" or str(
        quantization.get("mode")
    ) != "4bit":
        raise SystemicProviderError(
            "qwen_local only supports configured bitsandbytes 4bit loading"
        )
    return factory(
        load_in_4bit=True,
        bnb_4bit_quant_type=str(quantization.get("quant_type", "nf4")),
        bnb_4bit_compute_dtype=_torch_dtype(
            quantization.get("compute_dtype", "float16"), torch
        ),
        bnb_4bit_use_double_quant=bool(quantization.get("double_quant", True)),
    )


def _reject_cpu_disk_offload(model: Any, *, provider_name: str) -> None:
    device_map = getattr(model, "hf_device_map", None)
    if not isinstance(device_map, Mapping):
        return
    offloaded = {
        str(module): str(device)
        for module, device in device_map.items()
        if str(device).lower().split(":", maxsplit=1)[0] in {"cpu", "disk"}
    }
    if offloaded:
        raise SystemicProviderError(
            f"{provider_name} CPU/disk offload is forbidden: "
            + json.dumps(offloaded, sort_keys=True)
        )


def _vintern_patch_plan(
    configured: int,
) -> tuple[int, ...]:
    candidates = [
        configured,
        4,
        2,
        1,
    ]

    result: list[int] = []

    for value in candidates:
        value = min(
            configured,
            max(1, value),
        )

        if value not in result:
            result.append(value)

    return tuple(result)


def _reduce_multimage_request(
    request: ModelRequest,
) -> ModelRequest | None:
    image_count = len(request.image_paths)
    if image_count <= 1:
        return None
    maximum = max(1, (image_count + 1) // 2)
    if maximum == 1:
        indices = [image_count // 2]
    else:
        indices = sorted(
            {
                round(position * (image_count - 1) / (maximum - 1))
                for position in range(maximum)
            }
        )
    return replace(
        request,
        image_paths=tuple(request.image_paths[index] for index in indices),
    )


def _torch_dtype(value: Any, torch: Any):
    if not isinstance(value, str):
        return value
    normalized = value.lower()
    if normalized == "auto":
        return "auto"
    aliases = {
        "float16": "float16",
        "fp16": "float16",
        "bfloat16": "bfloat16",
    }
    attribute = aliases.get(normalized)
    if attribute is None:
        raise ValueError(f"unsupported torch dtype: {value}")
    return getattr(torch, attribute)


def _client_request_many(
    client: StructuredClient, requests: list[ModelRequest]
) -> list[dict[str, Any]]:
    request_many = getattr(client, "request_many", None)
    if callable(request_many):
        return request_many(requests)
    return [client.request(request) for request in requests]


def _complete_batch_or_raise(
    results: list[dict[str, Any] | None],
) -> list[dict[str, Any]]:
    missing = [index for index, result in enumerate(results) if result is None]
    if missing:
        raise BatchRequestError(
            results=results,
            errors={
                index: RuntimeError("missing structured response") for index in missing
            },
        )
    return [result for result in results if result is not None]


def _fallback_reason(exc: BaseException) -> str:
    if isinstance(exc, SystemicProviderError):
        return "systemic_local_runtime"
    name = type(exc).__name__.lower()
    if "validation" in name or "json" in name or isinstance(
        exc, (ValueError, TypeError)
    ):
        return "invalid_structured_response"
    return "request_error"


def _is_systemic_provider_error(exc: BaseException) -> bool:
    return isinstance(exc, SystemicProviderError)


def _is_systemic_runtime_error(exc: BaseException) -> bool:
    if isinstance(exc, SystemicProviderError):
        return True
    message = str(exc).lower()
    markers = (
        "device-side assert",
        "illegal memory access",
        "cuda error",
        "cublas",
        "cudnn",
        "driver shutting down",
    )
    return any(marker in message for marker in markers)


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
    try:
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            ipc_collect = getattr(torch.cuda, "ipc_collect", None)
            if callable(ipc_collect):
                ipc_collect()
    except RuntimeError:
        pass


def _reset_cuda_peak_memory() -> None:
    try:
        import torch
    except ImportError:  # pragma: no cover - optional runtime dependency guard
        return
    try:
        if torch.cuda.is_available():
            torch.cuda.reset_peak_memory_stats()
    except RuntimeError:
        pass


def _is_cuda_oom(exc: BaseException) -> bool:
    name = type(exc).__name__.lower()
    message = str(exc).lower()
    return "outofmemory" in name or "cuda out of memory" in message or (
        "cuda" in message and "out of memory" in message
    )


def _normalize_vintern_ocr_text(raw_text: str) -> dict[str, Any]:
    """Normalize plain Vintern OCR text into the canonical OCR response."""

    text = raw_text.strip()
    if text == "<NO_TEXT>":
        text = ""
    return {
        "full_text": text,
        "ocr_blocks": [],
        "language": "vi",
        "confidence": None,
    }


def _structured_prompt(request: ModelRequest) -> str:
    """Attach the exact JSON Schema contract to a local VLM request."""

    schema_json = json.dumps(
        request.response_schema,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return (
        request.prompt.rstrip()
        + "\n\nOUTPUT CONTRACT:\n"
        + "Return exactly one valid JSON object matching the JSON Schema below.\n"
        + "Do not use Markdown code fences. "
        + "Do not add explanations or any text before or after the JSON object.\n"
        + "Do not invent fields that are not allowed by the schema.\n"
        + f"JSON Schema:\n{schema_json}"
    )


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

    with Image.open(image_path) as opened:
        image = opened.convert("RGB").resize((448, 448))
    array = np.asarray(image).astype("float32") / 255.0
    tensor = torch.from_numpy(array).permute(2, 0, 1)
    mean = torch.tensor([0.485, 0.456, 0.406], dtype=tensor.dtype).view(3, 1, 1)
    std = torch.tensor([0.229, 0.224, 0.225], dtype=tensor.dtype).view(3, 1, 1)
    return ((tensor - mean) / std).unsqueeze(0)
