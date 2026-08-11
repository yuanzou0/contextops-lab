from paritok_lab.fallback import validate_or_fallback
from paritok_lab.validator import CompressionValidator, FallbackReason


def test_empty_output_falls_back_to_original():
    validator = CompressionValidator()
    decision = validate_or_fallback(
        validator,
        original="def refresh_token(): raise TokenExpiredError()",
        compressed="",
        original_tokens=20,
        compressed_tokens=0,
    )
    assert decision.used_compressed is False
    assert decision.fallback_reason is FallbackReason.EMPTY_OUTPUT
    assert decision.content.startswith("def refresh_token")


def test_missing_critical_signal_is_rejected():
    validator = CompressionValidator()
    result = validator.validate(
        original="Failure in refresh_token at src/auth.py: TokenExpiredError",
        compressed="Authentication failed in the token flow.",
        original_tokens=30,
        compressed_tokens=8,
        required_signals=("refresh_token",),
    )
    reasons = {finding.reason for finding in result.findings}
    assert FallbackReason.IDENTIFIER_LOSS in reasons
    assert FallbackReason.FILE_PATH_LOSS in reasons
    assert FallbackReason.ERROR_MESSAGE_LOSS in reasons


def test_valid_reference_and_signals_are_accepted():
    validator = CompressionValidator()
    result = validator.validate(
        original="Failure in refresh_token at src/auth.py: TokenExpiredError",
        compressed=(
            "[REF:abc123] refresh_token fails in src/auth.py with TokenExpiredError"
        ),
        original_tokens=30,
        compressed_tokens=12,
        available_references=("abc123",),
        required_signals=("refresh_token",),
    )
    assert result.accepted is True
