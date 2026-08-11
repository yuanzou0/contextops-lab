"""Production-shaped paired execution through direct and PariTok proxy endpoints."""

from __future__ import annotations

from datetime import datetime, timezone

from .benchmark import BenchmarkCase
from .execution import OpenAICompatibleAgent, estimate_tokens
from .experiments import RunOutcome
from .models import ExperimentArm, RequestEvent
from .paritok import PariTokGateway


class ProxyPairedExecutor:
    """Change only the endpoint between arms and capture proxy-attributed telemetry."""

    def __init__(
        self,
        baseline_agent: OpenAICompatibleAgent,
        paritok_agent: OpenAICompatibleAgent,
        gateway: PariTokGateway,
        *,
        experiment_id: str,
        config_version: str,
        config_sha256: str,
        pricing_version: str,
        require_proxy_telemetry: bool = True,
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

    def __call__(self, case: BenchmarkCase, arm: ExperimentArm) -> RunOutcome:
        original_tokens = estimate_tokens(case.original_context)
        compressed_tokens = original_tokens
        proxy_requests = 0
        proxy_tokens_saved = 0

        if arm is ExperimentArm.BASELINE:
            completion = self.baseline_agent.complete(case.instruction, case.original_context, case)
            original_tokens = completion.input_tokens
            compressed_tokens = completion.input_tokens
            treatment_name = "direct-provider"
            endpoint_role = "baseline_direct"
        else:
            before = self.gateway.stats()
            completion = self.paritok_agent.complete(case.instruction, case.original_context, case)
            after = self.gateway.stats()
            delta = after.delta(before)
            if self.require_proxy_telemetry and delta.total_requests != 1:
                raise RuntimeError(
                    "Expected exactly one PariTok request between telemetry snapshots; "
                    f"observed {delta.total_requests}"
                )
            if delta.total_requests:
                original_tokens = delta.input_tokens_original
                compressed_tokens = delta.input_tokens_compressed
                proxy_requests = delta.total_requests
                proxy_tokens_saved = delta.tokens_saved
            treatment_name = "paritok-proxy"
            endpoint_role = "treatment_proxy"

        success = case.is_success(completion.content)
        event = RequestEvent(
            experiment_id=self.experiment_id,
            task_id=case.task_id,
            session_id=f"{self.experiment_id}:{case.task_id}:{arm.value}",
            turn_id=1,
            arm=arm,
            treatment_name=treatment_name,
            model=self.baseline_agent.model,
            task_type=case.task.task_type,
            language=case.task.language,
            repo_size=case.task.repo_size,
            tool_count=case.task.tool_count,
            session_length=case.task.session_length,
            original_tokens=original_tokens,
            compressed_tokens=compressed_tokens,
            recalled_tokens=0,
            compression_latency_ms=0.0,
            total_latency_ms=completion.latency_ms,
            validator_result="proxy_managed" if arm is ExperimentArm.COMPRESSED else "not_applied",
            fallback_reason=None,
            task_success=success,
            tests_passed=success,
            manual_intervention=False,
            estimated_total_cost=completion.estimated_cost,
            recorded_at=datetime.now(timezone.utc).isoformat(),
            experiment_config_version=self.config_version,
            pricing_version=self.pricing_version,
            endpoint_role=endpoint_role,
            provider_input_tokens=completion.input_tokens,
            provider_output_tokens=completion.output_tokens,
            proxy_request_count=proxy_requests,
            proxy_tokens_saved=proxy_tokens_saved,
            config_sha256=self.config_sha256,
        )
        return RunOutcome(event)
