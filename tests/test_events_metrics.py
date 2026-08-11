from paritok_lab.events import JsonlEventStore
from paritok_lab.metrics import summarize
from paritok_lab.models import ExperimentArm, RequestEvent


def make_event(arm: ExperimentArm, success: bool, cost: float) -> RequestEvent:
    return RequestEvent(
        experiment_id="exp-1",
        task_id="task-1",
        session_id="session-1",
        turn_id=1,
        arm=arm,
        model="test-model",
        task_type="debugging",
        language="python",
        repo_size=100,
        tool_count=20,
        session_length=5,
        original_tokens=100,
        compressed_tokens=60 if arm is ExperimentArm.PARITOK else 100,
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


def test_event_store_and_quality_adjusted_cost(tmp_path):
    store = JsonlEventStore(tmp_path / "events.jsonl")
    baseline = make_event(ExperimentArm.BASELINE, True, 0.20)
    treatment = make_event(ExperimentArm.PARITOK, True, 0.12)
    store.append(baseline)
    store.append(treatment)

    assert len(store.read_all()) == 2
    metrics = summarize([baseline, treatment])
    assert metrics["baseline"]["cost_per_successful_task"] == 0.20
    assert metrics["paritok"]["effective_token_ratio"] == 0.60
