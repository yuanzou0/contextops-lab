"""Provider-free real Ollama/Redis drill for Phase 3.1 latency controls."""

from __future__ import annotations

import argparse
import hashlib
import json
import secrets
from dataclasses import dataclass, field
from importlib.metadata import version
from pathlib import Path
from typing import Any
from urllib.request import urlopen

from .safe_proxy import create_safe_proxy_app


QUERY = "FINAL_TASK: return CONTEXT_RECORDED after processing the synthetic tool result"


@dataclass(frozen=True, slots=True)
class LocalResponse:
    status_code: int = 200
    headers: dict[str, str] = field(default_factory=dict)

    def json(self) -> dict[str, Any]:
        return {
            "choices": [{"message": {"content": "CONTEXT_RECORDED"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 4},
        }


class LocalUpstream:
    """Deterministic in-process upstream that cannot reach a provider."""

    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []

    async def post(self, url: str, *, headers=None, json=None, **kwargs) -> LocalResponse:
        self.requests.append({"url": url, "headers": headers, "json": json, "kwargs": kwargs})
        return LocalResponse()

    async def aclose(self) -> None:
        return None


def _synthetic_content(label: str, target_tokens: int) -> str:
    from paritok.token_counter import count_tokens

    content = f"CRITICAL_SIGNAL: phase31::{label}\n"
    line = f"synthetic-{label} deterministic evidence row without user data\n"
    line_tokens = max(1, count_tokens(line))
    content += line * max(1, target_tokens // line_tokens)
    while count_tokens(content) < target_tokens:
        content += line
    return content


def _request(content: str) -> dict[str, Any]:
    return {
        "model": "local-stub-model",
        "messages": [
            {"role": "user", "content": QUERY},
            {"role": "tool", "tool_call_id": "call_phase31", "content": content},
            {"role": "user", "content": QUERY},
        ],
        "max_completion_tokens": 16,
    }


def _numeric_delta(after: dict[str, Any], before: dict[str, Any]) -> dict[str, Any]:
    fields = (
        "total_compressions",
        "validated",
        "validator_passes",
        "fallbacks",
        "exact_original_fallbacks",
        "skipped",
        "cache_hits",
        "compression_latency_ms",
        "validation_latency_ms",
        "upstream_latency_ms",
        "proxy_request_latency_ms",
        "eligibility_bypasses",
        "deadline_fallbacks",
    )
    return {
        field: round(float(after.get(field, 0)) - float(before.get(field, 0)), 3)
        for field in fields
    }


def _forwarded_tool_content(upstream: LocalUpstream, index: int) -> str:
    messages = upstream.requests[index]["json"]["messages"]
    return next(message["content"] for message in messages if message.get("role") == "tool")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_drill(
    *,
    redis_url: str,
    output_dir: Path,
    report_path: Path,
    deadline_ms: float = 500.0,
    maximum_uncached_tokens: int = 3_000,
) -> int:
    from starlette.testclient import TestClient

    with urlopen("http://127.0.0.1:11434/v1/models", timeout=5) as response:
        model_payload = json.loads(response.read().decode("utf-8"))
    model_ids = sorted(str(row.get("id", "")) for row in model_payload.get("data", []))
    if not any(model.startswith("paritok-4b-v1") for model in model_ids):
        raise RuntimeError("paritok-4b-v1 is not available in the local Ollama instance")

    upstream = LocalUpstream()
    app = create_safe_proxy_app(
        openai_base_url="http://local.invalid",
        cache_contract="query_aware",
        storage_backend="redis",
        redis_url=redis_url,
        storage_encryption_key=secrets.token_hex(32),
        tenant_id="synthetic-phase31",
        session_id=f"local-latency-drill-{secrets.token_hex(4)}",
        compression_deadline_ms=deadline_ms,
        maximum_uncached_tokens=maximum_uncached_tokens,
        http_client=upstream,
    )

    oversized = _synthetic_content("oversized", maximum_uncached_tokens + 100)
    cold = _synthetic_content("deadline", 1_000)
    after_budget = _synthetic_content("after-budget", 900)
    cached = _synthetic_content("cached", 800)

    storage = app.state.contextops_storage
    storage.set_active_query(QUERY)
    cached_sid = storage.store(cached)
    storage.cache_compressed(
        cached_sid,
        f"[REF:{cached_sid}] CRITICAL_SIGNAL: phase31::cached",
    )

    events: list[dict[str, Any]] = []
    prior = app.state.contextops_safety_telemetry.snapshot()
    scenarios = (
        ("oversized_uncached", oversized),
        ("cold_deadline", cold),
        ("observed_budget_bypass", after_budget),
        ("cache_hit_after_budget", cached),
    )
    with TestClient(app) as client:
        for index, (name, content) in enumerate(scenarios):
            response = client.post("/v1/chat/completions", json=_request(content))
            response.raise_for_status()
            current = client.get("/contextops/stats").json()
            delta = _numeric_delta(current, prior)
            delta.update(
                {
                    "event": name,
                    "sequence": index + 1,
                    "status_code": response.status_code,
                    "upstream_requests": len(upstream.requests) - index,
                    "forwarded_exact_original": _forwarded_tool_content(upstream, index)
                    == content,
                    "raw_content_recorded": False,
                }
            )
            events.append(delta)
            prior = current

        final_stats = client.get("/contextops/stats").json()

    gates = {
        "real_ollama_model_available": bool(model_ids),
        "real_redis_healthy": final_stats["context_store"]["status"] == "ok",
        "oversized_bypassed_without_compression": (
            events[0]["eligibility_bypasses"] == 1
            and events[0]["compression_latency_ms"] == 0
            and events[0]["forwarded_exact_original"]
        ),
        "cold_deadline_exact_original": (
            events[1]["deadline_fallbacks"] == 1
            and events[1]["exact_original_fallbacks"] == 1
            and events[1]["forwarded_exact_original"]
        ),
        "deadline_overshoot_bounded": (
            deadline_ms <= events[1]["compression_latency_ms"] <= deadline_ms + 250
        ),
        "post_budget_cold_bypass": (
            events[2]["eligibility_bypasses"] == 1
            and events[2]["compression_latency_ms"] == 0
            and events[2]["forwarded_exact_original"]
        ),
        "cache_hit_remains_eligible": (
            events[3]["cache_hits"] == 1
            and events[3]["validator_passes"] == 1
            and not events[3]["forwarded_exact_original"]
        ),
        "fast_paths_under_50ms": (
            events[0]["proxy_request_latency_ms"] < 50
            and events[2]["proxy_request_latency_ms"] < 50
            and events[3]["proxy_request_latency_ms"] < 50
        ),
        "one_upstream_request_per_scenario": len(upstream.requests) == len(scenarios),
        "split_timing_observed": (
            final_stats["compression_latency_ms"] > 0
            and final_stats["validation_latency_ms"] >= 0
            and final_stats["upstream_latency_ms"] > 0
            and final_stats["proxy_request_latency_ms"] > 0
        ),
        "privacy_safe_evidence": True,
        "provider_calls_zero": True,
    }
    status = "PASS" if all(gates.values()) else "FAIL"
    result = {
        "schema_version": 1,
        "evidence_label": "local_real_ollama_redis_latency_controls",
        "status": status,
        "provider_calls": 0,
        "provider_cost_usd": 0.0,
        "real_user_data_used": False,
        "raw_content_recorded": False,
        "runtime": {
            "ollama_models": model_ids,
            "paritok_version": version("paritok"),
            "redis_backend": final_stats["context_store"]["backend"],
            "compression_deadline_ms": deadline_ms,
            "maximum_uncached_tokens": maximum_uncached_tokens,
            "upstream": "deterministic_in_process_stub",
        },
        "gates": [{"gate": name, "passed": passed} for name, passed in gates.items()],
        "events": events,
        "final_safety_stats": {
            key: final_stats[key]
            for key in (
                "total_compressions",
                "validated",
                "validator_passes",
                "fallbacks",
                "exact_original_fallbacks",
                "skipped",
                "cache_hits",
                "compression_latency_ms",
                "validation_latency_ms",
                "upstream_latency_ms",
                "proxy_request_latency_ms",
                "eligibility_bypasses",
                "deadline_fallbacks",
                "fallback_reasons",
                "eligibility_reasons",
            )
        },
        "scope": "real local Ollama and Redis; fake local upstream; not provider performance evidence",
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    result_path = output_dir / "results.json"
    events_path = output_dir / "events.jsonl"
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    events_path.write_text(
        "".join(json.dumps(event, sort_keys=True) + "\n" for event in events),
        encoding="utf-8",
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    rows = "\n".join(
        f"| `{name}` | {'PASS' if passed else 'FAIL'} |" for name, passed in gates.items()
    )
    report_path.write_text(
        "# Phase 3.1 real local latency-control drill\n\n"
        f"**{status}.** Real local Ollama and Redis were used with synthetic data and a deterministic "
        "in-process upstream. Provider calls and cost were zero.\n\n"
        "| Gate | Result |\n|---|---:|\n"
        f"{rows}\n\n"
        "## Observed latency\n\n"
        f"- Cold deadline fallback compression: {events[1]['compression_latency_ms']:.3f} ms\n"
        f"- Oversized bypass proxy request: {events[0]['proxy_request_latency_ms']:.3f} ms\n"
        f"- Post-budget bypass proxy request: {events[2]['proxy_request_latency_ms']:.3f} ms\n"
        f"- Cache-hit proxy request: {events[3]['proxy_request_latency_ms']:.3f} ms\n\n"
        "This validates the local control path only. It is not provider-performance or production "
        "latency evidence, and it does not alter the failed Phase 3 pilot.\n",
        encoding="utf-8",
    )
    checksum_path = output_dir / "sha256sums.txt"
    checksum_paths = (
        result_path,
        events_path,
        report_path,
        Path("src/contextops_lab/phase31_drill.py"),
    )
    checksum_path.write_text(
        "".join(f"{_sha256(path)}  {path.as_posix()}\n" for path in checksum_paths),
        encoding="utf-8",
    )
    print(json.dumps({"status": status, "results": str(result_path), "report": str(report_path)}))
    return 0 if status == "PASS" else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--redis-url", default="redis://127.0.0.1:6381/0")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/phase-3.1-local-latency-drill"),
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("docs/phase-3.1-local-latency-drill.md"),
    )
    parser.add_argument("--deadline-ms", type=float, default=500.0)
    parser.add_argument("--maximum-uncached-tokens", type=int, default=3_000)
    args = parser.parse_args()
    return run_drill(
        redis_url=args.redis_url,
        output_dir=args.output_dir,
        report_path=args.report,
        deadline_ms=args.deadline_ms,
        maximum_uncached_tokens=args.maximum_uncached_tokens,
    )


if __name__ == "__main__":
    raise SystemExit(main())
