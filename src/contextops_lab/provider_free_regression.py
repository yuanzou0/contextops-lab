"""Provider-free transformed-context regression for multi-turn compression safety."""

from __future__ import annotations

import hashlib
import json
import time
from collections import Counter
from contextlib import ExitStack
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from typing import Any, Sequence
from unittest.mock import patch

from .cache_safety import build_paritok_storage
from .fallback import validate_or_fallback
from .validator import CompressionValidator
from .workloads import WorkloadScenario, build_session_messages


INTERMEDIATE_QUERY = "INTERMEDIATE_TASK: Reply only with CONTEXT_RECORDED."
FINAL_QUERY = (
    "FINAL_TASK: Return the three CRITICAL_SIGNAL values found in prior tool results exactly, "
    "one per line. Do not include labels or commentary."
)


class DeterministicSignalModel:
    """Intent-sensitive model used to make cache and fallback behavior reproducible in CI."""

    def __init__(self) -> None:
        self.calls = 0

    def compress(self, content: str, *, query: str | None = None, **_: Any) -> str:
        self.calls += 1
        if query and query.startswith("FINAL_TASK:"):
            signals = [line for line in content.splitlines() if line.startswith("CRITICAL_SIGNAL:")]
            return "\n".join(signals) or "no critical signal in this segment"
        return "historical context recorded"


@dataclass(frozen=True, slots=True)
class RegressionSpec:
    engine: str
    conditions: tuple[str, ...]
    stage: str
    config_version: str


def _signal_segments(scenario: WorkloadScenario) -> list[tuple[str, str]]:
    final_messages = build_session_messages(scenario)[-1]
    segments = []
    for message in final_messages:
        if message.get("role") != "tool" or not isinstance(message.get("content"), str):
            continue
        content = message["content"]
        matching = [signal for signal in scenario.required_signals if signal in content]
        if matching:
            segments.append((content, matching[0]))
    if len(segments) != len(scenario.required_signals):
        raise ValueError(
            f"Expected one signal-bearing segment per required signal for {scenario.scenario_id}"
        )
    return segments


def _set_query(storage: Any, query: str) -> None:
    setter = getattr(storage, "set_active_query", None)
    if setter:
        setter(query)


def _available_references(result: Any) -> tuple[str, ...]:
    return (result.shadow_id,) if result.shadow_id else ()


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _build_pipeline(engine: str, condition: str) -> tuple[Any, Any | None]:
    try:
        from paritok.config import ParitokConfig
        from paritok.pipelines.compress import CompressionPipeline
    except ImportError as error:
        raise RuntimeError("Install the live extra before provider-free regression") from error
    config = ParitokConfig()
    config.compression.min_tokens = 0
    config.compression.max_tokens = 50_000
    config.compression.refusal_threshold = 0.0
    config.local_model.timeout = 300.0
    storage = build_paritok_storage(condition)
    pipeline = CompressionPipeline(config=config, storage=storage)
    model = None
    if engine == "deterministic":
        model = DeterministicSignalModel()
        pipeline._model = model
    elif engine != "local_paritok_4b":
        raise ValueError(f"Unsupported regression engine: {engine}")
    return pipeline, model


def _run_condition(
    scenario: WorkloadScenario,
    *,
    engine: str,
    condition: str,
) -> dict[str, Any]:
    pipeline, model = _build_pipeline(engine, condition)
    segments = _signal_segments(scenario)
    validator = CompressionValidator()
    intermediate_hashes = []
    final_hashes = []
    intermediate_hits = 0
    final_hits = 0
    replay_hits = 0
    raw_recalled = 0
    guarded_recalled = 0
    fallback_reasons: Counter[str] = Counter()
    started = time.perf_counter()

    for content, _ in segments:
        _set_query(pipeline.storage, INTERMEDIATE_QUERY)
        result = pipeline.compress(content, query=INTERMEDIATE_QUERY, kind="log_output")
        intermediate_hits += int(bool(result.metadata.get("cache_hit", False)))
        intermediate_hashes.append(_sha256(result.compressed))

    for content, signal in segments:
        _set_query(pipeline.storage, FINAL_QUERY)
        result = pipeline.compress(content, query=FINAL_QUERY, kind="log_output")
        final_hits += int(bool(result.metadata.get("cache_hit", False)))
        final_hashes.append(_sha256(result.compressed))
        raw_recalled += int(signal in result.compressed)
        decision = validate_or_fallback(
            validator,
            original=content,
            compressed=result.compressed,
            original_tokens=result.original_tokens,
            compressed_tokens=result.compressed_tokens,
            available_references=_available_references(result),
            required_signals=(signal,),
        )
        guarded_recalled += int(signal in decision.content)
        if decision.fallback_reason:
            fallback_reasons[decision.fallback_reason.value] += 1

    for content, _ in segments:
        _set_query(pipeline.storage, FINAL_QUERY)
        replay = pipeline.compress(content, query=FINAL_QUERY, kind="log_output")
        replay_hits += int(bool(replay.metadata.get("cache_hit", False)))

    total = len(segments)
    expected_final_hits = total if condition == "content_only" else 0
    expected_replay_hits = total if condition in {"content_only", "query_aware"} else 0
    cache_behavior_passed = final_hits == expected_final_hits and replay_hits == expected_replay_hits
    guarded_safety_passed = guarded_recalled == total
    raw_quality_passed = raw_recalled == total
    return {
        "scenario_id": scenario.scenario_id,
        "task_type": scenario.task_type,
        "context_tokens": scenario.context_tokens,
        "session_turns": scenario.session_turns,
        "condition": condition,
        "signal_segments": total,
        "intermediate_cache_hits": intermediate_hits,
        "cross_query_final_cache_hits": final_hits,
        "same_query_replay_cache_hits": replay_hits,
        "raw_required_signals_recalled": raw_recalled,
        "guarded_required_signals_recalled": guarded_recalled,
        "fallback_count": sum(fallback_reasons.values()),
        "fallback_reasons": dict(sorted(fallback_reasons.items())),
        "intermediate_output_sha256": intermediate_hashes,
        "final_output_sha256": final_hashes,
        "cache_behavior_passed": cache_behavior_passed,
        "guarded_safety_passed": guarded_safety_passed,
        "raw_compression_quality_passed": raw_quality_passed,
        "model_calls": model.calls if model is not None else None,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
    }


def run_provider_free_regression(
    scenarios: Sequence[WorkloadScenario],
    spec: RegressionSpec,
) -> dict[str, Any]:
    """Execute prespecified transformed-context conditions without an upstream provider."""
    if not scenarios:
        raise ValueError("At least one scenario is required")
    if any(scenario.session_turns <= 1 for scenario in scenarios):
        raise ValueError("Provider-free intent-drift regression requires multi-turn scenarios")
    if any(condition not in {"content_only", "disabled", "query_aware"} for condition in spec.conditions):
        raise ValueError("Unsupported cache condition")

    rows = []
    # Avoid lazy tokenizer downloads. Token estimates are not an outcome in this regression.
    with ExitStack() as stack:
        stack.enter_context(
            patch(
                "paritok.pipelines.compress.count_tokens",
                side_effect=lambda text, *_: max(1, len(text) // 4),
            )
        )
        stack.enter_context(
            patch(
                "paritok.strategies.local_model.count_tokens",
                side_effect=lambda text, *_: max(1, len(text) // 4),
            )
        )
        for condition in spec.conditions:
            for scenario in scenarios:
                rows.append(_run_condition(scenario, engine=spec.engine, condition=condition))

    total_signals = sum(row["signal_segments"] for row in rows)
    raw_recalled = sum(row["raw_required_signals_recalled"] for row in rows)
    guarded_recalled = sum(row["guarded_required_signals_recalled"] for row in rows)
    recovery_rows = [row for row in rows if row["condition"] != "content_only"]
    try:
        paritok_version = version("paritok")
    except PackageNotFoundError:
        paritok_version = "unknown"
    return {
        "schema_version": 1,
        "config_version": spec.config_version,
        "evidence_label": f"provider_free_{spec.engine}_transformed_context_regression",
        "engine": spec.engine,
        "paritok_version": paritok_version,
        "stage": spec.stage,
        "provider_requests": 0,
        "provider_cost_usd": 0.0,
        "raw_content_recorded": False,
        "token_counter": "deterministic_len_div_4_not_an_outcome",
        "conditions": list(spec.conditions),
        "scenario_count": len(scenarios),
        "condition_scenario_count": len(rows),
        "required_signals_total": total_signals,
        "raw_required_signals_recalled": raw_recalled,
        "guarded_required_signals_recalled": guarded_recalled,
        "cache_behavior_all_passed": all(row["cache_behavior_passed"] for row in rows),
        "guarded_safety_all_passed": all(row["guarded_safety_passed"] for row in rows),
        "raw_compression_quality_all_passed": all(
            row["raw_compression_quality_passed"] for row in rows
        ),
        "recovery_conditions_raw_quality_passed": all(
            row["raw_compression_quality_passed"] for row in recovery_rows
        ),
        "wave_b_eligible": False,
        "rows": rows,
        "claim_boundary": (
            "Measures transformed-context signal retention and cache/fallback mechanics without "
            "an upstream agent provider. It does not measure end-task semantic quality, provider "
            "behavior, or synchronous latency eligibility."
        ),
    }


def build_regression_report(payload: dict[str, Any]) -> str:
    lines = [
        "# Provider-free transformed-context regression",
        "",
        f"- Engine: `{payload['engine']}`",
        f"- Evidence: `{payload['evidence_label']}`",
        f"- PariTok: `{payload['paritok_version']}`",
        f"- Provider requests / cost: {payload['provider_requests']} / $0.00",
        f"- Scenarios: {payload['scenario_count']}",
        f"- Conditions: {', '.join(payload['conditions'])}",
        "- Raw content recorded: no",
        "",
        "## Prespecified outcomes",
        "",
        f"- Cache behavior: {'PASS' if payload['cache_behavior_all_passed'] else 'FAIL'}",
        "- Guarded signal safety: "
        f"{'PASS' if payload['guarded_safety_all_passed'] else 'FAIL'} "
        f"({payload['guarded_required_signals_recalled']}/{payload['required_signals_total']})",
        "- Raw compression signal quality: "
        f"{'PASS' if payload['raw_compression_quality_all_passed'] else 'FAIL'} "
        f"({payload['raw_required_signals_recalled']}/{payload['required_signals_total']})",
        "- Recovery-condition raw quality: "
        f"{'PASS' if payload['recovery_conditions_raw_quality_passed'] else 'FAIL'}",
        f"- Wave B eligible: {'yes' if payload['wave_b_eligible'] else 'no'}",
        "",
        "| Workload | Condition | Cross-query hits | Replay hits | Raw recall | Guarded recall | Fallbacks |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in payload["rows"]:
        lines.append(
            f"| {row['task_type']} | {row['condition']} | "
            f"{row['cross_query_final_cache_hits']} | {row['same_query_replay_cache_hits']} | "
            f"{row['raw_required_signals_recalled']}/{row['signal_segments']} | "
            f"{row['guarded_required_signals_recalled']}/{row['signal_segments']} | "
            f"{row['fallback_count']} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation boundary",
            "",
            payload["claim_boundary"],
            "",
            "Passing guarded safety means unsafe transformed segments were replaced by exact "
            "original content in this directly observable pipeline. Passing raw compression "
            "quality is a separate and stricter requirement for a recovery pilot.",
            "",
        ]
    )
    return "\n".join(lines)


def write_regression_artifacts(payload: dict[str, Any], output: str, report: str) -> None:
    from pathlib import Path

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report_path = Path(report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(build_regression_report(payload), encoding="utf-8")
