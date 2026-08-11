"""Deterministic offline fixtures for validating the experiment pipeline."""

from __future__ import annotations

from .benchmark import BenchmarkCase
from .execution import CompletionResult, CompressionResult, estimate_tokens


class FixtureCompressor:
    name = "offline-fixture-compressor"

    def compress(self, context: str, case: BenchmarkCase) -> CompressionResult:
        if "COMPRESSION_TEST: empty" in context:
            return CompressionResult("", 0, 3.0, 0.00001)
        keep_lines = [line for line in context.splitlines() if line.startswith(("CASE:", "KEEP:"))]
        compressed = "\n".join(keep_lines)
        return CompressionResult(compressed, estimate_tokens(compressed), 3.0, 0.00001)


class FixtureAgent:
    model = "offline-deterministic-oracle"

    def complete(self, instruction: str, context: str, case: BenchmarkCase) -> CompletionResult:
        found = [marker for marker in case.expected_markers if marker in context]
        output = " | ".join(found)
        input_tokens = estimate_tokens(context)
        output_tokens = estimate_tokens(output)
        return CompletionResult(
            output,
            input_tokens,
            output_tokens,
            latency_ms=8.0 + input_tokens * 0.05,
            estimated_cost=input_tokens * 0.000002 + output_tokens * 0.000004,
        )
