import unittest

from contextops_lab.experiments import ExperimentTask, PairedExperimentRunner, RunOutcome
from contextops_lab.models import ExperimentArm, RequestEvent


class ExperimentTests(unittest.TestCase):
    def test_runner_records_both_arms(self):
        written = []

        def executor(task, arm):
            return RunOutcome(
                RequestEvent(
                    experiment_id="exp-1",
                    task_id=task.task_id,
                    session_id=f"{task.task_id}-{arm.value}",
                    turn_id=1,
                    arm=arm,
                    treatment_name="fixture-compressor",
                    model="test",
                    task_type=task.task_type,
                    language=task.language,
                    repo_size=task.repo_size,
                    tool_count=task.tool_count,
                    session_length=task.session_length,
                    original_tokens=100,
                    compressed_tokens=60 if arm is ExperimentArm.COMPRESSED else 100,
                    recalled_tokens=0,
                    compression_latency_ms=10 if arm is ExperimentArm.COMPRESSED else 0,
                    total_latency_ms=100,
                    validator_result="pass",
                    fallback_reason=None,
                    task_success=True,
                    tests_passed=True,
                    manual_intervention=False,
                    estimated_total_cost=0.1,
                )
            )

        outcomes = PairedExperimentRunner(executor, written.append).run(
            [ExperimentTask("t1", "debugging", "python", 100, 20, 5)]
        )
        self.assertEqual(len(outcomes), 2)
        self.assertEqual(
            {event.arm for event in written},
            {ExperimentArm.BASELINE, ExperimentArm.COMPRESSED},
        )

    def test_arm_order_is_reproducible(self):
        task = ExperimentTask("t1", "debugging", "python", 100, 20, 5)

        def run_order():
            order = []

            def executor(current_task, arm):
                order.append(arm)
                event = RequestEvent(
                    "exp", current_task.task_id, "session", 1, arm, "fixture", "model",
                    current_task.task_type, current_task.language, current_task.repo_size,
                    current_task.tool_count, current_task.session_length, 10, 10, 0, 0, 1,
                    "pass", None, True, True, False, 0,
                )
                return RunOutcome(event)

            PairedExperimentRunner(executor, lambda event: None, seed=29).run([task])
            return order

        self.assertEqual(run_order(), run_order())


if __name__ == "__main__":
    unittest.main()
