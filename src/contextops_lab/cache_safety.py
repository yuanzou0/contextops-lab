"""Fail-closed cache contracts and provider-free query-sensitivity diagnostics."""

from __future__ import annotations

import hashlib
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


def build_paritok_storage(contract: str) -> Any:
    """Build an isolated storage backend for a declared cache contract."""
    if contract not in {"content_only", "disabled", "query_aware"}:
        raise ValueError(f"Unsupported diagnostic cache contract: {contract}")
    try:
        from paritok.storage import MemoryShadowStorage
    except ImportError as error:
        raise RuntimeError("Install the live extra before building PariTok storage") from error

    class CacheDisabledStorage(MemoryShadowStorage):
        def cache_compressed(self, shadow_id: str, compressed: str) -> None:
            del shadow_id, compressed

        def get_cached_compressed(self, shadow_id: str) -> None:
            del shadow_id
            return None

    class QueryAwareStorage(MemoryShadowStorage):
        def __init__(self) -> None:
            super().__init__()
            self._active_query_hash = "unset"

        def set_active_query(self, query: str) -> None:
            self._active_query_hash = hashlib.sha256(query.encode()).hexdigest()

        def _cache_key(self, shadow_id: str) -> str:
            return f"{shadow_id}:{self._active_query_hash}"

        def cache_compressed(self, shadow_id: str, compressed: str) -> None:
            super().cache_compressed(self._cache_key(shadow_id), compressed)

        def get_cached_compressed(self, shadow_id: str) -> str | None:
            return super().get_cached_compressed(self._cache_key(shadow_id))

    if contract == "content_only":
        return MemoryShadowStorage()
    if contract == "disabled":
        return CacheDisabledStorage()
    return QueryAwareStorage()


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
