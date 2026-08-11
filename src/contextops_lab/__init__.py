"""ContextOps Lab: AI-agent context reliability and cost evaluation."""

from .benchmark import BenchmarkCase, load_benchmark_cases
from .execution import CompletionResult, DualArmExecutor, SubprocessCompressor
from .experiments import ExperimentTask, PairedExperimentRunner, RunOutcome
from .models import ExperimentArm, RequestEvent
from .policy import PolicyEngine, PolicyThresholds, generate_rollout_policy
from .strategy import CompressionMode
from .validator import CompressionValidator, FallbackReason, ValidationConfig

__all__ = [
    "BenchmarkCase",
    "CompletionResult",
    "CompressionValidator",
    "CompressionMode",
    "DualArmExecutor",
    "ExperimentArm",
    "ExperimentTask",
    "FallbackReason",
    "PairedExperimentRunner",
    "PolicyEngine",
    "PolicyThresholds",
    "RequestEvent",
    "RunOutcome",
    "SubprocessCompressor",
    "ValidationConfig",
    "generate_rollout_policy",
    "load_benchmark_cases",
]
