"""Paired latency decomposition with explicit measurement limitations."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import time
from typing import Iterable

from .models import ExperimentArm, RequestEvent


@dataclass(frozen=True, slots=True)
class LatencyBreakdown:
    task_id: str
    baseline_provider_ms: float
    treatment_end_to_end_ms: float
    incremental_local_and_proxy_ms: float
    measurement: str = "paired_estimate"

    def to_dict(self) -> dict:
        return asdict(self)


def decompose_paired_latency(events: Iterable[RequestEvent]) -> list[LatencyBreakdown]:
    """Estimate local+proxy overhead using the matched direct call as provider control.

    PariTok 1.3.3 does not expose separate compression/upstream timing headers. This function
    therefore labels the subtraction as an estimate instead of claiming exact instrumentation.
    """
    terminal = [event for event in events if event.is_terminal_turn]
    results: list[LatencyBreakdown] = []
    for task_id in sorted({event.task_id for event in terminal}):
        rows = [event for event in terminal if event.task_id == task_id]
        baseline = next((row for row in rows if row.arm is ExperimentArm.BASELINE), None)
        treatment = next((row for row in rows if row.arm is ExperimentArm.COMPRESSED), None)
        if baseline is None or treatment is None:
            continue
        results.append(
            LatencyBreakdown(
                task_id=task_id,
                baseline_provider_ms=baseline.total_latency_ms,
                treatment_end_to_end_ms=treatment.total_latency_ms,
                incremental_local_and_proxy_ms=max(
                    0.0, treatment.total_latency_ms - baseline.total_latency_ms
                ),
            )
        )
    return results


def measure_local_latency_states(
    compressor,
    cold_content: str,
    warm_uncached_content: str,
) -> dict:
    """Measure cold candidate, warm uncached, and exact-input cache reuse.

    The caller must restart the local backend immediately before this probe for the first row to
    be a valid cold-start observation. The function cannot inspect process-global model state.
    """
    if cold_content == warm_uncached_content:
        raise ValueError("warm_uncached_content must differ from cold_content")
    rows = []
    states = (
        ("cold_candidate", cold_content),
        ("warm_uncached", warm_uncached_content),
        ("cache_reuse", warm_uncached_content),
    )
    for index, (state, content) in enumerate(states, start=1):
        started = time.perf_counter()
        result = compressor(content)
        rows.append(
            {
                "iteration": index,
                "state": state,
                "latency_ms": (time.perf_counter() - started) * 1000,
                "cache_hit": bool(result.metadata.get("cache_hit", False)),
                "original_tokens": result.original_tokens,
                "compressed_tokens": result.compressed_tokens,
            }
        )
    return {
        "schema_version": 2,
        "measurement": "local_compression_only",
        "cold_start_valid_only_if_backend_restarted": True,
        "states": rows,
    }
