"""ContextOps-owned safety boundary around the external PariTok HTTP proxy."""

from __future__ import annotations

import re
import threading
import time
from contextlib import asynccontextmanager
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from .cache_safety import build_paritok_storage
from .fallback import validate_or_fallback
from .validator import CompressionValidator, FallbackReason


_CRITICAL_SIGNAL = re.compile(r"(?m)^CRITICAL_SIGNAL:\s*(.+?)\s*$")


@dataclass(slots=True)
class CompressionEligibilityGate:
    """Conservative synchronous-compression admission control.

    A cache miss is admitted until an observed cold compression consumes the latency
    budget. Subsequent cold work is bypassed until the process is restarted. Cache hits
    remain eligible because they do not invoke the local model.
    """

    latency_budget_ms: float = 500.0
    maximum_uncached_tokens: int = 3_000
    observed_uncached_calls: int = 0
    observed_uncached_max_ms: float = 0.0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def reason(self, *, original_tokens: int, cache_hit: bool) -> str | None:
        if cache_hit:
            return None
        if original_tokens > self.maximum_uncached_tokens:
            return "above_sync_token_limit"
        with self._lock:
            if (
                self.observed_uncached_calls
                and self.observed_uncached_max_ms >= self.latency_budget_ms
            ):
                return "observed_latency_budget_exceeded"
        return None

    def observe_uncached(self, latency_ms: float) -> None:
        with self._lock:
            self.observed_uncached_calls += 1
            self.observed_uncached_max_ms = max(self.observed_uncached_max_ms, latency_ms)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "latency_budget_ms": self.latency_budget_ms,
                "maximum_uncached_tokens": self.maximum_uncached_tokens,
                "observed_uncached_calls": self.observed_uncached_calls,
                "observed_uncached_max_ms": round(self.observed_uncached_max_ms, 3),
            }


@dataclass(slots=True)
class SafetyTelemetry:
    """Privacy-safe cumulative counters exposed beside PariTok's native telemetry."""

    cache_contract: str
    total_compressions: int = 0
    validated: int = 0
    validator_passes: int = 0
    fallbacks: int = 0
    exact_original_fallbacks: int = 0
    skipped: int = 0
    cache_hits: int = 0
    compression_latency_ms: float = 0.0
    validation_latency_ms: float = 0.0
    upstream_latency_ms: float = 0.0
    proxy_request_latency_ms: float = 0.0
    eligibility_bypasses: int = 0
    deadline_fallbacks: int = 0
    fallback_reasons: Counter[str] = field(default_factory=Counter)
    eligibility_reasons: Counter[str] = field(default_factory=Counter)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def record_pass(
        self, *, cache_hit: bool, compression_ms: float, validation_ms: float
    ) -> None:
        with self._lock:
            self.total_compressions += 1
            self.validated += 1
            self.validator_passes += 1
            self.cache_hits += int(cache_hit)
            self.compression_latency_ms += compression_ms
            self.validation_latency_ms += validation_ms

    def record_fallback(
        self,
        reason: str,
        *,
        cache_hit: bool,
        compression_ms: float,
        validation_ms: float,
    ) -> None:
        with self._lock:
            self.total_compressions += 1
            self.validated += 1
            self.fallbacks += 1
            self.exact_original_fallbacks += 1
            self.cache_hits += int(cache_hit)
            self.compression_latency_ms += compression_ms
            self.validation_latency_ms += validation_ms
            self.fallback_reasons[reason] += 1

    def record_skip(self, reason: str, *, compression_ms: float) -> None:
        is_backend_error = reason.startswith("backend_error:")
        is_deadline = is_backend_error and "timeout" in reason.lower()
        with self._lock:
            self.total_compressions += 1
            self.skipped += 1
            self.compression_latency_ms += compression_ms
            if is_backend_error:
                self.fallbacks += 1
                self.exact_original_fallbacks += 1
                self.fallback_reasons[FallbackReason.MODEL_TIMEOUT.value] += 1
            if is_deadline:
                self.deadline_fallbacks += 1

    def record_eligibility_bypass(self, reason: str) -> None:
        with self._lock:
            self.total_compressions += 1
            self.skipped += 1
            self.eligibility_bypasses += 1
            self.eligibility_reasons[reason] += 1

    def record_upstream(self, latency_ms: float) -> None:
        with self._lock:
            self.upstream_latency_ms += latency_ms

    def record_proxy_request(self, latency_ms: float) -> None:
        with self._lock:
            self.proxy_request_latency_ms += latency_ms

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "schema_version": 1,
                "status": "ok",
                "cache_contract": self.cache_contract,
                "validator_contract": "exact_original_on_rejection",
                "total_compressions": self.total_compressions,
                "validated": self.validated,
                "validator_passes": self.validator_passes,
                "fallbacks": self.fallbacks,
                "exact_original_fallbacks": self.exact_original_fallbacks,
                "skipped": self.skipped,
                "cache_hits": self.cache_hits,
                "compression_latency_ms": round(self.compression_latency_ms, 3),
                "validation_latency_ms": round(self.validation_latency_ms, 3),
                "upstream_latency_ms": round(self.upstream_latency_ms, 3),
                "proxy_request_latency_ms": round(self.proxy_request_latency_ms, 3),
                "eligibility_bypasses": self.eligibility_bypasses,
                "deadline_fallbacks": self.deadline_fallbacks,
                "fallback_reasons": dict(sorted(self.fallback_reasons.items())),
                "eligibility_reasons": dict(sorted(self.eligibility_reasons.items())),
                "raw_content_recorded": False,
            }


class _TimingHttpClient:
    """Record upstream I/O time without inspecting request or response content."""

    def __init__(self, delegate: Any, telemetry: SafetyTelemetry) -> None:
        self._delegate = delegate
        self._telemetry = telemetry

    async def post(self, *args: Any, **kwargs: Any) -> Any:
        started = time.perf_counter()
        try:
            return await self._delegate.post(*args, **kwargs)
        finally:
            self._telemetry.record_upstream((time.perf_counter() - started) * 1000)

    @asynccontextmanager
    async def stream(self, *args: Any, **kwargs: Any) -> Any:
        started = time.perf_counter()
        try:
            async with self._delegate.stream(*args, **kwargs) as response:
                yield response
        finally:
            self._telemetry.record_upstream((time.perf_counter() - started) * 1000)

    async def aclose(self) -> None:
        await self._delegate.aclose()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._delegate, name)


def _required_signals(content: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(match.strip() for match in _CRITICAL_SIGNAL.findall(content)))


def build_validated_pipeline(
    config: Any,
    *,
    storage: Any,
    telemetry: SafetyTelemetry,
    eligibility: CompressionEligibilityGate | None = None,
) -> Any:
    """Build a PariTok pipeline that validates every transformed segment before forwarding."""
    try:
        from paritok.pipelines.compress import CompressionPipeline, CompressionResult
        from paritok.storage import content_hash
        from paritok.token_counter import count_tokens
    except ImportError as error:  # pragma: no cover - exercised by optional integration
        raise RuntimeError("Install the live extra before building the safe proxy") from error

    class ValidatedCompressionPipeline(CompressionPipeline):
        def __init__(self) -> None:
            super().__init__(config=config, storage=storage)
            self._contextops_validator = CompressionValidator()

        def compress(self, content: str, **kwargs: Any) -> Any:
            query = kwargs.get("query") or ""
            if hasattr(self.storage, "set_active_query"):
                self.storage.set_active_query(query)
            upstream_model = kwargs.get("upstream_model")
            original_tokens = (
                count_tokens(content, upstream_model)
                if upstream_model
                else count_tokens(content)
            )
            sid = content_hash(content)
            cache_hit = self.storage.get_cached_compressed(sid) is not None
            if eligibility is not None:
                bypass_reason = eligibility.reason(
                    original_tokens=original_tokens,
                    cache_hit=cache_hit,
                )
                if bypass_reason:
                    telemetry.record_eligibility_bypass(bypass_reason)
                    return CompressionResult(
                        compressed=content,
                        original_tokens=original_tokens,
                        compressed_tokens=original_tokens,
                        metadata={
                            "skipped": True,
                            "reason": f"contextops_ineligible:{bypass_reason}",
                            "contextops_eligibility": "bypass",
                        },
                    )
            started = time.perf_counter()
            result = super().compress(content, **kwargs)
            compression_ms = (time.perf_counter() - started) * 1000
            if eligibility is not None and not cache_hit:
                eligibility.observe_uncached(compression_ms)
            if result.metadata.get("skipped"):
                telemetry.record_skip(
                    str(result.metadata.get("reason", "unknown")),
                    compression_ms=compression_ms,
                )
                return result

            observed_cache_hit = bool(
                result.metadata.get("cache_hit") or result.metadata.get("path_shortcircuit")
            )
            available_references = (result.shadow_id,) if result.shadow_id else ()
            validation_started = time.perf_counter()
            decision = validate_or_fallback(
                self._contextops_validator,
                original=content,
                compressed=result.compressed,
                original_tokens=result.original_tokens,
                compressed_tokens=result.compressed_tokens,
                available_references=available_references,
                required_signals=_required_signals(content),
            )
            validation_ms = (time.perf_counter() - validation_started) * 1000
            if decision.used_compressed:
                result.metadata["contextops_validator"] = "pass"
                telemetry.record_pass(
                    cache_hit=observed_cache_hit,
                    compression_ms=compression_ms,
                    validation_ms=validation_ms,
                )
                return result

            reason = (
                decision.fallback_reason.value
                if decision.fallback_reason
                else FallbackReason.POLICY_BYPASS.value
            )
            if result.shadow_id and hasattr(self.storage, "invalidate_compressed"):
                self.storage.invalidate_compressed(result.shadow_id)
            telemetry.record_fallback(
                reason,
                cache_hit=observed_cache_hit,
                compression_ms=compression_ms,
                validation_ms=validation_ms,
            )
            return CompressionResult(
                compressed=content,
                original_tokens=result.original_tokens,
                compressed_tokens=result.original_tokens,
                metadata={
                    "skipped": True,
                    "reason": f"contextops_fallback:{reason}",
                    "contextops_validator": "fallback",
                },
            )

    return ValidatedCompressionPipeline()


def create_safe_proxy_app(
    *,
    openai_base_url: str = "https://api.openai.com",
    anthropic_base_url: str = "https://api.anthropic.com",
    config_path: str | None = None,
    cache_contract: str = "query_aware",
    storage_backend: str = "redis",
    redis_url: str | None = None,
    storage_encryption_key: str | None = None,
    tenant_id: str = "",
    session_id: str = "",
    storage_ttl_seconds: int = 86_400,
    compression_deadline_ms: float = 500.0,
    maximum_uncached_tokens: int = 3_000,
    http_client: Any = None,
) -> Any:
    """Create the real PariTok proxy with a ContextOps-owned observable safety boundary."""
    if cache_contract not in {"disabled", "query_aware"}:
        raise ValueError("safe proxy cache_contract must be disabled or query_aware")
    try:
        from paritok.middleware import wrapper
        from paritok.proxy import server
        import httpx
        from starlette.middleware.base import BaseHTTPMiddleware
        from starlette.responses import JSONResponse
        from starlette.routing import Route
    except ImportError as error:  # pragma: no cover - optional dependency boundary
        raise RuntimeError("Install the live extra before creating the safe proxy") from error

    telemetry = SafetyTelemetry(cache_contract=cache_contract)
    eligibility = CompressionEligibilityGate(
        latency_budget_ms=compression_deadline_ms,
        maximum_uncached_tokens=maximum_uncached_tokens,
    )
    storage = build_paritok_storage(
        cache_contract,
        backend=storage_backend,
        redis_url=redis_url,
        encryption_key=storage_encryption_key,
        tenant_id=tenant_id,
        session_id=session_id,
        ttl_seconds=storage_ttl_seconds,
    )
    base_engine = wrapper.ParitokEngine

    class ContextOpsParitokEngine(base_engine):
        def __init__(self, config: Any, storage_override: Any = None) -> None:
            del storage_override
            super().__init__(config=config, storage=storage)
            config.model.timeout = min(config.model.timeout, compression_deadline_ms / 1000)
            self.pipeline = build_validated_pipeline(
                config,
                storage=storage,
                telemetry=telemetry,
                eligibility=eligibility,
            )

    base_http_client = http_client or httpx.AsyncClient(timeout=120.0)
    timed_http_client = _TimingHttpClient(base_http_client, telemetry)
    wrapper.ParitokEngine = ContextOpsParitokEngine
    try:
        app = server.create_app(
            anthropic_base_url=anthropic_base_url,
            openai_base_url=openai_base_url,
            config_path=config_path,
            http_client=timed_http_client,
        )
    finally:
        wrapper.ParitokEngine = base_engine

    class RequestTimingMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Any, call_next: Any) -> Any:
            measured = request.method == "POST" and request.url.path.startswith("/v1/")
            started = time.perf_counter()
            try:
                return await call_next(request)
            finally:
                if measured:
                    telemetry.record_proxy_request((time.perf_counter() - started) * 1000)

    app.add_middleware(RequestTimingMiddleware)

    async def safety_stats(_request: Any) -> Any:
        payload = telemetry.snapshot()
        payload["eligibility"] = eligibility.snapshot()
        payload["context_store"] = storage.health()
        return JSONResponse(payload)

    app.routes.append(Route("/contextops/stats", safety_stats, methods=["GET"]))
    app.state.contextops_safety_telemetry = telemetry
    app.state.contextops_storage = storage
    return app


def run_safe_proxy(
    *,
    host: str = "127.0.0.1",
    port: int = 8080,
    openai_base_url: str = "https://api.openai.com",
    anthropic_base_url: str = "https://api.anthropic.com",
    config_path: str | None = None,
    cache_contract: str = "query_aware",
    storage_backend: str = "redis",
    redis_url: str | None = None,
    storage_encryption_key: str | None = None,
    tenant_id: str = "",
    session_id: str = "",
    storage_ttl_seconds: int = 86_400,
    compression_deadline_ms: float = 500.0,
    maximum_uncached_tokens: int = 3_000,
    log_level: str = "info",
) -> None:
    """Start the validated external HTTP proxy."""
    try:
        import uvicorn
        from paritok.proxy.server import _preflight_backend
    except ImportError as error:  # pragma: no cover - CLI optional dependency boundary
        raise RuntimeError("Install the live extra before starting the safe proxy") from error

    _preflight_backend(config_path)
    app = create_safe_proxy_app(
        openai_base_url=openai_base_url,
        anthropic_base_url=anthropic_base_url,
        config_path=config_path,
        cache_contract=cache_contract,
        storage_backend=storage_backend,
        redis_url=redis_url,
        storage_encryption_key=storage_encryption_key,
        tenant_id=tenant_id,
        session_id=session_id,
        storage_ttl_seconds=storage_ttl_seconds,
        compression_deadline_ms=compression_deadline_ms,
        maximum_uncached_tokens=maximum_uncached_tokens,
    )
    print(f"ContextOps safe PariTok proxy starting on {host}:{port}")
    print(f"  Cache contract: {cache_contract}")
    print(f"  Context store:  {storage_backend} (ttl={storage_ttl_seconds}s)")
    print(
        "  Compression:    "
        f"deadline={compression_deadline_ms:g}ms, "
        f"max_uncached_tokens={maximum_uncached_tokens}"
    )
    print(f"  Safety stats:   http://{host}:{port}/contextops/stats")
    uvicorn.run(app, host=host, port=port, log_level=log_level)
