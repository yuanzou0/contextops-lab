"""Fail-closed cache contracts and provider-free query-sensitivity diagnostics."""

from __future__ import annotations

import hashlib
from contextvars import ContextVar
from dataclasses import asdict, dataclass
from importlib.metadata import PackageNotFoundError, version
from typing import Any, Sequence
from unittest.mock import patch

from .workloads import WorkloadScenario


CACHE_CONTRACTS = frozenset({"unverified", "disabled", "query_aware"})


@dataclass(frozen=True, slots=True)
class CacheSafetyDecision:
    allowed: bool
    rollout_eligible: bool
    contract: str
    intent_drift_present: bool
    research_override: bool
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["reasons"] = list(self.reasons)
        return payload


def decide_cache_safety(
    scenarios: Sequence[WorkloadScenario],
    *,
    contract: str,
    allow_unsafe_experiment: bool = False,
) -> CacheSafetyDecision:
    """Gate multi-turn execution when the proxy cache contract is not verified.

    ContextOps' staged workload changes from an intermediate acknowledgement intent to a final
    recall intent whenever ``session_turns > 1``. A content-only or unknown cache can therefore
    reuse a transformation created for the wrong intent.
    """
    if contract not in CACHE_CONTRACTS:
        raise ValueError(f"Unsupported compression cache contract: {contract}")
    drift = any(scenario.session_turns > 1 for scenario in scenarios)
    verified = contract in {"disabled", "query_aware"}
    if not drift:
        return CacheSafetyDecision(True, True, contract, False, False, ("single_intent",))
    if verified:
        return CacheSafetyDecision(True, True, contract, True, False, ("verified_contract",))
    if allow_unsafe_experiment:
        return CacheSafetyDecision(
            True,
            False,
            contract,
            True,
            True,
            ("query_sensitive_cache_risk", "research_only_override"),
        )
    return CacheSafetyDecision(
        False,
        False,
        contract,
        True,
        False,
        ("query_sensitive_cache_risk", "cache_contract_unverified"),
    )


class _IntentModel:
    """Deterministic stand-in that makes the active query observable in its output."""

    def __init__(self) -> None:
        self.calls = 0

    def compress(self, content: str, *, query: str | None = None, **_: Any) -> str:
        del content
        self.calls += 1
        digest = hashlib.sha256((query or "").encode()).hexdigest()[:12]
        return f"intent-summary::{digest}"


def _pipeline_result(pipeline: Any, model: _IntentModel, content: str, queries: Sequence[str]) -> dict:
    results = []
    for query in queries:
        if hasattr(pipeline.storage, "set_active_query"):
            pipeline.storage.set_active_query(query)
        result = pipeline.compress(content, query=query, kind="log_output")
        results.append(
            {
                "cache_hit": bool(result.metadata.get("cache_hit", False)),
                "output_sha256": hashlib.sha256(result.compressed.encode()).hexdigest(),
            }
        )
    return {
        "model_calls": model.calls,
        "results": results,
        "outputs_change_with_query": results[0]["output_sha256"] != results[1]["output_sha256"],
    }


def build_paritok_storage(
    contract: str,
    *,
    backend: str = "memory",
    redis_url: str | None = None,
    encryption_key: str | None = None,
    tenant_id: str = "development",
    session_id: str = "development",
    ttl_seconds: int = 86_400,
    base_storage: Any = None,
) -> Any:
    """Build isolated storage for a declared cache and durability contract.

    ``memory`` is an explicit test/development mode. The live safe-proxy command selects the
    fail-closed ``redis`` backend by default.
    """
    if contract not in {"content_only", "disabled", "query_aware"}:
        raise ValueError(f"Unsupported diagnostic cache contract: {contract}")
    if backend not in {"memory", "redis"}:
        raise ValueError(f"Unsupported context storage backend: {backend}")
    if base_storage is None and backend == "memory":
        try:
            from paritok.storage import MemoryShadowStorage
        except ImportError as error:
            raise RuntimeError("Install the live extra before building PariTok storage") from error
        base_storage = MemoryShadowStorage()
    elif base_storage is None:
        from .context_store import DurableRedisShadowStorage

        if not encryption_key:
            raise ValueError("Redis context storage requires an encryption key")
        base_storage = DurableRedisShadowStorage.from_url(
            redis_url or "",
            encryption_key=encryption_key,
            tenant_id=tenant_id,
            session_id=session_id,
            ttl_seconds=ttl_seconds,
        )

    class DelegatingStorage:
        def __init__(self, storage: Any) -> None:
            self._storage = storage

        def store(self, content: str) -> str:
            return self._storage.store(content)

        def retrieve(self, shadow_id: str) -> str | None:
            return self._storage.retrieve(shadow_id)

        def has(self, shadow_id: str) -> bool:
            return self._storage.has(shadow_id)

        def set_shadow_for_path(self, path: str, shadow_id: str) -> None:
            self._storage.set_shadow_for_path(path, shadow_id)

        def get_shadow_for_path(self, path: str) -> str | None:
            return self._storage.get_shadow_for_path(path)

        def get_shadows_for_path(self, path: str) -> list[str]:
            method = getattr(self._storage, "get_shadows_for_path", None)
            if method:
                return method(path)
            shadow_id = self.get_shadow_for_path(path)
            return [shadow_id] if shadow_id else []

        def get_path_for_shadow(self, shadow_id: str) -> str | None:
            method = getattr(self._storage, "get_path_for_shadow", None)
            return method(shadow_id) if method else None

        def pin_source(self, path: str) -> None:
            method = getattr(self._storage, "pin_source", None)
            if method:
                method(path)

        def is_source_pinned(self, path: str) -> bool:
            method = getattr(self._storage, "is_source_pinned", None)
            return bool(method(path)) if method else False

        def pin_shadow(self, shadow_id: str) -> None:
            method = getattr(self._storage, "pin_shadow", None)
            if method:
                method(shadow_id)

        def is_shadow_pinned(self, shadow_id: str) -> bool:
            method = getattr(self._storage, "is_shadow_pinned", None)
            return bool(method(shadow_id)) if method else False

        def retrieve_with_status(self, shadow_id: str) -> Any:
            method = getattr(self._storage, "retrieve_with_status", None)
            return method(shadow_id) if method else None

        def health(self) -> dict[str, Any]:
            method = getattr(self._storage, "health", None)
            return method() if method else {"status": "ok", "backend": "memory"}

    class CacheDisabledStorage(DelegatingStorage):
        def cache_compressed(self, shadow_id: str, compressed: str) -> None:
            del shadow_id, compressed

        def get_cached_compressed(self, shadow_id: str) -> None:
            del shadow_id
            return None

        def invalidate_compressed(self, shadow_id: str) -> None:
            del shadow_id

    class QueryAwareStorage(DelegatingStorage):
        def __init__(self, storage: Any) -> None:
            super().__init__(storage)
            self._active_query_hash: ContextVar[str] = ContextVar(
                "contextops_active_query_hash", default="unset"
            )

        def set_active_query(self, query: str) -> None:
            self._active_query_hash.set(hashlib.sha256(query.encode()).hexdigest())

        def _cache_key(self, shadow_id: str) -> str:
            return f"{shadow_id}:{self._active_query_hash.get()}"

        def cache_compressed(self, shadow_id: str, compressed: str) -> None:
            self._storage.cache_compressed(self._cache_key(shadow_id), compressed)

        def get_cached_compressed(self, shadow_id: str) -> str | None:
            return self._storage.get_cached_compressed(self._cache_key(shadow_id))

        def invalidate_compressed(self, shadow_id: str) -> None:
            method = getattr(self._storage, "invalidate_compressed", None)
            if method:
                method(self._cache_key(shadow_id))
            elif hasattr(self._storage, "_compressed_cache"):
                self._storage._compressed_cache.pop(self._cache_key(shadow_id), None)

    if contract == "content_only":
        return base_storage
    if contract == "disabled":
        return CacheDisabledStorage(base_storage)
    return QueryAwareStorage(base_storage)


def audit_installed_paritok_cache() -> dict[str, Any]:
    """Run a controlled, provider-free intervention against the installed PariTok pipeline.

    The compression model is replaced by a deterministic local stand-in. The audit therefore
    tests cache-key behavior without Ollama or an upstream provider; it does not retest semantic
    compression quality or prove that cache reuse was the sole cause of the Wave A failures.
    """
    try:
        from paritok.config import ParitokConfig
        from paritok.pipelines.compress import CompressionPipeline
    except ImportError as error:
        raise RuntimeError("Install the live extra before running cache-contract-audit") from error

    config = ParitokConfig()
    config.compression.min_tokens = 0
    config.compression.max_tokens = 50_000
    config.compression.refusal_threshold = 0.0
    content = "stable historical tool result with CRITICAL_SIGNAL " * 200
    intermediate = "INTERMEDIATE_TASK: Reply only with CONTEXT_RECORDED."
    final = "FINAL_TASK: Return the three CRITICAL_SIGNAL values exactly."

    def run(storage: Any, queries: Sequence[str]) -> dict:
        pipeline = CompressionPipeline(config=config, storage=storage)
        model = _IntentModel()
        pipeline._model = model
        return _pipeline_result(pipeline, model, content, queries)

    # Tokenizer assets may be downloaded lazily by the optional dependency. Cache behavior does
    # not depend on tokenizer fidelity, so keep this diagnostic strictly offline and deterministic.
    with patch(
        "paritok.pipelines.compress.count_tokens",
        side_effect=lambda text, *_: max(1, len(text) // 4),
    ):
        content_only = run(build_paritok_storage("content_only"), (intermediate, final))
        disabled = run(build_paritok_storage("disabled"), (intermediate, final))
        query_aware = run(build_paritok_storage("query_aware"), (intermediate, final, final))
    try:
        package_version = version("paritok")
    except PackageNotFoundError:
        package_version = "unknown"

    observed_risk = (
        content_only["model_calls"] == 1
        and content_only["results"][1]["cache_hit"]
        and not content_only["outputs_change_with_query"]
    )
    interventions_pass = (
        disabled["model_calls"] == 2
        and disabled["outputs_change_with_query"]
        and query_aware["model_calls"] == 2
        and query_aware["outputs_change_with_query"]
        and query_aware["results"][2]["cache_hit"]
    )
    return {
        "schema_version": 1,
        "evidence_label": "provider_free_controlled_cache_contract_audit",
        "paritok_version": package_version,
        "independent_variable": "cache_contract",
        "controlled_variables": ["content", "pipeline", "compression_model", "configuration"],
        "query_changed": True,
        "content_only": content_only,
        "cache_disabled": disabled,
        "query_aware": query_aware,
        "content_only_query_reuse_observed": observed_risk,
        "isolation_interventions_passed": interventions_pass,
        "rollout_decision": "off" if observed_risk else "requires_review",
        "claim_boundary": (
            "Confirms that the installed pipeline can reuse a query-dependent transformation "
            "after intent changes under controlled conditions. It supports, but does not alone "
            "prove, the Wave A root-cause attribution."
        ),
    }
