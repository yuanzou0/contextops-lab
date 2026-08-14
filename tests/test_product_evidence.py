import unittest
from dataclasses import replace

from contextops_lab.benchmark import load_benchmark_cases
from contextops_lab.compressors import ExtractiveRiskCompressor
from contextops_lab.eligibility import decide_eligibility
from contextops_lab.economics import build_multi_turn_economics
from contextops_lab.evidence import QualityReview, audit_evidence
from contextops_lab.events import load_events
from contextops_lab.latency import decompose_paired_latency, measure_local_latency_states
from contextops_lab.models import ExperimentArm


class ProductEvidenceTests(unittest.TestCase):
    def test_extractive_compressor_is_answer_independent_and_preserves_risk_lines(self):
        case = load_benchmark_cases("evals/tasks/mvp_tasks.jsonl")[0]
        compressor = ExtractiveRiskCompressor(maximum_token_ratio=0.75)
        result = compressor.compress(case.original_context, case)
        self.assertLess(result.tokens, len(case.original_context))
        self.assertIn("KEEP: file=", result.content)
        self.assertIn("KEEP: error=", result.content)

    def test_latency_eligibility_blocks_short_sync_and_allows_amortized_long_context(self):
        blocked = decide_eligibility(
            context_tokens=8_000,
            session_turns=1,
            risk_level="medium",
        )
        self.assertFalse(blocked.eligible)
        self.assertIn("latency_not_amortized", blocked.reasons)
        allowed = decide_eligibility(
            context_tokens=128_000,
            session_turns=5,
            risk_level="medium",
        )
        self.assertTrue(allowed.eligible)
        self.assertEqual(allowed.mode, "balanced")
        drifted = decide_eligibility(
            context_tokens=128_000,
            session_turns=5,
            risk_level="medium",
            reusable_cache=True,
            query_stable=False,
        )
        self.assertFalse(drifted.eligible)
        self.assertIn("query_sensitive_cache_risk", drifted.reasons)

    def test_current_smoke_fails_sample_context_and_review_gates(self):
        events = load_events("artifacts/phase-3-session-events.jsonl")
        audit = audit_evidence(events)
        self.assertFalse(audit["sample_gate_passed"])
        self.assertFalse(audit["context_gate_passed"])
        self.assertFalse(audit["quality_review"]["gate_passed"])
        self.assertFalse(audit["quality_claim_allowed"])

    def test_independent_quality_review_schema(self):
        row = QualityReview("task", ExperimentArm.BASELINE, "human", "reviewer-1", 0.8, "ok")
        self.assertEqual(row.to_dict()["arm"], "baseline")
        with self.assertRaises(ValueError):
            QualityReview("task", ExperimentArm.BASELINE, "marker", "reviewer-1", 1.0, "ok")

    def test_missing_required_workloads_cannot_pass_evidence_gate(self):
        events = [
            event
            for event in load_events("artifacts/phase-3-session-events.jsonl")
            if event.task_type == "read_heavy"
        ]
        audit = audit_evidence(events, minimum_pairs_per_segment=1, required_contexts=(8_000,))
        missing = next(row for row in audit["segments"] if row["task_type"] == "debugging")
        self.assertEqual(missing["paired_tasks"], 0)
        self.assertFalse(audit["sample_gate_passed"])

    def test_latency_decomposition_is_explicitly_estimated(self):
        rows = decompose_paired_latency(load_events("artifacts/phase-3-session-events.jsonl"))
        self.assertEqual(len(rows), 4)
        self.assertTrue(all(row.measurement == "paired_estimate" for row in rows))
        self.assertTrue(all(row.incremental_local_and_proxy_ms > 0 for row in rows))

    def test_local_probe_separates_warm_uncached_from_cache_reuse(self):
        class Result:
            original_tokens = 100
            compressed_tokens = 40

            def __init__(self, cache_hit):
                self.metadata = {"cache_hit": cache_hit}

        seen = []

        def compressor(content):
            cache_hit = content in seen
            seen.append(content)
            return Result(cache_hit)

        payload = measure_local_latency_states(compressor, "cold", "warm")
        states = payload["states"]
        self.assertEqual(
            [row["state"] for row in states],
            ["cold_candidate", "warm_uncached", "cache_reuse"],
        )
        self.assertEqual([row["cache_hit"] for row in states], [False, False, True])
        with self.assertRaises(ValueError):
            measure_local_latency_states(compressor, "same", "same")

    def test_multi_turn_economics_requires_explicit_latency_value_for_break_even(self):
        seed = load_events("artifacts/phase-3-session-events.jsonl")[:2]
        baseline = next(row for row in seed if row.arm is ExperimentArm.BASELINE)
        treatment = next(row for row in seed if row.arm is ExperimentArm.COMPRESSED)
        events = []
        for turn in (1, 2):
            events.extend(
                (
                    replace(
                        baseline,
                        task_id="curve-task",
                        turn_id=turn,
                        estimated_total_cost=0.10,
                        total_latency_ms=100,
                    ),
                    replace(
                        treatment,
                        task_id="curve-task",
                        turn_id=turn,
                        estimated_total_cost=0.04,
                        total_latency_ms=200,
                    ),
                )
            )
        without_value = build_multi_turn_economics(events)
        self.assertIsNone(without_value["tasks"][0]["break_even_turn"])
        valued = build_multi_turn_economics(events, latency_value_usd_per_second=0.1)
        self.assertEqual(valued["tasks"][0]["break_even_turn"], 1)
        self.assertAlmostEqual(valued["tasks"][0]["curve"][1]["net_value_usd"], 0.10)


if __name__ == "__main__":
    unittest.main()
