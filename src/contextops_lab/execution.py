"""Concrete adapters for running baseline and compressed experiment arms."""

from __future__ import annotations

import json
import subprocess
import time
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol, Sequence

from .benchmark import BenchmarkCase
from .experiments import RunOutcome
from .fallback import validate_or_fallback
from .models import ExperimentArm, RequestEvent
from .strategy import CompressionMode, settings_for
from .validator import CompressionValidator, FallbackReason, ValidationConfig


def estimate_tokens(text: str) -> int:
    return max(1, (len(text) + 3) // 4)


@dataclass(frozen=True, slots=True)
class CompletionResult:
    content: str
    input_tokens: int
    output_tokens: int
    latency_ms: float
    estimated_cost: float = 0.0


@dataclass(frozen=True, slots=True)
class CompressionResult:
    content: str
    tokens: int
    latency_ms: float
    estimated_cost: float = 0.0


class AgentClient(Protocol):
    model: str

    def complete(self, instruction: str, context: str, case: BenchmarkCase) -> CompletionResult: ...


class CompressorClient(Protocol):
    name: str

    def compress(self, context: str, case: BenchmarkCase) -> CompressionResult: ...


class SubprocessCompressor:
    """Real integration adapter for any compressor that accepts stdin and writes stdout."""

    def __init__(self, command: Sequence[str], *, name: str = "external-compressor"):
        if not command:
            raise ValueError("A compressor command is required")
        self.command = tuple(command)
        self.name = name

    def compress(self, context: str, case: BenchmarkCase) -> CompressionResult:
        started = time.perf_counter()
        completed = subprocess.run(
            self.command,
            input=context,
            text=True,
            capture_output=True,
            check=True,
        )
        latency_ms = (time.perf_counter() - started) * 1000
        return CompressionResult(completed.stdout, estimate_tokens(completed.stdout), latency_ms)


class OpenAICompatibleAgent:
    """Minimal standard-library adapter for an OpenAI-compatible chat endpoint."""

    def __init__(
        self,
        endpoint: str,
        model: str,
        *,
        api_key: str | None = None,
        input_cost_per_million: float = 0.0,
        output_cost_per_million: float = 0.0,
        timeout_seconds: float = 120.0,
    ):
        self.endpoint = endpoint
        self.model = model
        self.api_key = api_key
        self.input_cost_per_million = input_cost_per_million
        self.output_cost_per_million = output_cost_per_million
        self.timeout_seconds = timeout_seconds

    def complete(self, instruction: str, context: str, case: BenchmarkCase) -> CompletionResult:
        payload = json.dumps(
            {
                "model": self.model,
                "temperature": 0,
                "messages": [
                    {"role": "system", "content": instruction},
                    {"role": "user", "content": context},
                ],
            }
        ).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = urllib.request.Request(self.endpoint, data=payload, headers=headers, method="POST")
        started = time.perf_counter()
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            data = json.loads(response.read().decode("utf-8"))
        latency_ms = (time.perf_counter() - started) * 1000
        usage = data.get("usage", {})
        input_tokens = int(usage.get("prompt_tokens", estimate_tokens(context)))
        output = data["choices"][0]["message"]["content"]
        output_tokens = int(usage.get("completion_tokens", estimate_tokens(output)))
        cost = (
            input_tokens * self.input_cost_per_million
            + output_tokens * self.output_cost_per_million
        ) / 1_000_000
        return CompletionResult(output, input_tokens, output_tokens, latency_ms, cost)


class DualArmExecutor:
    """Execute the same benchmark case with full and validated compressed context."""

    def __init__(
        self,
        agent: AgentClient,
        compressor: CompressorClient,
        *,
        experiment_id: str = "phase-1",
        validator: CompressionValidator | None = None,
        mode: CompressionMode = CompressionMode.BALANCED,
        recorded_at: str | None = None,
        experiment_config_version: str = "v1",
        pricing_version: str = "unspecified",
    ):
        self.agent = agent
        self.compressor = compressor
        self.experiment_id = experiment_id
        self.validator = validator or CompressionValidator()
        self.mode = mode
        self.recorded_at = recorded_at
        self.experiment_config_version = experiment_config_version
        self.pricing_version = pricing_version

    def __call__(self, case: BenchmarkCase, arm: ExperimentArm) -> RunOutcome:
        original_tokens = estimate_tokens(case.original_context)
        content = case.original_context
        compressed_tokens = original_tokens
        compression_latency_ms = 0.0
        compressor_cost = 0.0
        fallback_reason: str | None = None
        validator_result = "not_applied"

        strategy = settings_for(self.mode, case.task.task_type)
        if arm is ExperimentArm.COMPRESSED and not strategy.enabled:
            validator_result = f"policy_{self.mode.value}"
        elif arm is ExperimentArm.COMPRESSED:
            try:
                compressed = self.compressor.compress(case.original_context, case)
                compressed_tokens = compressed.tokens
                compression_latency_ms = compressed.latency_ms
                compressor_cost = compressed.estimated_cost
                active_validator = self.validator
                if self.mode is CompressionMode.CONSERVATIVE:
                    active_validator = CompressionValidator(
                        ValidationConfig(maximum_token_ratio=strategy.maximum_token_ratio)
                    )
                decision = validate_or_fallback(
                    active_validator,
                    original=case.original_context,
                    compressed=compressed.content,
                    original_tokens=original_tokens,
                    compressed_tokens=compressed_tokens,
                    required_signals=case.required_signals,
                )
                content = decision.content
                validator_result = "pass" if decision.used_compressed else "fallback"
                fallback_reason = decision.fallback_reason.value if decision.fallback_reason else None
            except (OSError, subprocess.SubprocessError, TimeoutError):
                content = case.original_context
                compressed_tokens = 0
                validator_result = "fallback"
                fallback_reason = FallbackReason.MODEL_TIMEOUT.value

        completion = self.agent.complete(case.instruction, content, case)
        success = case.is_success(completion.content)
        event = RequestEvent(
            experiment_id=self.experiment_id,
            task_id=case.task.task_id,
            session_id=f"{self.experiment_id}:{case.task.task_id}:{arm.value}",
            turn_id=1,
            arm=arm,
            treatment_name=f"{self.compressor.name}:{self.mode.value}",
            model=self.agent.model,
            task_type=case.task.task_type,
            language=case.task.language,
            repo_size=case.task.repo_size,
            tool_count=case.task.tool_count,
            session_length=case.task.session_length,
            original_tokens=original_tokens,
            compressed_tokens=compressed_tokens,
            recalled_tokens=original_tokens if fallback_reason else 0,
            compression_latency_ms=compression_latency_ms,
            total_latency_ms=compression_latency_ms + completion.latency_ms,
            validator_result=validator_result,
            fallback_reason=fallback_reason,
            task_success=success,
            tests_passed=success,
            manual_intervention=False,
            estimated_total_cost=compressor_cost + completion.estimated_cost,
            recorded_at=self.recorded_at or datetime.now(timezone.utc).isoformat(),
            experiment_config_version=self.experiment_config_version,
            pricing_version=self.pricing_version,
        )
        return RunOutcome(event)
