import importlib.util
import unittest
from unittest.mock import patch

from contextops_lab.cache_safety import build_paritok_storage
from contextops_lab.safe_proxy import SafetyTelemetry, build_validated_pipeline


class IntentSignalModel:
    def __init__(self, *, retain_signal=True):
        self.retain_signal = retain_signal
        self.calls = 0

    def compress(self, content, *, query=None, **kwargs):
        del kwargs
        self.calls += 1
        if not self.retain_signal:
            return "summary without required evidence"
        signal = next(
            line.split("CRITICAL_SIGNAL: ", 1)[1]
            for line in content.splitlines()
            if line.startswith("CRITICAL_SIGNAL: ")
        )
        return f"query={query}\nCRITICAL_SIGNAL: {signal}"


class FakeUpstreamResponse:
    status_code = 200
    headers = {}

    def json(self):
        return {
            "choices": [{"message": {"content": "CONTEXT_RECORDED"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 4},
        }


class CapturingUpstreamClient:
    def __init__(self):
        self.requests = []

    async def post(self, url, *, headers=None, json=None, **kwargs):
        self.requests.append({"url": url, "headers": headers, "json": json, "kwargs": kwargs})
        return FakeUpstreamResponse()

    async def aclose(self):
        return None


@unittest.skipUnless(importlib.util.find_spec("paritok"), "optional live dependency not installed")
class SafeProxyPipelineTests(unittest.TestCase):
    def build_pipeline(self, model):
        from paritok.config import ParitokConfig

        config = ParitokConfig()
        config.compression.min_tokens = 0
        config.compression.max_tokens = 50_000
        config.compression.refusal_threshold = 0.0
        telemetry = SafetyTelemetry(cache_contract="query_aware")
        storage = build_paritok_storage("query_aware")
        pipeline = build_validated_pipeline(config, storage=storage, telemetry=telemetry)
        pipeline._model = model
        return pipeline, telemetry

    def test_query_aware_cache_changes_with_intent_and_reuses_stable_intent(self):
        model = IntentSignalModel()
        pipeline, telemetry = self.build_pipeline(model)
        content = "CRITICAL_SIGNAL: anchor::safe-proxy\n" + "historical evidence\n" * 300
        with patch(
            "paritok.pipelines.compress.count_tokens",
            side_effect=lambda text, *_: max(1, len(text) // 4),
        ):
            first = pipeline.compress(content, query="INTERMEDIATE_TASK")
            final = pipeline.compress(content, query="FINAL_TASK")
            replay = pipeline.compress(content, query="FINAL_TASK")

        self.assertEqual(model.calls, 2)
        self.assertNotEqual(first.compressed, final.compressed)
        self.assertTrue(replay.metadata["cache_hit"])
        self.assertEqual(telemetry.snapshot()["validator_passes"], 3)
        self.assertEqual(telemetry.snapshot()["fallbacks"], 0)

    def test_validator_rejection_forwards_exact_original_and_invalidates_cache(self):
        model = IntentSignalModel(retain_signal=False)
        pipeline, telemetry = self.build_pipeline(model)
        content = "CRITICAL_SIGNAL: anchor::must-survive\n" + "historical evidence\n" * 300
        with patch(
            "paritok.pipelines.compress.count_tokens",
            side_effect=lambda text, *_: max(1, len(text) // 4),
        ):
            result = pipeline.compress(content, query="FINAL_TASK")
            retried = pipeline.compress(content, query="FINAL_TASK")

        self.assertEqual(result.compressed, content)
        self.assertEqual(retried.compressed, content)
        self.assertEqual(model.calls, 2)
        snapshot = telemetry.snapshot()
        self.assertEqual(snapshot["fallbacks"], 2)
        self.assertEqual(snapshot["exact_original_fallbacks"], 2)

    def test_real_http_proxy_forwards_exact_original_after_validator_rejection(self):
        from starlette.testclient import TestClient

        from contextops_lab.safe_proxy import create_safe_proxy_app

        upstream = CapturingUpstreamClient()
        app = create_safe_proxy_app(http_client=upstream, cache_contract="query_aware")
        original = "CRITICAL_SIGNAL: anchor::http-boundary\n" + "historical evidence\n" * 600
        request = {
            "model": "gpt-5.6-luna",
            "messages": [
                {"role": "user", "content": "FINAL_TASK: return the critical signal"},
                {"role": "tool", "tool_call_id": "call_safe", "content": original},
                {"role": "user", "content": "FINAL_TASK: return the critical signal"},
            ],
            "max_completion_tokens": 32,
        }
        with (
            patch(
                "paritok.strategies.local_model.LocalModelStrategy.compress",
                return_value="summary missing evidence",
            ),
            patch(
                "paritok.pipelines.compress.count_tokens",
                side_effect=lambda text, *_: max(1, len(text) // 4),
            ),
            TestClient(app) as client,
        ):
            response = client.post("/v1/chat/completions", json=request)
            safety = client.get("/contextops/stats").json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(upstream.requests), 1)
        forwarded_tool = next(
            message
            for message in upstream.requests[0]["json"]["messages"]
            if message.get("role") == "tool"
        )
        self.assertEqual(forwarded_tool["content"], original)
        self.assertEqual(safety["fallbacks"], 1)
        self.assertEqual(safety["exact_original_fallbacks"], 1)


if __name__ == "__main__":
    unittest.main()
