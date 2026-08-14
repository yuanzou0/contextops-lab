# Provider-free transformed-context regression protocol

## Status

Prespecified before the local PariTok 4B results were inspected. Configuration:
`configs/provider-free-regression-v1.json`.

## Question

When task intent changes during a five-turn session, does query-aware cache isolation prevent stale
transformed-context reuse, preserve task-critical signals, and trigger exact-original fallback when
raw compression omits a required signal?

## Design

- Four Wave A workloads: read-heavy, debugging, MCP-heavy, and edit-critical.
- Fixed context/session band: 32K / five turns.
- Three signal-bearing tool segments per workload.
- Intermediate query followed by a distinct terminal signal-recall query.
- Same terminal query replayed once to test safe within-intent reuse.
- No upstream agent provider, API key, or provider request.
- Raw original and transformed content are not written to artifacts; only hashes and metrics remain.

The deterministic stage compares content-only, disabled, and query-aware cache conditions with a
fixed intent-sensitive compressor. The local-model stage evaluates only the query-aware recovery
condition with the installed PariTok 4B model. This bounds local compute while retaining all four
workloads and all twelve task-critical signals.

## Primary outcomes and fixed gates

1. Query-aware cross-query cache hits: exactly zero.
2. Query-aware same-query replay hit rate: 100%.
3. Guarded required-signal recall after validation/fallback: 100%.
4. Raw required-signal recall for a recovery pilot: 100%.
5. Provider requests and provider cost: zero.

Content-only cache is a negative control: cross-query hits and raw-signal loss are expected. It can
still pass guarded safety only if every invalid transformation falls back to exact original content.

## Stop and interpretation rules

- Stop on any local compression-backend error.
- Do not revise signal definitions or thresholds after seeing results.
- Provider-free success cannot make Wave B eligible by itself.
- Guarded safety and raw compression quality are separate claims.
- Latency eligibility remains a separate blocker even if signal gates pass.
- The local-model stage measures transformed-context behavior, not end-task semantic equivalence.
