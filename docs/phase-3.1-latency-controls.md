# Phase 3.1 provider-free latency controls

## Result

**PASS for the deterministic control contract.** No provider request was made. The implementation
now separates compression, validation, upstream, proxy-request, and derived proxy-overhead timing;
applies an auditable eligibility gate before cold synchronous compression; and converts a backend
deadline into exact-original fallback without retrying or duplicating the upstream request.

This is implementation evidence, not a claim that the local compressor meets the 500 ms rollout
budget. The first admitted cold compression may consume the full configured deadline. After that
budget is observed, later cold work is bypassed for the lifetime of the proxy process. Cache hits
remain eligible, while uncached content above the configured token ceiling is bypassed immediately.

## Gates

| Gate | Observation | Result |
|---|---|---:|
| Split latency attribution | Five privacy-safe timing fields available in schema-v7 events | PASS |
| Oversized uncached bypass | Original returned; compressor not invoked | PASS |
| Observed budget bypass | Subsequent cold work bypassed | PASS |
| Cache-hit preservation | Cached work remains eligible | PASS |
| Deadline fallback | Original forwarded to exactly one fake upstream request | PASS |
| Invalid controls | Non-positive values rejected before startup | PASS |

The complete suite passed 79 tests and 3 subtests. The two warnings are existing Starlette/httpx
test-client deprecations. Ruff, bytecode compilation, standard-library unittest discovery, JSON
validation, privacy scanning, and diff checks are separate final verification steps.

## Operational boundary

Default controls are `--compression-deadline-ms 500` and
`--maximum-uncached-tokens 3000`. The token ceiling matches one PariTok local-model chunk; raising
it means the HTTP deadline applies separately to each chunk. A bypass or deadline fallback protects correctness and latency;
it does not demonstrate compression benefit. Any successor paid pilot still requires a new config,
new evidence paths, provider-free preflight, and explicit request/cost authorization.

## Real local drill

The deterministic contract was subsequently exercised with real local Ollama 0.34.2, PariTok
1.3.11, and Redis 7.4.5. A deterministic in-process upstream ensured provider calls and cost stayed
at zero. All 12 gates passed: cold deadline fallback was observed at 536.182 ms, oversized and
post-budget bypasses completed in 3.574 ms and 2.196 ms, and the cache-hit request completed in
2.679 ms. See `phase-3.1-local-latency-drill.md` and the corresponding JSONL/SHA-256 bundle.
