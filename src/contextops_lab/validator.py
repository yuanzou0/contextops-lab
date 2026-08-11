"""Layered validation for compressed agent context."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Collection


class FallbackReason(str, Enum):
    EMPTY_OUTPUT = "empty_output"
    MALFORMED_REFERENCE = "malformed_reference"
    INVALID_REFERENCE = "invalid_reference"
    IDENTIFIER_LOSS = "identifier_loss"
    FILE_PATH_LOSS = "file_path_loss"
    ERROR_MESSAGE_LOSS = "error_message_loss"
    OUTPUT_EXPANSION = "output_expansion"
    MODEL_TIMEOUT = "model_timeout"
    POLICY_BYPASS = "policy_bypass"


@dataclass(frozen=True, slots=True)
class ValidationConfig:
    maximum_token_ratio: float = 1.05
    require_all_references: bool = True


@dataclass(frozen=True, slots=True)
class ValidationFinding:
    reason: FallbackReason
    detail: str


@dataclass(frozen=True, slots=True)
class ValidationResult:
    accepted: bool
    findings: tuple[ValidationFinding, ...]

    @property
    def primary_reason(self) -> FallbackReason | None:
        return self.findings[0].reason if self.findings else None


class CompressionValidator:
    _reference = re.compile(r"\[REF:([A-Za-z0-9_-]+)(?:\s+[^\]]*)?\]")
    _reference_prefix = re.compile(r"\[REF:")
    _file_path = re.compile(r"(?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+\.[A-Za-z0-9]+")
    _error_name = re.compile(r"\b[A-Z][A-Za-z0-9]*(?:Error|Exception)\b")

    def __init__(self, config: ValidationConfig | None = None):
        self.config = config or ValidationConfig()

    def validate(
        self,
        *,
        original: str,
        compressed: str,
        original_tokens: int,
        compressed_tokens: int,
        available_references: Collection[str] = (),
        required_signals: Collection[str] = (),
    ) -> ValidationResult:
        findings: list[ValidationFinding] = []
        if not compressed.strip():
            findings.append(ValidationFinding(FallbackReason.EMPTY_OUTPUT, "empty compression"))
            return ValidationResult(False, tuple(findings))

        if original_tokens > 0 and (
            compressed_tokens / original_tokens > self.config.maximum_token_ratio
        ):
            findings.append(
                ValidationFinding(
                    FallbackReason.OUTPUT_EXPANSION,
                    f"token ratio {compressed_tokens / original_tokens:.3f} exceeds limit",
                )
            )

        references = self._reference.findall(compressed)
        if len(references) != len(self._reference_prefix.findall(compressed)):
            findings.append(
                ValidationFinding(FallbackReason.MALFORMED_REFERENCE, "malformed [REF:] tag")
            )
        if self.config.require_all_references:
            missing_refs = sorted(set(references) - set(available_references))
            if missing_refs:
                findings.append(
                    ValidationFinding(
                        FallbackReason.INVALID_REFERENCE,
                        f"unavailable references: {', '.join(missing_refs)}",
                    )
                )

        signals = set(required_signals)
        signals.update(self._file_path.findall(original))
        signals.update(self._error_name.findall(original))
        missing = sorted(signal for signal in signals if signal and signal not in compressed)
        for signal in missing:
            if self._file_path.fullmatch(signal):
                reason = FallbackReason.FILE_PATH_LOSS
            elif self._error_name.fullmatch(signal):
                reason = FallbackReason.ERROR_MESSAGE_LOSS
            else:
                reason = FallbackReason.IDENTIFIER_LOSS
            findings.append(ValidationFinding(reason, f"missing critical signal: {signal}"))

        return ValidationResult(not findings, tuple(findings))
