"""Deterministic long-context, multi-turn workload design and cost audit."""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .execution import estimate_tokens


@dataclass(frozen=True, slots=True)
class WorkloadScenario:
    scenario_id: str
    task_type: str
    language: str
    context_tokens: int
    session_turns: int
    tool_count: int
    risk_level: str
    required_signals: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["required_signals"] = list(self.required_signals)
        return payload


@dataclass(frozen=True, slots=True)
class Pricing:
    model: str
    version: str
    input_per_million: float
    cached_input_per_million: float
    output_per_million: float


def _scenario_id(task_type: str, context_tokens: int, session_turns: int) -> str:
    task_slug = task_type.replace("_", "-")
    context_slug = f"{context_tokens // 1000}k"
    return f"{task_slug}-{context_slug}-{session_turns}t"


def load_workload_matrix(path: str | Path) -> tuple[dict, list[WorkloadScenario]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        raise ValueError("Unsupported workload matrix schema")
    scenarios: list[WorkloadScenario] = []
    for profile in payload["profiles"]:
        for context_tokens in payload["context_tokens"]:
            for session_turns in payload["session_turns"]:
                scenario_id = _scenario_id(
                    profile["task_type"], int(context_tokens), int(session_turns)
                )
                signals = (
                    f"anchor::{scenario_id}",
                    f"src/{profile['language']}/{scenario_id}.{_extension(profile['language'])}",
                    f"{scenario_id.replace('-', '').title()}Error",
                )
                scenarios.append(
                    WorkloadScenario(
                        scenario_id=scenario_id,
                        task_type=profile["task_type"],
                        language=profile["language"],
                        context_tokens=int(context_tokens),
                        session_turns=int(session_turns),
                        tool_count=int(profile["tool_count"]),
                        risk_level=profile["risk_level"],
                        required_signals=signals,
                    )
                )
    identifiers = [scenario.scenario_id for scenario in scenarios]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("Workload scenario identifiers must be unique")
    return payload, scenarios


def _extension(language: str) -> str:
    extensions = {"python": "py", "typescript": "ts", "go": "go", "java": "java", "rust": "rs"}
    try:
        return extensions[language]
    except KeyError as error:
        raise ValueError(f"Unsupported workload language: {language}") from error


def select_stage(matrix: dict, scenarios: list[WorkloadScenario], stage: str) -> list[WorkloadScenario]:
    try:
        rule = matrix["stages"][stage]
    except KeyError as error:
        raise ValueError(f"Unknown workload stage: {stage}") from error
    contexts = set(map(int, rule["context_tokens"]))
    turns = set(map(int, rule["session_turns"]))
    types = set(rule["task_types"])
    return [
        scenario
        for scenario in scenarios
        if scenario.context_tokens in contexts
        and scenario.session_turns in turns
        and scenario.task_type in types
    ]


def build_tool_schemas(scenario: WorkloadScenario) -> list[dict]:
    """Build valid but synthetic function schemas to exercise tool-selection overhead."""
    schemas = []
    for index in range(scenario.tool_count):
        schemas.append(
            {
                "type": "function",
                "function": {
                    "name": f"workspace_{scenario.task_type}_{index:03d}",
                    "description": (
                        f"Synthetic {scenario.task_type} workspace operation {index}; "
                        "accepts a path, query, and bounded result count."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "Repository-relative path"},
                            "query": {"type": "string", "description": "Exact search expression"},
                            "limit": {"type": "integer", "minimum": 1, "maximum": 200},
                        },
                        "required": ["path", "query"],
                        "additionalProperties": False,
                    },
                },
            }
        )
    return schemas


def _filler_line(scenario: WorkloadScenario, index: int) -> str:
    return (
        f"TRACE {index:06d} component=synthetic-{scenario.task_type} "
        f"language={scenario.language} status=observed detail=historical-context-"
        f"{index % 97:02d} repeated diagnostic evidence safe for compression."
    )


def build_session_messages(scenario: WorkloadScenario) -> list[list[dict[str, Any]]]:
    """Return the cumulative message list sent on each turn.

    The final prompt is within 3% of the target using the repository's deterministic token
    estimator. Critical identifiers are distributed across the history to test preservation.
    """
    system = {
        "role": "system",
        "content": (
            "You are evaluating a synthetic software-agent transcript. Preserve identifiers, "
            "paths, and error names exactly. Do not invent replacements."
        ),
    }
    messages: list[dict[str, Any]] = [system]
    outputs: list[list[dict[str, Any]]] = []
    target_chars = scenario.context_tokens * 4
    protocol_overhead_chars = 900 + scenario.session_turns * 500
    per_turn_chars = max(
        500,
        (target_chars - len(system["content"]) - protocol_overhead_chars)
        // scenario.session_turns,
    )
    line_index = 0
    for turn in range(1, scenario.session_turns + 1):
        blocks = max(1, math.ceil((scenario.context_tokens / scenario.session_turns) / 32_000))
        call_ids = [f"call_{scenario.scenario_id}_{turn}_{block}" for block in range(blocks)]
        messages.append(
            {
                "role": "user",
                "content": f"Inspect synthetic evidence batch {turn} for {scenario.scenario_id}.",
            }
        )
        messages.append(
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": call_id,
                        "type": "function",
                        "function": {
                            "name": f"workspace_{scenario.task_type}_{block:03d}",
                            "arguments": json.dumps(
                                {"path": f"batch/{turn}/{block}", "query": "critical signal"}
                            ),
                        },
                    }
                    for block, call_id in enumerate(call_ids)
                ],
            }
        )
        signal_turns = (1, max(1, math.ceil(scenario.session_turns / 2)), scenario.session_turns)
        turn_signals = [
            signal
            for signal, signal_turn in zip(scenario.required_signals, signal_turns, strict=True)
            if signal_turn == turn
        ]
        block_chars = max(400, per_turn_chars // blocks)
        for block, call_id in enumerate(call_ids):
            lines = [
                f"SESSION={scenario.scenario_id} TURN={turn}/{scenario.session_turns} "
                f"BLOCK={block + 1}/{blocks}"
            ]
            if block == 0:
                lines.extend(f"CRITICAL_SIGNAL: {signal}" for signal in turn_signals)
            while len("\n".join(lines)) < block_chars:
                lines.append(_filler_line(scenario, line_index))
                line_index += 1
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": "\n".join(lines)[:block_chars],
                }
            )
        if turn == scenario.session_turns:
            request = (
                "FINAL_TASK: Return the three CRITICAL_SIGNAL values found in prior tool results "
                "exactly, one per line. Do not include labels or commentary."
            )
        else:
            request = "INTERMEDIATE_TASK: Reply only with CONTEXT_RECORDED."
        messages.append({"role": "user", "content": request})
        outputs.append([dict(message) for message in messages])
        if turn < scenario.session_turns:
            messages.append({"role": "assistant", "content": "CONTEXT_RECORDED"})
    return outputs


def estimated_session_input_tokens(scenario: WorkloadScenario) -> int:
    tools = json.dumps(build_tool_schemas(scenario), sort_keys=True)
    tool_tokens = estimate_tokens(tools)
    return sum(
        estimate_tokens(json.dumps(messages, sort_keys=True)) + tool_tokens
        for messages in build_session_messages(scenario)
    )


def load_pricing(path: str | Path, model: str) -> Pricing:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    try:
        row = payload["models"][model]
    except KeyError as error:
        raise ValueError(f"Model not found in pricing registry: {model}") from error
    return Pricing(
        model=model,
        version=f"openai-{payload['effective_date']}",
        input_per_million=float(row["input"]),
        cached_input_per_million=float(row["cached_input"]),
        output_per_million=float(row["output"]),
    )


def audit_stage(scenarios: list[WorkloadScenario], pricing: Pricing) -> dict:
    rows = []
    total_input_tokens = 0
    for scenario in scenarios:
        input_tokens = estimated_session_input_tokens(scenario)
        total_input_tokens += input_tokens
        rows.append(
            {
                **scenario.to_dict(),
                "estimated_input_tokens_per_arm": input_tokens,
                "estimated_baseline_input_cost_usd": round(
                    input_tokens * pricing.input_per_million / 1_000_000, 6
                ),
            }
        )
    paired_input_tokens = total_input_tokens * 2
    return {
        "schema_version": 1,
        "model": pricing.model,
        "pricing_version": pricing.version,
        "scenario_count": len(rows),
        "paired_request_count": sum(scenario.session_turns for scenario in scenarios) * 2,
        "estimated_paired_input_tokens_before_compression": paired_input_tokens,
        "estimated_paired_input_cost_upper_bound_usd": round(
            paired_input_tokens * pricing.input_per_million / 1_000_000, 4
        ),
        "excludes_output_and_paritok_compute_cost": True,
        "scenarios": rows,
    }


def build_audit_markdown(audit: dict, *, stage: str, suite_id: str) -> str:
    lines = [
        "# Phase 3 workload audit",
        "",
        f"- Suite: `{suite_id}`",
        f"- Stage: `{stage}`",
        f"- Model: `{audit['model']}`",
        f"- Pricing: `{audit['pricing_version']}`",
        f"- Scenarios: {audit['scenario_count']}",
        f"- Paired requests: {audit['paired_request_count']}",
        "- Estimated paired input tokens before compression: "
        f"{audit['estimated_paired_input_tokens_before_compression']:,}",
        "- Estimated input-only upper bound: "
        f"${audit['estimated_paired_input_cost_upper_bound_usd']:.4f}",
        "",
        "> This is a preflight estimate, not measured evidence. It excludes output tokens and "
        "PariTok compute. Treatment input should be lower when compression is active.",
        "",
        "| Scenario | Type | History payload | Turns | Tools | Risk | Input tokens/arm | Baseline input cost |",
        "|---|---|---:|---:|---:|---|---:|---:|",
    ]
    for row in audit["scenarios"]:
        lines.append(
            f"| `{row['scenario_id']}` | {row['task_type']} | {row['context_tokens']:,} | "
            f"{row['session_turns']} | {row['tool_count']} | {row['risk_level']} | "
            f"{row['estimated_input_tokens_per_arm']:,} | "
            f"${row['estimated_baseline_input_cost_usd']:.4f} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation guardrails",
            "",
            "- Smoke results validate integration only and cannot authorize rollout.",
            "- Edit-critical scenarios require exact preservation of all critical signals.",
            "- The 8K/32K/128K band is message-history payload; tool schemas are measured overhead.",
            "- Report context cohorts separately; do not hide segment failures in a global mean.",
            "- Promote from smoke to core and extended only after the preceding stage passes.",
            "",
        ]
    )
    return "\n".join(lines)
