"""ContextOps Lab: AI-agent context reliability and cost evaluation."""

from .benchmark import BenchmarkCase, load_benchmark_cases
from .execution import CompletionResult, DualArmExecutor, SubprocessCompressor
from .experiments import ExperimentTask, PairedExperimentRunner, RunOutcome
from .models import ExperimentArm, RequestEvent
from .validator import CompressionValidator, FallbackReason, ValidationConfig

__all__ = [
    "BenchmarkCase",
    "CompletionResult",
    "CompressionValidator",
    "DualArmExecutor",
    "ExperimentArm",
    "ExperimentTask",
    "FallbackReason",
    "PairedExperimentRunner",
    "RequestEvent",
    "RunOutcome",
    "SubprocessCompressor",
    "ValidationConfig",
    "load_benchmark_cases",
]
