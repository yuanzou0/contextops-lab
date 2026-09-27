# Phase 3.1 real local latency-control drill

**PASS.** Real local Ollama and Redis were used with synthetic data and a deterministic in-process upstream. Provider calls and cost were zero.

| Gate | Result |
|---|---:|
| `real_ollama_model_available` | PASS |
| `real_redis_healthy` | PASS |
| `oversized_bypassed_without_compression` | PASS |
| `cold_deadline_exact_original` | PASS |
| `deadline_overshoot_bounded` | PASS |
| `post_budget_cold_bypass` | PASS |
| `cache_hit_remains_eligible` | PASS |
| `fast_paths_under_50ms` | PASS |
| `one_upstream_request_per_scenario` | PASS |
| `split_timing_observed` | PASS |
| `privacy_safe_evidence` | PASS |
| `provider_calls_zero` | PASS |

## Observed latency

- Cold deadline fallback compression: 536.182 ms
- Oversized bypass proxy request: 3.574 ms
- Post-budget bypass proxy request: 2.196 ms
- Cache-hit proxy request: 2.679 ms

This validates the local control path only. It is not provider-performance or production latency evidence, and it does not alter the failed Phase 3 pilot.
