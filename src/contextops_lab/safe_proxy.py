"""ContextOps-owned safety boundary around the external PariTok HTTP proxy."""

from __future__ import annotations

import re
import threading
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from .cache_safety import build_paritok_storage
from .fallback import validate_or_fallback
from .validator import CompressionValidator, FallbackReason


_CRITICAL_SIGNAL = re.compile(r"(?m)^CRITICAL_SIGNAL:\s*(.+?)\s*$")


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
    fallback_reasons: Counter[str] = field(default_factory=Counter)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def record_pass(self, *, cache_hit: bool, latency_ms: float) -> None:
        with self._lock:
            self.total_compressions += 1
            self.validated += 1
            self.validator_passes += 1
            self.cache_hits += int(cache_hit)
            self.compression_latency_ms += latency_ms

    def record_fallback(self, reason: str, *, cache_hit: bool, latency_ms: float) -> None:
        with self._lock:
            self.total_compressions += 1
            self.validated += 1
            self.fallbacks += 1
            self.exact_original_fallbacks += 1
            self.cache_hits += int(cache_hit)
            self.compression_latency_ms += latency_ms
            self.fallback_reasons[reason] += 1

    def record_skip(self, reason: str, *, latency_ms: float) -> None:
        is_backend_error = reason.startswith("backend_error:")
        with self._lock:
            self.total_compressions += 1
            self.skipped += 1
            self.compression_latency_ms += latency_ms
            if is_backend_error:
                self.fallbacks += 1
                self.exact_original_fallbacks += 1
                self.fallback_reasons[FallbackReason.MODEL_TIMEOUT.value] += 1

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
                "fallback_reasons": dict(sorted(self.fallback_reasons.items())),
                "raw_content_recorded": False,
            }


def _required_signals(content: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(match.strip() for match in _CRITICAL_SIGNAL.findall(content)))


def build_validated_pipeline(
    config: Any,
    *,
    storage: Any,
    telemetry: SafetyTelemetry,
) -> Any:
    """Build a PariTok pipeline that validates every transformed segment before forwarding."""
    try:
        from paritok.pipelines.compress import CompressionPipeline, CompressionResult
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
            started = time.perf_counter()
            result = super().compress(content, **kwargs)
            elapsed_ms = (time.perf_counter() - started) * 1000
            if result.metadata.get("skipped"):
                telemetry.record_skip(str(result.metadata.get("reason", "unknown")), latency_ms=elapsed_ms)
                return result

            cache_hit = bool(
                result.metadata.get("cache_hit") or result.metadata.get("path_shortcircuit")
            )
            available_references = (result.shadow_id,) if result.shadow_id else ()
            decision = validate_or_fallback(
                self._contextops_validator,
                original=content,
                compressed=result.compressed,
                original_tokens=result.original_tokens,
                compressed_tokens=result.compressed_tokens,
                available_references=available_references,
                required_signals=_required_signals(content),
            )
            if decision.used_compressed:
                result.metadata["contextops_validator"] = "pass"
                telemetry.record_pass(cache_hit=cache_hit, latency_ms=elapsed_ms)
                return result

            reason = (
                decision.fallback_reason.value
                if decision.fallback_reason
                else FallbackReason.POLICY_BYPASS.value
            )
            if result.shadow_id and hasattr(self.storage, "invalidate_compressed"):
                self.storage.invalidate_compressed(result.shadow_id)
            telemetry.record_fallback(reason, cache_hit=cache_hit, latency_ms=elapsed_ms)
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
    http_client: Any = None,
) -> Any:
    """Create the real PariTok proxy with a ContextOps-owned observable safety boundary."""
    if cache_contract not in {"disabled", "query_aware"}:
        raise ValueError("safe proxy cache_contract must be disabled or query_aware")
    try:
        from paritok.middleware import wrapper
        from paritok.proxy import server
        from starlette.responses import JSONResponse
        from starlette.routing import Route
    except ImportError as error:  # pragma: no cover - optional dependency boundary
        raise RuntimeError("Install the live extra before creating the safe proxy") from error

    telemetry = SafetyTelemetry(cache_contract=cache_contract)
    storage = build_paritok_storage(cache_contract)
    base_engine = wrapper.ParitokEngine

    class ContextOpsParitokEngine(base_engine):
        def __init__(self, config: Any, storage_override: Any = None) -> None:
            del storage_override
            super().__init__(config=config, storage=storage)
            self.pipeline = build_validated_pipeline(
                config,
                storage=storage,
                telemetry=telemetry,
            )

    wrapper.ParitokEngine = ContextOpsParitokEngine
    try:
        app = server.create_app(
            anthropic_base_url=anthropic_base_url,
            openai_base_url=openai_base_url,
            config_path=config_path,
            http_client=http_client,
        )
    finally:
        wrapper.ParitokEngine = base_engine

    async def safety_stats(_request: Any) -> Any:
        return JSONResponse(telemetry.snapshot())

    app.routes.append(Route("/contextops/stats", safety_stats, methods=["GET"]))
    app.state.contextops_safety_telemetry = telemetry
    return app


def run_safe_proxy(
    *,
    host: str = "127.0.0.1",
    port: int = 8080,
    openai_base_url: str = "https://api.openai.com",
    anthropic_base_url: str = "https://api.anthropic.com",
    config_path: str | None = None,
    cache_contract: str = "query_aware",
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
    )
    print(f"ContextOps safe PariTok proxy starting on {host}:{port}")
    print(f"  Cache contract: {cache_contract}")
    print(f"  Safety stats:   http://{host}:{port}/contextops/stats")
    uvicorn.run(app, host=host, port=port, log_level=log_level)
