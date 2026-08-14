"""Provider-neutral compressor adapters used as comparison controls."""

from __future__ import annotations

import re
import time

from .benchmark import BenchmarkCase
from .execution import CompressionResult, estimate_tokens


_RISK_PATTERNS = (
    re.compile(r"\b(error|exception|failed|identifier|file|path)\b", re.IGNORECASE),
    re.compile(r"(?:^|\s)(?:[\w.-]+/)+[\w.-]+"),
    re.compile(r"\b[A-Z][A-Za-z0-9_]*(?:Error|Exception)\b"),
)


class ExtractiveRiskCompressor:
    """Simple deterministic comparison compressor with no model dependency.

    It keeps boundary context and lines with generic identifier/path/error signals. It never reads
    benchmark answers, so it is a legitimate non-LLM baseline rather than an oracle compressor.
    """

    name = "extractive-risk-baseline"

    def __init__(self, *, maximum_token_ratio: float = 0.45):
        if not 0 < maximum_token_ratio <= 1:
            raise ValueError("maximum_token_ratio must be in (0, 1]")
        self.maximum_token_ratio = maximum_token_ratio

    def compress(self, context: str, case: BenchmarkCase) -> CompressionResult:
        del case  # This adapter deliberately does not inspect expected or required answers.
        started = time.perf_counter()
        lines = context.splitlines()
        target = max(1, int(estimate_tokens(context) * self.maximum_token_ratio))
        selected: list[tuple[int, str]] = []
        for index, line in enumerate(lines):
            boundary = index < 2 or index >= max(0, len(lines) - 2)
            risky = any(pattern.search(line) for pattern in _RISK_PATTERNS)
            if boundary or risky:
                selected.append((index, line))
        output: list[str] = []
        for _, line in sorted(set(selected)):
            candidate = "\n".join([*output, line])
            if estimate_tokens(candidate) > target and output:
                continue
            output.append(line)
        compressed = "\n".join(output)
        return CompressionResult(
            compressed,
            estimate_tokens(compressed),
            (time.perf_counter() - started) * 1000,
        )
