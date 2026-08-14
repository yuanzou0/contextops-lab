"""Markdown reporting for privacy-safe experiment events."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Iterable

from .metrics import summarize
from .models import RequestEvent


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def build_markdown_report(events: Iterable[RequestEvent], *, evidence_label: str) -> str:
    rows = list(events)
    overall = summarize(rows)
    segments: dict[str, list[RequestEvent]] = defaultdict(list)
    for event in rows:
        segments[event.task_type].append(event)

    lines = [
        "# ContextOps Lab — Phase 1 Analysis Report",
        "",
        f"**Generated:** {date.today().isoformat()}",
        f"**Evidence level:** {evidence_label}",
        "",
        "## Executive conclusion",
        "",
        "This report validates the paired-experiment, safety fallback, event, and analytics "
        "pipeline. It is not evidence that PariTok or another production compressor reduces "
        "real-world cost. A production recommendation requires live model runs.",
        "",
        "## Overall results",
        "",
        "| Arm | Runs | Task-proxy success | Cost / proxy success | Fallback | P95 latency | Token ratio |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for arm in ("baseline", "compressed"):
        values = overall[arm]
        lines.append(
            f"| {arm} | {int(values['runs'])} | {_pct(values['task_success_rate'])} | "
            f"{values['cost_per_successful_task']:.6f} | {_pct(values['fallback_rate'])} | "
            f"{values['p95_latency_ms']:.1f} ms | {_pct(values['effective_token_ratio'])} |"
        )

    lines.extend(
        [
            "",
            "## Workload segmentation",
            "",
            "| Workload | Compressed runs | Task-proxy success | Fallback | Token ratio |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for task_type, segment_rows in sorted(segments.items()):
        values = summarize(segment_rows)["compressed"]
        lines.append(
            f"| {task_type} | {int(values['runs'])} | {_pct(values['task_success_rate'])} | "
            f"{_pct(values['fallback_rate'])} | {_pct(values['effective_token_ratio'])} |"
        )

    lines.extend(
        [
            "",
            "## Release decision",
            "",
            "**Decision: do not enable production rollout yet.** The offline fixture demonstrates "
            "that rejected compression returns exact original context and remains observable. The "
            "next evidence gate is a live paired run using the same agent model, task snapshot, "
            "temperature, tools, and retry policy in both arms.",
            "",
            "## Known limitations",
            "",
            "- Task outcomes use a deterministic marker oracle, not human or model-based grading.",
            "- Costs and latency are fixture measurements used to validate calculation paths.",
            "- The 36 cases are executable pipeline fixtures, not a representative production sample.",
            "- No upstream PariTok benchmark or savings claim is reproduced here.",
            "",
        ]
    )
    return "\n".join(lines)


def build_phase2_report(events: Iterable[RequestEvent], policy: dict, *, evidence_label: str) -> str:
    from .analytics import segment_events
    from .failures import analyze_failures

    rows = list(events)
    segments = segment_events(rows, ("task_type",))
    failures = analyze_failures(rows)
    lines = [
        "# ContextOps Lab — Phase 2 Product-Loop Report",
        "",
        f"**Generated:** {date.today().isoformat()}",
        f"**Evidence level:** {evidence_label}",
        "",
        "## Decision",
        "",
        "Production rollout remains **locked** unless the policy evidence label is `production`. "
        "Offline recommendations validate segmentation and decision logic only.",
        "",
        "## Workload policy recommendations",
        "",
        "| Workload | Paired tasks | Task-proxy Δ (95% CI) | Cost improvement | Fallback | Mode | Reasons |",
        "|---|---:|---:|---:|---:|---|---|",
    ]
    rules = {rule["value"]: rule for rule in policy.get("rules", [])}
    for segment in segments:
        rule = rules[segment.value]
        cost_improvement = (
            _pct(segment.cost_improvement_rate)
            if segment.treatment_cost_per_success_defined
            else "N/A (0 treatment successes)"
        )
        lines.append(
            f"| {segment.value} | {segment.paired_tasks} | {_pct(segment.success_rate_delta)} "
            f"[{_pct(segment.success_delta_ci_low)}, {_pct(segment.success_delta_ci_high)}] | "
            f"{cost_improvement} | {_pct(segment.fallback_rate)} | "
            f"{rule['mode']} | {', '.join(rule['reasons'])} |"
        )
    lines.extend(["", "## Failure analysis", ""])
    if failures:
        lines.extend(["| Category | Reason | Count | Event rate |", "|---|---|---:|---:|"])
        for failure in failures:
            lines.append(
                f"| {failure.category} | {failure.reason} | {failure.count} | {_pct(failure.rate)} |"
            )
    else:
        lines.append("No failure or fallback events were recorded.")
    lines.extend(
        [
            "",
            "## Product controls delivered",
            "",
            "- self-contained analytics dashboard with workload filtering;",
            "- versioned evidence-gated rollout policy;",
            "- runtime `off`, `conservative`, and `balanced` strategies;",
            "- failure taxonomy with structured reason aggregation;",
            "- `doctor` checks for task pairing, privacy schema, policy integrity, and live adapters;",
            "- reproducible data lineage manifest for generated artifacts.",
            "- timestamped, versioned experiment and pricing metadata with duplicate-event checks.",
            "",
            "## Next evidence gate",
            "",
            "Run representative live tasks through the configured compressor and agent endpoint. "
            "Do not change `production_ready` manually; regenerate policy from production-labeled evidence.",
            "",
        ]
    )
    return "\n".join(lines)
