"""Workload segmentation and paired decision metrics."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from math import sqrt
from typing import Callable, Iterable

from .metrics import summarize
from .models import ExperimentArm, RequestEvent


@dataclass(frozen=True, slots=True)
class SegmentResult:
    dimension: str
    value: str
    paired_tasks: int
    baseline_success_rate: float
    compressed_success_rate: float
    success_rate_delta: float
    success_delta_ci_low: float
    success_delta_ci_high: float
    baseline_cost_per_success: float | None
    compressed_cost_per_success: float | None
    cost_improvement_rate: float
    treatment_cost_per_success_defined: bool
    baseline_p95_latency_ms: float
    compressed_p95_latency_ms: float
    p95_latency_delta_ms: float
    fallback_rate: float
    silent_failures: int

    def to_dict(self) -> dict:
        return asdict(self)


def _repo_size(value: int) -> str:
    if value < 25_000:
        return "small"
    if value <= 50_000:
        return "medium"
    return "large"


def _session_length(value: int) -> str:
    if value <= 8:
        return "short"
    if value <= 14:
        return "medium"
    return "long"


def _tool_density(value: int) -> str:
    if value <= 20:
        return "light"
    if value <= 35:
        return "medium"
    return "heavy"


SEGMENTERS: dict[str, Callable[[RequestEvent], str]] = {
    "task_type": lambda event: event.task_type,
    "language": lambda event: event.language,
    "repo_size": lambda event: _repo_size(event.repo_size),
    "session_length": lambda event: _session_length(event.session_length),
    "tool_density": lambda event: _tool_density(event.tool_count),
    "model": lambda event: event.model,
    "context_band": lambda event: f"{event.context_tokens // 1000}K"
    if event.context_tokens
    else "legacy",
    "risk_level": lambda event: event.risk_level,
}


def _safe_improvement(baseline: float, treatment: float) -> float:
    if baseline == float("inf") or treatment == float("inf") or baseline == 0:
        return 0.0
    return (baseline - treatment) / baseline


def _wilson(successes: int, total: int) -> tuple[float, float]:
    if not total:
        return 0.0, 1.0
    z = 1.96
    probability = successes / total
    denominator = 1 + z * z / total
    center = (probability + z * z / (2 * total)) / denominator
    margin = (
        z
        * sqrt(probability * (1 - probability) / total + z * z / (4 * total * total))
        / denominator
    )
    return max(0.0, center - margin), min(1.0, center + margin)


def _success_difference_interval(events: list[RequestEvent]) -> tuple[float, float]:
    terminal = [event for event in events if event.is_terminal_turn]
    baseline = [event for event in terminal if event.arm is ExperimentArm.BASELINE]
    compressed = [event for event in terminal if event.arm is ExperimentArm.COMPRESSED]
    baseline_low, baseline_high = _wilson(sum(event.task_success for event in baseline), len(baseline))
    compressed_low, compressed_high = _wilson(
        sum(event.task_success for event in compressed), len(compressed)
    )
    return compressed_low - baseline_high, compressed_high - baseline_low


def segment_events(
    events: Iterable[RequestEvent], dimensions: Iterable[str] = ("task_type",)
) -> list[SegmentResult]:
    rows = list(events)
    results: list[SegmentResult] = []
    for dimension in dimensions:
        if dimension not in SEGMENTERS:
            raise ValueError(f"Unknown segmentation dimension: {dimension}")
        segmenter = SEGMENTERS[dimension]
        values = sorted({segmenter(event) for event in rows})
        for value in values:
            segment_rows = [event for event in rows if segmenter(event) == value]
            by_task: dict[str, set[ExperimentArm]] = {}
            for event in segment_rows:
                by_task.setdefault(event.task_id, set()).add(event.arm)
            paired_ids = {
                task_id
                for task_id, arms in by_task.items()
                if {ExperimentArm.BASELINE, ExperimentArm.COMPRESSED} <= arms
            }
            paired_rows = [event for event in segment_rows if event.task_id in paired_ids]
            if not paired_rows:
                continue
            metrics = summarize(paired_rows)
            if "baseline" not in metrics or "compressed" not in metrics:
                continue
            baseline = metrics["baseline"]
            compressed = metrics["compressed"]
            ci_low, ci_high = _success_difference_interval(paired_rows)
            results.append(
                SegmentResult(
                    dimension=dimension,
                    value=value,
                    paired_tasks=len(paired_ids),
                    baseline_success_rate=baseline["task_success_rate"],
                    compressed_success_rate=compressed["task_success_rate"],
                    success_rate_delta=(
                        compressed["task_success_rate"] - baseline["task_success_rate"]
                    ),
                    success_delta_ci_low=ci_low,
                    success_delta_ci_high=ci_high,
                    baseline_cost_per_success=(
                        None
                        if baseline["cost_per_successful_task"] == float("inf")
                        else baseline["cost_per_successful_task"]
                    ),
                    compressed_cost_per_success=(
                        None
                        if compressed["cost_per_successful_task"] == float("inf")
                        else compressed["cost_per_successful_task"]
                    ),
                    cost_improvement_rate=_safe_improvement(
                        baseline["cost_per_successful_task"],
                        compressed["cost_per_successful_task"],
                    ),
                    treatment_cost_per_success_defined=(
                        compressed["cost_per_successful_task"] != float("inf")
                    ),
                    baseline_p95_latency_ms=baseline["p95_latency_ms"],
                    compressed_p95_latency_ms=compressed["p95_latency_ms"],
                    p95_latency_delta_ms=(
                        compressed["p95_latency_ms"] - baseline["p95_latency_ms"]
                    ),
                    fallback_rate=compressed["fallback_rate"],
                    silent_failures=sum(
                        event.silent_failure
                        for event in paired_rows
                        if event.arm is ExperimentArm.COMPRESSED
                    ),
                )
            )
    return results
