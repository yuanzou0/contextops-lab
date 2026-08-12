# Phase 3 workload audit

- Suite: `contextops-phase3-matrix-v1`
- Stage: `smoke`
- Model: `gpt-5.6-luna`
- Pricing: `openai-2026-08-12`
- Scenarios: 4
- Paired requests: 8
- Estimated paired input tokens before compression: 102,622
- Estimated input-only upper bound: $0.1026

> This is a preflight estimate, not measured evidence. It excludes output tokens and PariTok compute. Treatment input should be lower when compression is active.

| Scenario | Type | History payload | Turns | Tools | Risk | Input tokens/arm | Baseline input cost |
|---|---|---:|---:|---:|---|---:|---:|
| `read-heavy-8k-1t` | read_heavy | 8,000 | 1 | 24 | medium | 10,839 | $0.0108 |
| `debugging-8k-1t` | debugging | 8,000 | 1 | 36 | medium | 12,313 | $0.0123 |
| `mcp-heavy-8k-1t` | mcp_heavy | 8,000 | 1 | 72 | medium | 16,778 | $0.0168 |
| `edit-critical-8k-1t` | edit_critical | 8,000 | 1 | 28 | high | 11,381 | $0.0114 |

## Interpretation guardrails

- Smoke results validate integration only and cannot authorize rollout.
- Edit-critical scenarios require exact preservation of all critical signals.
- The 8K/32K/128K band is message-history payload; tool schemas are measured overhead.
- Report context cohorts separately; do not hide segment failures in a global mean.
- Promote from smoke to core and extended only after the preceding stage passes.
