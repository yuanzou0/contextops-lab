"""Paired multi-turn session execution for the staged Phase 3 workload matrix."""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Protocol, Sequence

from .execution import CompletionResult
from .models import ExperimentArm, RequestEvent
from .paritok import ContextOpsSafetyGateway, ContextOpsSafetyStats, PariTokGateway
from .workloads import WorkloadScenario, build_session_messages, build_tool_schemas


class MessageAgent(Protocol):
    model: str

    def complete_messages(
        self,
        messages: Sequence[dict[str, Any]],
        *,
        tools: Sequence[dict[str, Any]] | None = None,
    ) -> CompletionResult: ...


@dataclass(frozen=True, slots=True)
class SessionOutcome:
    scenario_id: str
    arm: ExperimentArm
    events: tuple[RequestEvent, ...]

    @property
    def terminal_success(self) -> bool:
        return self.events[-1].task_success


class MultiTurnProxyExecutor:
    """Run controlled cumulative histories directly and through a PariTok proxy."""

    def __init__(
        self,
        baseline_agent: MessageAgent,
        paritok_agent: MessageAgent,
        gateway: PariTokGateway,
        *,
        experiment_id: str,
        config_version: str,
        config_sha256: str,
        pricing_version: str,
        require_proxy_telemetry: bool = True,
        safety_gateway: ContextOpsSafetyGateway | None = None,
    ):
        if baseline_agent.model != paritok_agent.model:
            raise ValueError("Both experiment arms must use the same model")
        self.baseline_agent = baseline_agent
        self.paritok_agent = paritok_agent
        self.gateway = gateway
        self.experiment_id = experiment_id
        self.config_version = config_version
        self.config_sha256 = config_sha256
        self.pricing_version = pricing_version
        self.require_proxy_telemetry = require_proxy_telemetry
        self.safety_gateway = safety_gateway

    def run_arm(self, scenario: WorkloadScenario, arm: ExperimentArm) -> SessionOutcome:
        requests = build_session_messages(scenario)
        tools = build_tool_schemas(scenario)
        events: list[RequestEvent] = []
        agent = self.baseline_agent if arm is ExperimentArm.BASELINE else self.paritok_agent
        for turn_index, messages in enumerate(requests, start=1):
            original_tokens = 0
            compressed_tokens = 0
            proxy_requests = 0
            proxy_tokens_saved = 0
            compression_latency_ms = 0.0
            fallback_reason = None
            if arm is ExperimentArm.COMPRESSED:
                before = self.gateway.stats()
                safety_before = self.safety_gateway.stats() if self.safety_gateway else None
                completion = agent.complete_messages(messages, tools=tools)
                after = self.gateway.stats()
                delta = after.delta(before)
                safety_delta = self._safety_delta(safety_before)
                if self.require_proxy_telemetry and delta.total_requests != 1:
                    raise RuntimeError(
                        "Expected exactly one PariTok request between telemetry snapshots; "
                        f"observed {delta.total_requests}"
                    )
                original_tokens = delta.input_tokens_original or completion.input_tokens
                compressed_tokens = delta.input_tokens_compressed or completion.input_tokens
                proxy_requests = delta.total_requests
                proxy_tokens_saved = delta.tokens_saved
                if safety_delta is None:
                    treatment_name = "paritok-proxy:multi-turn"
                    endpoint_role = "treatment_proxy"
                    validator_result = "proxy_managed"
                else:
                    treatment_name = "contextops-safe-paritok-proxy:multi-turn"
                    endpoint_role = "treatment_safe_proxy"
                    compression_latency_ms = safety_delta.compression_latency_ms
                    if safety_delta.fallbacks:
                        validator_result = "fallback"
                        fallback_reason = self._primary_fallback_reason(safety_delta)
                    elif safety_delta.validated:
                        validator_result = "pass"
                    else:
                        validator_result = "safe_passthrough"
            else:
                completion = agent.complete_messages(messages, tools=tools)
                original_tokens = completion.input_tokens
                compressed_tokens = completion.input_tokens
                treatment_name = "direct-provider:multi-turn"
                endpoint_role = "baseline_direct"
                validator_result = "not_applied"

            terminal = turn_index == scenario.session_turns
            recalled_signals = (
                sum(signal in completion.content for signal in scenario.required_signals)
                if terminal
                else 0
            )
            turn_success = (
                recalled_signals == len(scenario.required_signals)
                if terminal
                else completion.content.strip() == "CONTEXT_RECORDED"
            )
            failure_reason = None
            if not turn_success:
                failure_reason = (
                    "missing_required_signals"
                    if terminal
                    else "protocol_acknowledgement_failed"
                )
            events.append(
                RequestEvent(
                    experiment_id=self.experiment_id,
                    task_id=scenario.scenario_id,
                    session_id=f"{self.experiment_id}:{scenario.scenario_id}:{arm.value}",
                    turn_id=turn_index,
                    arm=arm,
                    treatment_name=treatment_name,
                    model=self.baseline_agent.model,
                    task_type=scenario.task_type,
                    language=scenario.language,
                    repo_size=scenario.context_tokens,
                    tool_count=scenario.tool_count,
                    session_length=scenario.session_turns,
                    original_tokens=original_tokens,
                    compressed_tokens=compressed_tokens,
                    recalled_tokens=0,
                    compression_latency_ms=compression_latency_ms,
                    total_latency_ms=completion.latency_ms,
                    validator_result=validator_result,
                    fallback_reason=fallback_reason,
                    task_success=turn_success,
                    tests_passed=turn_success if terminal else None,
                    manual_intervention=False,
                    estimated_total_cost=completion.estimated_cost,
                    failure_reason=failure_reason,
                    recorded_at=datetime.now(timezone.utc).isoformat(),
                    experiment_config_version=self.config_version,
                    pricing_version=self.pricing_version,
                    endpoint_role=endpoint_role,
                    provider_input_tokens=completion.input_tokens,
                    provider_output_tokens=completion.output_tokens,
                    proxy_request_count=proxy_requests,
                    proxy_tokens_saved=proxy_tokens_saved,
                    config_sha256=self.config_sha256,
                    is_terminal_turn=terminal,
                    context_tokens=scenario.context_tokens,
                    risk_level=scenario.risk_level,
                    outcome_measure=(
                        "critical_signal_recall"
                        if terminal
                        else "protocol_acknowledgement"
                    ),
                    required_signals_total=len(scenario.required_signals) if terminal else 0,
                    required_signals_recalled=recalled_signals,
                )
            )
        return SessionOutcome(scenario.scenario_id, arm, tuple(events))

    def _safety_delta(
        self,
        before: ContextOpsSafetyStats | None,
    ) -> ContextOpsSafetyStats | None:
        if not self.safety_gateway:
            return None
        if before is None:  # pragma: no cover - defensive invariant
            raise RuntimeError("Missing ContextOps safety pre-request snapshot")
        delta = self.safety_gateway.stats().delta(before)
        if delta.fallbacks != delta.exact_original_fallbacks:
            raise RuntimeError("A ContextOps fallback was not exact-original")
        return delta

    @staticmethod
    def _primary_fallback_reason(stats: ContextOpsSafetyStats) -> str:
        if not stats.fallback_reasons:
            return "unknown_fallback"
        return sorted(stats.fallback_reasons.items(), key=lambda row: (-row[1], row[0]))[0][0]


def run_paired_sessions(
    scenarios: Sequence[WorkloadScenario],
    executor: MultiTurnProxyExecutor,
    event_writer: Callable[[RequestEvent], None],
    *,
    seed: int = 17,
) -> list[SessionOutcome]:
    randomizer = random.Random(seed)
    outcomes: list[SessionOutcome] = []
    for scenario in scenarios:
        arms = [ExperimentArm.BASELINE, ExperimentArm.COMPRESSED]
        randomizer.shuffle(arms)
        for arm in arms:
            outcome = executor.run_arm(scenario, arm)
            if outcome.scenario_id != scenario.scenario_id or outcome.arm is not arm:
                raise ValueError("Session executor returned an outcome for the wrong scenario or arm")
            for event in outcome.events:
                event_writer(event)
            outcomes.append(outcome)
    return outcomes
