import tempfile
import unittest
from pathlib import Path

from contextops_lab.events import JsonlEventStore
from contextops_lab.metrics import summarize
from contextops_lab.models import ExperimentArm, RequestEvent


def make_event(arm: ExperimentArm, success: bool, cost: float) -> RequestEvent:
    return RequestEvent(
        experiment_id="exp-1",
        task_id="task-1",
        session_id="session-1",
        turn_id=1,
        arm=arm,
        treatment_name="fixture-compressor",
        model="test-model",
        task_type="debugging",
        language="python",
        repo_size=100,
        tool_count=20,
        session_length=5,
        original_tokens=100,
        compressed_tokens=60 if arm is ExperimentArm.COMPRESSED else 100,
        recalled_tokens=0,
        compression_latency_ms=10,
        total_latency_ms=100,
        validator_result="pass",
        fallback_reason=None,
        task_success=success,
        tests_passed=success,
        manual_intervention=False,
        estimated_total_cost=cost,
    )


class EventMetricTests(unittest.TestCase):
    def test_event_store_and_quality_adjusted_cost(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JsonlEventStore(Path(directory) / "events.jsonl")
            baseline = make_event(ExperimentArm.BASELINE, True, 0.20)
            treatment = make_event(ExperimentArm.COMPRESSED, True, 0.12)
            store.append(baseline)
            store.append(treatment)
            self.assertEqual(len(store.read_all()), 2)
        metrics = summarize([baseline, treatment])
        self.assertEqual(metrics["baseline"]["cost_per_successful_task"], 0.20)
        self.assertEqual(metrics["compressed"]["effective_token_ratio"], 0.60)


if __name__ == "__main__":
    unittest.main()
