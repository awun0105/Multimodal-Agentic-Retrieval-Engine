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
