import json
import unittest
from pathlib import Path

from contextops_lab.execution import estimate_tokens
from contextops_lab.workloads import (
    audit_stage,
    build_session_messages,
    build_tool_schemas,
    load_pricing,
    load_workload_matrix,
    select_stage,
)


ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "configs/phase-3-workloads.json"
PRICING = ROOT / "configs/openai-pricing-2026-08-12.json"


class Phase3WorkloadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.matrix, cls.scenarios = load_workload_matrix(MATRIX)

    def test_matrix_expands_to_balanced_36_scenarios(self):
        self.assertEqual(len(self.scenarios), 36)
        self.assertEqual(len({item.scenario_id for item in self.scenarios}), 36)
        self.assertEqual(
            {item.task_type for item in self.scenarios},
            {"read_heavy", "debugging", "mcp_heavy", "edit_critical"},
        )
        self.assertEqual({item.context_tokens for item in self.scenarios}, {8000, 32000, 128000})
        self.assertEqual({item.session_turns for item in self.scenarios}, {1, 5, 10})

    def test_stages_limit_cost_exposure(self):
        self.assertEqual(len(select_stage(self.matrix, self.scenarios, "smoke")), 4)
        self.assertEqual(len(select_stage(self.matrix, self.scenarios, "core")), 16)
        wave_a = select_stage(self.matrix, self.scenarios, "wave_a")
        self.assertEqual(len(wave_a), 4)
        self.assertEqual(
            {(item.context_tokens, item.session_turns) for item in wave_a},
            {(32000, 5)},
        )
        evidence = select_stage(self.matrix, self.scenarios, "evidence")
        self.assertEqual(len(evidence), 20)
        self.assertEqual({item.context_tokens for item in evidence}, {32000, 128000})
        for task_type in {item.task_type for item in evidence}:
            self.assertEqual(sum(item.task_type == task_type for item in evidence), 5)
        self.assertEqual(len(select_stage(self.matrix, self.scenarios, "extended")), 36)

    def test_generated_history_hits_payload_band_and_preserves_signals(self):
        for scenario in self.scenarios:
            sessions = build_session_messages(scenario)
            self.assertEqual(len(sessions), scenario.session_turns)
            final_serialized = json.dumps(sessions[-1], sort_keys=True)
            final_tokens = estimate_tokens(final_serialized)
            self.assertLess(abs(final_tokens - scenario.context_tokens) / scenario.context_tokens, 0.03)
            for signal in scenario.required_signals:
                self.assertIn(signal, final_serialized)

    def test_tool_schema_count_matches_workload_profile(self):
        for scenario in self.scenarios:
            tools = build_tool_schemas(scenario)
            self.assertEqual(len(tools), scenario.tool_count)
            self.assertTrue(all(item["type"] == "function" for item in tools))

    def test_history_uses_compressible_bounded_tool_results(self):
        for scenario in self.scenarios:
            sessions = build_session_messages(scenario)
            tool_messages = [message for message in sessions[-1] if message["role"] == "tool"]
            self.assertTrue(tool_messages)
            self.assertTrue(
                all(estimate_tokens(message["content"]) < 50_000 for message in tool_messages)
            )
            final_request = sessions[-1][-1]["content"]
            self.assertNotIn(scenario.required_signals[0], final_request)

    def test_versioned_pricing_matches_selected_models(self):
        luna = load_pricing(PRICING, "gpt-5.6-luna")
        terra = load_pricing(PRICING, "gpt-5.6-terra")
        self.assertEqual(luna.version, "openai-2026-08-12")
        self.assertEqual((luna.input_per_million, luna.output_per_million), (1.0, 6.0))
        self.assertEqual((terra.input_per_million, terra.output_per_million), (2.5, 15.0))

    def test_smoke_audit_stays_below_declared_input_budget(self):
        smoke = select_stage(self.matrix, self.scenarios, "smoke")
        audit = audit_stage(smoke, load_pricing(PRICING, "gpt-5.6-luna"))
        self.assertEqual(audit["paired_request_count"], 8)
        self.assertLess(audit["estimated_paired_input_cost_upper_bound_usd"], 0.25)
        self.assertTrue(audit["excludes_output_and_paritok_compute_cost"])


if __name__ == "__main__":
    unittest.main()
