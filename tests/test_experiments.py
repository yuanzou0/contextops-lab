from paritok_lab.experiments import ExperimentTask, PairedExperimentRunner, RunOutcome
from paritok_lab.models import ExperimentArm, RequestEvent


def test_runner_records_both_arms():
    written = []

    def executor(task, arm):
        event = RequestEvent(
            experiment_id="exp-1",
            task_id=task.task_id,
            session_id=f"{task.task_id}-{arm.value}",
            turn_id=1,
            arm=arm,
            model="test",
            task_type=task.task_type,
            language=task.language,
            repo_size=task.repo_size,
            tool_count=task.tool_count,
            session_length=task.session_length,
            original_tokens=100,
            compressed_tokens=60 if arm is ExperimentArm.PARITOK else 100,
            recalled_tokens=0,
            compression_latency_ms=10 if arm is ExperimentArm.PARITOK else 0,
            total_latency_ms=100,
            validator_result="pass",
            fallback_reason=None,
            task_success=True,
            tests_passed=True,
            manual_intervention=False,
            estimated_total_cost=0.1,
        )
        return RunOutcome(event)

    runner = PairedExperimentRunner(executor, written.append)
    outcomes = runner.run([ExperimentTask("t1", "debugging", "python", 100, 20, 5)])

    assert len(outcomes) == 2
    assert {event.arm for event in written} == {
        ExperimentArm.BASELINE,
        ExperimentArm.PARITOK,
    }
