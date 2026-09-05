import tempfile
import unittest
from pathlib import Path

from contextops_lab.analytics import segment_events
from contextops_lab.dashboard import build_dashboard
from contextops_lab.doctor import CheckStatus, run_doctor
from contextops_lab.events import load_events
from contextops_lab.failures import analyze_failures
from contextops_lab.models import ExperimentArm, RequestEvent
from contextops_lab.policy import PolicyEngine, generate_rollout_policy, write_policy
from contextops_lab.strategy import CompressionMode, settings_for


ROOT = Path(__file__).resolve().parents[1]


def event(task_id: str, arm: ExperimentArm, *, task_type: str = "debugging") -> RequestEvent:
    return RequestEvent(
        experiment_id="production-eval",
        task_id=task_id,
        session_id=f"{task_id}:{arm.value}",
        turn_id=1,
        arm=arm,
        treatment_name="compressor:balanced",
        model="test-model",
        task_type=task_type,
        language="python",
        repo_size=30_000,
        tool_count=24,
        session_length=12,
        original_tokens=100,
        compressed_tokens=60 if arm is ExperimentArm.COMPRESSED else 100,
        recalled_tokens=0,
        compression_latency_ms=5 if arm is ExperimentArm.COMPRESSED else 0,
        total_latency_ms=90 if arm is ExperimentArm.COMPRESSED else 100,
        validator_result="pass",
        fallback_reason=None,
        task_success=True,
        tests_passed=True,
        manual_intervention=False,
        estimated_total_cost=0.08 if arm is ExperimentArm.COMPRESSED else 0.10,
    )


class Phase2ProductLoopTests(unittest.TestCase):
    def test_segmentation_reports_uncertainty_and_dimensions(self):
        events = load_events(ROOT / "artifacts/phase-1-events.jsonl")
        segments = segment_events(events, ("task_type", "language", "repo_size"))
        self.assertTrue(any(segment.dimension == "language" for segment in segments))
        debugging = next(segment for segment in segments if segment.value == "debugging")
        self.assertLess(debugging.success_delta_ci_low, 0)
        self.assertGreater(debugging.cost_improvement_rate, 0)

    def test_failure_analysis_keeps_structured_fallback_reason(self):
        failures = analyze_failures(load_events(ROOT / "artifacts/phase-1-events.jsonl"))
        self.assertTrue(any(item.reason == "empty_output" for item in failures))

    def test_offline_policy_cannot_unlock_runtime(self):
        events = load_events(ROOT / "artifacts/phase-1-events.jsonl")
        policy = generate_rollout_policy(events, evidence_label="offline_deterministic")
        self.assertFalse(policy["production_ready"])
        self.assertIs(
            PolicyEngine(policy).mode_for(task_type="debugging"),
            CompressionMode.OFF,
        )

    def test_large_production_sample_can_select_balanced(self):
        events = []
        for index in range(400):
            events.extend(
                [
                    event(f"task-{index}", ExperimentArm.BASELINE),
                    event(f"task-{index}", ExperimentArm.COMPRESSED),
                ]
            )
        policy = generate_rollout_policy(events, evidence_label="production")
        self.assertTrue(policy["production_ready"])
        self.assertIs(
            PolicyEngine(policy).mode_for(task_type="debugging"),
            CompressionMode.BALANCED,
        )

    def test_strategy_modes_have_distinct_runtime_behavior(self):
        self.assertFalse(settings_for(CompressionMode.OFF, "debugging").enabled)
        self.assertFalse(settings_for(CompressionMode.CONSERVATIVE, "edit_critical").enabled)
        self.assertTrue(settings_for(CompressionMode.BALANCED, "debugging").enabled)

    def test_zero_treatment_successes_do_not_render_infinite_cost_improvement(self):
        baseline = event("failed-treatment", ExperimentArm.BASELINE)
        treatment = RequestEvent(
            **{
                **event("failed-treatment", ExperimentArm.COMPRESSED).to_dict(),
                "arm": ExperimentArm.COMPRESSED,
                "task_success": False,
                "tests_passed": False,
            }
        )
        segment = segment_events([baseline, treatment])[0]
        self.assertFalse(segment.treatment_cost_per_success_defined)
        self.assertEqual(segment.cost_improvement_rate, 0.0)

    def test_dashboard_and_doctor_enforce_evidence_boundary(self):
        events = load_events(ROOT / "artifacts/phase-1-events.jsonl")
        policy = generate_rollout_policy(events, evidence_label="offline_deterministic")
        dashboard = build_dashboard(events, policy, evidence_label="offline_deterministic")
        self.assertIn("Production rollout locked", dashboard)
        self.assertIn("Workload segmentation", dashboard)
        with tempfile.TemporaryDirectory() as directory:
            policy_path = Path(directory) / "policy.json"
            write_policy(policy, policy_path)
            checks = run_doctor(
                manifest=ROOT / "evals/tasks/mvp_tasks.jsonl",
                events=ROOT / "artifacts/phase-1-events.jsonl",
                policy=policy_path,
            )
        self.assertFalse(any(check.status is CheckStatus.FAIL for check in checks))


if __name__ == "__main__":
    unittest.main()
