import json
import unittest
from pathlib import Path
from unittest.mock import patch

from contextops_lab.benchmark import load_benchmark_cases
from contextops_lab.cli import build_parser
from contextops_lab.execution import CompletionResult
from contextops_lab.live import ProxyPairedExecutor
from contextops_lab.live_config import load_live_config
from contextops_lab.models import ExperimentArm
from contextops_lab.paritok import PariTokGateway, ProxyStats


ROOT = Path(__file__).resolve().parents[1]


class _Agent:
    model = "same-model"

    def complete(self, instruction, context, case):
        return CompletionResult(
            content=" ".join(case.expected_markers),
            input_tokens=100,
            output_tokens=10,
            latency_ms=25.0,
            estimated_cost=0.002,
        )


class _Gateway:
    def __init__(self):
        self.snapshots = iter(
            [
                ProxyStats(9, 900, 600, 300, 0.09),
                ProxyStats(10, 1000, 660, 340, 0.10),
            ]
        )

    def stats(self):
        return next(self.snapshots)


class Phase3LiveIntegrationTests(unittest.TestCase):
    def test_config_is_validated_and_hashed_without_reading_secret(self):
        config, digest = load_live_config(ROOT / "configs/phase-3.example.json")
        self.assertEqual(config.config_version, "phase-3-v1")
        self.assertEqual(len(digest), 64)
        self.assertNotIn("api_key", config.public_dict())

    def test_proxy_stats_delta_rejects_counter_reset(self):
        current = ProxyStats(1, 100, 50, 50, 0.01)
        previous = ProxyStats(2, 200, 100, 100, 0.02)
        with self.assertRaises(ValueError):
            current.delta(previous)

    def test_gateway_parses_health_and_stats_contract(self):
        payloads = iter(
            [
                {"status": "ok", "version": "1.3.0"},
                {
                    "total_requests": 7,
                    "input_tokens_original": 700,
                    "input_tokens_compressed": 420,
                    "tokens_saved": 280,
                    "estimated_cost_saved_usd": 0.07,
                },
            ]
        )

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return json.dumps(next(payloads)).encode()

        gateway = PariTokGateway("http://proxy/health", "http://proxy/stats")
        with patch("urllib.request.urlopen", side_effect=[Response(), Response()]):
            self.assertEqual(gateway.health()["version"], "1.3.0")
            self.assertEqual(gateway.stats().tokens_saved, 280)

    def test_gateway_accepts_currency_formatted_saved_cost(self):
        stats = ProxyStats.from_dict({"estimated_cost_saved_usd": "$1.01"})
        self.assertEqual(stats.estimated_cost_saved_usd, 1.01)

    def test_gateway_fails_closed_when_compression_model_is_missing(self):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return json.dumps({"data": [{"id": "another-model"}]}).encode()

        gateway = PariTokGateway("http://proxy/health", "http://proxy/stats")
        with patch("urllib.request.urlopen", return_value=Response()):
            with self.assertRaisesRegex(RuntimeError, "Compression model"):
                gateway.require_compression_model("http://ollama/v1/models", "paritok-4b-v1")

    def test_gateway_accepts_namespaced_ollama_model(self):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return json.dumps({"data": [{"id": "paritok/paritok-4b-v1:latest"}]}).encode()

        gateway = PariTokGateway("http://proxy/health", "http://proxy/stats")
        with patch("urllib.request.urlopen", return_value=Response()):
            payload = gateway.require_compression_model(
                "http://ollama/v1/models", "paritok-4b-v1"
            )
        self.assertEqual(payload["data"][0]["id"], "paritok/paritok-4b-v1:latest")

    def test_proxy_arm_attributes_tokens_from_isolated_stats_delta(self):
        case = load_benchmark_cases(ROOT / "evals/tasks/mvp_tasks.jsonl")[0]
        executor = ProxyPairedExecutor(
            _Agent(),
            _Agent(),
            _Gateway(),
            experiment_id="live-test",
            config_version="v1",
            config_sha256="a" * 64,
            pricing_version="prices-v1",
        )
        event = executor(case, ExperimentArm.COMPRESSED).event
        self.assertTrue(event.task_success)
        self.assertEqual(event.original_tokens, 100)
        self.assertEqual(event.compressed_tokens, 60)
        self.assertEqual(event.proxy_tokens_saved, 40)
        self.assertEqual(event.proxy_request_count, 1)
        self.assertEqual(event.endpoint_role, "treatment_proxy")

    def test_proxy_arm_fails_closed_when_stats_are_not_isolated(self):
        class BusyGateway(_Gateway):
            def __init__(self):
                self.snapshots = iter(
                    [ProxyStats(1, 10, 8, 2, 0.0), ProxyStats(3, 30, 20, 10, 0.0)]
                )

        case = load_benchmark_cases(ROOT / "evals/tasks/mvp_tasks.jsonl")[0]
        executor = ProxyPairedExecutor(
            _Agent(),
            _Agent(),
            BusyGateway(),
            experiment_id="live-test",
            config_version="v1",
            config_sha256="b" * 64,
            pricing_version="prices-v1",
        )
        with self.assertRaisesRegex(RuntimeError, "exactly one PariTok request"):
            executor(case, ExperimentArm.COMPRESSED)

    def test_live_cli_requires_explicit_cost_confirmation(self):
        parser = build_parser()
        args = parser.parse_args(["live-run"])
        self.assertEqual(args.func(args), 2)

    def test_session_cli_requires_confirmation_before_api_key_or_gateway(self):
        parser = build_parser()
        args = parser.parse_args(["live-session-run"])
        self.assertEqual(args.func(args), 2)

    def test_session_cli_blocks_cost_above_explicit_ceiling(self):
        parser = build_parser()
        args = parser.parse_args(
            [
                "live-session-run",
                "--stage",
                "extended",
                "--max-estimated-input-cost-usd",
                "0.01",
                "--confirm-live-costs",
            ]
        )
        self.assertEqual(args.func(args), 2)

    def test_session_cli_blocks_unverified_cache_before_paid_wave_a(self):
        parser = build_parser()
        args = parser.parse_args(
            [
                "live-session-run",
                "--config",
                "configs/phase-3-luna-wave-a.json",
                "--stage",
                "wave_a",
                "--confirm-live-costs",
            ]
        )
        self.assertEqual(args.func(args), 2)

    def test_live_configs_disable_retries_for_measured_runs(self):
        for name in ("phase-3-luna-smoke.json", "phase-3-terra-formal.json"):
            config, _ = load_live_config(ROOT / "configs" / name)
            self.assertEqual(config.max_retries, 0)
        luna, _ = load_live_config(ROOT / "configs/phase-3-luna-smoke.json")
        self.assertGreaterEqual(
            luna.timeout_seconds,
            300,
        )


if __name__ == "__main__":
    unittest.main()
