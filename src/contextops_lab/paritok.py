"""PariTok proxy health and cumulative telemetry client."""

from __future__ import annotations

import json
import urllib.request
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
