"""Decision-oriented metrics for experiment events."""

from __future__ import annotations

from collections import defaultdict
from statistics import median
from typing import Iterable

from .models import RequestEvent


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, int((len(ordered) - 1) * percentile))
    return float(ordered[index])


def summarize(events: Iterable[RequestEvent]) -> dict[str, dict[str, float]]:
    groups: dict[str, list[RequestEvent]] = defaultdict(list)
    for event in events:
        groups[event.arm.value].append(event)

    result: dict[str, dict[str, float]] = {}
    for arm, rows in groups.items():
        successes = sum(row.task_success for row in rows)
        total_cost = sum(row.estimated_total_cost for row in rows)
        fallback_count = sum(row.fallback_reason is not None for row in rows)
        latencies = [row.total_latency_ms for row in rows]
        original_tokens = sum(row.original_tokens for row in rows)
        effective_tokens = sum(row.compressed_tokens + row.recalled_tokens for row in rows)
        result[arm] = {
            "runs": float(len(rows)),
            "task_success_rate": successes / len(rows),
            "cost_per_successful_task": total_cost / successes if successes else float("inf"),
            "fallback_rate": fallback_count / len(rows),
            "median_latency_ms": float(median(latencies)),
            "p95_latency_ms": _percentile(latencies, 0.95),
            "effective_token_ratio": effective_tokens / original_tokens if original_tokens else 0.0,
        }
    return result
