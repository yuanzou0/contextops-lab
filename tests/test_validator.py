import unittest

from contextops_lab.fallback import validate_or_fallback
from contextops_lab.validator import CompressionValidator, FallbackReason


class ValidatorTests(unittest.TestCase):
    def test_empty_output_falls_back_to_original(self):
        decision = validate_or_fallback(
            CompressionValidator(),
            original="def refresh_token(): raise TokenExpiredError()",
            compressed="",
            original_tokens=20,
            compressed_tokens=0,
        )
        self.assertFalse(decision.used_compressed)
        self.assertIs(decision.fallback_reason, FallbackReason.EMPTY_OUTPUT)
        self.assertTrue(decision.content.startswith("def refresh_token"))

    def test_missing_critical_signal_is_rejected(self):
        result = CompressionValidator().validate(
            original="Failure in refresh_token at src/auth.py: TokenExpiredError",
            compressed="Authentication failed in the token flow.",
            original_tokens=30,
            compressed_tokens=8,
            required_signals=("refresh_token",),
        )
        reasons = {finding.reason for finding in result.findings}
        self.assertIn(FallbackReason.IDENTIFIER_LOSS, reasons)
        self.assertIn(FallbackReason.FILE_PATH_LOSS, reasons)
        self.assertIn(FallbackReason.ERROR_MESSAGE_LOSS, reasons)

    def test_valid_reference_and_signals_are_accepted(self):
        result = CompressionValidator().validate(
            original="Failure in refresh_token at src/auth.py: TokenExpiredError",
            compressed="[REF:abc123] refresh_token fails in src/auth.py with TokenExpiredError",
            original_tokens=30,
            compressed_tokens=12,
            available_references=("abc123",),
            required_signals=("refresh_token",),
        )
        self.assertTrue(result.accepted)


if __name__ == "__main__":
    unittest.main()
