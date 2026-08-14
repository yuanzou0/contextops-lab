"""Multi-turn product-economics curves with explicit latency valuation."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable

from .models import ExperimentArm, RequestEvent


@dataclass(frozen=True, slots=True)
class TurnEconomics:
    task_id: str
    turn_id: int
    cumulative_baseline_cost_usd: float
    cumulative_treatment_cost_usd: float
    cumulative_cost_saving_usd: float
    cumulative_baseline_latency_ms: float
    cumulative_treatment_latency_ms: float
    cumulative_latency_penalty_ms: float
    baseline_task_proxy_success: bool
    treatment_task_proxy_success: bool
    net_value_usd: float | None

    def to_dict(self) -> dict:
        return asdict(self)


def build_multi_turn_economics(
    events: Iterable[RequestEvent],
    *,
    latency_value_usd_per_second: float | None = None,
) -> dict:
    """Build paired cumulative curves without mixing dollars and seconds implicitly."""
    if latency_value_usd_per_second is not None and latency_value_usd_per_second < 0:
        raise ValueError("latency_value_usd_per_second cannot be negative")
    rows = list(events)
    tasks = []
    for task_id in sorted({event.task_id for event in rows}):
        task_rows = [event for event in rows if event.task_id == task_id]
        baseline = {event.turn_id: event for event in task_rows if event.arm is ExperimentArm.BASELINE}
        treatment = {
            event.turn_id: event for event in task_rows if event.arm is ExperimentArm.COMPRESSED
        }
        paired_turns = sorted(set(baseline) & set(treatment))
        cumulative_baseline_cost = 0.0
        cumulative_treatment_cost = 0.0
        cumulative_baseline_latency = 0.0
        cumulative_treatment_latency = 0.0
        curve = []
        for turn_id in paired_turns:
            baseline_row = baseline[turn_id]
            treatment_row = treatment[turn_id]
            cumulative_baseline_cost += baseline_row.estimated_total_cost
            cumulative_treatment_cost += treatment_row.estimated_total_cost
            cumulative_baseline_latency += baseline_row.total_latency_ms
            cumulative_treatment_latency += treatment_row.total_latency_ms
            saving = cumulative_baseline_cost - cumulative_treatment_cost
            latency_penalty = cumulative_treatment_latency - cumulative_baseline_latency
            net_value = None
            if latency_value_usd_per_second is not None:
                net_value = saving - max(0.0, latency_penalty) / 1000 * latency_value_usd_per_second
            curve.append(
                TurnEconomics(
                    task_id=task_id,
                    turn_id=turn_id,
                    cumulative_baseline_cost_usd=cumulative_baseline_cost,
                    cumulative_treatment_cost_usd=cumulative_treatment_cost,
                    cumulative_cost_saving_usd=saving,
                    cumulative_baseline_latency_ms=cumulative_baseline_latency,
                    cumulative_treatment_latency_ms=cumulative_treatment_latency,
                    cumulative_latency_penalty_ms=latency_penalty,
                    baseline_task_proxy_success=baseline_row.task_success,
                    treatment_task_proxy_success=treatment_row.task_success,
                    net_value_usd=net_value,
                ).to_dict()
            )
        break_even = next(
            (
                row["turn_id"]
                for row in curve
                if row["net_value_usd"] is not None
                and row["net_value_usd"] >= 0
                and row["baseline_task_proxy_success"]
                and row["treatment_task_proxy_success"]
            ),
            None,
        )
        tasks.append({"task_id": task_id, "break_even_turn": break_even, "curve": curve})
    return {
        "schema_version": 1,
        "latency_value_usd_per_second": latency_value_usd_per_second,
        "break_even_enabled": latency_value_usd_per_second is not None,
        "limitation": (
            "Break-even requires an explicit latency valuation; task-proxy success is not "
            "semantic quality equivalence."
        ),
        "tasks": tasks,
    }
