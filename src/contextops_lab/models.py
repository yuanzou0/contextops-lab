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
        }
        invalid = [name for name, value in non_negative.items() if value < 0]
        if invalid:
            raise ValueError(f"Negative event values are not allowed: {', '.join(invalid)}")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["arm"] = self.arm.value
        return payload
