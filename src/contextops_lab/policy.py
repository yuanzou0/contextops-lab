"""Evidence-gated rollout policy generation and runtime lookup."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Iterable

from .analytics import SegmentResult, segment_events
from .models import RequestEvent
from .strategy import CompressionMode


@dataclass(frozen=True, slots=True)
class PolicyThresholds:
    minimum_paired_tasks: int = 5
    maximum_success_degradation: float = 0.02
    minimum_cost_improvement: float = 0.05
    maximum_p95_latency_increase_ms: float = 500.0
    maximum_fallback_rate: float = 0.25
    require_zero_silent_failures: bool = True


@dataclass(frozen=True, slots=True)
class RolloutRule:
    dimension: str
    value: str
    mode: CompressionMode
    reasons: tuple[str, ...]
    metrics: SegmentResult

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["mode"] = self.mode.value
        return payload


def _select_mode(segment: SegmentResult, thresholds: PolicyThresholds) -> tuple[CompressionMode, tuple[str, ...]]:
    blockers: list[str] = []
    cautions: list[str] = []
    if segment.paired_tasks < thresholds.minimum_paired_tasks:
        blockers.append("insufficient_sample")
    if segment.success_delta_ci_low < -thresholds.maximum_success_degradation:
        blockers.append("success_non_inferiority_failed")
    if not segment.treatment_cost_per_success_defined:
        blockers.append("no_successful_treatment_tasks")
    elif segment.cost_improvement_rate < thresholds.minimum_cost_improvement:
        blockers.append("cost_improvement_below_threshold")
    if (
        thresholds.require_zero_silent_failures
        and segment.silent_failures > 0
    ):
        blockers.append("silent_failure_detected")
    if segment.p95_latency_delta_ms > thresholds.maximum_p95_latency_increase_ms:
        cautions.append("latency_budget_exceeded")
    if segment.fallback_rate > thresholds.maximum_fallback_rate:
        cautions.append("fallback_rate_high")
    if blockers:
        return CompressionMode.OFF, tuple(blockers + cautions)
    if cautions or segment.value in {"edit_critical", "intent_pivot"}:
        reason = cautions or ["risk_sensitive_workload"]
        return CompressionMode.CONSERVATIVE, tuple(reason)
    return CompressionMode.BALANCED, ("evidence_gate_passed",)


def generate_rollout_policy(
    events: Iterable[RequestEvent],
    *,
    thresholds: PolicyThresholds | None = None,
    evidence_label: str,
) -> dict:
    active_thresholds = thresholds or PolicyThresholds()
    segments = segment_events(events, ("task_type",))
    rules = []
    for segment in segments:
        mode, reasons = _select_mode(segment, active_thresholds)
        rules.append(RolloutRule(segment.dimension, segment.value, mode, reasons, segment))
    production_ready = evidence_label == "production" and any(
        rule.mode is not CompressionMode.OFF for rule in rules
    )
    return {
        "schema_version": 1,
        "generated": date.today().isoformat(),
        "evidence_label": evidence_label,
        "production_ready": production_ready,
        "default_mode": CompressionMode.OFF.value,
        "thresholds": asdict(active_thresholds),
        "rules": [rule.to_dict() for rule in rules],
    }


def write_policy(policy: dict, path: str | Path) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(policy, indent=2, sort_keys=True) + "\n", encoding="utf-8")


class PolicyEngine:
    def __init__(self, policy: dict):
        self.policy = policy
        self._rules = {
            (rule["dimension"], rule["value"]): CompressionMode(rule["mode"])
            for rule in policy.get("rules", [])
        }

    @classmethod
    def from_path(cls, path: str | Path) -> "PolicyEngine":
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))

    def mode_for(self, *, task_type: str) -> CompressionMode:
        if not self.policy.get("production_ready", False):
            return CompressionMode.OFF
        return self._rules.get(
            ("task_type", task_type),
            CompressionMode(self.policy.get("default_mode", "off")),
        )
