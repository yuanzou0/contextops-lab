import unittest
from pathlib import Path

from contextops_lab.execution import CompletionResult
from contextops_lab.metrics import summarize
from contextops_lab.models import ExperimentArm
from contextops_lab.paritok import ContextOpsSafetyStats, ProxyStats
from contextops_lab.session_live import MultiTurnProxyExecutor, run_paired_sessions
from contextops_lab.workloads import load_workload_matrix


ROOT = Path(__file__).resolve().parents[1]


class FakeMessageAgent:
    model = "gpt-5.6-luna"

    def __init__(self, signals):
        self.signals = signals
        self.calls = 0

    def complete_messages(self, messages, *, tools=None):
        self.calls += 1
        terminal = "FINAL_TASK:" in messages[-1]["content"]
        content = "\n".join(self.signals) if terminal else "CONTEXT_RECORDED"
        return CompletionResult(content, 60, 4, 10.0, 0.001)


class IncrementingGateway:
    def __init__(self):
        self.call = 0

    def stats(self):
        request = self.call // 2
        after = self.call % 2
        self.call += 1
        return ProxyStats(
            total_requests=request + after,
            input_tokens_original=(request + after) * 100,
            input_tokens_compressed=(request + after) * 60,
            tokens_saved=(request + after) * 40,
            estimated_cost_saved_usd=(request + after) * 0.00004,
        )


class IncrementingSafetyGateway:
    def __init__(self):
        self.call = 0

    def stats(self):
        request = self.call // 2
        after = self.call % 2
        self.call += 1
        count = request + after
        return ContextOpsSafetyStats(
            cache_contract="query_aware",
            total_compressions=count,
            validated=count,
            validator_passes=count,
            fallbacks=0,
            exact_original_fallbacks=0,
            skipped=0,
            cache_hits=0,
            compression_latency_ms=count * 5.0,
            fallback_reasons={},
        )


class SessionLiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _, scenarios = load_workload_matrix(ROOT / "configs/phase-3-workloads.json")
        cls.scenario = next(
            item
            for item in scenarios
            if item.task_type == "read_heavy"
            and item.context_tokens == 8000
            and item.session_turns == 5
        )

    def test_multi_turn_arm_records_every_request_and_one_terminal_result(self):
        baseline = FakeMessageAgent(self.scenario.required_signals)
        treatment = FakeMessageAgent(self.scenario.required_signals)
        executor = MultiTurnProxyExecutor(
            baseline,
            treatment,
            IncrementingGateway(),
            experiment_id="session-test",
            config_version="v1",
            config_sha256="a" * 64,
            pricing_version="openai-test",
        )
        outcome = executor.run_arm(self.scenario, ExperimentArm.COMPRESSED)
        self.assertEqual(len(outcome.events), 5)
        self.assertTrue(outcome.terminal_success)
        self.assertEqual(sum(event.is_terminal_turn for event in outcome.events), 1)
        self.assertEqual([event.turn_id for event in outcome.events], [1, 2, 3, 4, 5])
        self.assertTrue(all(event.proxy_request_count == 1 for event in outcome.events))
        self.assertTrue(all(event.proxy_tokens_saved == 40 for event in outcome.events))
        self.assertEqual(outcome.events[-1].outcome_measure, "critical_signal_recall")
        self.assertEqual(outcome.events[-1].required_signals_total, 3)
        self.assertEqual(outcome.events[-1].required_signals_recalled, 3)

    def test_paired_runner_and_metrics_count_session_success_not_ack_turns(self):
        baseline = FakeMessageAgent(self.scenario.required_signals)
        treatment = FakeMessageAgent(self.scenario.required_signals)
        executor = MultiTurnProxyExecutor(
            baseline,
            treatment,
            IncrementingGateway(),
            experiment_id="session-test",
            config_version="v1",
            config_sha256="b" * 64,
            pricing_version="openai-test",
        )
        events = []
        outcomes = run_paired_sessions([self.scenario], executor, events.append, seed=17)
        self.assertEqual(len(outcomes), 2)
        self.assertEqual(len(events), 10)
        metrics = summarize(events)
        self.assertEqual(metrics["baseline"]["runs"], 1)
        self.assertEqual(metrics["baseline"]["requests"], 5)
        self.assertAlmostEqual(metrics["baseline"]["cost_per_successful_task"], 0.005)

    def test_safe_proxy_telemetry_is_attributed_to_treatment_events(self):
        baseline = FakeMessageAgent(self.scenario.required_signals)
        treatment = FakeMessageAgent(self.scenario.required_signals)
        executor = MultiTurnProxyExecutor(
            baseline,
            treatment,
            IncrementingGateway(),
            experiment_id="safe-session-test",
            config_version="v1",
            config_sha256="c" * 64,
            pricing_version="openai-test",
            safety_gateway=IncrementingSafetyGateway(),
        )
        outcome = executor.run_arm(self.scenario, ExperimentArm.COMPRESSED)
        self.assertTrue(outcome.terminal_success)
        self.assertTrue(all(event.validator_result == "pass" for event in outcome.events))
        self.assertTrue(all(event.fallback_reason is None for event in outcome.events))
        self.assertTrue(all(event.compression_latency_ms == 5.0 for event in outcome.events))
        self.assertTrue(
            all(event.endpoint_role == "treatment_safe_proxy" for event in outcome.events)
        )


if __name__ == "__main__":
    unittest.main()
