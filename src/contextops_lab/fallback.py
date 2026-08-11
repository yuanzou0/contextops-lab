"""Fail-open-to-original decision logic."""

from __future__ import annotations

from dataclasses import dataclass

from .validator import CompressionValidator, FallbackReason, ValidationResult


@dataclass(frozen=True, slots=True)
class CompressionDecision:
    content: str
    used_compressed: bool
    fallback_reason: FallbackReason | None
    validation: ValidationResult


def validate_or_fallback(
    validator: CompressionValidator,
    *,
    original: str,
    compressed: str,
    original_tokens: int,
    compressed_tokens: int,
    available_references: tuple[str, ...] = (),
    required_signals: tuple[str, ...] = (),
) -> CompressionDecision:
    validation = validator.validate(
        original=original,
        compressed=compressed,
        original_tokens=original_tokens,
        compressed_tokens=compressed_tokens,
        available_references=available_references,
        required_signals=required_signals,
    )
    if validation.accepted:
        return CompressionDecision(compressed, True, None, validation)
    return CompressionDecision(original, False, validation.primary_reason, validation)
