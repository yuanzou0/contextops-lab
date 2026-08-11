"""Typed, privacy-safe experiment events."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any


class ExperimentArm(str, Enum):
    BASELINE = "baseline"
    COMPRESSED = "compressed"


@dataclass(frozen=True, slots=True)
class RequestEvent:
    experiment_id: str
    task_id: str
    session_id: str
    turn_id: int
    arm: ExperimentArm
    treatment_name: str
    model: str
    task_type: str
    language: str
    repo_size: int
    tool_count: int
    session_length: int
    original_tokens: int
    compressed_tokens: int
    recalled_tokens: int
    compression_latency_ms: float
    total_latency_ms: float
    validator_result: str
    fallback_reason: str | None
    task_success: bool
    tests_passed: bool | None
    manual_intervention: bool
    estimated_total_cost: float
    schema_version: int = 3
    failure_reason: str | None = None
    upstream_error: str | None = None
    silent_failure: bool = False
    recorded_at: str | None = None
    experiment_config_version: str = "v1"
    pricing_version: str = "unspecified"
    endpoint_role: str = "unspecified"
    provider_input_tokens: int = 0
    provider_output_tokens: int = 0
    proxy_request_count: int = 0
    proxy_tokens_saved: int = 0
    config_sha256: str = ""

    def __post_init__(self) -> None:
        non_negative = {
            "turn_id": self.turn_id,
            "repo_size": self.repo_size,
            "tool_count": self.tool_count,
            "session_length": self.session_length,
            "original_tokens": self.original_tokens,
            "compressed_tokens": self.compressed_tokens,
            "recalled_tokens": self.recalled_tokens,
            "compression_latency_ms": self.compression_latency_ms,
            "total_latency_ms": self.total_latency_ms,
            "estimated_total_cost": self.estimated_total_cost,
            "schema_version": self.schema_version,
            "provider_input_tokens": self.provider_input_tokens,
            "provider_output_tokens": self.provider_output_tokens,
            "proxy_request_count": self.proxy_request_count,
            "proxy_tokens_saved": self.proxy_tokens_saved,
        }
        invalid = [name for name, value in non_negative.items() if value < 0]
        if invalid:
            raise ValueError(f"Negative event values are not allowed: {', '.join(invalid)}")
        if self.schema_version < 1:
            raise ValueError("schema_version must be positive")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["arm"] = self.arm.value
        return payload
