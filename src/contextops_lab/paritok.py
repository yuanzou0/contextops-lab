"""PariTok proxy health and cumulative telemetry client."""

from __future__ import annotations

import json
import urllib.request
from collections import Counter
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProxyStats:
    total_requests: int
    input_tokens_original: int
    input_tokens_compressed: int
    tokens_saved: int
    estimated_cost_saved_usd: float

    @classmethod
    def from_dict(cls, payload: dict) -> "ProxyStats":
        saved_cost = payload.get("estimated_cost_saved_usd", 0.0)
        if isinstance(saved_cost, str):
            saved_cost = saved_cost.strip().removeprefix("$") or "0"
        return cls(
            total_requests=int(payload.get("total_requests", 0)),
            input_tokens_original=int(payload.get("input_tokens_original", 0)),
            input_tokens_compressed=int(payload.get("input_tokens_compressed", 0)),
            tokens_saved=int(payload.get("tokens_saved", 0)),
            estimated_cost_saved_usd=float(saved_cost),
        )

    def delta(self, previous: "ProxyStats") -> "ProxyStats":
        values = {
            field: getattr(self, field) - getattr(previous, field)
            for field in (
                "total_requests",
                "input_tokens_original",
                "input_tokens_compressed",
                "tokens_saved",
                "estimated_cost_saved_usd",
            )
        }
        if any(value < 0 for value in values.values()):
            raise ValueError("PariTok cumulative stats moved backwards during the experiment")
        return ProxyStats(**values)


class PariTokGateway:
    def __init__(self, health_url: str, stats_url: str, *, timeout_seconds: float = 10.0):
        self.health_url = health_url
        self.stats_url = stats_url
        self.timeout_seconds = timeout_seconds

    def _get(self, url: str) -> dict:
        request = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))

    def health(self) -> dict:
        payload = self._get(self.health_url)
        if str(payload.get("status", "")).lower() not in {"ok", "healthy"}:
            raise RuntimeError(f"PariTok health check failed: {payload}")
        return payload

    def stats(self) -> ProxyStats:
        return ProxyStats.from_dict(self._get(self.stats_url))

    def require_compression_model(self, models_url: str, model: str) -> dict:
        payload = self._get(models_url)
        rows = payload.get("data") or payload.get("models") or []
        identifiers = {
            str(row.get("id") or row.get("name") or row.get("model"))
            for row in rows
        }
        accepted = {model, f"{model}:latest", f"paritok/{model}", f"paritok/{model}:latest"}
        if not identifiers & accepted:
            raise RuntimeError(
                f"Compression model {model!r} is not available at {models_url}; "
                f"observed={sorted(identifiers)}"
            )
        return payload


@dataclass(frozen=True, slots=True)
class ContextOpsSafetyStats:
    cache_contract: str
    total_compressions: int
    validated: int
    validator_passes: int
    fallbacks: int
    exact_original_fallbacks: int
    skipped: int
    cache_hits: int
    compression_latency_ms: float
    fallback_reasons: dict[str, int]

    @classmethod
    def from_dict(cls, payload: dict) -> "ContextOpsSafetyStats":
        return cls(
            cache_contract=str(payload.get("cache_contract", "unverified")),
            total_compressions=int(payload.get("total_compressions", 0)),
            validated=int(payload.get("validated", 0)),
            validator_passes=int(payload.get("validator_passes", 0)),
            fallbacks=int(payload.get("fallbacks", 0)),
            exact_original_fallbacks=int(payload.get("exact_original_fallbacks", 0)),
            skipped=int(payload.get("skipped", 0)),
            cache_hits=int(payload.get("cache_hits", 0)),
            compression_latency_ms=float(payload.get("compression_latency_ms", 0.0)),
            fallback_reasons={
                str(reason): int(count)
                for reason, count in payload.get("fallback_reasons", {}).items()
            },
        )

    def delta(self, previous: "ContextOpsSafetyStats") -> "ContextOpsSafetyStats":
        if self.cache_contract != previous.cache_contract:
            raise ValueError("ContextOps safety cache contract changed during the experiment")
        scalar_fields = (
            "total_compressions",
            "validated",
            "validator_passes",
            "fallbacks",
            "exact_original_fallbacks",
            "skipped",
            "cache_hits",
            "compression_latency_ms",
        )
        values = {
            name: getattr(self, name) - getattr(previous, name)
            for name in scalar_fields
        }
        reasons = Counter(self.fallback_reasons)
        reasons.subtract(previous.fallback_reasons)
        if any(value < 0 for value in values.values()) or any(
            count < 0 for count in reasons.values()
        ):
            raise ValueError("ContextOps safety counters moved backwards during the experiment")
        return ContextOpsSafetyStats(
            cache_contract=self.cache_contract,
            fallback_reasons={key: value for key, value in reasons.items() if value},
            **values,
        )


class ContextOpsSafetyGateway:
    def __init__(self, stats_url: str, *, timeout_seconds: float = 10.0):
        self.stats_url = stats_url
        self.timeout_seconds = timeout_seconds

    def _get(self) -> dict:
        request = urllib.request.Request(
            self.stats_url,
            headers={"Accept": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))

    def health(self, *, expected_contract: str) -> dict:
        payload = self._get()
        if str(payload.get("status", "")).lower() != "ok":
            raise RuntimeError(f"ContextOps safety boundary is unhealthy: {payload}")
        if payload.get("cache_contract") != expected_contract:
            raise RuntimeError(
                "ContextOps safety cache contract mismatch: "
                f"expected={expected_contract}, observed={payload.get('cache_contract')}"
            )
        if payload.get("validator_contract") != "exact_original_on_rejection":
            raise RuntimeError("ContextOps exact-original fallback contract is not active")
        return payload

    def stats(self) -> ContextOpsSafetyStats:
        return ContextOpsSafetyStats.from_dict(self._get())
