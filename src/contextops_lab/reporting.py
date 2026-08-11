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
        "| Arm | Runs | Task success | Cost / success | Fallback | P95 latency | Token ratio |",
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
            "| Workload | Compressed runs | Success | Fallback | Token ratio |",
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
