import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from contextops_lab.benchmark import load_benchmark_cases
from contextops_lab.execution import DualArmExecutor, OpenAICompatibleAgent, SubprocessCompressor
from contextops_lab.fixtures import FixtureAgent, FixtureCompressor
from contextops_lab.models import ExperimentArm


ROOT = Path(__file__).resolve().parents[1]


class BenchmarkExecutionTests(unittest.TestCase):
    def test_manifest_loads_as_36_executable_cases(self):
        cases = load_benchmark_cases(ROOT / "evals/tasks/mvp_tasks.jsonl")
        self.assertEqual(len(cases), 36)
        self.assertEqual(len({case.task_id for case in cases}), 36)
        self.assertTrue(all(case.expected_markers for case in cases))

    def test_dual_arm_executor_preserves_task_success(self):
        cases = load_benchmark_cases(ROOT / "evals/tasks/mvp_tasks.jsonl")
        executor = DualArmExecutor(FixtureAgent(), FixtureCompressor())
        for case in cases:
            for arm in (ExperimentArm.BASELINE, ExperimentArm.COMPRESSED):
                outcome = executor(case, arm)
                self.assertTrue(outcome.event.task_success)
                if outcome.event.fallback_reason:
                    self.assertEqual(outcome.event.validator_result, "fallback")

    def test_subprocess_compressor_runs_a_real_command_adapter(self):
        case = load_benchmark_cases(ROOT / "evals/tasks/mvp_tasks.jsonl")[0]
        compressor = SubprocessCompressor(
            [sys.executable, "-c", "import sys; print(sys.stdin.read().splitlines()[0])"]
        )
        result = compressor.compress(case.original_context, case)
        self.assertIn(case.task_id, result.content)
        self.assertGreater(result.latency_ms, 0)

    def test_openai_compatible_agent_parses_standard_response(self):
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return json.dumps(
                    {
                        "choices": [{"message": {"content": "answer"}}],
                        "usage": {"prompt_tokens": 10, "completion_tokens": 2},
                    }
                ).encode()

        case = load_benchmark_cases(ROOT / "evals/tasks/mvp_tasks.jsonl")[0]
        agent = OpenAICompatibleAgent("http://local.test/v1/chat/completions", "test-model")
        with patch("urllib.request.urlopen", return_value=FakeResponse()):
            result = agent.complete(case.instruction, case.original_context, case)
        self.assertEqual(result.content, "answer")
        self.assertEqual(result.input_tokens, 10)


if __name__ == "__main__":
    unittest.main()
