"""Versioned, secret-free configuration for live paired experiments."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlparse


def _http_url(value: str, field: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"{field} must be an HTTP(S) URL")
    return value


@dataclass(frozen=True, slots=True)
class LiveExperimentConfig:
    experiment_id: str
    config_version: str
    model: str
    baseline_endpoint: str
    paritok_endpoint: str
    paritok_health_url: str
    paritok_stats_url: str
    api_key_environment: str
    pricing_version: str
    input_cost_per_million: float
    output_cost_per_million: float
    temperature: float = 0.0
    timeout_seconds: float = 120.0
    max_retries: int = 2
    require_proxy_telemetry: bool = True
    evidence_label: str = "live_unreviewed"

    def __post_init__(self) -> None:
        for field in (
            "baseline_endpoint",
            "paritok_endpoint",
            "paritok_health_url",
            "paritok_stats_url",
        ):
            _http_url(getattr(self, field), field)
        if not self.experiment_id or not self.config_version or not self.model:
            raise ValueError("experiment_id, config_version, and model are required")
        if self.temperature < 0 or self.timeout_seconds <= 0 or self.max_retries < 0:
            raise ValueError("temperature, timeout_seconds, and max_retries are invalid")
        if self.input_cost_per_million < 0 or self.output_cost_per_million < 0:
            raise ValueError("pricing values cannot be negative")

    @property
    def api_key(self) -> str | None:
        return os.environ.get(self.api_key_environment) if self.api_key_environment else None

    def public_dict(self) -> dict:
        return asdict(self)


def load_live_config(path: str | Path) -> tuple[LiveExperimentConfig, str]:
    source = Path(path)
    raw = source.read_bytes()
    payload = json.loads(raw)
    config = LiveExperimentConfig(**payload)
    return config, hashlib.sha256(raw).hexdigest()
