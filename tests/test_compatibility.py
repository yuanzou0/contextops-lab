import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from contextops_lab.compatibility import (
    audit_installed_paritok_compatibility,
    load_compatibility_matrix,
)


ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "configs/paritok-compatibility.json"


class CompatibilityMatrixTests(unittest.TestCase):
    def test_matrix_declares_historical_and_current_default_versions(self):
        payload = load_compatibility_matrix(MATRIX)
        versions = {row["version"] for row in payload["tested_versions"]}
        self.assertEqual(payload["default_version"], "1.3.11")
        self.assertEqual(versions, {"1.3.3", "1.3.11"})

    def test_matrix_rejects_default_outside_tested_versions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "matrix.json"
            path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "default_version": "9.9.9",
                        "latest_checked_at": "2026-09-05",
                        "tested_versions": [{"version": "1.3.11"}],
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "default_version"):
                load_compatibility_matrix(path)

    @patch("contextops_lab.compatibility.version", return_value="9.9.9")
    def test_unsupported_installed_version_fails_without_running_cache_audit(self, _version):
        with patch("contextops_lab.compatibility.audit_installed_paritok_cache") as cache_audit:
            payload = audit_installed_paritok_compatibility(MATRIX)
        self.assertFalse(payload["supported"])
        self.assertFalse(payload["passed"])
        self.assertIsNone(payload["cache_audit"])
        cache_audit.assert_not_called()

    @unittest.skipUnless(importlib.util.find_spec("paritok"), "optional live dependency not installed")
    def test_installed_version_satisfies_compatibility_contract(self):
        payload = audit_installed_paritok_compatibility(MATRIX)
        self.assertTrue(payload["supported"])
        self.assertTrue(payload["passed"])
        self.assertTrue(payload["checks"]["content_only_query_reuse_observed"])
        self.assertTrue(payload["checks"]["isolation_interventions_passed"])


if __name__ == "__main__":
    unittest.main()
